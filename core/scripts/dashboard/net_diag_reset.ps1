<#
.SYNOPSIS
    Executa Reset de Pilha de Rede (DNS/ARP/NetBIOS/DHCP Renew) e testa conectividade com a infraestrutura HUL.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Continue'

$Mode = "{{mode}}".Trim().ToLower()

$LogData = @{
    Script      = "Diagnóstico e Reset de Rede ($Mode)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

function Test-TcpEndpoint([string]$HostTarget, [int]$Port, [int]$TimeoutMs = 1500) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostTarget, $Port, $null, $null)
        $wait = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($wait -and $client.Connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

try {
    if ($Mode -eq "reset_and_diag") {
        $LogData.Detalhes += "=== [ETAPA 1] Limpeza e Renovação de Cache de Rede ==="
        & ipconfig.exe /flushdns *>&1 | Out-Null
        $LogData.Detalhes += "-> Cache DNS limpo (ipconfig /flushdns)."

        & arp.exe -d * *>&1 | Out-Null
        $LogData.Detalhes += "-> Tabela ARP reiniciada (arp -d *)."

        & nbtstat.exe -R *>&1 | Out-Null
        & nbtstat.exe -RR *>&1 | Out-Null
        $LogData.Detalhes += "-> Cache NetBIOS recarregado e registrado (nbtstat -R / -RR)."

        & ipconfig.exe /registerdns *>&1 | Out-Null
        $LogData.Detalhes += "-> Registro dinâmico de DNS disparado (ipconfig /registerdns)."
    }

    $LogData.Detalhes += "=== [ETAPA 2] Teste de Conectividade com Infraestrutura HUL ==="
    $netCfg = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = 'True'" | Select-Object -First 1
    $gw = if ($netCfg -and $netCfg.DefaultIPGateway) { $netCfg.DefaultIPGateway[0] } else { $null }

    $failures = 0

    if ($gw) {
        $gwOk = Test-Connection -ComputerName $gw -Count 1 -Quiet -ErrorAction SilentlyContinue
        $statusGw = if ($gwOk) { "OK (Online)" } else { $failures++; "FALHA (Sem resposta ICMP)" }
        $LogData.Detalhes += "-> Gateway Padrão ($gw): $statusGw"
    }

    $endpoints = @(
        @{ Name = "Zabbix Server";     Host = "10.8.245.12";             Port = 10050 },
        @{ Name = "GLPI Inventory";    Host = "chamados.hul-ufs.ebserh"; Port = 443   },
        @{ Name = "Repositório SMB";   Host = "hul-vp-imagem-cc";        Port = 445   }
    )

    $summaryParts = @()
    foreach ($ep in $endpoints) {
        $ok = Test-TcpEndpoint -HostTarget $ep.Host -Port $ep.Port
        if ($ok) {
            $LogData.Detalhes += "-> $($ep.Name) ($($ep.Host):$($ep.Port)): OK (Conectado)"
            $summaryParts += "$($ep.Name): OK"
        } else {
            $failures++
            $LogData.Detalhes += "-> $($ep.Name) ($($ep.Host):$($ep.Port)): FALHA (Porta $($ep.Port) inacessível)"
            $summaryParts += "$($ep.Name): FALHA"
        }
    }

    if ($failures -gt 0) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Diagnóstico concluído com $failures alerta(s) — " + ($summaryParts -join " | ")
    } else {
        $prefix = if ($Mode -eq "reset_and_diag") { "Cache de rede resetado e todos" } else { "Todos" }
        $LogData.Mensagem = "$prefix os serviços acessíveis (" + ($summaryParts -join " | ") + ")."
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Erro no diagnóstico de rede: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}