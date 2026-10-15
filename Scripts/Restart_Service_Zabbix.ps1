<#
.SYNOPSIS
    Reinicia o serviço Zabbix Agent remotamente e retorna JSON.
#>
$LogData = @{
    Script = "Restart Zabbix"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Mensagem = ""
}

try {
    $NomesPossiveis = @("Zabbix Agent 2", "Zabbix Agent")
    $ServicoEncontrado = $null

    foreach ($nome in $NomesPossiveis) {
        $serv = Get-CimInstance -ClassName Win32_Service -Filter "Name='$nome'" -ErrorAction SilentlyContinue
        if ($serv) { $ServicoEncontrado = $serv; break }
    }

    if (-not $ServicoEncontrado) { throw "Nenhum serviço Zabbix encontrado na máquina." }

    Invoke-CimMethod -InputObject $ServicoEncontrado -MethodName StopService -ErrorAction Stop | Out-Null
    Start-Sleep -Seconds 2
    
    $servAtualizado = Get-CimInstance -ClassName Win32_Service -Filter "Name='$($ServicoEncontrado.Name)'" -ErrorAction Stop
    Invoke-CimMethod -InputObject $servAtualizado -MethodName StartService -ErrorAction Stop | Out-Null
    Start-Sleep -Seconds 2

    $servFinal = Get-CimInstance -ClassName Win32_Service -Filter "Name='$($ServicoEncontrado.Name)'" -ErrorAction Stop
    $LogData.Mensagem = "Serviço '$($ServicoEncontrado.Name)' reiniciado. Status atual: $($servFinal.State)"

} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}