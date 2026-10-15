# Telemetria completa do endpoint: OS, hardware, disco, sessões, agentes.
# Sem variáveis — receita fixa que devolve um JSON grande.
# O Python faz .get() em cada campo com valor default, então é seguro
# omitir qualquer chave quando o sensor não suportar.

$ErrorActionPreference = 'SilentlyContinue'

# 1. Armazenamento
$drive = Get-PSDrive C -ErrorAction SilentlyContinue
$free = if ($drive) { [math]::Round($drive.Free / 1GB, 2) } else { 0 }
$used = if ($drive) { [math]::Round($drive.Used / 1GB, 2) } else { 0 }
$total = [math]::Round($free + $used, 2)
$pct = if ($total -gt 0) { [math]::Round(($used / $total) * 100, 1) } else { 0 }

# 2. Sessões
$profiles = (Get-ChildItem -Path 'C:\Users' -Directory -Force -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -notmatch '^(Public|Público|Default|All Users|Default User|Usuário Padrão)$' }).Count
$loggedUsers = 0
try {
    $q = quser 2>&1
    $lines = $q -split '\r?\n' | Where-Object { $_.Trim() -ne '' }
    if ($lines.Count -gt 1 -and $lines[0] -match 'USERNAME|USUÁRIO|NOME|ID') {
        $loggedUsers = $lines.Count - 1
    }
} catch { }

# 3. OS e Rede
$os = Get-CimInstance Win32_OperatingSystem -Property Caption, LastBootUpTime, TotalVisibleMemorySize, FreePhysicalMemory -ErrorAction SilentlyContinue
$hostname = $env:COMPUTERNAME
$uptimeStr = "N/A"
$osCaption = if ($os) { $os.Caption } else { "N/A" }
if ($os) {
    $uptime = (Get-Date) - $os.LastBootUpTime
    $uptimeStr = "$($uptime.Days)d $($uptime.Hours)h $($uptime.Minutes)m"
}

$net = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = 'True'" -Property IPAddress, MACAddress -ErrorAction SilentlyContinue | Select-Object -First 1
$ip = if ($net) { $net.IPAddress[0] } else { "N/A" }
$mac = if ($net) { $net.MACAddress } else { "N/A" }

# 4. Hardware e Desempenho (CPU/RAM/Temp)
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cpuModel = if ($cpu) { $cpu.Name -replace "\s*\(R\)|\s*\(TM\)|CPU\s+|@\s*\d+\.\d+GHz", "" } else { "Desconhecido" }
$cpuUsage = if ($cpu) { $cpu.LoadPercentage } else { 0 }

$cpuTempStr = "N/A"
try {
    $thermal = Get-CimInstance -Namespace "root\wmi" -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $thermal -and $thermal.CurrentTemperature) {
        $tempC = [math]::Round(($thermal.CurrentTemperature / 10) - 273.15, 1)
        if ($tempC -gt 0 -and $tempC -lt 150) { $cpuTempStr = $tempC.ToString() }
    }
} catch { }

$totalRamGB = if ($os) { [math]::Round($os.TotalVisibleMemorySize / 1MB, 1) } else { 0 }
$freeRamGB = if ($os) { [math]::Round($os.FreePhysicalMemory / 1MB, 1) } else { 0 }
$usedRamGB = [math]::Round($totalRamGB - $freeRamGB, 1)
$ramPct = if ($totalRamGB -gt 0) { [math]::Round(($usedRamGB / $totalRamGB) * 100, 1) } else { 0 }

# 5. Segurança
$av = "Windows Defender (Nativo)"
try {
    $avInfo = Get-CimInstance -Namespace "root\SecurityCenter2" -ClassName "AntivirusProduct" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($avInfo) { $av = $avInfo.displayName }
} catch { }

$actStatus = "Desconhecido"
try {
    $slmgr = cscript.exe //nologo C:\Windows\System32\slmgr.vbs /dli 2>&1
    $slmgrText = $slmgr -join " "
    if ($slmgrText -match "Licenciado|Licensed") { $actStatus = "Ativado (Licenciado)" }
    elseif ($slmgrText -match "Notificação|Notification|grace|Inicial") { $actStatus = "Não Ativado" }
} catch { }

# 6. Agentes e Softwares Adicionais
$rdpReg = Get-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name 'fDenyTSConnections' -ErrorAction SilentlyContinue
$rdpStatus = if ($null -ne $rdpReg -and $rdpReg.fDenyTSConnections -eq 0) { "Ativado" } else { "Desativado" }

$vncStatus = "Não Instalado"
$uvnc = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
$tvnc = Get-Service -Name "tvnserver" -ErrorAction SilentlyContinue
if ($uvnc) { $vncStatus = if ($uvnc.Status.ToString() -eq 'Running') { "Ativo (Rodando)" } else { "Parado" } }
elseif ($tvnc) { $vncStatus = if ($tvnc.Status.ToString() -eq 'Running') { "Ativo (Rodando)" } else { "Parado" } }

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

$dinfoProc = Get-Process -Name "DesktopInfo*" -ErrorAction SilentlyContinue | Select-Object -First 1
$dinfoStatus = if ($dinfoProc) { "Ativo (Rodando)" } else { "Parado / Não Instalado" }

# 7. Winget (App Installer)
# Estratégia: procura em 4 locais (incluindo -AllUsers), versão em 3 fallbacks
$wingetStatus = "Não Instalado"
$wingetExe = $null
$wingetAppxVer = ""

$cmd = Get-Command winget -ErrorAction SilentlyContinue
if ($cmd) { $wingetExe = $cmd.Source }

if (-not $wingetExe) {
    $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
    if (Test-Path $candidate) { $wingetExe = $candidate }
}

if (-not $wingetExe) {
    $appx = Get-AppxPackage -AllUsers -Name "Microsoft.DesktopAppInstaller" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($appx) {
        $wingetAppxVer = "$($appx.Version)"
        if ($appx.InstallLocation) {
            $candidate = Join-Path $appx.InstallLocation "winget.exe"
            if (Test-Path $candidate) { $wingetExe = $candidate }
        }
    }
}

if (-not $wingetExe) {
    $appInst = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($appInst) { $wingetExe = $appInst.FullName }
}

if ($wingetExe -or $wingetAppxVer) {
    $wgVer = ""

    if ($wingetExe) {
        try {
            $wgVer = (& $wingetExe --version 2>$null | Select-Object -First 1) -join ""
            $wgVer = $wgVer.Trim()
        } catch { }
    }

    if (-not $wgVer -and $wingetExe) {
        try {
            $fv = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($wingetExe)
            if ($fv.FileVersion) { $wgVer = $fv.FileVersion }
            elseif ($fv.ProductVersion) { $wgVer = $fv.ProductVersion }
        } catch { }
    }

    if (-not $wgVer -and $wingetAppxVer) { $wgVer = $wingetAppxVer }

    if ($wgVer) {
        $wgVer = $wgVer.TrimStart('v').Trim()
        $wgVer = $wgVer -replace '\.0+$', ''
        $wgVer = $wgVer -replace '\.0+$', ''
        if ($wgVer -notmatch '^v') { $wgVer = "v$wgVer" }
        $wingetStatus = "Instalado ($wgVer)"
    } else {
        $wingetStatus = "Instalado"
    }
}

# 8. Reboot Pendente (Windows Update / CBS / PendingFileRenameOperations)
$rebootPending = $false
$rebootReasons = @()

if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') {
    $rebootPending = $true
    $rebootReasons += "WU"
}

if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') {
    $rebootPending = $true
    $rebootReasons += "CBS"
}

$pfro = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name 'PendingFileRenameOperations' -ErrorAction SilentlyContinue).PendingFileRenameOperations
if ($pfro -and $pfro.Count -gt 0) {
    $rebootPending = $true
    $rebootReasons += "PFR"
}

$rebootStatus = if ($rebootPending) { "Pendente (" + ($rebootReasons -join ", ") + ")" } else { "OK" }

# Resultado
[PSCustomObject]@{
    HostName = $hostname
    OSVersion = $osCaption
    Activation = $actStatus
    CPUModel = $cpuModel
    CPUUsage = $cpuUsage
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