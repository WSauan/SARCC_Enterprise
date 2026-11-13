<#
.SYNOPSIS
    Encerra um processo à força (via Base64 para evitar quebras).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$targetPid = [int][System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{pid_b64}}'))
$targetName = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{nome_b64}}'))

$LogData = @{
    Script      = "Ação de Processo (Kill)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @(
        "Alvo: Processo '$targetName' (PID: $targetPid)",
        "Comando executado: Stop-Process -Id $targetPid -Force"
    )
    Mensagem    = "O processo '$targetName' (PID: $targetPid) foi encerrado com sucesso à força."
}

try {
    Stop-Process -Id $targetPid -Force -ErrorAction Stop
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao encerrar processo '$targetName' (PID $targetPid): $($_.Exception.Message)"
    $LogData.Detalhes += "Erro: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
}