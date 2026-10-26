<#
.SYNOPSIS
    Define ExecutionPolicy=RemoteSigned no LocalMachine.
    Equivale à política GPO "Turn on Script Execution: Allow local scripts and remote signed scripts".
#>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LogData = @{
    Script      = "Configurar ExecutionPolicy"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -ErrorAction Stop

    $current = Get-ExecutionPolicy -Scope LocalMachine
    $LogData.Detalhes += "ExecutionPolicy (LocalMachine) = $current"
    $LogData.Mensagem = "ExecutionPolicy definida para RemoteSigned."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}