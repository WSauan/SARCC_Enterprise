<#
.SYNOPSIS
    Reset lógico de rede: limpa cache DNS, reseta Winsock e interface IP.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Reset Logico de Rede"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/3] Limpando Cache DNS (ipconfig /flushdns)..."
    $out1 = & ipconfig.exe /flushdns 2>&1
    $LogData.Detalhes += (($out1 | ForEach-Object { $_.ToString().Trim() }) -join " ")

    $LogData.Detalhes += "[2/3] Resetando Winsock Catalog (netsh winsock reset)..."
    $out2 = & netsh.exe winsock reset 2>&1
    $LogData.Detalhes += (($out2 | ForEach-Object { $_.ToString().Trim() }) -join " ")

    $LogData.Detalhes += "[3/3] Resetando Interface IP (netsh int ip reset)..."
    $out3 = & netsh.exe int ip reset 2>&1
    $LogData.Detalhes += (($out3 | ForEach-Object { $_.ToString().Trim() }) -join " ")

    $LogData.Detalhes += "ATENÇÃO: É recomendado reiniciar a máquina para aplicar os resets do Winsock."
    $LogData.Mensagem = "Reset lógico de rede concluído. Reinicie a estação para aplicar totalmente."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha no reset de rede: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}