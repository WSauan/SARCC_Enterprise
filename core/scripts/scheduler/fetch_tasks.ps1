# Lista as tarefas do SARCC agendadas no alvo (namespace \SARCC\).
# Sem variáveis.

$tasks = Get-ScheduledTask -TaskPath "\SARCC\" -ErrorAction SilentlyContinue
$list = @()

if ($tasks) {
    foreach ($t in $tasks) {
        $list += [PSCustomObject]@{
            Name  = $t.TaskName
            State = $t.State.ToString()
        }
    }
}

@{ Tarefas = $list } | ConvertTo-Json -Depth 3 -Compress