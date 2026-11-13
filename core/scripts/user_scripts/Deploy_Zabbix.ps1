<#
.SYNOPSIS
    Deploy Zabbix Agent 2 com auto-diagnóstico de erro 1603, PerfMon Rebuild e Auto-Healing.
.NOTES
    - Requer [REQUIRE_CREDENTIALS]
    - Passa SERVER/SERVERACTIVE exigidos pelo MSI oficial do Zabbix (10.8.245.12).
    - Reconstrói contadores de desempenho (lodctr /R) e ativa Auto-Healing no serviço.
#>

$AdminUserRaw = '[[ADMIN_USER]]'
$AdminPassRaw = '[[ADMIN_PASS]]'

if ($AdminUserRaw.StartsWith("[[") -or $AdminUserRaw.Length -lt 4) {
    $UseContaMaquina = $true
    $AdminUser = ""
    $AdminPass = ""
} else {
    $UseContaMaquina = $false
    $AdminUser = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AdminUserRaw))
    $AdminPass = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AdminPassRaw))
}

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ShareServerPath   = "\\hul-vp-imagem-cc\netshared"
$DriveLetter       = "Z"
$ZabbixServiceName = "Zabbix Agent 2"
$ZabbixInstallDir  = "C:\Program Files\Zabbix Agent 2"
$FirewallRuleName  = "Zabbix Agent 2"
$FirewallPort      = 10050
$LocalTempDir      = "C:\Windows\Temp"
$LocalMsiPath      = Join-Path $LocalTempDir "zabbix_agent2_deploy.msi"
$MsiLogPath        = Join-Path $LocalTempDir "zabbix_install.log"

# IP oficial do servidor Zabbix HUL (também verificado dinamicamente no .conf da rede)
$ZabbixServer       = "10.8.245.12"
$ZabbixServerActive = $ZabbixServer

$LogData = @{
    Script      = "Deploy Zabbix Agent 2 (Auto-Diagnóstico & Auto-Healing)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false
$shareRoot    = $null

try {
    # --- 1. Verificar PendingFileRenameOperations ---
    $LogData.Detalhes += "[1/8] Verificando operações pendentes de reboot ..."
    $pending = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
    if ($pending) {
        $LogData.Detalhes += "      !! ATENÇÃO: há arquivos pendentes de reboot na máquina."
    } else {
        $LogData.Detalhes += "      -> Sem pendências críticas."
    }

    # --- 2. Montar compartilhamento de rede ---
    $LogData.Detalhes += "[2/8] Montando compartilhamento $ShareServerPath ..."
    if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    if ($UseContaMaquina) {
        $LogData.Detalhes += "      -> Modo conta-máquina (SYSTEM)"
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareServerPath -Scope Global -ErrorAction Stop
        $driveCreated = $true
        $shareRoot = "${DriveLetter}:"
    } else {
        $LogData.Detalhes += "      -> Modo credencial explícita ($AdminUser)"
        try {
            $secPass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
            $cred    = New-Object System.Management.Automation.PSCredential($AdminUser, $secPass)
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareServerPath -Credential $cred -Scope Global -ErrorAction Stop
            $driveCreated = $true
            $shareRoot = "${DriveLetter}:"
        } catch {
            & cmd.exe /c "net use `"$ShareServerPath`" `"$AdminPass`" /user:`"$AdminUser`" /persistent:no >nul 2>&1"
            if (Test-Path -LiteralPath $ShareServerPath) {
                $shareRoot = $ShareServerPath
                $LogData.Detalhes += "      -> Conectado via sessão UNC direta."
            } else {
                throw "Falha ao autenticar no compartilhamento SMB: $($_.Exception.Message)"
            }
        }
    }

    # Lê o IP do servidor diretamente do zabbix_agent2.conf na rede (se existir)
    $configSource = Join-Path $shareRoot "zabbix_agent2.conf"
    if (Test-Path -LiteralPath $configSource) {
        $confLines = Get-Content -LiteralPath $configSource -ErrorAction SilentlyContinue
        foreach ($line in $confLines) {
            if ($line -match "^\s*Server\s*=\s*([^\r\n#]+)") {
                $ZabbixServer = $matches[1].Trim()
                $ZabbixServerActive = $ZabbixServer
                break
            }
        }
    }

    # --- 3. Limpeza de instalação anterior corrompida (apenas se o serviço não existir) ---
    $svc = Get-Service -Name $ZabbixServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        $LogData.Detalhes += "[3/8] Verificando resíduos de instalações Zabbix anteriores ..."
        $oldProducts = Get-CimInstance -ClassName Win32_Product -Filter "Name LIKE '%Zabbix%'" -ErrorAction SilentlyContinue
        if ($oldProducts) {
            foreach ($p in $oldProducts) {
                $LogData.Detalhes += "      -> Removendo registro órfão: $($p.Name) v$($p.Version)"
                try {
                    $null = Invoke-CimMethod -InputObject $p -MethodName Uninstall -ErrorAction Stop
                    Start-Sleep -Seconds 3
                } catch {
                    $LogData.Detalhes += "      !! Aviso ao remover anterior: $($_.Exception.Message)"
                }
            }
        } else {
            $LogData.Detalhes += "      -> Nenhum resíduo anterior encontrado."
        }

        # --- 4. Copiar e instalar MSI ---
        $LogData.Detalhes += "[4/8] Copiando MSI para disco local ..."
        $msiFile = Get-ChildItem -LiteralPath $shareRoot -Filter "zabbix_agent2*.msi" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $msiFile) { throw "Nenhum zabbix_agent2*.msi encontrado em $ShareServerPath" }
        Copy-Item -LiteralPath $msiFile.FullName -Destination $LocalMsiPath -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> $($msiFile.Name) copiado. Instalando (Server=$ZabbixServer)..."

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
            if (Test-Path -LiteralPath $MsiLogPath) {
                $logTail = Get-Content -LiteralPath $MsiLogPath -Tail 35 -ErrorAction SilentlyContinue
                $LogData.Detalhes += "      === ÚLTIMAS LINHAS DO LOG MSI ==="
                foreach ($linha in $logTail) {
                    $LogData.Detalhes += "        $linha"
                }
                $LogData.Detalhes += "      ================================="
            }
            throw "MSIExec retornou código $($proc.ExitCode)."
        }
        $LogData.Detalhes += "      -> MSI instalado com sucesso."
    } else {
        $LogData.Detalhes += "[3-4/8] Serviço '$ZabbixServiceName' já instalado. Atualizando configuração e serviço..."
    }

    # --- 5. Aplicar zabbix_agent2.conf ---
    $LogData.Detalhes += "[5/8] Aplicando zabbix_agent2.conf ..."
    if (Test-Path -LiteralPath $configSource) {
        if (-not (Test-Path -LiteralPath $ZabbixInstallDir)) {
            New-Item -ItemType Directory -Path $ZabbixInstallDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $configSource -Destination (Join-Path $ZabbixInstallDir "zabbix_agent2.conf") -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> Configuração aplicada (Server=$ZabbixServer)."
    } else {
        $LogData.Detalhes += "      !! zabbix_agent2.conf não encontrado na rede — mantendo configuração do MSI."
    }

    # --- 6. Firewall (TCP 10050) ---
    $LogData.Detalhes += "[6/8] Verificando regra de firewall (TCP $FirewallPort) ..."
    if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $FirewallRuleName `
            -Direction Inbound -Protocol TCP -LocalPort $FirewallPort `
            -Action Allow -Profile Domain,Private -ErrorAction Stop | Out-Null
        $LogData.Detalhes += "      -> Regra TCP $FirewallPort criada."
    } else {
        $LogData.Detalhes += "      -> Regra TCP $FirewallPort já existia."
    }

    # --- 7. Reconstrução de Contadores PerfMon ---
    $LogData.Detalhes += "[7/8] Reconstruindo contadores de desempenho (PerfMon) ..."
    try {
        & "$env:windir\system32\lodctr.exe" /R *>&1 | Out-Null
        & "$env:windir\syswow64\lodctr.exe" /R *>&1 | Out-Null
        & winmgmt /resyncperf *>&1 | Out-Null
        $LogData.Detalhes += "      -> Contadores reconstruídos com sucesso."
    } catch {
        $LogData.Detalhes += "      !! Aviso ao reconstruir contadores: $($_.Exception.Message)"
    }

    # --- 8. Auto-Healing e Restart do Serviço ---
    $LogData.Detalhes += "[8/8] Configurando Auto-Healing e reiniciando serviço ..."
    Set-Service -Name $ZabbixServiceName -StartupType Automatic -ErrorAction Stop
    & sc.exe failure $ZabbixServiceName reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
    Restart-Service -Name $ZabbixServiceName -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    $svcFinal = Get-Service -Name $ZabbixServiceName
    $LogData.Mensagem = "Zabbix Agent 2 operacional (Server: $ZabbixServer | Status: $($svcFinal.Status))."

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    if (Test-Path -LiteralPath $LocalMsiPath) {
        Remove-Item -LiteralPath $LocalMsiPath -Force -ErrorAction SilentlyContinue
    }
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    if (-not $UseContaMaquina) {
        & cmd.exe /c "net use `"$ShareServerPath`" /delete /y >nul 2>&1"
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}