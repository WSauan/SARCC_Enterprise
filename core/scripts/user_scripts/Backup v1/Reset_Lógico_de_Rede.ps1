$LogData = @{ Script = "Reset Logico de Rede"; Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Computador = $env:COMPUTERNAME; StatusFinal = "SUCESSO"; Detalhes = @() }
try {
    $LogData.Detalhes += "Limpando Cache DNS..."
    $out1 = ipconfig /flushdns 2>&1
    $LogData.Detalhes += ($out1 -join " ")
    
    $LogData.Detalhes += "Resetando Winsock Catalog..."
    $out2 = netsh winsock reset 2>&1
    $LogData.Detalhes += ($out2 -join " ")
    
    $LogData.Detalhes += "Resetando Interface IP..."
    $out3 = netsh int ip reset 2>&1
    $LogData.Detalhes += ($out3 -join " ")
    
    $LogData.Detalhes += "ATENÇÃO: É recomendado reiniciar a máquina para aplicar os resets do Winsock."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}