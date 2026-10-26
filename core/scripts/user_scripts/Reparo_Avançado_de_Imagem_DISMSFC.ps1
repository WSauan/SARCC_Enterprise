$LogData = @{
    Script = "Reparo Avançado (DISM/SFC)"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes = @()
}
try {
    $LogData.Detalhes += "Iniciando DISM (Cleanup-Image / RestoreHealth)..."
    $dismOut = DISM /Online /Cleanup-Image /RestoreHealth 2>&1
    $LogData.Detalhes += ($dismOut -join " ")
    
    $LogData.Detalhes += "Iniciando SFC (System File Checker)..."
    $sfcOut = sfc /scannow 2>&1
    $LogData.Detalhes += ($sfcOut -join " ")
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha na execução: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}