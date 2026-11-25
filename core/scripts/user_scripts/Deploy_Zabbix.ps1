<#
.SYNOPSIS
    Deploy Zabbix Agent 2 (versão verbosa) com auto-diagnóstico de erro 1603.
.NOTES
    - Requer [REQUIRE_CREDENTIALS] (credenciais decodificadas em memória via Base64).
    - Passa SERVER/SERVERACTIVE exigidos pelo MSI oficial do Zabbix.
    - Em caso de falha, anexa o final do log verbose do MSI ao JSON.
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

$ShareServerPath   = "\\hul-vp-imagem-cc\netshared"
$DriveLetter       = "Z"
$ZabbixServiceName = "Zabbix Agent 2"
$ZabbixInstallDir  = "C:\Program Files\Zabbix Agent 2"
$FirewallRuleName  = "Zabbix Agent 2"
$FirewallPort      = 10050
$LocalTempDir      = "C:\Windows\Temp"
$LocalMsiPath      = Join-Path $LocalTempDir "zabbix_agent2_deploy.msi"
$MsiLogPath        = Join-Path $LocalTempDir "zabbix_install.log"

# >>> AJUSTE ESTES DOIS VALORES <<<
$ZabbixServer      = "10.8.128.10"
$ZabbixServerActive= $ZabbixServer

$LogData = @{
    Script      = "Deploy Zabbix Agent 2 (auto-diagnóstico)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false

try {
    $LogData.Detalhes += "[INFO] Alvo: $env:COMPUTERNAME | Usuário atual: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

    # --- 0. Limpeza de instalação anterior corrompida ---
    $LogData.Detalhes += "[0/7] Verificando instalações Zabbix anteriores ..."
    try {
        $oldProducts = Get-CimInstance -ClassName Win32_Product -Filter "Name LIKE '%Zabbix%'" -ErrorAction SilentlyContinue
        if ($oldProducts) {
            foreach ($p in $oldProducts) {
                $LogData.Detalhes += "      -> Removendo produto anterior: $($p.Name) v$($p.Version)"
                try {
                    $null = Invoke-CimMethod -InputObject $p -MethodName Uninstall -ErrorAction Stop
                    Start-Sleep -Seconds 5
                } catch {
                    $LogData.Detalhes += "      !! Falha ao remover '$($p.Name)': $($_.Exception.Message)"
                }
            }
        } else {
            $LogData.Detalhes += "      -> Nenhum produto Zabbix anterior encontrado."
        }
    } catch {
        $LogData.Detalhes += "      -> Aviso ao verificar produtos Zabbix anteriores: $($_.Exception.Message)"
    }

    # --- 1. Verificar PendingFileRenameOperations (bloqueia MSI com 1603) ---
    $LogData.Detalhes += "[1/7] Verificando operações pendentes de reboot ..."
    try {
        $pending = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
        if ($pending) {
            $LogData.Detalhes += "      !! ATENÇÃO: há arquivos pendentes de reboot — pode causar 1603."
        } else {
            $LogData.Detalhes += "      -> Sem pendências."
        }
    } catch {
        $LogData.Detalhes += "      -> Aviso ao ler PendingFileRenameOperations: $($_.Exception.Message)"
    }

    # --- 2. Montar drive ---
    $LogData.Detalhes += "[2/7] Montando compartilhamento ..."
    try {
        if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
            Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
            $LogData.Detalhes += "      -> PSDrive '$DriveLetter:' anterior removido."
        }
        & cmd.exe /c "net use $ShareServerPath /delete /y >nul 2>&1"
        & cmd.exe /c "net use \\hul-vp-imagem-cc\IPC$ /delete /y >nul 2>&1"
    } catch {
        $LogData.Detalhes += "      -> Aviso ao limpar sessão SMB prévia: $($_.Exception.Message)"
    }

    if ($UseContaMaquina) {
        $LogData.Detalhes += "      -> Modo conta-máquina (SYSTEM)"
        try {
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                                -Root $ShareServerPath `
                                -Scope Global -ErrorAction Stop
        } catch {
            $LogData.Detalhes += "      !! Falha New-PSDrive conta-máquina: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      -> Modo credencial explícita ($AdminUser)"
        try {
            $secPass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
            $cred    = New-Object System.Management.Automation.PSCredential($AdminUser, $secPass)
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                                -Root $ShareServerPath -Credential $cred `
                                -Scope Global -ErrorAction Stop
        } catch {
            $LogData.Detalhes += "      !! Falha New-PSDrive com credencial ($AdminUser): $($_.Exception.Message)"
            throw
        }
    }
    $driveCreated = $true
    $shareRoot = "${DriveLetter}:"

    # --- 3. Copiar MSI ---
    $LogData.Detalhes += "[3/7] Copiando MSI para disco local ..."
    try {
        $msiFile = Get-ChildItem -LiteralPath $shareRoot -Filter "zabbix_agent2*.msi" -ErrorAction Stop |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
    } catch {
        $LogData.Detalhes += "      !! Falha ao listar MSI em '$shareRoot': $($_.Exception.Message)"
        throw
    }
    if (-not $msiFile) { throw "Nenhum zabbix_agent2*.msi em $ShareServerPath" }

    try {
        Copy-Item -LiteralPath $msiFile.FullName -Destination $LocalMsiPath -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> $($msiFile.Name) copiado."
    } catch {
        $LogData.Detalhes += "      !! Falha ao copiar MSI para '$LocalMsiPath': $($_.Exception.Message)"
        throw
    }

    # --- 4. Instalação com log verbose ---
    $svc = Get-Service -Name $ZabbixServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        $LogData.Detalhes += "[4/7] Instalando MSI com log verbose ..."
        $LogData.Detalhes += "      -> Servidor Zabbix alvo: $ZabbixServer"

        $msiArgs = @(
            "/i", "`"$LocalMsiPath`"",
            "/qn",
            "/norestart",
            "/l*v", "`"$MsiLogPath`"",
            "SERVER=`"$ZabbixServer`"",
            "SERVERACTIVE=`"$ZabbixServerActive`"",
            "HOSTNAME=`"$env:COMPUTERNAME`"",
            "ALLUSERS=1",
            "REBOOT=R"
        ) -join " "

        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow -ErrorAction Stop
        $LogData.Detalhes += "      -> msiexec retornou código $($proc.ExitCode)."

        if ($proc.ExitCode -notin @(0, 3010)) {
            if (Test-Path -LiteralPath $MsiLogPath) {
                $logTail = Get-Content -LiteralPath $MsiLogPath -Tail 40 -ErrorAction SilentlyContinue
                $LogData.Detalhes += "      === ÚLTIMAS LINHAS DO LOG MSI (para diagnóstico) ==="
                foreach ($linha in $logTail) {
                    $LogData.Detalhes += "        $linha"
                }
                $LogData.Detalhes += "      ==================================================="
            }
            throw "MSIExec retornou código $($proc.ExitCode). Veja o log MSI acima nas linhas '==='."
        }
        $LogData.Detalhes += "      -> Instalado com sucesso."
    } else {
        $LogData.Detalhes += "[4/7] Zabbix já instalado. Pulando MSI."
    }

    # --- 5. Configuração ---
    $LogData.Detalhes += "[5/7] Aplicando zabbix_agent2.conf ..."
    $configSource = Join-Path $shareRoot "zabbix_agent2.conf"
    if (Test-Path -LiteralPath $configSource) {
        try {
            if (-not (Test-Path -LiteralPath $ZabbixInstallDir)) {
                New-Item -ItemType Directory -Path $ZabbixInstallDir -Force -ErrorAction Stop | Out-Null
            }
            Copy-Item -LiteralPath $configSource `
                      -Destination (Join-Path $ZabbixInstallDir "zabbix_agent2.conf") `
                      -Force -ErrorAction Stop
            $LogData.Detalhes += "      -> Config aplicada."
        } catch {
            $LogData.Detalhes += "      !! Falha ao aplicar zabbix_agent2.conf: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      !! .conf não encontrado — pulando (MSI já tem config padrão)."
    }

    # --- 6. Firewall ---
    $LogData.Detalhes += "[6/7] Verificando firewall ..."
    try {
        if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $FirewallRuleName `
                -Direction Inbound -Protocol TCP -LocalPort $FirewallPort `
                -Action Allow -Profile Domain,Private -ErrorAction Stop | Out-Null
            $LogData.Detalhes += "      -> Regra TCP $FirewallPort criada."
        } else {
            $LogData.Detalhes += "      -> Regra já existia."
        }
    } catch {
        $LogData.Detalhes += "      !! Falha ao configurar regra de firewall: $($_.Exception.Message)"
        throw
    }

    # --- 7. Restart ---
    $LogData.Detalhes += "[7/7] Reiniciando serviço ..."
    try {
        Set-Service -Name $ZabbixServiceName -StartupType Automatic -ErrorAction Stop
        Restart-Service -Name $ZabbixServiceName -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
        $svcFinal = Get-Service -Name $ZabbixServiceName -ErrorAction Stop
        $LogData.Mensagem = "Deploy concluído. Status: $($svcFinal.Status)."
    } catch {
        $LogData.Detalhes += "      !! Falha ao reiniciar serviço '$ZabbixServiceName': $($_.Exception.Message)"
        throw
    }

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    if ($driveCreated) {
        try { Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue } catch { }
        try { & cmd.exe /c "net use $ShareServerPath /delete /y >nul 2>&1" } catch { }
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}