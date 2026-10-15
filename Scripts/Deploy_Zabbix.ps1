<#
.SYNOPSIS
    Deploy Zabbix Agent 2 com auto-diagnóstico de erro 1603.
.NOTES
    - Requer [REQUIRE_CREDENTIALS]
    - Passa SERVER/SERVERACTIVE exigidos pelo MSI oficial do Zabbix.
    - Em caso de falha, anexa o final do log verbose do MSI ao JSON.
#>

$AdminUserRaw = '[[ADMIN_USER]]'
$AdminPassRaw = '[[ADMIN_PASS]]'

# --- Detecta modo de execução ---
# Se ainda há "[[..." → SARCC NÃO injetou credencial → modo conta-máquina (SYSTEM)
# Se já virou Base64 → SARCC injetou → decodifica em runtime
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
# IP/hostname do servidor Zabbix que o agent vai reportar
$ZabbixServer      = "10.8.128.10"   # <- troque pelo IP do seu Zabbix Server
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
    # --- 0. Limpeza de instalação anterior corrompida ---
    $LogData.Detalhes += "[0/7] Verificando instalações Zabbix anteriores ..."
    $oldProducts = Get-CimInstance -ClassName Win32_Product -Filter "Name LIKE '%Zabbix%'" -ErrorAction SilentlyContinue
    if ($oldProducts) {
        foreach ($p in $oldProducts) {
            $LogData.Detalhes += "      -> Removendo produto anterior: $($p.Name) v$($p.Version)"
            try {
                $null = Invoke-CimMethod -InputObject $p -MethodName Uninstall -ErrorAction Stop
                Start-Sleep -Seconds 5
            } catch {
                $LogData.Detalhes += "      !! Falha ao remover: $($_.Exception.Message)"
            }
        }
    } else {
        $LogData.Detalhes += "      -> Nenhum produto Zabbix anterior encontrado."
    }

    # --- 1. Verificar PendingFileRenameOperations (bloqueia MSI com 1603) ---
    $LogData.Detalhes += "[1/7] Verificando operações pendentes de reboot ..."
    $pending = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
    if ($pending) {
        $LogData.Detalhes += "      !! ATENÇÃO: há arquivos pendentes de reboot — pode causar 1603."
    } else {
        $LogData.Detalhes += "      -> Sem pendências."
    }

    # --- 2. Montar drive ---
    $LogData.Detalhes += "[2/7] Montando compartilhamento ..."
    if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    if ($UseContaMaquina) {
        # SYSTEM / conta-máquina (Kerberos assume a identidade da máquina)
        $LogData.Detalhes += "      -> Modo conta-máquina (SYSTEM)"
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                            -Root $ShareServerPath `
                            -Scope Global -ErrorAction Stop
    } else {
        # SARCC ativo: credencial explícita injetada em memória
        $LogData.Detalhes += "      -> Modo credencial explícita ($AdminUser)"
        $secPass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
        $cred    = New-Object System.Management.Automation.PSCredential($AdminUser, $secPass)
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                            -Root $ShareServerPath -Credential $cred `
                            -Scope Global -ErrorAction Stop
    }
    $driveCreated = $true
    $shareRoot = "${DriveLetter}:"

    # --- 3. Copiar MSI ---
    $LogData.Detalhes += "[3/7] Copiando MSI para disco local ..."
    $msiFile = Get-ChildItem -LiteralPath $shareRoot -Filter "zabbix_agent2*.msi" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $msiFile) { throw "Nenhum zabbix_agent2*.msi em $ShareServerPath" }
    Copy-Item -LiteralPath $msiFile.FullName -Destination $LocalMsiPath -Force -ErrorAction Stop
    $LogData.Detalhes += "      -> $($msiFile.Name) copiado."

    # --- 4. Instalação com log verbose ---
    $svc = Get-Service -Name $ZabbixServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        $LogData.Detalhes += "[4/7] Instalando MSI com log verbose ..."
        $LogData.Detalhes += "      -> Servidor Zabbix alvo: $ZabbixServer"

        # Zabbix MSI EXIGE SERVER/SERVERACTIVE. Sem isso, 1603.
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

        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow
        $LogData.Detalhes += "      -> msiexec retornou código $($proc.ExitCode)."

        if ($proc.ExitCode -notin @(0, 3010)) {
            # Lê o final do log para diagnóstico
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
        if (-not (Test-Path -LiteralPath $ZabbixInstallDir)) {
            New-Item -ItemType Directory -Path $ZabbixInstallDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $configSource `
                  -Destination (Join-Path $ZabbixInstallDir "zabbix_agent2.conf") `
                  -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> Config aplicada."
    } else {
        $LogData.Detalhes += "      !! .conf não encontrado — pulando (MSI já tem config padrão)."
    }

    # --- 6. Firewall ---
    $LogData.Detalhes += "[6/7] Verificando firewall ..."
    if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $FirewallRuleName `
            -Direction Inbound -Protocol TCP -LocalPort $FirewallPort `
            -Action Allow -Profile Domain,Private -ErrorAction Stop | Out-Null
        $LogData.Detalhes += "      -> Regra TCP $FirewallPort criada."
    } else {
        $LogData.Detalhes += "      -> Regra já existia."
    }

    # --- 7. Restart ---
    $LogData.Detalhes += "[7/7] Reiniciando serviço ..."
    Set-Service -Name $ZabbixServiceName -StartupType Automatic -ErrorAction Stop
    Restart-Service -Name $ZabbixServiceName -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    $svcFinal = Get-Service -Name $ZabbixServiceName
    $LogData.Mensagem = "Deploy concluído. Status: $($svcFinal.Status)."

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}