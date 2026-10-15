<#
.SYNOPSIS
    Força atualização de políticas de grupo (gpupdate /force) com análise de resultado.
.DESCRIPTION
    - Detecta se a máquina está em domínio antes de tentar
    - Captura saída com encoding correto (CP850)
    - Verifica exit code real do gpupdate
    - Detecta avisos de reboot/logoff pendentes
.NOTES
    - Não requer credenciais.
    - Não reinicia nem faz logoff — apenas aplica as políticas.
#>

# --- Encoding correto (gpupdate.exe retorna em CP850/CP437) ---
$OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $oemCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding($oemCP)
} catch {
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(850)
}

$LogData = @{
    Script      = "Atualização de GPO (gpupdate /force)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    # --- [1/4] Verifica associação ao domínio ---
    $LogData.Detalhes += "[1/4] Verificando associação ao domínio..."
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue

    if (-not $cs -or $cs.PartOfDomain -ne $true) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Máquina não está associada a um domínio. gpupdate não se aplica."
        $LogData.Detalhes += "      -> PartOfDomain = $($cs.PartOfDomain)"
        return
    }
    $LogData.Detalhes += "      -> Domínio: $($cs.Domain)"

    # --- [2/4] Executa gpupdate /force ---
    $LogData.Detalhes += "[2/4] Executando 'gpupdate /force' (pode levar 30-120s)..."

    $startGpu = Get-Date
    $gpoOutput = & gpupdate /force 2>&1 | Out-String
    $exitCode = $LASTEXITCODE
    $elapsed = [math]::Round(((Get-Date) - $startGpu).TotalSeconds, 1)

    $LogData.Detalhes += "      -> Concluído em ${elapsed}s. Código de saída: $exitCode"

    # --- [3/4] Analisa saída ---
    $LogData.Detalhes += "[3/4] Analisando saída do gpupdate:"
    $gpoLines = $gpoOutput -split "`r?`n" | Where-Object { $_.Trim() -ne '' }
    foreach ($linha in $gpoLines) {
        $LogData.Detalhes += "      $linha"
    }

    # Detecta avisos de reboot/logoff pendentes (texto pt-BR e en-US)
    $needsReboot = $gpoOutput -match "(?i)(reinicializa|reiniciar|restart|reboot)"
    $needsLogoff = $gpoOutput -match "(?i)(logoff|fazer logoff|sair e entrar|logon)"

    if ($needsReboot) {
        $LogData.Detalhes += "      ⚠️ ATENÇÃO: Políticas exigem REINICIALIZAÇÃO para aplicar completamente."
    }
    if ($needsLogoff) {
        $LogData.Detalhes += "      ⚠️ ATENÇÃO: Políticas exigem LOGOFF/LOGON para aplicar completamente."
    }

    # --- [4/4] Determina status final baseado em exit code + avisos ---
    if ($exitCode -ne 0) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "gpupdate finalizou com código $exitCode. Verifique os detalhes (pode ser DC inacessível)."
    } elseif ($needsReboot) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Políticas atualizadas com sucesso, mas exigem REINICIALIZAÇÃO para aplicar completamente."
    } elseif ($needsLogoff) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Políticas atualizadas com sucesso, mas exigem LOGOFF/LOGON para aplicar completamente."
    } else {
        $LogData.Mensagem = "Todas as políticas foram atualizadas com sucesso. Nenhum reboot/logoff necessário."
    }

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}