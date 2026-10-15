$LogData = @{ Script = "Ativar Wake-on-LAN (OS)"; Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Computador = $env:COMPUTERNAME; StatusFinal = "SUCESSO"; Detalhes = @() }

try {
    $LogData.Detalhes += "Habilitando Magic Packet nos adaptadores de rede físicos..."
    # A palavra 'Enabled' foi removida, usando apenas a chave de ativação
    Enable-NetAdapterPowerManagement -Name "*" -WakeOnMagicPacket -ErrorAction Stop
    $LogData.Mensagem = "Wake-on-LAN ativado nas propriedades avançadas das Placas de Rede."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha ao ativar: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}