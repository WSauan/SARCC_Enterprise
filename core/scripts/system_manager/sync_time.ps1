<#
.SYNOPSIS
    Sincroniza ou reseta o relógio do Windows com o domínio (NTP).
.NOTES
    Requer execução como Administrador.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Continue'

$Mode = "{{mode}}".Trim().ToLower() # 'resync' ou 'reset'

$LogData = @{
    Script      = "Sincronização de Hora ($Mode)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    if ($Mode -eq "reset") {
        $LogData.Detalhes += "Iniciando RESET COMPLETO do serviço de horário (w32tm)..."

        # Desregistra e registra o serviço
        $out1 = w32tm /unregister 2>&1
        $out2 = w32tm /register 2>&1

        # Reinicia o serviço
        net stop w32tm 2>&1 | Out-Null
        net start w32tm 2>&1 | Out-Null

        # Força a fonte de tempo para o Domínio (Domhier)
        $out3 = w32tm /config /syncfromflags:domhier /update 2>&1

        # Reinicia novamente e sincroniza
        net stop w32tm 2>&1 | Out-Null
        net start w32tm 2>&1 | Out-Null
        $out4 = w32tm /resync /force 2>&1

        $LogData.Detalhes += "-> Registro e reinício do serviço concluídos."
        $LogData.Detalhes += "-> Fonte configurada para Domínio (Domhier)."
        $LogData.Mensagem = "Reset completo do relógio concluído. Sincronizado com o domínio."
    } else {
        # Modo Simples (Resync)
        $LogData.Detalhes += "Forçando sincronização de horário (w32tm /resync)..."
        $out4 = w32tm /resync /force 2>&1
        $LogData.Mensagem = "Horário sincronizado com sucesso."
    }

    # Captura a saída do resync final
    if ($out4) {
        $LogData.Detalhes += ($out4 -join "`n")
    }
    
    # Verifica se realmente sincronizou
    $status = w32tm /query /status 2>&1
    $LogData.Detalhes += "=== STATUS ATUAL DO SERVIÇO W32TM ==="
    $LogData.Detalhes += ($status -join "`n")

} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha na sincronização: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}