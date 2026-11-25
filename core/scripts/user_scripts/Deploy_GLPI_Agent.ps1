<#
.SYNOPSIS
    Deploy GLPI Agent: instala/atualiza via MSI na rede, aplica config OAuth e força inventário.
.NOTES
    - Detecta modo conta-máquina (SYSTEM/tarefa agendada) ou credencial explícita (SARCC ativo).
    - Busca sempre o MSI mais recente no compartilhamento.
    - Compara versão instalada com a do MSI e só reinstala se necessário.
#>

$AdminUserRaw = '[[ADMIN_USER]]'
$AdminPassRaw = '[[ADMIN_PASS]]'

if ($AdminUserRaw.StartsWith("[[")) {
    $UseContaMaquina = $true
    $AdminUser = ""
    $AdminPass = ""
} else {
    $UseContaMaquina = $false
    $AdminUser = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AdminUserRaw))
    $AdminPass = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AdminPassRaw))
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# --- Configuração ---
$ShareServerPath = "\\hul-vp-imagem-cc\netshared"
$DriveLetter     = "Z"
$ServerUrl       = "https://chamados.hul-ufs.ebserh/front/inventory.php"
$OAuthClientId   = "{{glpi_oauth_id}}"
$OAuthClientSecret = "{{glpi_oauth_secret}}"
$RegPath         = "HKLM:\SOFTWARE\GLPI-Agent"
$AgentBatPath    = "C:\Program Files\GLPI-Agent\glpi-agent.bat"
$ServiceName     = "glpi-agent"
$LocalTempDir    = "C:\Windows\Temp"

$LogData = @{
    Script      = "Deploy GLPI Agent"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false

try {
    # --- [0/6] Aplicar chaves de registro (OAuth) ---
    $LogData.Detalhes += "[0/6] Aplicando chaves de registro (OAuth)..."
    if (-not (Test-Path $RegPath)) {
        New-Item -Path $RegPath -Force | Out-Null
    }
    Set-ItemProperty -Path $RegPath -Name "server"               -Value $ServerUrl         -Type String
    Set-ItemProperty -Path $RegPath -Name "authentication"       -Value "oauth"            -Type String
    Set-ItemProperty -Path $RegPath -Name "oauth-client-id"      -Value $OAuthClientId     -Type String
    Set-ItemProperty -Path $RegPath -Name "oauth-client-secret"  -Value $OAuthClientSecret -Type String
    Set-ItemProperty -Path $RegPath -Name "no-ssl-check"         -Value "1"                -Type String
    $LogData.Detalhes += "      -> Registro configurado para $ServerUrl"

    # --- [1/6] Montar compartilhamento (credencial ou conta-máquina) ---
    $LogData.Detalhes += "[1/6] Montando compartilhamento..."
    if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }

    if ($UseContaMaquina) {
        $LogData.Detalhes += "      -> Modo conta-máquina (SYSTEM)"
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                            -Root $ShareServerPath `
                            -Scope Global -ErrorAction Stop
    } else {
        $LogData.Detalhes += "      -> Modo credencial explícita ($AdminUser)"
        $secPass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
        $cred    = New-Object System.Management.Automation.PSCredential($AdminUser, $secPass)
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                            -Root $ShareServerPath -Credential $cred `
                            -Scope Global -ErrorAction Stop
    }
    $driveCreated = $true
    $shareRoot = "${DriveLetter}:"

    # --- [2/6] Localizar MSI mais recente ---
    $LogData.Detalhes += "[2/6] Buscando MSI mais recente em $ShareServerPath ..."
    $msiFile = Get-ChildItem -LiteralPath $shareRoot -Filter "GLPI-Agent*.msi" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $msiFile) {
        throw "Nenhum 'GLPI-Agent*.msi' encontrado em $ShareServerPath"
    }
    $targetVersion = if ($msiFile.Name -match "GLPI-Agent-(.*?)-x64") { $matches[1] } else { "Desconhecida" }
    $LogData.Detalhes += "      -> MSI: $($msiFile.Name) (versão $targetVersion)"

    # --- [3/6] Verificar versão instalada ---
    $LogData.Detalhes += "[3/6] Verificando versão instalada..."
    $needsInstall = $false
    if (Test-Path $AgentBatPath) {
        try {
            $currentVersion = (Get-Command $AgentBatPath).FileVersionInfo.FileVersion
            $LogData.Detalhes += "      -> Versão atual: $currentVersion"
            if ($currentVersion -notmatch [regex]::Escape($targetVersion)) {
                $needsInstall = $true
                $LogData.Detalhes += "      -> Versão divergente. Atualização necessária."
            } else {
                $LogData.Detalhes += "      -> Versão em dia. Pulando instalação."
            }
        } catch {
            $needsInstall = $true
            $LogData.Detalhes += "      -> Falha ao ler versão. Forçando reinstalação."
        }
    } else {
        $needsInstall = $true
        $LogData.Detalhes += "      -> GLPI Agent não instalado."
    }

    # --- [4/6] Instalação/atualização ---
    if ($needsInstall) {
        $LogData.Detalhes += "[4/6] Instalando/atualizando GLPI Agent..."
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue

        # Copia para temp local (evita erro de acesso SMB durante o MSI)
        $msiLocal = Join-Path $LocalTempDir $msiFile.Name
        Copy-Item -LiteralPath $msiFile.FullName -Destination $msiLocal -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> MSI copiado para $msiLocal"

        # Desinstala versão anterior via CIM (Win32_Product é lento mas confiável aqui)
        $LogData.Detalhes += "      -> Removendo instalações anteriores (se houver)..."
        $existing = Get-CimInstance -ClassName Win32_Product -Filter "Name LIKE '%GLPI-Agent%'" -ErrorAction SilentlyContinue
        if ($existing) {
            foreach ($app in $existing) {
                $LogData.Detalhes += "         -> Desinstalando: $($app.Name) v$($app.Version)"
                $null = Invoke-CimMethod -InputObject $app -MethodName Uninstall -ErrorAction SilentlyContinue
            }
        }

        # Instala com argumentos + propriedades do MSI
        $msiArgs = @(
            "/i", "`"$msiLocal`"",
            "/qn",
            "/norestart",
            "SERVER=`"$ServerUrl`"",
            "AUTHENTICATION=`"oauth`"",
            "OAUTH-CLIENT-ID=`"$OAuthClientId`"",
            "OAUTH-CLIENT-SECRET=`"$OAuthClientSecret`"",
            "NO-SSL-CHECK=`"1`"",
            "RUNNOW=`"1`""
        ) -join " "

        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow
        $LogData.Detalhes += "      -> msiexec retornou código $($proc.ExitCode)."

        if ($proc.ExitCode -notin @(0, 3010)) {
            throw "Instalação falhou (código $($proc.ExitCode))."
        }

        Remove-Item -LiteralPath $msiLocal -Force -ErrorAction SilentlyContinue
        $LogData.Detalhes += "      -> Instalação concluída com sucesso."
    } else {
        $LogData.Detalhes += "[4/6] Nenhuma ação necessária."
    }

    # --- [5/6] Reiniciar serviço ---
    $LogData.Detalhes += "[5/6] Reiniciando serviço $ServiceName ..."
    Set-Service -Name $ServiceName -StartupType Automatic -ErrorAction SilentlyContinue
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $svcFinal = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svcFinal -and $svcFinal.Status -eq 'Running') {
        $LogData.Detalhes += "      -> Serviço ativo. Status: Running"
    } else {
        $LogData.Detalhes += "      -> AVISO: status do serviço é '$($svcFinal.Status)'"
    }

    # --- [6/6] Forçar inventário ---
    $LogData.Detalhes += "[6/6] Forçando execução do inventário..."
    if (Test-Path $AgentBatPath) {
        try {
            Start-Process -FilePath $AgentBatPath -ArgumentList "--force" -NoNewWindow -Wait -ErrorAction Stop
            $LogData.Detalhes += "      -> Inventário enviado ao servidor."
        } catch {
            $LogData.Detalhes += "      -> Falha ao forçar inventário: $($_.Exception.Message)"
        }
    } else {
        $LogData.Detalhes += "      -> glpi-agent.bat não encontrado em $AgentBatPath"
    }

    $LogData.Mensagem = "GLPI Agent operacional. Versão: $targetVersion. Serviço: $($svcFinal.Status)."

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}