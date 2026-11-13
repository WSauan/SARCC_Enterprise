<#
.SYNOPSIS
    Instalação automática de drivers do repositório de rede por modelo de placa-mãe e categoria.
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

$LogData = @{
    Script      = "Deploy Auto Drivers"
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
            # Fallback via net use direto no caminho UNC para que o pnputil.exe tenha acesso em sessão não-interativa
            & cmd.exe /c "net use `"$ShareRoot`" `"$AdminPass`" /user:`"$AdminUser`" /persistent:no >nul 2>&1"
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

    $CaminhoRede = Join-Path $SharePath "Drivers\COLETAS\$Manuf\$Model"
    if (-not (Test-Path -LiteralPath $CaminhoRede)) {
        throw "Nenhum backup de drivers encontrado na rede para: $Manuf / $Model"
    }

    $Infs = @(Get-ChildItem -Path $CaminhoRede -Filter "*.inf" -Recurse -ErrorAction SilentlyContinue)
    $CountSucesso = 0
    $CountFalha   = 0

    foreach ($inf in $Infs) {
        $content = Get-Content -LiteralPath $inf.FullName -TotalCount 120 -ErrorAction SilentlyContinue
        $ClassName = "Desconhecido"

        if ($content) {
            foreach ($line in $content) {
                if ($line -match "^\s*Class\s*=\s*([a-zA-Z0-9_\-]+)") {
                    $ClassName = $matches[1].Trim()
                    break
                }
            }
        }

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
            $out = & pnputil.exe /add-driver "$($inf.FullName)" /install 2>&1
            $outStr = $out -join " "

            if ($outStr -match "Successfully|êxito|exito" -or $LASTEXITCODE -in @(0, 3010, 259)) {
                $LogData.Detalhes += "-> INSTALADO: [$ClassName] $($inf.Name)"
                $CountSucesso++
            } else {
                $LogData.Detalhes += "-> FALHA: [$ClassName] $($inf.Name) (Código $LASTEXITCODE)"
                $CountFalha++
            }
        }
    }

    $ResumoMsg = "Deploy concluído ($Manuf $Model): $CountSucesso instalado(s), $CountFalha falha(s)."
    $LogData.Mensagem = $ResumoMsg
    $LogData.Detalhes += $ResumoMsg
    if ($CountFalha -gt 0 -and $CountSucesso -eq 0) {
        $LogData.StatusFinal = "ERRO"
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha no deploy de drivers: $($_.Exception.Message)"
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