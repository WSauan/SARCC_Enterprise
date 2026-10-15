# Desliga o computador após 15s, com mensagem para o usuário.

$LogData = @{
    Script      = "Ação de Energia (Desligar)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
}

try {
    $LogData.Detalhes += "Disparando comando de Desligar remoto..."
    shutdown.exe /s /t 15 /c "O Suporte de TI esta desligando esta maquina." /f | Out-Null
    $LogData.Detalhes += "Comando enviado com sucesso à camada OS (Kernel)."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}