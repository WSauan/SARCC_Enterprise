<#
.SYNOPSIS
    Inicia, para ou reinicia um serviço de forma segura via Base64.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$action = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{action_b64}}'))
$svcName = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{svc_name_b64}}'))
$acaoPt = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{acao_pt_b64}}'))

$LogData = @{
    Script      = "Ação de Serviço ($action)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @(
        "Alvo: Serviço '$svcName'",
        "Comando executado: ${action}-Service -Name '$svcName' -Force"
    )
    Mensagem = "O serviço '$svcName' foi $acaoPt com sucesso."
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