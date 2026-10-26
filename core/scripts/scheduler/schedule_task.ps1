<#
.SYNOPSIS
    Agenda uma tarefa remota usando System (Conta-Máquina).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$TaskName    = "SARCC_{{task_name}}"
$TriggerType = "{{trigger_type}}" 
$TriggerTime = "{{trigger_time}}" 
$TriggerIso  = "{{trigger_iso}}"
$TriggerDays = "{{trigger_days}}" 
$ScriptB64   = "{{script_b64}}"

try {
    # 1. Preparar a Pasta Invisível
    $ScriptDir = "C:\ProgramData\SARCC\Scripts"
    if (-not (Test-Path $ScriptDir)) { $null = New-Item -Path $ScriptDir -ItemType Directory -Force }
    $ScriptPath = "$ScriptDir\$TaskName.ps1"

    # 2. Descodificar Payload Base64
    $bytes = [System.Convert]::FromBase64String($ScriptB64)
    $scriptDecoded = [System.Text.Encoding]::UTF8.GetString($bytes)
    $scriptDecoded | Out-File -FilePath $ScriptPath -Encoding UTF8 -Force

    # 3. Remover Tarefa Antiga se existir
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # 4. Criar Gatilho (Trigger) Dinâmico
    $Trigger = $null
    switch ($TriggerType) {
        "Boot"   { $Trigger = New-ScheduledTaskTrigger -AtStartup }
        "Logon"  { $Trigger = New-ScheduledTaskTrigger -AtLogOn }
        "Once"   { $Trigger = New-ScheduledTaskTrigger -Once -At $TriggerIso }
        "Daily"  { $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime }
        "Weekly" { 
            $daysArray = $TriggerDays -split ","
            $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $daysArray -At $TriggerTime
        }
        default  { $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime }
    }

    # 5. Criar Ação Invisível
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

    # 6. Rodar como SYSTEM (Nível Máximo, Acesso de Rede com Conta-Máquina)
    $Principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    # 7. Registar no Windows
    $null = Register-ScheduledTask -TaskName $TaskName -Trigger $Trigger -Action $Action -Principal $Principal -Force

    @{ StatusFinal = "SUCESSO"; Mensagem = "Tarefa '$TaskName' agendada para: $TriggerType" } | ConvertTo-Json -Compress
} catch {
    @{ StatusFinal = "ERRO"; Mensagem = $_.Exception.Message } | ConvertTo-Json -Compress
}