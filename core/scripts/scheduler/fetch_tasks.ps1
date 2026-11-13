<#
.SYNOPSIS
    Lista tarefas do SARCC filtrando datas vazias/1999 do Windows Task Scheduler.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$tasks = @(Get-ScheduledTask -TaskPath "\" -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match '^SARCC_' })
$result = @()

foreach ($t in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -ErrorAction SilentlyContinue

    $triggerStr = "Desconhecido"
    if ($t.Triggers -and $t.Triggers.Count -gt 0) {
        $trig = $t.Triggers[0]
        $trClass = $trig.CimClass.CimClassName

        if ($trClass -match "BootTrigger")       { $triggerStr = "Ao iniciar a máquina" }
        elseif ($trClass -match "LogonTrigger")  { $triggerStr = "Ao fazer logon" }
        elseif ($trClass -match "TimeTrigger")   { $triggerStr = "Uma vez" }
        elseif ($trClass -match "DailyTrigger")  { $triggerStr = "Diariamente" }
        elseif ($trClass -match "WeeklyTrigger") { $triggerStr = "Semanalmente" }
        elseif ($trClass -match "EventTrigger")  { $triggerStr = "Por Evento" }
    }

    $nextRunStr = "N/A"
    if ($info -and $info.NextRunTime -and $info.NextRunTime.Year -gt 2000) {
        $nextRunStr = $info.NextRunTime.ToString('dd/MM/yyyy HH:mm:ss')
    }

    $lastRunStr = "Nunca executada"
    if ($info -and $info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
        $lastRunStr = $info.LastRunTime.ToString('dd/MM/yyyy HH:mm:ss')
    }

    $result += [PSCustomObject]@{
        TaskName = $t.TaskName
        Status   = $t.State.ToString()
        Trigger  = $triggerStr
        NextRun  = $nextRunStr
        LastRun  = $lastRunStr
    }
}

@{ Tasks = @($result) } | ConvertTo-Json -Depth 4 -Compress | Write-Output