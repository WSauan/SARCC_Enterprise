# Cria/sobrescreve uma tarefa agendada do SARCC no alvo.
# A tarefa roda como SYSTEM (conta-maquina via Kerberos, sem senha no alvo).
#
# Variáveis:
#   {{task_name}}     - nome da tarefa (sem o prefixo SARCC_)
#   {{b64_script}}    - conteúdo do .ps1 codificado em Base64 (UTF-8)
#   {{trigger_type}}  - "Ao Iniciar a Máquina (Boot)" ou "Diariamente (Horário Específico)"
#   {{trigger_time}}  - "HH:mm" (ignorado se trigger_type for Boot)

$TaskName    = '{{task_name}}'
$EncodedScript = '{{b64_script}}'
$TriggerType = '{{trigger_type}}'
$TriggerTime = '{{trigger_time}}'

$LogData = @{
    Script      = "Agendamento ($TaskName)"
    StatusFinal = "SUCESSO"
    Detalhes    = @()
}

try {
    $ScriptDir = "C:\ProgramData\SARCC\Scripts"
    if (-not (Test-Path $ScriptDir)) {
        New-Item -ItemType Directory -Path $ScriptDir -Force | Out-Null
    }
    $ScriptPath = Join-Path $ScriptDir "$TaskName.ps1"

    # Decodifica e grava o script do agendamento
    [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String($EncodedScript)
    ) | Out-File -FilePath $ScriptPath -Encoding UTF8 -Force

    # Remove versão anterior, se existir
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Ação
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

    # Trigger: diário com horário específico OU ao iniciar
    if ($TriggerType -like "*Diariamente*") {
        $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
    } else {
        $Trigger = New-ScheduledTaskTrigger -AtStartup
    }

    # Principal: SYSTEM com privilégios máximos
    $Principal = New-ScheduledTaskPrincipal `
        -UserId "SYSTEM" `
        -LogonType ServiceAccount `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath "\SARCC\" `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Force | Out-Null

    $LogData.Detalhes += "Tarefa '$TaskName' agendada com sucesso!"
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData | ConvertTo-Json -Compress | Write-Output
}