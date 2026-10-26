<#
.SYNOPSIS
    Instalação Multi-Engine (Winget, Chocolatey e Offline via SMB) Robusta.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$Engine = '{{engine}}'
$PacotesOnline = @({{pacotes_online}})
$PacotesOffline = @({{pacotes_offline}})
$ShareRoot = '{{share_root}}'

$RawUser = '[[ADMIN_USER]]'
$RawPass = '[[ADMIN_PASS]]'
$UseCredentials = ($RawUser.Length -gt 14)

$LogData = @{
    Script      = "Instalação Multi-Engine ($Engine)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    PacotesProcessados = @()
    Detalhes    = @()
}

$driveCreated = $false
$DriveLetter  = 'Z'
$SharePath    = $ShareRoot

try {
    if ($PacotesOffline.Count -gt 0) {
        if ($UseCredentials) {
            $LogData.Detalhes += "Montando unidade de rede com credenciais..."
            $AdminUser = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($RawUser))
            $AdminPass = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($RawPass))

            & cmd.exe /c "net use * /delete /y >nul 2>&1"
            if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }

            try {
                $securePass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
                $cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $securePass)
                $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareRoot -Credential $cred -Scope Global -ErrorAction Stop
                $driveCreated = $true
                $SharePath = "${DriveLetter}:"
            } catch {
                $LogData.PacotesProcessados += @{ Software = "Rede"; Log = "Falha no mapeamento SMB." }
                throw "Falha de Acesso: Acesso negado ao share de rede. Verifique as credenciais."
            }
        } else {
            $LogData.Detalhes += "Acedendo à rede via SSO (Conta-Máquina)..."
            if (-not (Test-Path -LiteralPath $ShareRoot)) { throw "Acesso negado ao share (Modo SSO)." }
        }

        $LocalTempDir = "C:\Windows\Temp"
        foreach ($sw in $PacotesOffline) {
            $remoteInstaller = Join-Path $SharePath "Softwares\$sw"
            if (-not (Test-Path -LiteralPath $remoteInstaller)) {
                $LogData.PacotesProcessados += @{ Software = $sw; Log = "Ficheiro não encontrado." }
                $LogData.StatusFinal = "ALERTA/ERRO"
                continue
            }

            $localInstaller = Join-Path $LocalTempDir "SARCC_$sw"
            Copy-Item -LiteralPath $remoteInstaller -Destination $localInstaller -Force -ErrorAction SilentlyContinue

            try {
                $regPaths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
                $before = Get-ItemProperty $regPaths -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayName
                
                $proc = $null
                if ($sw -match '\.msi$') {
                    $args = "/i `"$localInstaller`" /qn /norestart ALLUSERS=1"
                    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $args -PassThru -NoNewWindow
                } else {
                    $args = "/S /silent /quiet /norestart"
                    $proc = Start-Process -FilePath $localInstaller -ArgumentList $args -PassThru -NoNewWindow
                }

                $baseName = [System.IO.Path]::GetFileNameWithoutExtension($sw)
                $timeout = 300 
                $isRunning = $true

                while ($isRunning -and $timeout -gt 0) {
                    Start-Sleep -Seconds 3
                    $timeout -= 3
                    $activeProc = Get-Process | Where-Object { $_.Id -eq $proc.Id -or $_.Name -match $baseName }
                    if (-not $activeProc) { $isRunning = $false }
                }
                if ($isRunning) { Get-Process | Where-Object { $_.Id -eq $proc.Id -or $_.Name -match $baseName } | Stop-Process -Force -ErrorAction SilentlyContinue }

                Start-Sleep -Seconds 3
                $after = Get-ItemProperty $regPaths -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayName
                $newApps = Compare-Object $before $after | Where-Object { $_.SideIndicator -eq '=>' }
                
                if ($newApps -or $proc.ExitCode -in @(0, 3010)) {
                    $LogData.PacotesProcessados += @{ Software = $sw; Log = "Instalado com sucesso." }
                } else {
                    $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falha/Inconclusivo." }
                    $LogData.StatusFinal = "ALERTA/ERRO"
                }
            } finally {
                Remove-Item -LiteralPath $localInstaller -Force -ErrorAction SilentlyContinue
            }
        }
    }

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
                foreach ($sw in $PacotesOnline) {
                    $cmdArgs = "install --id `"$sw`" -e --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget"
                    $outText = & cmd.exe /c "`"$wingetCmd`" $cmdArgs 2>&1" | Out-String
                    $outText = $outText.Trim()
                    
                    $jaInstalado = ($LASTEXITCODE -in @(-1978335189, -1978335212, -1978335211)) -or ($outText -match "já instalado|already installed")
                    
                    if ($LASTEXITCODE -in @(0, 19, 3010) -or $outText -match "Successfully|êxito|installed|Sucesso" -or $jaInstalado) {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Sucesso (Winget)." }
                    } else {
                        $LogData.PacotesProcessados += @{ Software = $sw; Log = "Falha." }
                        $LogData.StatusFinal = "ALERTA/ERRO"
                    }
                    $LogData.Detalhes += "Winget Out: $outText"
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