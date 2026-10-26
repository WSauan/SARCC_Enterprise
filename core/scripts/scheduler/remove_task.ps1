<#
.SYNOPSIS
    Remove múltiplas tarefas e apaga os scripts residuais.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

# Recebe os nomes separados por vírgula e divide-os num Array
$TaskNamesStr = '{{task_names}}'
$TaskNames = $TaskNamesStr -split ","
$Count = 0

try {
    foreach ($TaskName in $TaskNames) {
        $t = $TaskName.Trim()
        if (-not $t) { continue }
        
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction Stop
        
        # Higiene: apaga o script base64 associado
        $ScriptPath = "C:\ProgramData\SARCC\Scripts\$t.ps1"
        if (Test-Path $ScriptPath) { Remove-Item -Path $ScriptPath -Force }
        $Count++
    }
    @{ StatusFinal = "SUCESSO"; Mensagem = "$Count tarefa(s) removida(s) com sucesso." } | ConvertTo-Json -Compress
} catch {
    @{ StatusFinal = "ERRO"; Mensagem = $_.Exception.Message } | ConvertTo-Json -Compress
}