# 1. Defina as variáveis da regra
$RuleName = "Suporte TI - UltraVNC Server"
$Port = 5900

try {
    # 2. Execute o comando silenciando a saída com $null ou Out-Null
    # O uso do $null = na frente é a forma mais performática de ocultar a saída no PowerShell
    $null = New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow -ErrorAction Stop

    # 3. Retorne APENAS o que o seu sistema espera. 
    # Se o SARCC exige JSON, construa um objeto customizado e converta:
    $Response = @{
        Status  = "Sucesso"
        Message = "Regra de Firewall criada com sucesso!"
        Target  = $env:COMPUTERNAME
    }
    
    $Response | ConvertTo-Json -Compress

} catch {
    # Tratamento de erro limpo, também retornando em formato JSON
    $ErrorResponse = @{
        Status  = "Erro"
        Message = $_.Exception.Message
        Target  = $env:COMPUTERNAME
    }
    
    $ErrorResponse | ConvertTo-Json -Compress
}