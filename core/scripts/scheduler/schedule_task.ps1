<#
.SYNOPSIS
    Agenda uma tarefa remota usando System (Conta-Máquina) com suporte a bateria e recuperação de falha.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$RawName     = "{{task_name}}".Trim()
$SafeName    = ($RawName -replace '[<>:"/\\|?*]', '_')
$TaskName    = if ($SafeName -match '^SARCC_') { $SafeName } else { "SARCC_$SafeName" }
$TriggerType = "{{trigger_type}}"
$TriggerTime = "{{trigger_time}}"
$TriggerIso  = "{{trigger_iso}}"
$TriggerDays = "{{trigger_days}}"
$ScriptB64   = "{{script_b64}}"

$LogData = @{
    Script      = "Agendar Tarefa ($TaskName)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Mensagem    = ""
    Detalhes    = @()
}

try {
    # 1. Preparar diretório local seguro
    $ScriptDir = "C:\ProgramData\SARCC\Scripts"
    if (-not (Test-Path -LiteralPath $ScriptDir)) {
        $null = New-Item -Path $ScriptDir -ItemType Directory -Force
    }
    $ScriptPath = Join-Path $ScriptDir "$TaskName.ps1"

    # 2. Decodificar Payload Base64 e gravar em UTF-8
    $bytes = [System.Convert]::FromBase64String($ScriptB64)
    $scriptDecoded = [System.Text.Encoding]::UTF8.GetString($bytes)
    [System.IO.File]::WriteAllText($ScriptPath, $scriptDecoded, [System.Text.Encoding]::UTF8)

    # 3. Remover tarefa antiga homônima se existir
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # 4. Criar Gatilho (Trigger) Dinâmico
    $Trigger = $null
    switch ($TriggerType) {
        "Boot"   { $Trigger = New-ScheduledTaskTrigger -AtStartup }
        "Logon"  { $Trigger = New-ScheduledTaskTrigger -AtLogOn }
        "Once"   {
            $dtOnce = [datetime]::Parse($TriggerIso, [System.Globalization.CultureInfo]::InvariantCulture)
            $Trigger = New-ScheduledTaskTrigger -Once -At $dtOnce
        }
        "Daily"  { $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime }
        "Weekly" {
            $daysArray = @($TriggerDays -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $daysArray -At $TriggerTime
        }
        default  { $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime }
    }

    # 5. Criar Ação e Configurações Resilientes (executa mesmo em bateria ou se ligou atrasado)
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
    $Principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    # 6. Registrar no Windows
    $null = Register-ScheduledTask -TaskName $TaskName -Trigger $Trigger -Action $Action -Settings $Settings -Principal $Principal -Force

    $LogData.Mensagem = "Tarefa '$TaskName' agendada com sucesso ($TriggerType)."
    $LogData.Detalhes += "Script salvo em: $ScriptPath"
    $LogData.Detalhes += "Gatilho configurado: $TriggerType ($TriggerTime)"
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao agendar '$TaskName': $($_.Exception.Message)"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}