<#
.SYNOPSIS
    Lista tarefas do SARCC com telemetria rica.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$tasks = Get-ScheduledTask -TaskPath "\" | Where-Object { $_.TaskName -match '^SARCC_' }
$result = @()

foreach ($t in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -ErrorAction SilentlyContinue
    
    $triggerStr = "Desconhecido"
    if ($t.Triggers.Count -gt 0) {
        $trig = $t.Triggers[0]
        $trClass = $trig.CimClass.CimClassName
        
        if ($trClass -match "BootTrigger") { $triggerStr = "Ao iniciar a máquina" }
        elseif ($trClass -match "LogonTrigger") { $triggerStr = "Ao fazer logon" }
        elseif ($trClass -match "TimeTrigger") { $triggerStr = "Uma vez" }
        elseif ($trClass -match "DailyTrigger") { $triggerStr = "Diariamente" }
        elseif ($trClass -match "WeeklyTrigger") { $triggerStr = "Semanalmente" }
        elseif ($trClass -match "EventTrigger") { $triggerStr = "Por Evento" }
    }

    $result += [PSCustomObject]@{
        TaskName = $t.TaskName
        Status   = $t.State.ToString()
        Trigger  = $triggerStr
        NextRun  = if ($info.NextRunTime) { $info.NextRunTime.ToString('dd/MM/yyyy HH:mm:ss') } else { "N/A" }
        LastRun  = if ($info.LastRunTime) { $info.LastRunTime.ToString('dd/MM/yyyy HH:mm:ss') } else { "N/A" }
    }
}

@{ Tasks = $result } | ConvertTo-Json -Compress