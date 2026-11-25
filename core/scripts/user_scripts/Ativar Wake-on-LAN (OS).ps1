<#
.SYNOPSIS
    Ativa Wake-on-LAN (Magic Packet) nos adaptadores de rede físicos ativos.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Ativar Wake-on-LAN (OS)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/2] Localizando adaptadores de rede físicos..."
    $adapters = @(Get-NetAdapter -Physical -ErrorAction Stop)
    if ($adapters.Count -eq 0) {
        throw "Nenhum adaptador de rede físico encontrado."
    }

    $habilitados = 0
    $falhas = 0

    $LogData.Detalhes += "[2/2] Habilitando Magic Packet nos adaptadores físicos..."
    foreach ($nic in $adapters) {
        try {
            Enable-NetAdapterPowerManagement -Name $nic.Name -WakeOnMagicPacket -ErrorAction Stop
            $LogData.Detalhes += "      -> $($nic.Name) ($($nic.InterfaceDescription)): OK"
            $habilitados++
        } catch {
            $LogData.Detalhes += "      !! $($nic.Name) ($($nic.InterfaceDescription)): $($_.Exception.Message)"
            $falhas++
        }
    }

    if ($habilitados -eq 0) {
        throw "Nenhum adaptador aceitou WakeOnMagicPacket."
    }

    if ($falhas -gt 0) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "WoL ativado em $habilitados adaptador(es); $falhas não suportaram ou falharam."
    } else {
        $LogData.Mensagem = "Wake-on-LAN ativado em $habilitados adaptador(es) físico(s)."
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha ao ativar Wake-on-LAN: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}