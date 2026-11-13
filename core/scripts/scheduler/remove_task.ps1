<#
.SYNOPSIS
    Remove múltiplas tarefas agendadas de forma independente e apaga os scripts residuais.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$TaskNamesStr = '{{task_names}}'
$TaskNames = @($TaskNamesStr -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$RemovedCount = 0
$Erros = @()

$LogData = @{
    Script      = "Remover Tarefas Agendadas"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Mensagem    = ""
    Detalhes    = @()
}

foreach ($t in $TaskNames) {
    try {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction Stop
        $ScriptPath = "C:\ProgramData\SARCC\Scripts\$t.ps1"
        if (Test-Path -LiteralPath $ScriptPath) {
            Remove-Item -LiteralPath $ScriptPath -Force -ErrorAction SilentlyContinue
        }
        $RemovedCount++
        $LogData.Detalhes += "Removida: $t"
    } catch {
        $Erros += "$t ($($_.Exception.Message))"
        $LogData.Detalhes += "Falha ao remover '$t': $($_.Exception.Message)"
    }
}

if ($Erros.Count -gt 0 -and $RemovedCount -eq 0) {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao remover tarefa(s): $($Erros -join '; ')"
} elseif ($Erros.Count -gt 0) {
    $LogData.StatusFinal = "ALERTA"
    $LogData.Mensagem = "$RemovedCount tarefa(s) removida(s), mas $($Erros.Count) falharam."
} else {
    $LogData.Mensagem = "$RemovedCount tarefa(s) removida(s) com sucesso."
}

$LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output