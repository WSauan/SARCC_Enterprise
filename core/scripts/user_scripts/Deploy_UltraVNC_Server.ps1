<#
.SYNOPSIS
    Deploy UltraVNC Server (Stealth - versão verbosa) com credenciais seguras via New-PSDrive.
.NOTES
    - Requer [REQUIRE_CREDENTIALS]: SARCC injeta credenciais em Base64 decodificadas apenas em memória.
    - Não usa net use com senha em cmdline.
    - Copia instalador para temp local antes de executar.
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

$ShareServerPath  = "{{share_root}}"
$DriveLetter      = "Z"
$VncInstallDir    = "$env:ProgramFiles\uvnc bvba\UltraVNC"
$VncExeLocal      = Join-Path $VncInstallDir "winvnc.exe"
$VncProgramData   = "$env:ProgramData\UltraVNC"
$LocalTempDir     = "C:\Windows\Temp"
$FirewallRuleName = "Suporte TI - UltraVNC Server"
$FirewallPort     = 5900

$RemoteInstaller  = "UltraVNC.exe"
$RemoteInf        = "uvnc_install.inf"
$RemoteIni        = "ultravnc.ini"
$RemoteAcl        = "mslogon.acl"

$LocalInstaller   = Join-Path $LocalTempDir "UltraVNC_Deploy.exe"
$LocalInf         = Join-Path $LocalTempDir "uvnc_install.inf"

$LogData = @{
    Script      = "Deploy UltraVNC Server (Stealth)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false

try {
    $LogData.Detalhes += "[INFO] Alvo: $env:COMPUTERNAME | Usuário atual: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

    # --- [0/8] Limpeza de resíduos ---
    $LogData.Detalhes += "[0/8] Encerrando servicos/processos VNC zumbis ..."
    try {
        Stop-Process -Name "winvnc"    -Force -ErrorAction SilentlyContinue
        Stop-Process -Name "vncviewer" -Force -ErrorAction SilentlyContinue
    } catch {
        $LogData.Detalhes += "      -> Aviso ao encerrar processos VNC: $($_.Exception.Message)"
    }

    $ghostSvc = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
    if ($ghostSvc) {
        try {
            Stop-Service -Name "uvnc_service" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            & sc.exe delete "uvnc_service" | Out-Null
            $LogData.Detalhes += "      -> uvnc_service anterior removido."
        } catch {
            $LogData.Detalhes += "      !! Falha ao remover uvnc_service anterior: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      -> Sem servico anterior."
    }
    Start-Sleep -Seconds 1

    # --- [1/8] Montar compartilhamento com credencial segura ---
    $LogData.Detalhes += "[1/8] Montando compartilhamento com credencial segura ..."
    try {
        if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
            Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
            $LogData.Detalhes += "      -> PSDrive '$DriveLetter:' anterior removido."
        }
        & cmd.exe /c "net use {{share_root}} /delete /y >nul 2>&1"
        & cmd.exe /c "net use {{server_root}}\C$ /delete /y >nul 2>&1"
    } catch {
        $LogData.Detalhes += "      -> Aviso ao limpar sessão SMB prévia: $($_.Exception.Message)"
    }

    if ($UseContaMaquina) {
        $LogData.Detalhes += "[+] Modo conta-máquina (SYSTEM)"
        try {
            $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                                -Root $ShareServerPath `
                                -Scope Global -ErrorAction Stop
        } catch {
            $LogData.Detalhes += "      !! Falha New-PSDrive conta-máquina: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "[+] Modo credencial explícita ($AdminUser)"
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

    if (-not (Test-Path -LiteralPath $shareRoot)) {
        throw "Drive mapeado mas inacessivel. Verifique credenciais ou SMB (445)."
    }
    $LogData.Detalhes += "      -> Acesso autenticado em $shareRoot"

    # --- [2/8] Copiar instalador (+inf) para temp local ---
    $LogData.Detalhes += "[2/8] Copiando instalador para disco local ..."
    $remoteInstaller = Join-Path $shareRoot $RemoteInstaller
    if (-not (Test-Path -LiteralPath $remoteInstaller)) {
        throw "Instalador '$RemoteInstaller' nao encontrado em $ShareServerPath."
    }
    try {
        Copy-Item -LiteralPath $remoteInstaller -Destination $LocalInstaller -Force -ErrorAction Stop
    } catch {
        $LogData.Detalhes += "      !! Falha ao copiar instalador '$remoteInstaller': $($_.Exception.Message)"
        throw
    }

    $remoteInf = Join-Path $shareRoot $RemoteInf
    if (Test-Path -LiteralPath $remoteInf) {
        try {
            Copy-Item -LiteralPath $remoteInf -Destination $LocalInf -Force -ErrorAction Stop
            $LogData.Detalhes += "      -> $RemoteInstaller + $RemoteInf copiados."
        } catch {
            $LogData.Detalhes += "      !! Falha ao copiar '$remoteInf': $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      -> $RemoteInstaller copiado (sem .inf — usando defaults)."
    }

    # --- [3/8] Instalação silenciosa (com log verbose) ---
    $LogData.Detalhes += "[3/8] Executando instalacao silenciosa (com log) ..."
    $InnoLog = Join-Path $LocalTempDir "ultravnc_install.log"
    try { Remove-Item -LiteralPath $InnoLog -Force -ErrorAction SilentlyContinue } catch { }

    $argList = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$InnoLog`" /DIR=`"$VncInstallDir`""
    if (Test-Path -LiteralPath $LocalInf) {
        $argList = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOADINF=`"$LocalInf`" /LOG=`"$InnoLog`" /DIR=`"$VncInstallDir`""
    }
    $proc = Start-Process -FilePath $LocalInstaller -ArgumentList $argList -Wait -PassThru -NoNewWindow -ErrorAction Stop
    $LogData.Detalhes += "      -> Instalador retornou codigo $($proc.ExitCode)."

    if ($proc.ExitCode -notin @(0, 3010)) {
        if (Test-Path -LiteralPath $InnoLog) {
            $logTail = Get-Content -LiteralPath $InnoLog -Tail 40 -ErrorAction SilentlyContinue
            $LogData.Detalhes += "      === ULTIMAS LINHAS DO LOG INNO ==="
            foreach ($l in $logTail) { $LogData.Detalhes += "        $l" }
            $LogData.Detalhes += "      =================================="
        }
        throw "Falha na instalacao do EXE (Cod: $($proc.ExitCode))."
    }

    # --- [4/8] Modo Stealth ---
    $LogData.Detalhes += "[4/8] Aplicando modo stealth ..."
    $startMenu = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\UltraVNC"
    if (Test-Path -LiteralPath $startMenu) {
        try {
            Remove-Item -LiteralPath $startMenu -Recurse -Force -ErrorAction Stop
            $LogData.Detalhes += "      -> Atalhos do Menu Iniciar removidos."
        } catch {
            $LogData.Detalhes += "      -> Aviso ao remover atalhos do Menu Iniciar: $($_.Exception.Message)"
        }
    }
    $viewerPath = Join-Path $VncInstallDir "vncviewer.exe"
    if (Test-Path -LiteralPath $viewerPath) {
        try {
            Remove-Item -LiteralPath $viewerPath -Force -ErrorAction Stop
            $LogData.Detalhes += "      -> vncviewer.exe removido (server-only)."
        } catch {
            $LogData.Detalhes += "      -> Aviso ao remover vncviewer.exe: $($_.Exception.Message)"
        }
    }

    # --- [5/8] Configuração (.ini + .acl) ---
    $LogData.Detalhes += "[5/8] Aplicando configuracao (.ini / .acl) ..."
    try {
        if (-not (Test-Path -LiteralPath $VncProgramData)) {
            New-Item -ItemType Directory -Path $VncProgramData -Force -ErrorAction Stop | Out-Null
        }
    } catch {
        $LogData.Detalhes += "      !! Falha ao criar pasta '$VncProgramData': $($_.Exception.Message)"
        throw
    }

    $remoteIni = Join-Path $shareRoot $RemoteIni
    if (Test-Path -LiteralPath $remoteIni) {
        try {
            Copy-Item -LiteralPath $remoteIni `
                      -Destination (Join-Path $VncProgramData "ultravnc.ini") -Force -ErrorAction Stop
            Copy-Item -LiteralPath $remoteIni `
                      -Destination (Join-Path $VncInstallDir "ultravnc.ini") -Force -ErrorAction SilentlyContinue
            $LogData.Detalhes += "      -> ultravnc.ini aplicado."
        } catch {
            $LogData.Detalhes += "      !! Falha ao aplicar ultravnc.ini: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      -> ultravnc.ini nao encontrado na rede."
    }

    $remoteAcl = Join-Path $shareRoot $RemoteAcl
    if (Test-Path -LiteralPath $remoteAcl) {
        try {
            Copy-Item -LiteralPath $remoteAcl `
                      -Destination (Join-Path $VncProgramData "mslogon.acl") -Force -ErrorAction Stop
            $aclTool = Join-Path $VncInstallDir "MSLogonACL.exe"
            if (Test-Path -LiteralPath $aclTool) {
                & $aclTool /i /o "$VncProgramData\mslogon.acl" | Out-Null
                $LogData.Detalhes += "      -> ACL importada."
            }
        } catch {
            $LogData.Detalhes += "      !! Falha ao aplicar/importar ACL: $($_.Exception.Message)"
            throw
        }
    }

    # --- [6/8] Firewall ---
    $LogData.Detalhes += "[6/8] Verificando regra de firewall ..."
    try {
        if (-not (Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $FirewallRuleName `
                -Direction Inbound -LocalPort $FirewallPort `
                -Protocol TCP -Action Allow `
                -Profile Domain,Private -ErrorAction Stop | Out-Null
            $LogData.Detalhes += "      -> Regra TCP $FirewallPort criada."
        } else {
            $LogData.Detalhes += "      -> Regra ja existia."
        }
    } catch {
        $LogData.Detalhes += "      !! Falha ao configurar regra de firewall: $($_.Exception.Message)"
        throw
    }

    # --- [7/8] Instalar serviço ---
    $LogData.Detalhes += "[7/8] Instalando servico uvnc_service ..."
    if (-not (Test-Path -LiteralPath $VncExeLocal)) {
        throw "winvnc.exe nao encontrado em $VncInstallDir apos instalacao."
    }
    try {
        & $VncExeLocal -install | Out-Null
        Start-Sleep -Seconds 3

        $vncService = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
        if ($vncService) {
            Restart-Service -Name "uvnc_service" -Force -ErrorAction Stop
            Start-Sleep -Seconds 2
            $final = Get-Service -Name "uvnc_service" -ErrorAction Stop
            $LogData.Detalhes += "      -> Servico ativo. Status: $($final.Status)"
        } else {
            throw "Servico uvnc_service nao foi criado."
        }
    } catch {
        $LogData.Detalhes += "      !! Falha ao instalar/iniciar uvnc_service: $($_.Exception.Message)"
        throw
    }

    # --- [8/8] Validação final ---
    $LogData.Detalhes += "[8/8] Validacao final ..."
    $svcCheck = Get-Service -Name "uvnc_service" -ErrorAction SilentlyContinue
    if ($svcCheck -and $svcCheck.Status -eq 'Running') {
        $LogData.Mensagem = "UltraVNC instalado e rodando. Porta $FirewallPort disponivel."
    } else {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Instalado, mas servico esta em estado '$($svcCheck.Status)'."
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