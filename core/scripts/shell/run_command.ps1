<#
.SYNOPSIS
    Motor de execução do Terminal Interativo (Shell Remoto).
#>
$ErrorActionPreference = 'Continue'

$OutputEncoding = [System.Text.Encoding]::UTF8
[System.Console]::InputEncoding = [System.Text.Encoding]::UTF8

# Comandos nativos do Windows escrevem na Code Page OEM do sistema, não em UTF-8.
# Forçar a leitura da Code Page correta evita quebras de acentuação no retorno.
try {
    $oemCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding($oemCP)
} catch {
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(850)
}

$CmdB64 = "{{command_b64}}"

try {
    $bytes = [System.Convert]::FromBase64String($CmdB64)
    $CmdDecoded = [System.Text.Encoding]::UTF8.GetString($bytes)
    
    # Executa o comando arbitrário e converte a saída estruturada para texto puro
    Invoke-Expression $CmdDecoded | Out-String
} catch {
    Write-Output "SARCC_SHELL_ERROR: $($_.Exception.Message)"
}