<#
.SYNOPSIS
    Telemetria Ultra-Rápida para o Dashboard.
    (Removido 'quser' para evitar lentidão e timeout na Sessão 0)
#>
$ErrorActionPreference = 'SilentlyContinue'

# 1. Armazenamento
$drive = Get-PSDrive C -ErrorAction SilentlyContinue
$free = if ($drive) { [math]::Round($drive.Free / 1GB, 2) } else { 0 }
$used = if ($drive) { [math]::Round($drive.Used / 1GB, 2) } else { 0 }
$total = [math]::Round($free + $used, 2)
$pct = if ($total -gt 0) { [math]::Round(($used / $total) * 100, 1) } else { 0 }

# 2. Perfis e Sessões (Reescrito para precisão e velocidade extrema)
$profilesList = @()
$loggedNames = @()

$profilesRaw = Get-CimInstance Win32_UserProfile -Filter "Special = False" -ErrorAction SilentlyContinue | Where-Object { $_.LocalPath -match '^C:\\Users\\' -and $_.LocalPath -notmatch 'Public|Público|Default' }
foreach ($p in $profilesRaw) {
    $name = (Split-Path $p.LocalPath -Leaf)
    $lastUseStr = "N/A"
    
    if ($p.LastUseTime) {
        $lastUseDate = [datetime]$p.LastUseTime
        $lastUseStr = $lastUseDate.ToString('yyyy-MM-dd HH:mm')
    }

    # Só adiciona utilizadores que usaram a máquina no último ano
    if ($lastUseDate -and ($lastUseDate -gt (Get-Date).AddYears(-1))) {
        $profilesList += [PSCustomObject]@{ Name = $name; LastUse = $lastUseStr; Loaded = [bool]$p.Loaded }
        # Se Loaded = True, o utilizador está com sessão aberta agora.
        if ([bool]$p.Loaded) {
            $loggedNames += $name
        }
    }
}
$profiles = $profilesList.Count
$loggedUsers = $loggedNames.Count

# 3. OS e Rede
$os = Get-CimInstance Win32_OperatingSystem -Property Caption, LastBootUpTime, TotalVisibleMemorySize, FreePhysicalMemory -ErrorAction SilentlyContinue
$uptimeStr = "N/A"
if ($os) {
    $up = (Get-Date) - $os.LastBootUpTime
    $uptimeStr = "$($up.Days)d $($up.Hours)h $($up.Minutes)m"
}

$net = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = 'True'" -Property IPAddress, MACAddress -ErrorAction SilentlyContinue | Select-Object -First 1
$ip = if ($net) { $net.IPAddress[0] } else { "N/A" }
$mac = if ($net) { $net.MACAddress } else { "N/A" }

# 4. Hardware
$cpu = Get-CimInstance Win32_Processor -Property Name, LoadPercentage -ErrorAction SilentlyContinue | Select-Object -First 1
$cpuModel = if ($cpu) { $cpu.Name -replace "\s*\(R\)|\s*\(TM\)|CPU\s+|@\s*\d+\.\d+GHz", "" } else { "Desconhecido" }

$cpuTempStr = "N/A"
$thermal = Get-CimInstance -Namespace "root\wmi" -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1
if ($thermal -and $thermal.CurrentTemperature) {
    $tempC = [math]::Round(($thermal.CurrentTemperature / 10) - 273.15, 1)
    if ($tempC -gt 0 -and $tempC -lt 150) { $cpuTempStr = $tempC.ToString() }
}

$totalRamGB = if ($os) { [math]::Round($os.TotalVisibleMemorySize / 1MB, 1) } else { 0 }
$freeRamGB = if ($os) { [math]::Round($os.FreePhysicalMemory / 1MB, 1) } else { 0 }
$usedRamGB = [math]::Round($totalRamGB - $freeRamGB, 1)
$ramPct = if ($totalRamGB -gt 0) { [math]::Round(($usedRamGB / $totalRamGB) * 100, 1) } else { 0 }

# 5. Segurança
$av = "Windows Defender (Nativo)"
$avInfo = Get-CimInstance -Namespace "root\SecurityCenter2" -ClassName "AntivirusProduct" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($avInfo) { $av = $avInfo.displayName }

$actStatus = "Não Ativado"
$sl = Get-CimInstance SoftwareLicensingProduct -Filter "PartialProductKey IS NOT NULL" -ErrorAction SilentlyContinue | Where-Object { $_.ApplicationId -eq '55c92734-d682-4d71-983e-d6ec3f16059f' } | Select-Object -First 1
if ($sl -and $sl.LicenseStatus -eq 1) { $actStatus = "Ativado (Licenciado)" }

# 6. Agentes
$rdpReg = Get-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name 'fDenyTSConnections' -ErrorAction SilentlyContinue
$rdpStatus = if ($null -ne $rdpReg -and $rdpReg.fDenyTSConnections -eq 0) { "Ativado" } else { "Desativado" }

$vncStatus = "Não Instalado"
$vncSvc = Get-Service -Name "uvnc_service", "tvnserver" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vncSvc) { $vncStatus = if ($vncSvc.Status.ToString() -eq 'Running') { "Ativo (Rodando)" } else { "Parado" } }

$anydeskId = "Não Instalado"
$sysConf = "C:\ProgramData\AnyDesk\system.conf"
if (Test-Path $sysConf) {
    $anydeskId = "Instalado (ID Oculto)"
    $match = Select-String -Path $sysConf -Pattern "^ad\.anynet\.id=(\d+)" -ErrorAction SilentlyContinue
    if ($match) {
        $rawId = $match.Matches.Groups[1].Value
        $anydeskId = '{0} {1} {2}' -f $rawId.Substring(0,3), $rawId.Substring(3,3), $rawId.Substring(6)
    }
} elseif (Test-Path "C:\Program Files (x86)\AnyDesk\AnyDesk.exe") { $anydeskId = "Instalado" }

$wol = Get-NetAdapterPowerManagement -ErrorAction SilentlyContinue | Where-Object { $_.WakeOnMagicPacket -eq 'Enabled' }
$wolStatus = if ($wol) { "Ativado (OS)" } else { "Desativado" }

$zabbixSvc = Get-Service -Name "Zabbix Agent 2", "Zabbix Agent" -ErrorAction SilentlyContinue | Select-Object -First 1
$zabbixStatus = if ($zabbixSvc) { if ($zabbixSvc.Status.ToString() -eq 'Running') { "Ativo (Rodando)" } else { "Parado" } } else { "Não Instalado" }

$glpiSvc = Get-Service -Name "glpi-agent", "FusionInventory-Agent" -ErrorAction SilentlyContinue | Select-Object -First 1
$glpiStatus = if ($glpiSvc) { if ($glpiSvc.Status.ToString() -eq 'Running') { "Ativo (Rodando)" } else { "Parado" } } else { "Não Instalado" }

$dinfoStatus = if (Get-Process -Name "DesktopInfo*" -ErrorAction SilentlyContinue | Select-Object -First 1) { "Ativo (Rodando)" } else { "Parado / Não Instalado" }

# 7. Winget
$wingetStatus = "Não Instalado"
$wingetExe = $null
$realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($realApp) { $wingetExe = $realApp.FullName }
if (-not $wingetExe) { $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"; if (Test-Path $candidate) { $wingetExe = $candidate } }

if ($wingetExe) {
    $wgVer = ""
    try {
        $fv = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($wingetExe)
        if ($fv.FileVersion) { $wgVer = $fv.FileVersion } elseif ($fv.ProductVersion) { $wgVer = $fv.ProductVersion }
    } catch { }
    
    if ($wgVer) {
        $wgVer = $wgVer -replace '\.0+$', ''
        if ($wgVer -notmatch '^v') { $wgVer = "v$wgVer" }
        $wingetStatus = "Instalado ($wgVer)"
    } else {
        $wingetStatus = "Instalado"
    }
}

# 8. Reboot Pendente
$rebootPending = $false
$rebootReasons = @()

if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') { $rebootPending = $true; $rebootReasons += "WU" }
if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') { $rebootPending = $true; $rebootReasons += "CBS" }

$pfro = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name 'PendingFileRenameOperations' -ErrorAction SilentlyContinue).PendingFileRenameOperations
if ($pfro -and $pfro.Count -gt 0) { $rebootPending = $true; $rebootReasons += "PFR" }

$rebootStatus = if ($rebootPending) { "Pendente (" + ($rebootReasons -join ", ") + ")" } else { "OK" }

# Resultado
[PSCustomObject]@{
    HostName = $env:COMPUTERNAME
    OSVersion = if ($os) { $os.Caption } else { "N/A" }
    Activation = $actStatus
    CPUModel = $cpuModel
    CPUUsage = if ($cpu) { $cpu.LoadPercentage } else { 0 }
    CPUTemp = $cpuTempStr
    TotalRAM = $totalRamGB
    UsedRAM = $usedRamGB
    RAMPct = $ramPct
    AVProduct = $av
    DiskTotal = $total
    DiskFree = $free
    DiskUsed = $used
    DiskPct = $pct
    ProfilesCount = $profiles
    LoggedUsers = $loggedUsers
    ProfilesList = @($profilesList)
    LoggedNames = @($loggedNames)
    IP = $ip
    MAC = $mac
    Uptime = $uptimeStr
    RDP = $rdpStatus
    VNC = $vncStatus
    WOL = $wolStatus
    AnyDesk = $anydeskId
    Zabbix = $zabbixStatus
    GLPI = $glpiStatus
    DesktopInfo = $dinfoStatus
    Winget = $wingetStatus
    RebootPending = $rebootStatus
} | ConvertTo-Json -Compress