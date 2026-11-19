<#
.SYNOPSIS
    Motor de execução do Terminal Interativo (Shell Remoto) com suporte híbrido CP850/OEM -> UTF-8 e largura 4096.
#>
$ErrorActionPreference = 'Continue'

try {
    $bytes = [System.Convert]::FromBase64String("{{command_b64}}")
    $CmdDecoded = [System.Text.Encoding]::UTF8.GetString($bytes)

    $cp850 = try { [System.Text.Encoding]::GetEncoding(850) } catch { [System.Text.Encoding]::Default }
    $utf8  = [System.Text.Encoding]::UTF8

    $isNativeLegacyCmd = ($CmdDecoded -match '(?i)^\s*(ping|ipconfig|arp|nbtstat|tracert|netsh)\b')

    if ($isNativeLegacyCmd) {
        $tmpOut = [System.IO.Path]::GetTempFileName()
        try {
            & cmd.exe /c "$CmdDecoded > `"$tmpOut`" 2>&1"
            if (Test-Path -LiteralPath $tmpOut) {
                $rawBytes = [System.IO.File]::ReadAllBytes($tmpOut)
                $utf8Bytes = [System.Text.Encoding]::Convert($cp850, $utf8, $rawBytes)
                $outputText = $utf8.GetString($utf8Bytes).TrimEnd()
            } else {
                $outputText = ""
            }
        } finally {
            if (Test-Path -LiteralPath $tmpOut) {
                Remove-Item -LiteralPath $tmpOut -Force -ErrorAction SilentlyContinue
            }
        }
    } else {
        try { [Console]::OutputEncoding = $utf8 } catch { }
        try { $OutputEncoding = $utf8 } catch { }

        $outputText = (Invoke-Expression $CmdDecoded 2>&1 | Out-String -Width 4096).TrimEnd()
    }

    if (-not [string]::IsNullOrWhiteSpace($outputText)) {
        Write-Output $outputText
    }
} catch {
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    Write-Output "SARCC_SHELL_ERROR: $($_.Exception.Message)"
}