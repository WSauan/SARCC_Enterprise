<#
.SYNOPSIS
    Telemetria Ultra-Rápida para o Dashboard com Inventário Físico, S.M.A.R.T., Slots de RAM e Perfis TEMP*.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

# 1. Armazenamento e Saúde S.M.A.R.T.
$drive = Get-PSDrive C -ErrorAction SilentlyContinue
$free = if ($drive) { [math]::Round($drive.Free / 1GB, 2) } else { 0 }
$used = if ($drive) { [math]::Round($drive.Used / 1GB, 2) } else { 0 }
$total = [math]::Round($free + $used, 2)
$pct = if ($total -gt 0) { [math]::Round(($used / $total) * 100, 1) } else { 0 }

$diskTypeStr = "Desconhecido"
$diskSmartStr = "N/A"
try {
    $physDisk = Get-PhysicalDisk -ErrorAction SilentlyContinue | Where-Object { $_.DeviceId -eq '0' -or $_.MediaType -ne 'Unspecified' } | Select-Object -First 1
    if (-not $physDisk) {
        $physDisk = Get-PhysicalDisk -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($physDisk) {
        $media = [string]$physDisk.MediaType
        $bus   = [string]$physDisk.BusType
        if ($bus -match 'NVMe') { $diskTypeStr = "NVMe SSD" }
        elseif ($media -match 'SSD') { $diskTypeStr = "SSD" }
        elseif ($media -match 'HDD') { $diskTypeStr = "HDD" }
        else { $diskTypeStr = if ($bus) { $bus } else { "Disco Local" } }

        $health = [string]$physDisk.HealthStatus
        $opStatus = [string]$physDisk.OperationalStatus
        if ($health -eq 'Healthy' -and ($opStatus -match 'OK')) {
            $diskSmartStr = "Saudável (OK)"
        } elseif ($health -eq 'Warning' -or $opStatus -match 'Predictive|Degraded') {
            $diskSmartStr = "Alerta ($health)"
        } else {
            $diskSmartStr = "Crítico ($health)"
        }
    }
} catch { }

if ($diskSmartStr -eq "N/A") {
    $wmiDisk = Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wmiDisk) {
        if ($wmiDisk.Model -match 'NVMe') { $diskTypeStr = "NVMe SSD" }
        elseif ($wmiDisk.Model -match 'SSD') { $diskTypeStr = "SSD" }
        $diskSmartStr = if ($wmiDisk.Status -eq 'OK') { "Saudável (OK)" } else { "Alerta ($($wmiDisk.Status))" }
    }
}

# 2. Perfis e Sessões (Híbrido: Win32_UserProfile + Pastas Físicas em C:\Users)
$profilesList = @()
$loggedNames = @()
$seenNames = @{}
$ignoredFolders = @(
    'public', 'público', 'publico',
    'default', 'default user', 'defaultuser0', 'usuário padrão', 'usuario padrao',
    'all users', 'todos os usuários', 'todos os usuarios',
    'defaultapppool', 'MSSQL$SQLEXPRESS'
)

$profilesRaw = @(Get-CimInstance Win32_UserProfile -Filter "Special = False" -ErrorAction SilentlyContinue | Where-Object {
    (-not [string]::IsNullOrWhiteSpace($_.LocalPath)) -and
    ($_.LocalPath -match '^[A-Za-z]:\\Users\\')
})

foreach ($p in $profilesRaw) {
    $name = Split-Path -Path $p.LocalPath -Leaf -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    $nameLower = $name.ToLower()
    if ($ignoredFolders -contains $nameLower) { continue }

    $lastUseDate = $null
    $lastUseStr = "N/A"

    if ($p.LastUseTime) {
        try {
            $lastUseDate = [datetime]$p.LastUseTime
            $lastUseStr = $lastUseDate.ToString('yyyy-MM-dd HH:mm')
        } catch { }
    }

    if (-not $lastUseDate -and (Test-Path -LiteralPath $p.LocalPath)) {
        try {
            $itemFolder = Get-Item -LiteralPath $p.LocalPath -Force -ErrorAction SilentlyContinue
            if ($itemFolder -and $itemFolder.LastWriteTime) {
                $lastUseDate = [datetime]$itemFolder.LastWriteTime
                $lastUseStr = $lastUseDate.ToString('yyyy-MM-dd HH:mm')
            }
        } catch { }
    }

    $isLoaded = [bool]$p.Loaded
    $isTemp = [bool]($name -match '^(?i)TEMP(\.|$)')

    $seenNames[$nameLower] = $true
    $profilesList += [PSCustomObject]@{
        Name    = $name
        LastUse = $lastUseStr
        Loaded  = $isLoaded
        IsTemp  = $isTemp
    }

    if ($isLoaded) {
        $loggedNames += $name
    }
}

$usersRoot = "$env:SystemDrive\Users"
if (Test-Path -LiteralPath $usersRoot) {
    $diskFolders = @(Get-ChildItem -LiteralPath $usersRoot -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
        (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) -and
        (($_.Attributes -band [System.IO.FileAttributes]::System) -eq 0)
    })
    foreach ($folder in $diskFolders) {
        $fName = $folder.Name
        if ([string]::IsNullOrWhiteSpace($fName)) { continue }
        $fLower = $fName.ToLower()

        if ($ignoredFolders -contains $fLower) { continue }
        if ($seenNames.ContainsKey($fLower)) { continue }

        $seenNames[$fLower] = $true
        $isTempFolder = [bool]($fName -match '^(?i)TEMP(\.|$)')
        $fLastUse = if ($folder.LastWriteTime) { $folder.LastWriteTime.ToString('yyyy-MM-dd HH:mm') } else { "N/A" }

        $profilesList += [PSCustomObject]@{
            Name    = $fName
            LastUse = $fLastUse
            Loaded  = $false
            IsTemp  = $isTempFolder
        }
    }
}

$tempProfilesCount = @($profilesList | Where-Object { $_.IsTemp -eq $true }).Count
$normalProfilesCount = @($profilesList | Where-Object { $_.IsTemp -eq $false }).Count
$profiles = $profilesList.Count
$loggedUsers = $loggedNames.Count

# 3. OS, Descrição (Local/Setor) e Rede
$os = Get-CimInstance Win32_OperatingSystem -Property Caption, Description, LastBootUpTime, TotalVisibleMemorySize, FreePhysicalMemory -ErrorAction SilentlyContinue
$uptimeStr = "N/A"
if ($os -and $os.LastBootUpTime) {
    $up = (Get-Date) - $os.LastBootUpTime
    $uptimeStr = "$($up.Days)d $($up.Hours)h $($up.Minutes)m"
}
$compDesc = if ($os -and -not [string]::IsNullOrWhiteSpace($os.Description)) { $os.Description.Trim() } else { "Sem descrição" }

$net = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = 'True'" -Property IPAddress, MACAddress -ErrorAction SilentlyContinue | Select-Object -First 1
$ip = if ($net -and $net.IPAddress) { $net.IPAddress[0] } else { "N/A" }
$mac = if ($net -and $net.MACAddress) { $net.MACAddress } else { "N/A" }

# 4. Hardware Físico (Modelo, BIOS Serial, CPU e Topologia RAM)
$cs = Get-CimInstance Win32_ComputerSystem -Property Manufacturer, Model -ErrorAction SilentlyContinue
$bios = Get-CimInstance Win32_BIOS -Property SerialNumber -ErrorAction SilentlyContinue
$hwModel = "N/A"
if ($cs) {
    $manuf = ($cs.Manufacturer -replace 'Inc\.|Corporation|Ltd\.|Co\.', '').Trim()
    $mod = ($cs.Model).Trim()
    $hwModel = "$manuf $mod".Trim()
}
$serialNum = if ($bios -and -not [string]::IsNullOrWhiteSpace($bios.SerialNumber)) { $bios.SerialNumber.Trim() } else { "N/A" }

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

$ramSlotsStr = "N/A"
try {
    $memModules = @(Get-CimInstance Win32_PhysicalMemory -Property Speed, ConfiguredClockSpeed -ErrorAction SilentlyContinue)
    $memArray = Get-CimInstance Win32_PhysicalMemoryArray -Property MemoryDevices -ErrorAction SilentlyContinue | Select-Object -First 1
    $usedSlots = $memModules.Count
    $totalSlots = if ($memArray -and $memArray.MemoryDevices) { $memArray.MemoryDevices } else { $usedSlots }
    $speed = if ($memModules.Count -gt 0) {
        if ($memModules[0].ConfiguredClockSpeed) { $memModules[0].ConfiguredClockSpeed } else { $memModules[0].Speed }
    } else { $null }

    if ($usedSlots -gt 0) {
        $ramSlotsStr = if ($speed) { "$usedSlots/$totalSlots slots ($speed MHz)" } else { "$usedSlots/$totalSlots slots" }
    }
} catch { }

# 5. Segurança
$av = "Windows Defender (Nativo)"
$avInfo = Get-CimInstance -Namespace "root\SecurityCenter2" -ClassName "AntivirusProduct" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($avInfo -and $avInfo.displayName) { $av = $avInfo.displayName }

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
        if ($rawId.Length -ge 9) {
            $anydeskId = '{0} {1} {2}' -f $rawId.Substring(0,3), $rawId.Substring(3,3), $rawId.Substring(6)
        } else {
            $anydeskId = $rawId
        }
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
    HostName            = $env:COMPUTERNAME
    ComputerDesc        = $compDesc
    HardwareModel       = $hwModel
    SerialNumber        = $serialNum
    OSVersion           = if ($os) { $os.Caption } else { "N/A" }
    Activation          = $actStatus
    CPUModel            = $cpuModel
    CPUUsage            = if ($cpu) { $cpu.LoadPercentage } else { 0 }
    CPUTemp             = $cpuTempStr
    TotalRAM            = $totalRamGB
    UsedRAM             = $usedRamGB
    RAMPct              = $ramPct
    RAMSlots            = $ramSlotsStr
    AVProduct           = $av
    DiskTotal           = $total
    DiskFree            = $free
    DiskUsed            = $used
    DiskPct             = $pct
    DiskType            = $diskTypeStr
    DiskSmart           = $diskSmartStr
    ProfilesCount       = $profiles
    NormalProfilesCount = $normalProfilesCount
    TempProfilesCount   = $tempProfilesCount
    LoggedUsers         = $loggedUsers
    ProfilesList        = @($profilesList)
    LoggedNames         = @($loggedNames)
    IP                  = $ip
    MAC                 = $mac
    Uptime              = $uptimeStr
    RDP                 = $rdpStatus
    VNC                 = $vncStatus
    WOL                 = $wolStatus
    AnyDesk             = $anydeskId
    Zabbix              = $zabbixStatus
    GLPI                = $glpiStatus
    DesktopInfo         = $dinfoStatus
    Winget              = $wingetStatus
    RebootPending       = $rebootStatus
} | ConvertTo-Json -Depth 4 -Compress