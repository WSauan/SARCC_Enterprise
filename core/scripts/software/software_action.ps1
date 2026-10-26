<#
.SYNOPSIS
    Ações de Update/Uninstall via Winget com caça a Apps Globais/Utilizador.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$Action = '{{action}}'
$Engine = '{{engine}}'
$ForceFlag = '{{force_flag}}'
$Pacotes = @({{pacotes}})

$LogData = @{
    Script = "$($Action.ToUpper()) ($Engine)"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    PacotesProcessados = @()
    Detalhes = @()
}

try {
    $wingetCmd = $null
    $realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($realApp) { $wingetCmd = $realApp.FullName }

    if (-not $wingetCmd) {
        $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
        if (Test-Path $candidate) { $wingetCmd = $candidate }
    }

    if (-not $wingetCmd) { throw "Winget não localizado na máquina alvo." }

    foreach ($p in $Pacotes) {
        $LogData.Detalhes += "Processando: $p ($Action)"
        
        if ($Action -eq "uninstall") {
            $cmdArgs = "uninstall --id `"$p`" --exact --silent --accept-source-agreements"
            $outText = & cmd.exe /c "`"$wingetCmd`" $cmdArgs 2>&1" | Out-String
            
            if ($LASTEXITCODE -notin @(0, 19, 3010)) {
                $LogData.Detalhes += "Tentando fallback WMI..."
                $wmi = Get-CimInstance Win32_Product -Filter "Name LIKE '%$p%'" -ErrorAction SilentlyContinue
                if ($wmi) { $null = Invoke-CimMethod -InputObject $wmi -MethodName Uninstall; $LASTEXITCODE = 0 }
            }

            if ($LASTEXITCODE -notin @(0, 19, 3010)) {
                $LogData.Detalhes += "Tentando desinstalação forçada em diretórios padrão..."
                
                $uninstallPaths = @(
                    "C:\Users\*\AppData\Local\Programs\*\uninstall.exe",
                    "C:\Users\*\AppData\Local\Programs\*\*\uninstall.exe",
                    "C:\Program Files\*\uninstall.exe",
                    "C:\Program Files (x86)\*\uninstall.exe"
                )
                $userUninstalls = Get-ChildItem -Path $uninstallPaths -ErrorAction SilentlyContinue
                
                $appNameRaw = $p.Split('.')[0] 
                
                foreach ($exe in $userUninstalls) {
                    if ($exe.FullName -match $appNameRaw -or $exe.DirectoryName -match $appNameRaw) {
                        $LogData.Detalhes += "Encontrado desinstalador: $($exe.FullName)"
                        Start-Process -FilePath $exe.FullName -ArgumentList "/S /silent /quiet" -Wait -NoNewWindow -ErrorAction SilentlyContinue
                        $LASTEXITCODE = 0
                    }
                }
            }
        } elseif ($Action -eq "upgrade") {
            $cmdArgs = "upgrade --id `"$p`" --exact --silent --accept-package-agreements --accept-source-agreements $ForceFlag"
            $outText = & cmd.exe /c "`"$wingetCmd`" $cmdArgs 2>&1" | Out-String
        }

        $outText = $outText.Trim()
        $isSharingViolation = ($LASTEXITCODE -eq -2147024864) -or ($outText -match "0x80070020|usado por")
        if ($isSharingViolation) {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "App em uso." }; $LogData.StatusFinal = "ALERTA/ERRO"; continue
        }

        if ($LASTEXITCODE -in @(0, 19, 3010) -or $outText -match "Successfully|êxito|installed|Sucesso") {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "Sucesso." }
        } else {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "Falha." }; $LogData.StatusFinal = "ALERTA/ERRO"
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"; $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}