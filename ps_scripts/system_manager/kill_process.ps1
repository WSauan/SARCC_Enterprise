# Encerra um processo à força.
# Variáveis: {{pid}}, {{nome}}

$targetPid = [int]'{{pid}}'
$targetName = '{{nome}}'

$LogData = @{
    Script      = "Ação de Processo (Kill)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @(
        "Alvo: Processo '$targetName' (PID: $targetPid)",
        "Comando executado: Stop-Process -Id $targetPid -Force"
    )
    Mensagem = "O processo '$targetName' (PID: $targetPid) foi encerrado com sucesso à força."
}

try {
    Stop-Process -Id $targetPid -Force -ErrorAction Stop
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao encerrar processo '$targetName' (PID $targetPid): $($_.Exception.Message)"
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
}