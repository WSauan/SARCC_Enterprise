<#
.SYNOPSIS
    Reparo e Deploy Automatizado de Agentes Corporativos (Zabbix Agent 2, UltraVNC, GLPI Agent, DesktopInfo ou Todos).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$AgentTarget     = "{{agent_target}}".Trim().ToLower()
$ShareServerPath = "\\hul-vp-imagem-cc\netshared"
$DriveLetter     = "Z"
$LocalTempDir    = "C:\Windows\Temp"

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

$LogData = @{
    Script      = "Reparo/Deploy de Agente ($AgentTarget)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false
$shareRoot    = $null

function Mount-SarccShare {
    if ($script:shareRoot) { return $script:shareRoot }

    if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }

    if ($UseContaMaquina) {
        $LogData.Detalhes += "[Rede] Montando share em modo Conta-Máquina (SYSTEM)..."
        $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareServerPath -Scope Global -ErrorAction Stop
        $script:driveCreated = $true
        $script:shareRoot = "${DriveLetter}:"
    } else {
        $LogData.Detalhes += "[Rede] Autenticando em $ShareServerPath com credencial ($AdminUser)..."
        try {
            $secPass = ConvertTo-SecureString $AdminPass -AsPlainText -Force
            $cred    = New-Object System.Management.Automation.PSCredential($AdminUser, $secPass)
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem -Root $ShareServerPath -Credential $cred -Scope Global -ErrorAction Stop
            $script:driveCreated = $true
            $script:shareRoot = "${DriveLetter}:"
        } catch {
            & cmd.exe /c "net use `"$ShareServerPath`" `"$AdminPass`" /user:`"$AdminUser`" /persistent:no >nul 2>&1"
            if (Test-Path -LiteralPath $ShareServerPath) {
                $script:shareRoot = $ShareServerPath
            } else {
                throw "Falha ao acessar $ShareServerPath via SMB (445): $($_.Exception.Message)"
            }
        }
    }
    return $script:shareRoot
}

function Repair-ZabbixAgent {
    $LogData.Detalhes += "=== [ZABBIX AGENT 2] Iniciando verificação e reparo ==="
    $ZabbixServiceName = "Zabbix Agent 2"
    $ZabbixInstallDir  = "C:\Program Files\Zabbix Agent 2"
    $FirewallRuleName  = "Zabbix Agent 2"
    $FirewallPort      = 10050

    $root = Mount-SarccShare
    $configSource = Join-Path $root "zabbix_agent2.conf"

    # IP oficial do servidor Zabbix HUL (lê do .conf se disponível)
    $ZabbixServer = "10.8.245.12"
    if (Test-Path -LiteralPath $configSource) {
        $confLines = Get-Content -LiteralPath $configSource -ErrorAction SilentlyContinue
        foreach ($line in $confLines) {
            if ($line -match "^\s*Server\s*=\s*([^\r\n#]+)") {
                $ZabbixServer = $matches[1].Trim()
                break
            }
        }
    }

    $svc = Get-Service -Name $ZabbixServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        $LogData.Detalhes += "-> Serviço não encontrado. Instalando MSI a partir da rede (Server=$ZabbixServer)..."
        $msiFile = Get-ChildItem -LiteralPath $root -Filter "zabbix_agent2*.msi" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $msiFile) { throw "Instalador zabbix_agent2*.msi não encontrado em $ShareServerPath" }

        $LocalMsiPath = Join-Path $LocalTempDir "zabbix_agent2_deploy.msi"
        $MsiLogPath   = Join-Path $LocalTempDir "zabbix_install.log"
        Copy-Item -LiteralPath $msiFile.FullName -Destination $LocalMsiPath -Force -ErrorAction Stop

        $msiArgs = @(
            "/i", "`"$LocalMsiPath`"",
            "/qn", "/norestart",
            "/l*v", "`"$MsiLogPath`"",
            "SERVER=`"$ZabbixServer`"",
            "SERVERACTIVE=`"$ZabbixServer`"",
            "HOSTNAME=`"$env:COMPUTERNAME`"",
            "ALLUSERS=1", "REBOOT=R"
        ) -join " "

        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow
        Remove-Item -LiteralPath $LocalMsiPath -Force -ErrorAction SilentlyContinue
        if ($proc.ExitCode -notin @(0, 3010)) {
            throw "Falha no MSI do Zabbix (Código $($proc.ExitCode))."
        }
        $LogData.Detalhes += "-> MSI do Zabbix instalado com sucesso."
    } else {
        $LogData.Detalhes += "-> Serviço já instalado (Status atual: $($svc.Status)). Atualizando configuração..."
    }

    if (Test-Path -LiteralPath $configSource) {
        if (-not (Test-Path -LiteralPath $ZabbixInstallDir)) {
            New-Item -ItemType Directory -Path $ZabbixInstallDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $configSource -Destination (Join-Path $ZabbixInstallDir "zabbix_agent2.conf") -Force -ErrorAction Stop
        $LogData.Detalhes += "-> Arquivo zabbix_agent2.conf sincronizado (Server=$ZabbixServer)."
    }

    if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Protocol TCP -LocalPort $FirewallPort -Action Allow -Profile Domain,Private -ErrorAction SilentlyContinue | Out-Null
        $LogData.Detalhes += "-> Regra de Firewall TCP $FirewallPort criada."
    }

    try {
        & "$env:windir\system32\lodctr.exe" /R *>&1 | Out-Null
        & "$env:windir\syswow64\lodctr.exe" /R *>&1 | Out-Null
        & winmgmt /resyncperf *>&1 | Out-Null
        $LogData.Detalhes += "-> Contadores de desempenho (PerfMon) ressincronizados."
    } catch { }

    Set-Service -Name $ZabbixServiceName -StartupType Automatic -ErrorAction SilentlyContinue
    & sc.exe failure $ZabbixServiceName reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
    Restart-Service -Name $ZabbixServiceName -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    $finalSvc = Get-Service -Name $ZabbixServiceName -ErrorAction SilentlyContinue
    $LogData.Detalhes += "-> Zabbix Agent 2 finalizado com status: $($finalSvc.Status)"
}

function Repair-UltraVnc {
    $LogData.Detalhes += "=== [ULTRAVNC SERVER] Iniciando verificação e reparo ==="
    $VncInstallDir    = "$env:ProgramFiles\uvnc bvba\UltraVNC"
    $VncExeLocal      = Join-Path $VncInstallDir "winvnc.exe"
    $VncProgramData   = "$env:ProgramData\UltraVNC"
    $FirewallRuleName = "Suporte TI - UltraVNC Server"
    $FirewallPort     = 5900

    $root = Mount-SarccShare

    if (-not (Test-Path -LiteralPath $VncExeLocal)) {
        $LogData.Detalhes += "-> UltraVNC não encontrado. Executando instalação Stealth..."
        Stop-Process -Name "winvnc" -Force -ErrorAction SilentlyContinue
        $LocalInstaller = Join-Path $LocalTempDir "UltraVNC_Deploy.exe"
        $LocalInf       = Join-Path $LocalTempDir "uvnc_install.inf"

        $remoteInstaller = Join-Path $root "UltraVNC.exe"
        if (-not (Test-Path -LiteralPath $remoteInstaller)) {
            throw "UltraVNC.exe não encontrado em $ShareServerPath"
        }
        Copy-Item -LiteralPath $remoteInstaller -Destination $LocalInstaller -Force -ErrorAction Stop

        $remoteInf = Join-Path $root "uvnc_install.inf"
        $argList = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /COMPONENTS=`"server,server\service`" /DIR=`"$VncInstallDir`""
        if (Test-Path -LiteralPath $remoteInf) {
            Copy-Item -LiteralPath $remoteInf -Destination $LocalInf -Force -ErrorAction Stop
            $argList = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOADINF=`"$LocalInf`" /DIR=`"$VncInstallDir`""
        }

        $proc = Start-Process -FilePath $LocalInstaller -ArgumentList $argList -Wait -PassThru -NoNewWindow
        Remove-Item -LiteralPath $LocalInstaller -Force -ErrorAction SilentlyContinue
        if ($proc.ExitCode -notin @(0, 3010)) {
            throw "Falha na instalação do UltraVNC (Código $($proc.ExitCode))."
        }
    }

    $startMenu = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\UltraVNC"
    if (Test-Path -LiteralPath $startMenu) {
        Remove-Item -LiteralPath $startMenu -Recurse -Force -ErrorAction SilentlyContinue
    }
    $viewerPath = Join-Path $VncInstallDir "vncviewer.exe"
    if (Test-Path -LiteralPath $viewerPath) {
        Remove-Item -LiteralPath $viewerPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $VncProgramData)) {
        New-Item -ItemType Directory -Path $VncProgramData -Force | Out-Null
    }

    $remoteIni = Join-Path $root "ultravnc.ini"
    if (Test-Path -LiteralPath $remoteIni) {
        Copy-Item -LiteralPath $remoteIni -Destination (Join-Path $VncProgramData "ultravnc.ini") -Force -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath $remoteIni -Destination (Join-Path $VncInstallDir "ultravnc.ini") -Force -ErrorAction SilentlyContinue
        $LogData.Detalhes += "-> ultravnc.ini aplicado em ProgramData e Program Files."
    }

    $remoteAcl = Join-Path $root "mslogon.acl"
    if (Test-Path -LiteralPath $remoteAcl) {
        Copy-Item -LiteralPath $remoteAcl -Destination (Join-Path $VncProgramData "mslogon.acl") -Force -ErrorAction SilentlyContinue
        $aclTool = Join-Path $VncInstallDir "MSLogonACL.exe"
        if (Test-Path -LiteralPath $aclTool) {
            & $aclTool /i /o "$VncProgramData\mslogon.acl" | Out-Null
            $LogData.Detalhes += "-> Permissões MSLogonACL aplicadas."
        }
    }

    if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -LocalPort $FirewallPort -Protocol TCP -Action Allow -Profile Domain,Private -ErrorAction SilentlyContinue | Out-Null
    }

    $vncService = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
    if (-not $vncService -and (Test-Path -LiteralPath $VncExeLocal)) {
        & $VncExeLocal -install | Out-Null
        Start-Sleep -Seconds 2
    }

    Set-Service -Name "uvnc_service" -StartupType Automatic -ErrorAction SilentlyContinue
    Restart-Service -Name "uvnc_service" -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    $finalVnc = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
    $LogData.Detalhes += "-> UltraVNC finalizado com status: $($finalVnc.Status)"
}

function Repair-GlpiAgent {
    $LogData.Detalhes += "=== [GLPI AGENT] Iniciando verificação e sincronização ==="
    $ServerUrl         = "https://chamados.hul-ufs.ebserh/front/inventory.php"
    $OAuthClientId     = "c71e449337c73c0457245268e55e3143c623c3e8a7534d4a1e755cbd18743d1a"
    $OAuthClientSecret = "3fcba97de33697cf59dd2b862b49a8907594b10172c8a6d89905542a6306c300"
    $RegPath           = "HKLM:\SOFTWARE\GLPI-Agent"
    $AgentBatPath      = "C:\Program Files\GLPI-Agent\glpi-agent.bat"
    $ServiceName       = "glpi-agent"

    if (-not (Test-Path $RegPath)) { New-Item -Path $RegPath -Force | Out-Null }
    Set-ItemProperty -Path $RegPath -Name "server"              -Value $ServerUrl         -Type String
    Set-ItemProperty -Path $RegPath -Name "authentication"      -Value "oauth"            -Type String
    Set-ItemProperty -Path $RegPath -Name "oauth-client-id"     -Value $OAuthClientId     -Type String
    Set-ItemProperty -Path $RegPath -Name "oauth-client-secret" -Value $OAuthClientSecret -Type String
    Set-ItemProperty -Path $RegPath -Name "no-ssl-check"        -Value "1"                -Type String

    if (-not (Test-Path -LiteralPath $AgentBatPath)) {
        $LogData.Detalhes += "-> GLPI Agent ausente. Instalando via MSI da rede..."
        $root = Mount-SarccShare
        $msiFile = Get-ChildItem -LiteralPath $root -Filter "GLPI-Agent*.msi" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $msiFile) { throw "GLPI-Agent*.msi não encontrado em $ShareServerPath" }

        $msiLocal = Join-Path $LocalTempDir $msiFile.Name
        Copy-Item -LiteralPath $msiFile.FullName -Destination $msiLocal -Force -ErrorAction Stop

        $msiArgs = @(
            "/i", "`"$msiLocal`"", "/qn", "/norestart",
            "SERVER=`"$ServerUrl`"", "AUTHENTICATION=`"oauth`"",
            "OAUTH-CLIENT-ID=`"$OAuthClientId`"", "OAUTH-CLIENT-SECRET=`"$OAuthClientSecret`"",
            "NO-SSL-CHECK=`"1`"", "RUNNOW=`"1`""
        ) -join " "

        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow
        Remove-Item -LiteralPath $msiLocal -Force -ErrorAction SilentlyContinue
        if ($proc.ExitCode -notin @(0, 3010)) {
            throw "Falha ao instalar GLPI Agent (Código $($proc.ExitCode))."
        }
    }

    Set-Service -Name $ServiceName -StartupType Automatic -ErrorAction SilentlyContinue
    Restart-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    if (Test-Path -LiteralPath $AgentBatPath) {
        Start-Process -FilePath $AgentBatPath -ArgumentList "--force" -NoNewWindow -Wait -ErrorAction SilentlyContinue
        $LogData.Detalhes += "-> Inventário GLPI forçado e enviado ao servidor."
    }
}

function Repair-DesktopInfo {
    $LogData.Detalhes += "=== [DESKTOP INFO] Iniciando atualização e execução ==="
    $root = Mount-SarccShare
    $remoteFolder = Join-Path $root "DesktopInfo"
    $remoteExe    = Join-Path $remoteFolder "DesktopInfoHUL.exe"
    $remoteIni    = Join-Path $remoteFolder "DesktopInfo.ini"

    $InstallDir   = "C:\Program Files\Desktop Info"
    $LegacyDir    = "C:\Program Files\DesktopInfo"
    $LocalExe     = Join-Path $InstallDir "DesktopInfoHUL.exe"
    $RunKeyPath   = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

    if (-not (Test-Path -LiteralPath $remoteExe)) {
        throw "Executável DesktopInfoHUL.exe não encontrado em $remoteFolder"
    }

    # Encerra instâncias anteriores e limpa pasta duplicada legada
    Get-Process -Name "DesktopInfo*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $LegacyDir) {
        Remove-Item -LiteralPath $LegacyDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    Copy-Item -LiteralPath $remoteExe -Destination $LocalExe -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $remoteIni) {
        Copy-Item -LiteralPath $remoteIni -Destination (Join-Path $InstallDir "DesktopInfo.ini") -Force -ErrorAction SilentlyContinue
    }

    # Registra na chave Run do Registro para iniciar em todos os logons
    Set-ItemProperty -Path $RunKeyPath -Name "DesktopInfo" -Value "`"$LocalExe`"" -Force -ErrorAction SilentlyContinue
    $LogData.Detalhes += "-> Binário copiado para '$InstallDir' e registrado no Startup."

    # Dispara imediatamente na sessão interativa do usuário logado (fura o isolamento da Session 0 do WinRM)
    try {
        $tempTaskName = "SARCC_Launch_DesktopInfo"
        $action = New-ScheduledTaskAction -Execute $LocalExe -WorkingDirectory $InstallDir
        $principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Limited
        Register-ScheduledTask -TaskName $tempTaskName -Action $action -Principal $principal -Force -ErrorAction SilentlyContinue | Out-Null
        Start-ScheduledTask -TaskName $tempTaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Unregister-ScheduledTask -TaskName $tempTaskName -Confirm:$false -ErrorAction SilentlyContinue
        $LogData.Detalhes += "-> DesktopInfo iniciado na sessão do usuário logado."
    } catch { }
}

try {
    switch ($AgentTarget) {
        "zabbix" {
            Repair-ZabbixAgent
            $LogData.Mensagem = "Zabbix Agent 2 reparado e em execução."
        }
        "uvnc" {
            Repair-UltraVnc
            $LogData.Mensagem = "UltraVNC Server reparado e em execução."
        }
        "glpi" {
            Repair-GlpiAgent
            $LogData.Mensagem = "GLPI Agent reparado e inventário sincronizado."
        }
        "desktopinfo" {
            Repair-DesktopInfo
            $LogData.Mensagem = "DesktopInfo atualizado e iniciado na área de trabalho."
        }
        "all" {
            Repair-ZabbixAgent
            Repair-UltraVnc
            Repair-GlpiAgent
            Repair-DesktopInfo
            $LogData.Mensagem = "Todos os agentes (Zabbix, UltraVNC, GLPI e DesktopInfo) foram reparados."
        }
        default {
            throw "Agente desconhecido: $AgentTarget"
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha no reparo ($AgentTarget): $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    if (-not $UseContaMaquina) {
        & cmd.exe /c "net use `"$ShareServerPath`" /delete /y >nul 2>&1"
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}