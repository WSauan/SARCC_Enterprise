<#
.SYNOPSIS
    Coleta inteligente de drivers.
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
    Script      = "Coleta Inteligente Direta"
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

    $Destino = Join-Path $SharePath "Drivers\COLETAS\$Manuf\$Model"
    if (-not (Test-Path $Destino)) { $null = New-Item -ItemType Directory -Force -Path $Destino }

    $Drivers = Get-WindowsDriver -Online
    $CountCopiados = 0
    $CountIgnorados = 0
    
    foreach ($drv in $Drivers) {
        $ClassName = $drv.ClassName
        $Match = $false
        
        foreach ($cat in $Categories) {
            $catTrimmed = $cat.Trim()
            if ($catTrimmed -eq "Camera_Image" -and $ClassName -match "(?i)^(Camera|Image)$") { $Match = $true; break }
            elseif ($ClassName -match "(?i)^$catTrimmed$") { $Match = $true; break }
        }
        
        if ($Match) {
            $InfPath = $drv.OriginalFileName
            $PastaOriginalDriver = Split-Path $InfPath -Parent
            $PastaRealDriver = (Split-Path $InfPath -Leaf) -replace '\.inf$', ''
            $CaminhoDestinoFinal = Join-Path $Destino $PastaRealDriver
            
            $Atualizar = $false
            $infRede = Get-ChildItem -Path $Destino -Filter (Split-Path $InfPath -Leaf) -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

            if (-not $infRede) { $Atualizar = $true } else { $Atualizar = $true }
            
            if ($Atualizar) {
                if ($infRede) { $null = Remove-Item -Path $infRede.Directory.FullName -Recurse -Force }
                if (Test-Path $CaminhoDestinoFinal) { $null = Remove-Item -Path $CaminhoDestinoFinal -Recurse -Force }
                $null = Copy-Item -Path $PastaOriginalDriver -Destination $CaminhoDestinoFinal -Recurse -Force
                $CountCopiados++
                $LogData.Detalhes += "-> TRANSFERIDO: $ClassName ($PastaRealDriver)"
            } else { $CountIgnorados++ }
        }
    }
    
    $LogData.Detalhes += "=== RESUMO DA COLETA ==="
    $LogData.Detalhes += "Total: $CountCopiados transferidos, $CountIgnorados mantidos."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha: $($_.Exception.Message)"
} finally {
    if ($driveCreated) { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}