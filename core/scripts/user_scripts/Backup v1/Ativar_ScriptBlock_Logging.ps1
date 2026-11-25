<#
.SYNOPSIS
    Ativa "Turn on PowerShell Script Block Logging".
    Logs em: Event Viewer > Microsoft-Windows-PowerShell/Operational
#>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LogData = @{
    Script      = "Ativar Script Block Logging"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $regPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
    if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }
    Set-ItemProperty -Path $regPath -Name "EnableScriptBlockLogging" -Value 1 -Type DWord -Force

    $check = (Get-ItemProperty -Path $regPath -Name EnableScriptBlockLogging -ErrorAction SilentlyContinue).EnableScriptBlockLogging
    $LogData.Detalhes += "EnableScriptBlockLogging = $check (esperado: 1)"
    $LogData.Mensagem = "Script Block Logging ativado. Logs em Event Viewer > Microsoft-Windows-PowerShell/Operational."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}