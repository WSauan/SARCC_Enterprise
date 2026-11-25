<#
.SYNOPSIS
    Define ExecutionPolicy=RemoteSigned no LocalMachine.
    Equivale à política GPO "Turn on Script Execution: Allow local scripts and remote signed scripts".
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Configurar ExecutionPolicy"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/2] Definindo ExecutionPolicy para RemoteSigned no escopo LocalMachine..."
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -ErrorAction Stop

    $LogData.Detalhes += "[2/2] Validando política aplicada..."
    $current = Get-ExecutionPolicy -Scope LocalMachine -ErrorAction Stop
    $LogData.Detalhes += "      -> ExecutionPolicy (LocalMachine) = $current"
    $LogData.Mensagem = "ExecutionPolicy definida para $current."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha ao configurar ExecutionPolicy: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}