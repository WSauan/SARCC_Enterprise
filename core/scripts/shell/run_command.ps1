# Executa um comando PowerShell no alvo e devolve a saída como texto puro.
# Variável: {{command}}

$OutputEncoding = [System.Text.Encoding]::UTF8
[System.Console]::InputEncoding = [System.Text.Encoding]::UTF8

# Comandos nativos do Windows (ping.exe, ipconfig, tracert, arp, netstat,
# nslookup, route) escrevem em CP850/CP437 (ANSI/OEM do sistema), NÃO em
# UTF-8, mesmo com chcp 65001. Setamos o Console::OutputEncoding para a
# OEM CP do sistema para que o PowerShell decodifique corretamente.
try {
    $oemCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding($oemCP)
} catch {
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(850)
}

{{command}} | Out-String