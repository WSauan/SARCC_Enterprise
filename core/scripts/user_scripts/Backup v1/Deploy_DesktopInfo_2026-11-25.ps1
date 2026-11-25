<#
.SYNOPSIS
    Deploy DesktopInfo: copia para C:\Program Files\DesktopInfo e registra startup.
.NOTES
    - Requer [REQUIRE_CREDENTIALS]: SARCC injeta INJECT_USER_AUTO / INJECT_PASS_AUTO
    - Fonte: \\hul-vp-imagem-cc\netshared\DesktopInfo\DesktopInfoHUL.exe
    - Registra via HKLM Run key (inicia no próximo logon do usuário).
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
    # --- [0/6] Montar drive com credencial ---
    $LogData.Detalhes += "[0/6] Montando compartilhamento ..."
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

    $remoteFolder = "${DriveLetter}:\$RemoteSubDir"
    $remoteExe    = Join-Path $remoteFolder $RemoteExeName
    $remoteIni    = Join-Path $remoteFolder "DesktopInfo.ini"

    if (-not (Test-Path -LiteralPath $remoteExe)) {
        throw "Executável '$RemoteExeName' não encontrado em $remoteFolder."
    }
    $LogData.Detalhes += "      -> Fonte OK: $remoteExe"

    # --- [1/6] Encerrar instância anterior ---
    $LogData.Detalhes += "[1/6] Encerrando instância anterior (se houver) ..."
    $running = Get-Process -Name $ProcessMatch -ErrorAction SilentlyContinue
    if ($running) {
        $running | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        $LogData.Detalhes += "      -> $($running.Count) processo(s) encerrado(s)."
    } else {
        $LogData.Detalhes += "      -> Nenhum processo ativo."
    }

    # --- [2/6] Preparar pasta de destino ---
    $LogData.Detalhes += "[2/6] Preparando pasta de instalação ..."
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    $LogData.Detalhes += "      -> $InstallDir"

    # --- [3/6] Copiar arquivos (exe + ini, se existir) ---
    $LogData.Detalhes += "[3/6] Copiando arquivos ..."
    $localExe = Join-Path $InstallDir $InstallExeName
    Copy-Item -LiteralPath $remoteExe -Destination $localExe -Force -ErrorAction Stop
    $LogData.Detalhes += "      -> $RemoteExeName copiado."

    if (Test-Path -LiteralPath $remoteIni) {
        $localIni = Join-Path $InstallDir "DesktopInfo.ini"
        Copy-Item -LiteralPath $remoteIni -Destination $localIni -Force -ErrorAction Stop
        $LogData.Detalhes += "      -> DesktopInfo.ini copiado."
    } else {
        $LogData.Detalhes += "      -> (sem .ini na pasta de origem; usando defaults)"
    }

    # --- [4/6] Registrar startup no registro ---
    $LogData.Detalhes += "[4/6] Registrando startup no HKLM Run ..."
    $runValue = "`"$localExe`""
    Set-ItemProperty -Path $RunKeyPath -Name $RunKeyName -Value $runValue -Force -ErrorAction Stop
    $LogData.Detalhes += "      -> $RunKeyName = $runValue"

    # --- [5/6] Iniciar imediatamente (se possível) ---
    # Nota: via WinRM o processo inicia na Session 0 e pode não aparecer
    # na tela do usuário até o próximo logon. Isso é limitação do WinRM.
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
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    if ($driveCreated) {
        Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
    }
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}