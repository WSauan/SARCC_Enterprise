<#
.SYNOPSIS
    Instalação Multi-Engine (Winget, Chocolatey e Offline via SMB) com Fallback de Manifesto Oficial e Timeout.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

function Repair-Mojibake ([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    if ($Text -match 'Ã') {
        try {
            $bytes = [System.Text.Encoding]::GetEncoding(1252).GetBytes($Text)
            return [System.Text.Encoding]::UTF8.GetString($bytes)
        } catch { return $Text }
    }
    return $Text
}

function Invoke-ProcessWithTimeout {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds = 240
    )
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $FilePath
    $escapedArgs = foreach ($arg in $ArgumentList) {
        if ($arg -match '\s') { "`"$arg`"" } else { $arg }
    }
    $pinfo.Arguments = ($escapedArgs -join ' ')
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    $pinfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $pinfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $pinfo
    $null = $proc.Start()

    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()

    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        try { $proc.Kill() } catch { }
        return [PSCustomObject]@{
            ExitCode = -999
            Output   = "TIMEOUT: O processo excedeu $TimeoutSeconds segundos e foi finalizado."
            TimedOut = $true
        }
    }

    $proc.WaitForExit()
    $combined = ($outTask.Result + "`n" + $errTask.Result).Trim()
    return [PSCustomObject]@{
        ExitCode = $proc.ExitCode
        Output   = (Repair-Mojibake $combined)
        TimedOut = $false
    }
}

function Install-FromWingetManifestFallback {
    param(
        [string]$PackageId,
        [string]$WingetCmd
    )
    $logs = @()
    $ts = (Get-Date).ToString('HH:mm:ss')
    $logs += "[$ts] [Fallback Manifesto] Consultando catálogo oficial microsoft/winget-pkgs para '$PackageId'..."

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $headers = @{ "User-Agent" = "SARCC-Enterprise/2.0" }

        $parts = $PackageId.Split('.')
        if ($parts.Count -lt 2) {
            return [PSCustomObject]@{ Success = $false; ExitCode = -1; Logs = ($logs + "ID de pacote inválido para manifesto: $PackageId") }
        }
        $firstLetter = $PackageId.Substring(0, 1).ToLower()
        $relPath = ($parts -join '/')
        $apiUrl = "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/$firstLetter/$relPath"

        $items = Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 20 -ErrorAction Stop
        $dirs = @($items | Where-Object { $_.type -eq 'dir' })
        if ($dirs.Count -eq 0) {
            throw "Nenhuma pasta de versão encontrada no repositório oficial."
        }

        # Ordenação numérica de versão para selecionar sempre a release mais recente
        $latestDir = $dirs | Sort-Object {
            $vStr = ($_.name -replace '[^0-9\.]', '').Trim('.')
            $vParts = $vStr -split '\.' | Where-Object { $_ -ne '' }
            $nums = foreach ($vp in ($vParts | Select-Object -First 4)) {
                if ($vp.Length -gt 8) { $vp = $vp.Substring(0, 8) }
                [long]$vp
            }
            while ($nums.Count -lt 4) { $nums += 0L }
            "{0:D10}.{1:D10}.{2:D10}.{3:D10}" -f $nums[0], $nums[1], $nums[2], $nums[3]
        } | Select-Object -Last 1

        $verName = $latestDir.name
        $logs += "[$ts] [Fallback Manifesto] Versão mais recente localizada: $verName"

        $verFiles = Invoke-RestMethod -Uri $latestDir.url -Headers $headers -TimeoutSec 20 -ErrorAction Stop
        $yamlFiles = @($verFiles | Where-Object { $_.name -match '\.ya?ml$' })

        $manifestDir = Join-Path "C:\Windows\Temp" "SARCC_Manifest_$($PackageId -replace '[^a-zA-Z0-9]', '_')"
        if (Test-Path $manifestDir) { Remove-Item $manifestDir -Recurse -Force -ErrorAction SilentlyContinue }
        New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null

        $installerYamlContent = ""
        foreach ($yf in $yamlFiles) {
            $destYaml = Join-Path $manifestDir $yf.name
            Invoke-WebRequest -Uri $yf.download_url -OutFile $destYaml -UseBasicParsing -TimeoutSec 20 -ErrorAction Stop
            if ($yf.name -match '\.installer\.ya?ml$' -or $yamlFiles.Count -eq 1) {
                $installerYamlContent = Get-Content -Path $destYaml -Raw -Encoding UTF8
            }
        }

        # Tentativa A: Executar winget install --manifest (não requer source2.msix)
        $null = Invoke-ProcessWithTimeout -FilePath $WingetCmd -ArgumentList @("settings", "--enable", "LocalManifestFiles") -TimeoutSeconds 15
        $mArgs = @("install", "--manifest", $manifestDir, "--silent", "--accept-package-agreements", "--disable-interactivity", "--scope", "machine")
        $resM = Invoke-ProcessWithTimeout -FilePath $WingetCmd -ArgumentList $mArgs -TimeoutSeconds 240

        if ($resM.ExitCode -in @(0, 19, 3010) -or $resM.Output -match "(?i)Successfully|êxito|Sucesso|already installed|já instalado") {
            Remove-Item $manifestDir -Recurse -Force -ErrorAction SilentlyContinue
            $logs += "[$ts] [Fallback Manifesto] Instalado via 'winget --manifest' (ExitCode $($resM.ExitCode))."
            return [PSCustomObject]@{ Success = $true; ExitCode = $resM.ExitCode; Logs = $logs }
        }

        # Tentativa B: Download direto da InstallerUrl oficial do manifesto (Bypass total de bloqueio GPO do Winget)
        $logs += "[$ts] [Fallback Manifesto] Extraindo InstallerUrl oficial do manifesto YAML..."
        if ([string]::IsNullOrWhiteSpace($installerYamlContent)) {
            throw "Conteúdo do manifesto installer.yaml vazio."
        }

        $rootType = if ($installerYamlContent -match '(?m)^InstallerType:\s*([a-zA-Z0-9_]+)') { $matches[1].ToLower() } else { "" }
        $rootSilent = if ($installerYamlContent -match '(?m)^\s*Silent:\s*(.+)$') { $matches[1].Trim().Trim('"', "'") } else { "" }

        $installersSection = ($installerYamlContent -split '(?m)^Installers:\s*')[1]
        $blocks = $installersSection -split '(?m)^\s*-\s+' | Where-Object { $_ -match 'InstallerUrl:' }

        $bestUrl = $null
        $bestType = $rootType
        $bestSilent = $rootSilent
        $bestScore = -9999

        foreach ($blk in $blocks) {
            if ($blk -notmatch 'InstallerUrl:\s*(\S+)') { continue }
            $urlCandidate = $matches[1].Trim().Trim('"', "'")
            $arch = if ($blk -match 'Architecture:\s*(\S+)') { $matches[1].Trim().ToLower() } else { "x64" }
            $blkType = if ($blk -match 'InstallerType:\s*(\S+)') { $matches[1].Trim().ToLower() } else { $rootType }
            $blkSilent = if ($blk -match '(?m)^\s*Silent:\s*(.+)$') { $matches[1].Trim().Trim('"', "'") } else { $rootSilent }

            $score = 0
            if ($arch -eq "x64") { $score += 100 }
            elseif ($arch -in @("x86", "neutral")) { $score += 50 }
            elseif ($arch -match "arm") { $score -= 1000 }

            if ($blkType -in @("msi", "wix") -or $urlCandidate -match '\.msi(\?|$)') { $score += 25 }
            if ($urlCandidate -match '\.(msix|appx)') { $score -= 50 }

            if ($score -gt $bestScore) {
                $bestScore = $score
                $bestUrl = $urlCandidate
                $bestType = $blkType
                $bestSilent = $blkSilent
            }
        }

        if (-not $bestUrl) {
            throw "Não foi possível localizar uma InstallerUrl compatível no manifesto."
        }

        $uriObj = [System.Uri]$bestUrl
        $fileName = [System.IO.Path]::GetFileName($uriObj.LocalPath)
        if ([string]::IsNullOrWhiteSpace($fileName) -or $fileName -notmatch '\.(exe|msi)$') {
            $ext = if ($bestType -in @("msi", "wix")) { ".msi" } else { ".exe" }
            $fileName = "SARCC_Pkg_$($PackageId -replace '[^a-zA-Z0-9]', '_')$ext"
        }
        $localInstaller = Join-Path "C:\Windows\Temp" "SARCC_$fileName"

        $logs += "[$ts] [Fallback Manifesto] Baixando instalador oficial: $bestUrl"
        Invoke-WebRequest -Uri $bestUrl -OutFile $localInstaller -UseBasicParsing -TimeoutSec 180 -ErrorAction Stop

        $execRes = $null
        if ($localInstaller -match '\.msi$' -or $bestType -in @("msi", "wix")) {
            $msiArgs = @("/i", $localInstaller, "/qn", "/norestart", "ALLUSERS=1")
            $logs += "[$ts] [Fallback Manifesto] Executando msiexec.exe $($msiArgs -join ' ')"
            $execRes = Invoke-ProcessWithTimeout -FilePath "msiexec.exe" -ArgumentList $msiArgs -TimeoutSeconds 300
        } else {
            $silentSwitch = if ($bestSilent) {
                $bestSilent
            } elseif ($bestType -eq "nullsoft") {
                "/S"
            } elseif ($bestType -eq "inno") {
                "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"
            } elseif ($bestType -eq "burn") {
                "/quiet /norestart"
            } else {
                "/S /silent /quiet /norestart"
            }
            $argArray = $silentSwitch -split '\s+'
            $logs += "[$ts] [Fallback Manifesto] Executando instalador com flags: $silentSwitch"
            $execRes = Invoke-ProcessWithTimeout -FilePath $localInstaller -ArgumentList $argArray -TimeoutSeconds 300
        }

        Remove-Item $localInstaller -Force -ErrorAction SilentlyContinue
        Remove-Item $manifestDir -Recurse -Force -ErrorAction SilentlyContinue

        if ($execRes.ExitCode -in @(0, 1641, 3010)) {
            $logs += "[$ts] [Fallback Manifesto] Instalação direta concluída com sucesso (ExitCode $($execRes.ExitCode))."
            return [PSCustomObject]@{ Success = $true; ExitCode = $execRes.ExitCode; Logs = $logs }
        } else {
            $logs += "[$ts] [Fallback Manifesto] Instalador retornou ExitCode $($execRes.ExitCode): $($execRes.Output)"
            return [PSCustomObject]@{ Success = $false; ExitCode = $execRes.ExitCode; Logs = $logs }
        }
    } catch {
        $logs += "[$ts] [Fallback Manifesto] Erro: $($_.Exception.Message)"
        return [PSCustomObject]@{ Success = $false; ExitCode = -1; Logs = $logs }
    }
}

$Engine = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{engine_b64}}'))
$ShareRoot = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{share_root_b64}}'))
$PacotesOnlineRaw = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{pacotes_online_b64}}'))
$PacotesOfflineRaw = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{pacotes_offline_b64}}'))

$PacotesOnline = if ($PacotesOnlineRaw) { $PacotesOnlineRaw -split ',' } else { @() }
$PacotesOffline = if ($PacotesOfflineRaw) { $PacotesOfflineRaw -split ',' } else { @() }

$RawUser = '[[ADMIN_USER]]'
$RawPass = '[[ADMIN_PASS]]'
$UseCredentials = ($RawUser.Length -gt 14)

$LogData = @{
    Script             = "Instalação Multi-Engine ($Engine)"
    Inicio             = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador         = $env:COMPUTERNAME
    StatusFinal        = "SUCESSO"
    PacotesProcessados = @()
    Detalhes           = @()
}

$driveCreated = $false
$DriveLetter  = 'Z'
$SharePath    = $ShareRoot

try {
    # --- BLOCO 1: INSTALAÇÃO OFFLINE VIA REDE SMB ---
    if ($PacotesOffline.Count -gt 0) {
        if ($UseCredentials) {
            $LogData.Detalhes += "[SMB] Montando unidade de rede ($ShareRoot) com credenciais..."
            $AdminUser = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($RawUser))
            $AdminPass = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($RawPass))

            & cmd.exe /c "net use * /delete /y >nul 2>&1"
            if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
                Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }

            try {
                $securePass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
                $cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $securePass)
                $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareRoot -Credential $cred -Scope Global -ErrorAction Stop
                $driveCreated = $true
                $SharePath = "${DriveLetter}:"
                $LogData.Detalhes += "[SMB] Unidade Z: mapeada com sucesso."
            } catch {
                $LogData.PacotesProcessados += @{ Software = "Rede SMB"; Log = "Falha no mapeamento." }
                throw "Falha de Acesso ao share de rede: $($_.Exception.Message)"
            }
        } else {
            $LogData.Detalhes += "[SMB] Acessando compartilhamento via SSO..."
            if (-not (Test-Path -LiteralPath $ShareRoot)) { throw "Acesso negado ao share (Modo SSO)." }
        }

        $LocalTempDir = "C:\Windows\Temp"
        foreach ($sw in $PacotesOffline) {
            if ([string]::IsNullOrWhiteSpace($sw)) { continue }
            $remoteInstaller = Join-Path $SharePath "Softwares\$sw"
            if (-not (Test-Path -LiteralPath $remoteInstaller)) {
                $LogData.PacotesProcessados += @{ Software = $sw; Log = "Arquivo não encontrado na rede." }
                $LogData.StatusFinal = "ALERTA/ERRO"
                continue
            }

            $localInstaller = Join-Path $LocalTempDir "SARCC_$sw"
            $LogData.Detalhes += "[Offline] Copiando '$sw' para $localInstaller..."
            Copy-Item -LiteralPath $remoteInstaller -Destination $localInstaller -Force -ErrorAction SilentlyContinue

            try {
                $regPaths = @(
                    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
                )
                $before = Get-ItemProperty $regPaths -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayName

                $proc = $null
                if ($sw -match '\.msi$') {
                    $msiArgs = "/i `"$localInstaller`" /qn /norestart ALLUSERS=1"
                    $LogData.Detalhes += "[Offline] Executando msiexec.exe $msiArgs"
                    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -PassThru -NoNewWindow
                } else {
                    $exeArgs = "/S /silent /quiet /norestart"
                    $LogData.Detalhes += "[Offline] Executando $localInstaller $exeArgs"
                    $proc = Start-Process -FilePath $localInstaller -ArgumentList $exeArgs -PassThru -NoNewWindow
                }

                $baseName = [regex]::Escape([System.IO.Path]::GetFileNameWithoutExtension($sw))
                $timeout = 300
                $isRunning = $true

                while ($isRunning -and $timeout -gt 0) {
                    Start-Sleep -Seconds 3
                    $timeout -= 3
                    $activeProc = Get-Process | Where-Object { $_.Id -eq $proc.Id -or $_.Name -match $baseName }
                    if (-not $activeProc) { $isRunning = $false }
                }
                if ($isRunning) {
                    Get-Process | Where-Object { $_.Id -eq $proc.Id -or $_.Name -match $baseName } | Stop-Process -Force -ErrorAction SilentlyContinue
                }

                Start-Sleep -Seconds 2
                $after = Get-ItemProperty $regPaths -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayName
                $newApps = Compare-Object $before $after | Where-Object { $_.SideIndicator -eq '=>' }

                if ($newApps -or $proc.ExitCode -in @(0, 3010)) {
                    $LogData.PacotesProcessados += @{ Software = $sw; Log = "Instalado com sucesso (ExitCode $($proc.ExitCode))." }
                    $LogData.Detalhes += "[Offline] '$sw' concluído com sucesso."
                } else {
                    $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falha/Inconclusivo (ExitCode $($proc.ExitCode))." }
                    $LogData.StatusFinal = "ALERTA/ERRO"
                }
            } finally {
                Remove-Item -LiteralPath $localInstaller -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # --- BLOCO 2: INSTALAÇÃO ONLINE (WINGET / CHOCOLATEY) ---
    if ($PacotesOnline.Count -gt 0) {
        if ($Engine -eq "Winget") {
            $wingetCmd = $null
            $realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($realApp) { $wingetCmd = $realApp.FullName }
            if (-not $wingetCmd) {
                $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
                if (Test-Path $candidate) { $wingetCmd = $candidate }
            }

            if (-not $wingetCmd) {
                $LogData.PacotesProcessados += @{ Software = "Winget"; Log = "Winget não localizado." }
                $LogData.StatusFinal = "ERRO FATAL"
            } else {
                $LogData.Detalhes += "[Winget] Binário localizado: $wingetCmd"

                # 1. Define região geográfica (Brasil = 32)
                try { Set-WinHomeLocation -GeoId 32 -ErrorAction SilentlyContinue } catch { }

                # 2. Grava settings.json nos caminhos Packaged e Unpackaged (essencial quando chamado de WindowsApps)
                $settingsPaths = @(
                    "$env:LOCALAPPDATA\Microsoft\WinGet\Settings\defaultState\settings.json",
                    "$env:LOCALAPPDATA\Microsoft\WinGet\Settings\settings.json",
                    "$env:LOCALAPPDATA\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\settings.json",
                    "C:\Windows\System32\config\systemprofile\AppData\Local\Microsoft\WinGet\Settings\defaultState\settings.json",
                    "C:\Windows\System32\config\systemprofile\AppData\Local\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\settings.json"
                )
                $settingsJson = '{"$schema":"https://aka.ms/winget-settings.schema.json","network":{"downloader":"wininet"},"installBehavior":{"preferences":{"scope":"machine"}}}'
                foreach ($sp in $settingsPaths) {
                    try {
                        $dir = Split-Path $sp -Parent
                        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
                        Set-Content -Path $sp -Value $settingsJson -Encoding UTF8 -Force -ErrorAction SilentlyContinue
                    } catch { }
                }

                # 3. Atualiza origem 'winget'
                $LogData.Detalhes += "[Winget] Sincronizando índice da origem 'winget' (HTTP wininet)..."
                $updRes = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList @("source", "update", "--name", "winget", "--disable-interactivity") -TimeoutSeconds 60

                foreach ($sw in $PacotesOnline) {
                    if ([string]::IsNullOrWhiteSpace($sw)) { continue }
                    $ts = (Get-Date).ToString('HH:mm:ss')

                    $wArgs = @(
                        "install", "--id", $sw, "--exact", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements",
                        "--disable-interactivity", "--source", "winget", "--scope", "machine"
                    )
                    $LogData.Detalhes += "[$ts] Executando: winget.exe $($wArgs -join ' ')"
                    $resW = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList $wArgs -TimeoutSeconds 240
                    $outText = $resW.Output
                    $exitCode = $resW.ExitCode

                    # Fallback sem '--scope machine' caso o pacote não possua instalador machine-wide
                    if ($exitCode -ne 0 -and -not $resW.TimedOut -and $outText -match "(?i)No applicable installer|Nenhum instalador aplicável") {
                        $ts = (Get-Date).ToString('HH:mm:ss')
                        $LogData.Detalhes += "[$ts] Retentando sem filtro '--scope machine'..."
                        $wArgsFallback = @(
                            "install", "--id", $sw, "--exact", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements",
                            "--disable-interactivity", "--source", "winget"
                        )
                        $resW = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList $wArgsFallback -TimeoutSeconds 240
                        $outText = $resW.Output
                        $exitCode = $resW.ExitCode
                    }

                    # Camada 2: Reparo do índice V2 (source2.msix) + source reset caso ocorra 0x8a15000f
                    if ($outText -match "0x8a15000f" -or $exitCode -eq -1978335217) {
                        $ts = (Get-Date).ToString('HH:mm:ss')
                        $LogData.Detalhes += "[$ts] Detectado erro 0x8a15000f. Resetando origem e provisionando source2.msix (V2)..."
                        try {
                            $null = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList @("source", "reset", "--name", "winget", "--force") -TimeoutSeconds 30
                            $srcMsix = Join-Path "C:\Windows\Temp" "winget_source2.msix"
                            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                            Invoke-WebRequest -Uri "https://cdn.winget.microsoft.com/cache/source2.msix" -OutFile $srcMsix -UseBasicParsing -TimeoutSec 45 -ErrorAction Stop
                            Add-AppxProvisionedPackage -Online -PackagePath $srcMsix -SkipLicense -ErrorAction SilentlyContinue | Out-Null
                            Add-AppxPackage -Path $srcMsix -ErrorAction SilentlyContinue | Out-Null
                            Remove-Item $srcMsix -Force -ErrorAction SilentlyContinue

                            $resW = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList $wArgs -TimeoutSeconds 240
                            $outText = $resW.Output
                            $exitCode = $resW.ExitCode
                        } catch {
                            $LogData.Detalhes += "[$ts] Aviso ao reparar source2.msix: $($_.Exception.Message)"
                        }
                    }

                    # Camada 3: Fallback Direto via Manifesto Oficial do Winget (Bypass de AppxSvc/GPO)
                    if ($outText -match "0x8a15000f" -or $exitCode -eq -1978335217) {
                        $fbRes = Install-FromWingetManifestFallback -PackageId $sw -WingetCmd $wingetCmd
                        $LogData.Detalhes += $fbRes.Logs
                        if ($fbRes.Success) {
                            $LogData.PacotesProcessados += @{ Software = $sw; Log = "Sucesso (Winget Manifesto Oficial)." }
                            continue
                        } else {
                            $exitCode = $fbRes.ExitCode
                        }
                    }

                    $jaInstalado = ($exitCode -in @(-1978335189, -1978335212, -1978335211)) -or ($outText -match "(?i)já instalado|already installed|No available upgrade")

                    if ($exitCode -in @(0, 19, 3010) -or $outText -match "(?i)Successfully|êxito|Sucesso" -or $jaInstalado) {
                        $statusMsg = if ($jaInstalado) { "Já instalado." } else { "Sucesso (Winget)." }
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = $statusMsg }
                        $LogData.Detalhes += "[$(Get-Date -Format 'HH:mm:ss')] Resultado [$sw]: $statusMsg (ExitCode $exitCode)"
                    } else {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falhou (ExitCode $exitCode)." }
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        $LogData.Detalhes += "[$(Get-Date -Format 'HH:mm:ss')] Winget Erro [$sw] (ExitCode $exitCode): $outText"
                    }
                }
            }
        } elseif ($Engine -eq "Chocolatey") {
            $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
            if (-not (Test-Path $choco)) {
                $LogData.Detalhes += "[Choco] Chocolatey não encontrado no computador alvo ($env:COMPUTERNAME). Instalando motor Chocolatey automaticamente..."
                try {
                    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                    $chocoMsiUrl = "https://github.com/chocolatey/choco/releases/latest/download/chocolatey.x.x.x.nupkg" # URL base, veja nota abaixo
                    $chocoMsiPath = Join-Path $env:TEMP "chocolatey_installer.msi"

                    # O Chocolatey não tem um MSI "puro" oficial no GitHub Releases de forma direta.
                    # A forma recomendada e mais segura pela própria documentação deles para CI/CD
                    # é usar o script da comunidade com validação de hash, OU usar o gerenciador de pacotes do Windows.
                    
                    # COMO ESTAMOS EM 2026, a Microsoft já embute o Winget no Windows 10/11 por padrão.
                    # A forma mais segura de instalar o Chocolatey se ele não existir é usando o Winget para isso!
                    
                    $wingetCmd = $null
                    $realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                    if ($realApp) { $wingetCmd = $realApp.FullName }
                    if (-not $wingetCmd) {
                        $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
                        if (Test-Path $candidate) { $wingetCmd = $candidate }
                    }

                    if ($wingetCmd) {
                        $LogData.Detalhes += "[Choco] Instalando Chocolatey via Winget (seguro e sempre atualizado)..."
                        # O ID no Winget para o Chocolatey é 'Chocolatey.Chocolatey'
                        $resW = Invoke-ProcessWithTimeout -FilePath $wingetCmd -ArgumentList @("install", "--id", "Chocolatey.Chocolatey", "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements") -TimeoutSeconds 120
                        
                        if ($resW.ExitCode -notin @(0, 3010, -1978335189)) { # -1978335189 = Já instalado
                            $LogData.Detalhes += "[Choco] Falha ao instalar via Winget. ExitCode: $($resW.ExitCode)"
                        } else {
                            $LogData.Detalhes += "[Choco] Chocolatey instalado com sucesso via Winget."
                        }
                    } else {
                        $LogData.Detalhes += "[Choco] Winget não encontrado. Não é possível instalar o Chocolatey com segurança sem ele."
                    }
                } catch {
                    $LogData.Detalhes += "[Choco] Falha ao auto-instalar Chocolatey: $($_.Exception.Message)"
                }
            }

            if (-not (Test-Path $choco)) {
                $LogData.PacotesProcessados += @{ Software = "Chocolatey"; Log = "Chocolatey ausente no computador alvo." }
                $LogData.StatusFinal = "ERRO FATAL"
            } else {
                $env:ChocolateyForce = "true"
                foreach ($sw in $PacotesOnline) {
                    if ([string]::IsNullOrWhiteSpace($sw)) { continue }
                    $ts = (Get-Date).ToString('HH:mm:ss')
                    $cArgs = @("install", $sw, "-y", "-r", "--no-progress")
                    $LogData.Detalhes += "[$ts] Executando: choco.exe $($cArgs -join ' ')"
                    $resC = Invoke-ProcessWithTimeout -FilePath $choco -ArgumentList $cArgs -TimeoutSeconds 240
                    $cout = $resC.Output
                    $exitCode = $resC.ExitCode

                    if ($exitCode -in @(0, 1641, 3010) -or $cout -match "(?i)installed successfully|has been installed") {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Sucesso (Choco)." }
                        $LogData.Detalhes += "[$ts] Sucesso [$sw] (ExitCode $exitCode)"
                    } else {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falhou (ExitCode $exitCode)." }
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        $LogData.Detalhes += "[$ts] Choco Erro [$sw] (ExitCode $exitCode): $cout"
                    }
                }
            }
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Detalhes += "Exceção: $($_.Exception.Message)"
} finally {
    if ($driveCreated) { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}