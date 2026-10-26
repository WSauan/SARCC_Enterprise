# Remove uma tarefa agendada do SARCC e o .ps1 associado.
# Variável: {{task_name}}

$TaskName = '{{task_name}}'

$LogData = @{
    Script      = "Remover Agendamento ($TaskName)"
    StatusFinal = "SUCESSO"
    Detalhes    = @()
}

try {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        $LogData.Detalhes += "Tarefa '$TaskName' removida com sucesso."
    } else {
        $LogData.Detalhes += "Tarefa não encontrada."
    }

    $ScriptPath = Join-Path "C:\ProgramData\SARCC\Scripts" "$TaskName.ps1"
    if (Test-Path $ScriptPath) {
        Remove-Item -Path $ScriptPath -Force
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData | ConvertTo-Json -Compress | Write-Output
}