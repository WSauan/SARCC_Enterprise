<#
.SYNOPSIS
    Motor de execução do Terminal Interativo (Shell Remoto) com suporte híbrido OEM -> UTF-8 e largura 4096.
#>
$ErrorActionPreference = 'Continue'

try {
    $bytes = [System.Convert]::FromBase64String("{{command_b64}}")
    $CmdDecoded = [System.Text.Encoding]::UTF8.GetString($bytes)

    # 1. Usa a Code Page OEM (ex: 850) durante a execução para decodificar utilitários nativos (ping, ipconfig, netsh)
    try {
        $oemCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage
        [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding($oemCP)
    } catch {
        [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(850)
    }

    $outputText = (Invoke-Expression $CmdDecoded 2>&1 | Out-String -Width 4096).TrimEnd()

    # 2. Muda a saída do console para UTF-8 antes de devolver ao Python (evita corromper cmdlets do PowerShell)
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8

    if (-not [string]::IsNullOrWhiteSpace($outputText)) {
        Write-Output $outputText
    }
} catch {
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    Write-Output "SARCC_SHELL_ERROR: $($_.Exception.Message)"
}