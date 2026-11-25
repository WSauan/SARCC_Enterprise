<#
.SYNOPSIS
    Coleta inteligente de drivers comparando versões do DriverVer antes de transferir pela rede.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$CategoriesStr = '{{categories}}'
$Categories = @($CategoriesStr -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$ShareRoot = '{{share_root}}'

$RawUser = '[[ADMIN_USER]]'
$RawPass = '[[ADMIN_PASS]]'
$UseCredentials = ($RawUser.Length -gt 14)

function Get-InfDriverVersion {
    param([string]$InfFilePath)
    if (-not $InfFilePath -or -not (Test-Path -LiteralPath $InfFilePath)) { return $null }
    try {
        $lines = Get-Content -LiteralPath $InfFilePath -TotalCount 150 -ErrorAction SilentlyContinue
        foreach ($line in $lines) {
            if ($line -match "^\s*DriverVer\s*=\s*[^,]+,\s*([0-9\.]+)") {
                $verStr = ($matches[1] -split '[^0-9\.]')[0].Trim('.')
                $verObj = $null
                if ([System.Version]::TryParse($verStr, [ref]$verObj)) {
                    return $verObj
                }
            }
        }
    } catch { }
    return $null
}

$LogData = @{
    Script      = "Coleta Inteligente Direta"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Mensagem    = ""
    Detalhes    = @("Categorias alvo: $CategoriesStr")
}

$DriveLetter  = 'Z'
$driveCreated = $false
$SharePath    = $null

try {
    if ($UseCredentials) {
        $LogData.Detalhes += "Montando unidade de rede com credenciais..."
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
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareRoot -Credential $cred -Scope Global -Persist -ErrorAction Stop
            $driveCreated = $true
            $SharePath = "${DriveLetter}:"
            $LogData.Detalhes += "[+] PSDrive Z: montado."
        } catch {
            if (Test-Path -LiteralPath $ShareRoot) {
                $SharePath = $ShareRoot
                $LogData.Detalhes += "[+] Share autenticado via sessão UNC direta."
            } else {
                throw "Falha ao montar rede SMB: $($_.Exception.Message)"
            }
        }
    } else {
        if (-not (Test-Path -LiteralPath $ShareRoot)) {
            throw "Acesso negado ao share (Modo SSO)."
        }
        $SharePath = $ShareRoot
        $LogData.Detalhes += "[+] Acesso ao share via SSO."
    }

    $Sys   = Get-CimInstance -ClassName Win32_ComputerSystem
    $Manuf = if ($Sys.Manufacturer) { $Sys.Manufacturer.Trim() -replace '[^a-zA-Z0-9]', '_' } else { "Generico" }
    $Model = if ($Sys.Model)        { $Sys.Model.Trim()        -replace '[^a-zA-Z0-9]', '_' } else { "Padrao" }

    $Destino = Join-Path $SharePath "Drivers\COLETAS\$Manuf\$Model"
    if (-not (Test-Path -LiteralPath $Destino)) {
        $null = New-Item -ItemType Directory -Force -Path $Destino
    }

    $Drivers = @(Get-WindowsDriver -Online -ErrorAction Stop)
    $CountCopiados  = 0
    $CountIgnorados = 0

    foreach ($drv in $Drivers) {
        $ClassName = [string]$drv.ClassName
        $Match = $false

        foreach ($catTrimmed in $Categories) {
            if ($catTrimmed -eq "Camera_Image" -and $ClassName -match "(?i)^(Camera|Image)$") {
                $Match = $true
                break
            } elseif ($ClassName -match "(?i)^$([regex]::Escape($catTrimmed))$") {
                $Match = $true
                break
            }
        }

        if ($Match) {
            $InfPath = $drv.OriginalFileName
            if (-not $InfPath -or -not (Test-Path -LiteralPath $InfPath)) { continue }

            $PastaOriginalDriver = Split-Path $InfPath -Parent
            $InfLeaf             = Split-Path $InfPath -Leaf
            $PastaRealDriver     = $InfLeaf -replace '\.inf$', ''
            $CaminhoDestinoFinal = Join-Path $Destino $PastaRealDriver

            $Atualizar = $false
            $infRede = Get-ChildItem -Path $CaminhoDestinoFinal -Filter $InfLeaf -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

            if (-not $infRede) {
                $Atualizar = $true
            } else {
                $verLocal = Get-InfDriverVersion -InfFilePath $InfPath
                $verRede  = Get-InfDriverVersion -InfFilePath $infRede.FullName
                if ($null -ne $verLocal -and $null -ne $verRede) {
                    if ($verLocal -gt $verRede) {
                        $Atualizar = $true
                    }
                } elseif ($drv.Date -and $infRede.LastWriteTime -and ($drv.Date -gt $infRede.LastWriteTime)) {
                    $Atualizar = $true
                }
            }

            if ($Atualizar) {
                if (Test-Path -LiteralPath $CaminhoDestinoFinal) {
                    $null = Remove-Item -LiteralPath $CaminhoDestinoFinal -Recurse -Force -ErrorAction SilentlyContinue
                }
                $null = Copy-Item -LiteralPath $PastaOriginalDriver -Destination $CaminhoDestinoFinal -Recurse -Force
                $CountCopiados++
                $LogData.Detalhes += "-> TRANSFERIDO: $ClassName ($PastaRealDriver v$($drv.Version))"
            } else {
                $CountIgnorados++
                $LogData.Detalhes += "-> MANTIDO (Já atualizado na rede): $ClassName ($PastaRealDriver v$($drv.Version))"
            }
        }
    }

    $ResumoMsg = "Coleta concluída ($Manuf $Model): $CountCopiados transferido(s), $CountIgnorados já atualizado(s)."
    $LogData.Mensagem = $ResumoMsg
    $LogData.Detalhes += "=== RESUMO DA COLETA ==="
    $LogData.Detalhes += $ResumoMsg
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha na coleta de drivers: $($_.Exception.Message)"
    $LogData.Detalhes += "Falha: $($_.Exception.Message)"
} finally {
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    if ($UseCredentials) {
        & cmd.exe /c "net use `"$ShareRoot`" /delete /y >nul 2>&1"
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}