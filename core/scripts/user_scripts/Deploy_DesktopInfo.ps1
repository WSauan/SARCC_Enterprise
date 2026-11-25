<#
.SYNOPSIS
    Deploy DesktopInfo (versão verbosa): copia para C:\Program Files\DesktopInfo e registra startup.
.NOTES
    - Requer [REQUIRE_CREDENTIALS]: SARCC injeta credenciais em Base64 decodificadas apenas em memória.
    - Fonte: \\hul-vp-imagem-cc\netshared\DesktopInfo\DesktopInfoHUL.exe
    - Registra via HKLM Run key (inicia no próximo logon do usuário).
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
$RemoteSubDir      = "DesktopInfo"
$RemoteExeName     = "DesktopInfoHUL.exe"
$InstallDir        = "C:\Program Files\DesktopInfo"
$InstallExeName    = "DesktopInfoHUL.exe"
$RunKeyPath        = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
$RunKeyName        = "DesktopInfo"
$ProcessMatch      = "DesktopInfo*"

$LogData = @{
    Script      = "Deploy DesktopInfo"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$driveCreated = $false

try {
    $LogData.Detalhes += "[INFO] Alvo: $env:COMPUTERNAME | Usuário atual: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

    # --- [0/6] Preparar sessão SMB e montar drive ---
    $LogData.Detalhes += "[0/6] Montando compartilhamento ..."
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

    $remoteFolder = "${DriveLetter}:\$RemoteSubDir"
    $remoteExe    = Join-Path $remoteFolder $RemoteExeName
    $remoteIni    = Join-Path $remoteFolder "DesktopInfo.ini"

    if (-not (Test-Path -LiteralPath $remoteExe)) {
        throw "Executável '$RemoteExeName' não encontrado em $remoteFolder."
    }
    $LogData.Detalhes += "      -> Fonte OK: $remoteExe"

    # --- [1/6] Encerrar instância anterior ---
    $LogData.Detalhes += "[1/6] Encerrando instância anterior (se houver) ..."
    try {
        $running = Get-Process -Name $ProcessMatch -ErrorAction SilentlyContinue
        if ($running) {
            $running | Stop-Process -Force -ErrorAction Stop
            Start-Sleep -Seconds 2
            $LogData.Detalhes += "      -> $($running.Count) processo(s) encerrado(s)."
        } else {
            $LogData.Detalhes += "      -> Nenhum processo ativo."
        }
    } catch {
        $LogData.Detalhes += "      !! Falha ao encerrar processo anterior: $($_.Exception.Message)"
        throw
    }

    # --- [2/6] Preparar pasta de destino ---
    $LogData.Detalhes += "[2/6] Preparando pasta de instalação ..."
    try {
        if (-not (Test-Path -LiteralPath $InstallDir)) {
            New-Item -ItemType Directory -Path $InstallDir -Force -ErrorAction Stop | Out-Null
        }
        $LogData.Detalhes += "      -> $InstallDir"
    } catch {
        $LogData.Detalhes += "      !! Falha ao criar pasta de destino '$InstallDir': $($_.Exception.Message)"
        throw
    }

    # --- [3/6] Copiar arquivos (exe + ini, se existir) ---
    $LogData.Detalhes += "[3/6] Copiando arquivos ..."
    $localExe = Join-Path $InstallDir $InstallExeName
    try {
        Copy-Item -LiteralPath $remoteExe -Destination $localExe -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> $RemoteExeName copiado."
    } catch {
        $LogData.Detalhes += "      !! Falha ao copiar '$remoteExe' para '$localExe': $($_.Exception.Message)"
        throw
    }

    if (Test-Path -LiteralPath $remoteIni) {
        try {
            $localIni = Join-Path $InstallDir "DesktopInfo.ini"
            Copy-Item -LiteralPath $remoteIni -Destination $localIni -Force -ErrorAction Stop
            $LogData.Detalhes += "      -> DesktopInfo.ini copiado."
        } catch {
            $LogData.Detalhes += "      !! Falha ao copiar DesktopInfo.ini: $($_.Exception.Message)"
            throw
        }
    } else {
        $LogData.Detalhes += "      -> (sem .ini na pasta de origem; usando defaults)"
    }

    # --- [4/6] Registrar startup no registro ---
    $LogData.Detalhes += "[4/6] Registrando startup no HKLM Run ..."
    $runValue = "`"$localExe`""
    try {
        Set-ItemProperty -Path $RunKeyPath -Name $RunKeyName -Value $runValue -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> $RunKeyName = $runValue"
    } catch {
        $LogData.Detalhes += "      !! Falha ao gravar chave de registro '$RunKeyPath': $($_.Exception.Message)"
        throw
    }

    # --- [5/6] Iniciar imediatamente (se possível) ---
    $LogData.Detalhes += "[5/6] Tentando iniciar agora ..."
    try {
        Start-Process -FilePath $localExe -ErrorAction Stop
        Start-Sleep -Seconds 3
        $LogData.Detalhes += "      -> Processo disparado (pode aparecer apenas no próximo logon via WinRM)."
    } catch {
        $LogData.Detalhes += "      !! Falha ao iniciar agora: $($_.Exception.Message)"
    }

    # --- [6/6] Verificação final ---
    $LogData.Detalhes += "[6/6] Verificando ..."
    $final = Get-Process -Name $ProcessMatch -ErrorAction SilentlyContinue
    $runKeyOk = (Get-ItemProperty -Path $RunKeyPath -Name $RunKeyName -ErrorAction SilentlyContinue).$RunKeyName

    if ($runKeyOk -and (Test-Path -LiteralPath $localExe)) {
        $statusProcesso = if ($final) { "rodando (PID $($final.Id -join ','))" } else { "aguardando próximo logon" }
        $LogData.Mensagem = "DesktopInfo instalado. Processo: $statusProcesso. Startup: registrado."
    } else {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Instalação incompleta — verificar Run key e arquivo local."
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