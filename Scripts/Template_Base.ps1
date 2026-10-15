<#
.SYNOPSIS
    Template Padrão de Execução SARCC v2
#>
$LogData = @{
    Script = "NOME_DO_SCRIPT_AQUI"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes = @()
    Mensagem = ""
}

try {
    # ==============================================================
    # INSIRA SEU CÓDIGO AQUI NO MEIO
    # Sempre use: $LogData.Detalhes += "Seu log" para registrar passos
    # ==============================================================
    
    $LogData.Detalhes += "Iniciando processo..."
    # Exemplo: $out = ipconfig 2>&1
    # $LogData.Detalhes += ($out -join " ")
    
    $LogData.Mensagem = "Rotina finalizada sem erros."
    
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha na execução: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}