<#
.SYNOPSIS
    Ações de Update/Uninstall via Winget, Chocolatey, MSIX/AppX e Registry com modo Verbose.
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

$Action = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{action_b64}}'))
$Engine = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{engine_b64}}'))
$ForceFlag = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{force_flag_b64}}'))
$PacotesRaw = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{pacotes_b64}}'))
$Pacotes = $PacotesRaw -split ','

$LogData = @{
    Script             = "$($Action.ToUpper()) ($Engine)"
    Inicio             = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador         = $env:COMPUTERNAME
    StatusFinal        = "SUCESSO"
    PacotesProcessados = @()
    Detalhes           = @()
}

try {
    $wingetCmd = $null
    $realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($realApp) { $wingetCmd = $realApp.FullName }
    if (-not $wingetCmd) {
        $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
        if (Test-Path $candidate) { $wingetCmd = $candidate }
    }

    foreach ($p in $Pacotes) {
        if ([string]::IsNullOrWhiteSpace($p)) { continue }
        $ts = (Get-Date).ToString('HH:mm:ss')
        $LogData.Detalhes += "[$ts] Iniciando $Action para o pacote: '$p'"

        # 1. Tratamento nativo para pacotes MSIX / AppX da Microsoft Store / Sistema
        if ($Action -eq "uninstall" -and $p -like "MSIX\*") {
            $msixFull = $p -replace '^MSIX\\', ''
            $msixBase = ($msixFull -split '_')[0]
            $LogData.Detalhes += "[$ts] Detectado pacote MSIX/AppX ('$msixBase'). Executando Remove-AppxPackage..."

            $appxList = @(Get-AppxPackage -AllUsers | Where-Object { $_.PackageFullName -eq $msixFull -or $_.Name -eq $msixBase })
            $removedAppx = $false

            foreach ($appx in $appxList) {
                try {
                    Remove-AppxPackage -Package $appx.PackageFullName -AllUsers -ErrorAction Stop
                    $removedAppx = $true
                    $LogData.Detalhes += "[$ts] AppX removido (AllUsers): $($appx.PackageFullName)"
                } catch {
                    try {
                        Remove-AppxPackage -Package $appx.PackageFullName -ErrorAction Stop
                        $removedAppx = $true
                        $LogData.Detalhes += "[$ts] AppX removido (CurrentUser): $($appx.PackageFullName)"
                    } catch {
                        $LogData.Detalhes += "[$ts] Aviso Remove-AppxPackage: $($_.Exception.Message)"
                    }
                }
            }

            $provList = @(Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Where-Object { $_.PackageName -eq $msixFull -or $_.DisplayName -eq $msixBase })
            foreach ($prov in $provList) {
                try {
                    $null = Remove-AppxProvisionedPackage -Online -PackageName $prov.PackageName -ErrorAction Stop
                    $removedAppx = $true
                    $LogData.Detalhes += "[$ts] Pacote provisionado removido: $($prov.PackageName)"
                } catch { }
            }

            if ($removedAppx) {
                $LogData.PacotesProcessados += @{ Software = $p; Log = "Sucesso (AppX/MSIX)." }
            } else {
                $LogData.PacotesProcessados += @{ Software = $p; Log = "Bloqueado pelo SO ou ausente." }
                $LogData.StatusFinal = "ALERTA/ERRO"
            }
            continue
        }

        # 2. Execução via Chocolatey
        if ($Engine -eq "Chocolatey") {
            $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
            if (-not (Test-Path $choco)) { throw "Chocolatey não encontrado em $choco." }
            $env:ChocolateyForce = "true"
            $chocoVerb = if ($Action -eq "uninstall") { "uninstall" } else { "upgrade" }
            $outText = (& $choco $chocoVerb $p -y -r 2>&1 | Out-String).Trim()
            $exitCode = $LASTEXITCODE
            $LogData.Detalhes += "[$ts] Retorno Choco (ExitCode $exitCode): $outText"

            if ($exitCode -in @(0, 1605, 1614, 1641, 3010)) {
                $LogData.PacotesProcessados += @{ Software = $p; Log = "Sucesso (Choco)." }
            } else {
                $LogData.PacotesProcessados += @{ Software = $p; Log = "Falha (ExitCode $exitCode)." }
                $LogData.StatusFinal = "ALERTA/ERRO"
            }
            continue
        }

        # 3. Execução via Winget (Invocação direta sem cmd.exe para evitar Acesso Negado)
        if (-not $wingetCmd) { throw "Winget não localizado na máquina alvo." }

        $outText = ""
        $exitCode = -1

        if ($Action -eq "uninstall") {
            $wingetArgs = @("uninstall", "--id", $p, "--exact", "--silent", "--accept-source-agreements", "--disable-interactivity")
            $LogData.Detalhes += "[$ts] Comando: winget.exe $($wingetArgs -join ' ')"
            $outText = Repair-Mojibake ((& $wingetCmd @wingetArgs 2>&1 | Out-String).Trim())
            $exitCode = $LASTEXITCODE
            $LogData.Detalhes += "[$ts] Winget ExitCode: $exitCode | Saída: $outText"

            # Fallback 1: QuietUninstallString / UninstallString no Registro do Windows
            if ($exitCode -notin @(0, 19, 3010) -and $outText -notmatch "(?i)Successfully|êxito|Sucesso") {
                $LogData.Detalhes += "[$ts] Tentando fallback via Registro (UninstallString)..."
                $cleanId = ($p -replace '^(ARP|MSIX)\\[^\\]+\\[^\\]+\\', '') -replace '^(ARP|MSIX)\\', ''
                $regPaths = @(
                    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
                )
                $regMatch = Get-ItemProperty $regPaths -ErrorAction SilentlyContinue | Where-Object {
                    $_.PSChildName -eq $cleanId -or $_.DisplayName -like "*$cleanId*"
                } | Select-Object -First 1

                if ($regMatch -and ($regMatch.QuietUninstallString -or $regMatch.UninstallString)) {
                    $uStr = if ($regMatch.QuietUninstallString) { $regMatch.QuietUninstallString } else { $regMatch.UninstallString }
                    $LogData.Detalhes += "[$ts] Encontrado no Registro: $($regMatch.DisplayName) -> $uStr"
                    if ($uStr -match '(?i)msiexec' -or $cleanId -match '^\{[0-9A-Fa-f\-]+\}$') {
                        $guid = if ($cleanId -match '^\{[0-9A-Fa-f\-]+\}$') { $cleanId } else { ([regex]::Match($uStr, '\{[0-9A-Fa-f\-]+\}')).Value }
                        if ($guid) {
                            $pMsi = Start-Process -FilePath "msiexec.exe" -ArgumentList "/x $guid /qn /norestart" -Wait -PassThru -NoNewWindow
                            $exitCode = $pMsi.ExitCode
                            $LogData.Detalhes += "[$ts] msiexec /x $guid finalizado com ExitCode: $exitCode"
                        }
                    }
                }
            }

            # Fallback 2: Diretórios padrão (Com [regex]::Escape para nunca quebrar com barras '\')
            if ($exitCode -notin @(0, 19, 1605, 3010) -and $outText -notmatch "(?i)Successfully|êxito|Sucesso") {
                $LogData.Detalhes += "[$ts] Tentando busca de uninstall.exe em diretórios padrão..."
                $uninstallPaths = @(
                    "C:\Users\*\AppData\Local\Programs\*\uninstall.exe",
                    "C:\Program Files\*\uninstall.exe",
                    "C:\Program Files (x86)\*\uninstall.exe"
                )
                $userUninstalls = Get-ChildItem -Path $uninstallPaths -ErrorAction SilentlyContinue
                $cleanToken = (($p -replace '^(MSIX|ARP)\\', '') -split '[\\.]')[0]
                $safeRegex = [regex]::Escape($cleanToken)

                if ($cleanToken.Length -ge 3) {
                    foreach ($exe in $userUninstalls) {
                        if ($exe.FullName -match $safeRegex -or $exe.DirectoryName -match $safeRegex) {
                            $LogData.Detalhes += "[$ts] Executando desinstalador local: $($exe.FullName)"
                            $procU = Start-Process -FilePath $exe.FullName -ArgumentList "/S /silent /quiet" -Wait -PassThru -NoNewWindow -ErrorAction SilentlyContinue
                            $exitCode = if ($procU) { $procU.ExitCode } else { 0 }
                        }
                    }
                }
            }
        } elseif ($Action -eq "upgrade") {
            $wingetArgs = @("upgrade", "--id", $p, "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity", "--source", "winget")
            if (-not [string]::IsNullOrWhiteSpace($ForceFlag)) { $wingetArgs += $ForceFlag }
            $LogData.Detalhes += "[$ts] Comando: winget.exe $($wingetArgs -join ' ')"
            $outText = Repair-Mojibake ((& $wingetCmd @wingetArgs 2>&1 | Out-String).Trim())
            $exitCode = $LASTEXITCODE
            $LogData.Detalhes += "[$ts] Winget ExitCode: $exitCode | Saída: $outText"
        }

        $isSharingViolation = ($exitCode -eq -2147024864) -or ($outText -match "0x80070020|usado por")
        if ($isSharingViolation) {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "App em uso (0x80070020)." }
            $LogData.StatusFinal = "ALERTA/ERRO"
            continue
        }

        if ($exitCode -in @(0, 19, 1605, 3010) -or $outText -match "(?i)Successfully|êxito|installed|Sucesso") {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "Sucesso (ExitCode $exitCode)." }
        } else {
            $LogData.PacotesProcessados += @{ Software = $p; Log = "Falha (ExitCode $exitCode)." }
            $LogData.StatusFinal = "ALERTA/ERRO"
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Detalhes += "Exceção Crítica: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}