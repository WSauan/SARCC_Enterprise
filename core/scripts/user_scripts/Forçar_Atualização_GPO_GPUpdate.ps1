$LogData = @{ Script = "Atualização de GPO"; Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Computador = $env:COMPUTERNAME; StatusFinal = "SUCESSO"; Detalhes = @() }
try {
    $LogData.Detalhes += "Solicitando atualização forçada de políticas (gpupdate /force)..."
    $gpo = gpupdate /force 2>&1
    $LogData.Detalhes += ($gpo -join " ")
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}