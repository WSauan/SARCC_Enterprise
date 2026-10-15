# Inicia, para ou reinicia um serviço.
# Variáveis: {{svc_name}}, {{action}} (Start|Stop|Restart), {{acao_pt}} (texto PT-BR)
#
# Nota: $action é variável (não literal) porque o cmdlet é composto em runtime
#       via "& "${action}-Service"". Isso mantém o arquivo válido para o parser
#       ANTES da substituição dos placeholders.

$action = '{{action}}'
$svcName = '{{svc_name}}'

$LogData = @{
    Script      = "Ação de Serviço ($action)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @(
        "Alvo: Serviço '$svcName'",
        "Comando executado: ${action}-Service -Name '$svcName' -Force"
    )
    Mensagem = "O serviço '$svcName' foi {{acao_pt}} com sucesso."
}

try {
    & "${action}-Service" -Name $svcName -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    $checkSvc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    $LogData.Detalhes += "Status atual após comando: $($checkSvc.Status)"
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha na ação $action do serviço '$svcName': $($_.Exception.Message)"
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
}