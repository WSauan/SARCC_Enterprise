<#
.SYNOPSIS
    Instalação Multi-Engine (Winget, Chocolatey e Offline via SMB) com bypass de GPO/DO e modo Verbose.
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

                # 1. Define região geográfica (Brasil = 32) para a sessão SYSTEM
                try { Set-WinHomeLocation -GeoId 32 -ErrorAction SilentlyContinue } catch { }

                # 2. Configura downloader 'wininet' no settings.json para contornar bloqueio GPO de Delivery Optimization
                $settingsPaths = @(
                    "$env:LOCALAPPDATA\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\settings.json",
                    "C:\Windows\System32\config\systemprofile\AppData\Local\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\settings.json"
                )
                $settingsJson = '{"$schema":"https://aka.ms/winget-settings.schema.json","network":{"downloader":"wininet"}}'
                foreach ($sp in $settingsJsonPath in $settingsPaths) {
                    try {
                        $dir = Split-Path $sp -Parent
                        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
                        Set-Content -Path $sp -Value $settingsJson -Encoding UTF8 -Force -ErrorAction SilentlyContinue
                    } catch { }
                }

                # 3. Provisiona/Atualiza exclusivamente a origem 'winget' (ignorando 'msstore' bloqueada por GPO)
                $LogData.Detalhes += "[Winget] Sincronizando índice da origem 'winget' (HTTP wininet)..."
                $null = & $wingetCmd source update --name winget --disable-interactivity 2>&1

                foreach ($sw in $PacotesOnline) {
                    if ([string]::IsNullOrWhiteSpace($sw)) { continue }
                    $ts = (Get-Date).ToString('HH:mm:ss')

                    $wArgs = @(
                        "install", "--id", $sw, "--exact", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements",
                        "--disable-interactivity", "--source", "winget", "--scope", "machine"
                    )
                    $LogData.Detalhes += "[$ts] Executando: winget.exe $($wArgs -join ' ')"
                    $outText = Repair-Mojibake ((& $wingetCmd @wArgs 2>&1 | Out-String).Trim())
                    $exitCode = $LASTEXITCODE

                    # Fallback sem '--scope machine' caso o pacote só possua instalador User/ Genérico
                    if ($exitCode -ne 0 -and $outText -match "(?i)No applicable installer|Nenhum instalador aplicável") {
                        $LogData.Detalhes += "[$ts] Retentando sem filtro '--scope machine'..."
                        $wArgsFallback = @(
                            "install", "--id", $sw, "--exact", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements",
                            "--disable-interactivity", "--source", "winget"
                        )
                        $outText = Repair-Mojibake ((& $wingetCmd @wArgsFallback 2>&1 | Out-String).Trim())
                        $exitCode = $LASTEXITCODE
                    }

                    # Fallback de reparo de índice caso 0x8a15000f persista no perfil SYSTEM
                    if ($outText -match "0x8a15000f") {
                        $LogData.Detalhes += "[$ts] Detectado erro de cache 0x8a15000f no perfil SYSTEM. Reparando pacote Microsoft.Winget.Source..."
                        try {
                            $srcMsix = Join-Path $env:TEMP "winget_source.msix"
                            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                            Invoke-WebRequest -Uri "https://cdn.winget.microsoft.com/cache/source.msix" -OutFile $srcMsix -UseBasicParsing -ErrorAction Stop
                            Add-AppxProvisionedPackage -Online -PackagePath $srcMsix -SkipLicense -ErrorAction SilentlyContinue | Out-Null
                            Remove-Item $srcMsix -Force -ErrorAction SilentlyContinue
                            $outText = Repair-Mojibake ((& $wingetCmd @wArgs 2>&1 | Out-String).Trim())
                            $exitCode = $LASTEXITCODE
                        } catch {
                            $LogData.Detalhes += "[$ts] Aviso ao reparar source.msix: $($_.Exception.Message)"
                        }
                    }

                    $jaInstalado = ($exitCode -in @(-1978335189, -1978335212, -1978335211)) -or ($outText -match "(?i)já instalado|already installed|No available upgrade")

                    if ($exitCode -in @(0, 19, 3010) -or $outText -match "(?i)Successfully|êxito|Sucesso" -or $jaInstalado) {
                        $statusMsg = if ($jaInstalado) { "Já instalado." } else { "Sucesso (Winget)." }
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = $statusMsg }
                        $LogData.Detalhes += "[$ts] Resultado [$sw]: $statusMsg (ExitCode $exitCode)"
                    } else {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falhou (ExitCode $exitCode)." }
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        $LogData.Detalhes += "[$ts] Winget Erro [$sw] (ExitCode $exitCode): $outText"
                    }
                }
            }
        } elseif ($Engine -eq "Chocolatey") {
            $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
            if (-not (Test-Path $choco)) {
                $LogData.Detalhes += "[Choco] Chocolatey não encontrado no endpoint. Instalando motor Chocolatey automaticamente..."
                try {
                    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
                } catch {
                    $LogData.Detalhes += "[Choco] Falha ao auto-instalar Chocolatey: $($_.Exception.Message)"
                }
            }

            if (-not (Test-Path $choco)) {
                $LogData.PacotesProcessados += @{ Software = "Chocolatey"; Log = "Chocolatey ausente no alvo." }
                $LogData.StatusFinal = "ERRO FATAL"
            } else {
                $env:ChocolateyForce = "true"
                foreach ($sw in $PacotesOnline) {
                    if ([string]::IsNullOrWhiteSpace($sw)) { continue }
                    $ts = (Get-Date).ToString('HH:mm:ss')
                    $LogData.Detalhes += "[$ts] Executando: choco.exe install $sw -y -r --no-progress"
                    $cout = Repair-Mojibake ((& $choco install $sw -y -r --no-progress 2>&1 | Out-String).Trim())
                    $exitCode = $LASTEXITCODE

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