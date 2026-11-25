$LogData = @{ Script = "Auditoria BitLocker"; Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Computador = $env:COMPUTERNAME; StatusFinal = "SUCESSO"; Detalhes = @() }
try {
    $LogData.Detalhes += "Consultando status do volume C:..."
    $bde = manage-bde -status C: 2>&1
    $LogData.Detalhes += ($bde -join "`n")
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}