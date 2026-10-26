<#
.SYNOPSIS
    Instalação automática de drivers.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$CategoriesStr = '{{categories}}'
$Categories = $CategoriesStr -split ','
$ShareRoot = '{{share_root}}'

$RawUser = '[[ADMIN_USER]]'
$RawPass = '[[ADMIN_PASS]]'
$UseCredentials = ($RawUser.Length -gt 14)

$LogData = @{
    Script      = "Deploy Auto Drivers"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
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
        if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }

        try {
            $securePass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
            $cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $securePass)
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareRoot -Credential $cred -Scope Global -Persist -ErrorAction Stop
            
            $driveCreated = $true
            $SharePath = "${DriveLetter}:"
            $LogData.Detalhes += "[+] PSDrive Z: montado."
        } catch {
            throw "Falha ao montar rede SMB: $($_.Exception.Message)"
        }
    } else {
        if (-not (Test-Path -LiteralPath $ShareRoot)) { throw "Acesso negado ao share (Modo SSO)." }
        $SharePath = $ShareRoot
        $LogData.Detalhes += "[+] Acesso ao share via SSO."
    }

    $Sys   = Get-CimInstance -ClassName Win32_ComputerSystem
    $Manuf = $Sys.Manufacturer.Trim() -replace '[^a-zA-Z0-9]', '_'
    $Model = $Sys.Model.Trim()        -replace '[^a-zA-Z0-9]', '_'

    $CaminhoRede = Join-Path $SharePath "Drivers\COLETAS\$Manuf\$Model"
    if (-not (Test-Path $CaminhoRede)) { throw "Nenhum backup encontrado na rede para: $Manuf $Model" }

    $Infs = Get-ChildItem -Path $CaminhoRede -Filter "*.inf" -Recurse
    $CountSucesso = 0
    $CountFalha   = 0

    foreach ($inf in $Infs) {
        $content = Get-Content $inf.FullName -TotalCount 35 -ErrorAction SilentlyContinue
        $ClassName = "Desconhecido"
        
        if ($content) {
            foreach ($line in $content) {
                if ($line -match "Class\s*=\s*([a-zA-Z0-9_]+)") {
                    $ClassName = $matches[1]
                    break
                }
            }
        }

        $Match = $false
        foreach ($cat in $Categories) {
            $catTrimmed = $cat.Trim()
            if ($catTrimmed -eq "Camera_Image" -and $ClassName -match "(?i)^(Camera|Image)$") { $Match = $true; break }
            elseif ($ClassName -match "(?i)^$catTrimmed$") { $Match = $true; break }
        }

        if ($Match) {
            $out = pnputil.exe /add-driver $inf.FullName /install 2>&1
            $outStr = $out -join " "

            if ($outStr -match "Successfully|êxito" -or $LASTEXITCODE -in @(0, 3010, 259)) {
                $LogData.Detalhes += "-> INSTALADO: [$ClassName] $($inf.Name)"
                $CountSucesso++
            } else {
                $CountFalha++
            }
        }
    }
    $LogData.Detalhes += "Deploy concluido. $CountSucesso instalados, $CountFalha falhas."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha: $($_.Exception.Message)"
} finally {
    if ($driveCreated) { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}