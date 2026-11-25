<#
.SYNOPSIS
    Ativa o Remote Desktop (RDP), altera o registro, libera o Firewall e inicia o serviço.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Ativar RDP (Acesso Remoto)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/3] Habilitando RDP no Registro (fDenyTSConnections = 0)..."
    $tsPath = 'HKLM:\System\CurrentControlSet\Control\Terminal Server'
    Set-ItemProperty -Path $tsPath -Name "fDenyTSConnections" -Value 0 -Type DWord -Force -ErrorAction Stop

    $LogData.Detalhes += "[2/3] Habilitando regras de Firewall (Área de Trabalho Remota / Remote Desktop)..."
    foreach ($grp in @("Área de Trabalho Remota", "Remote Desktop")) {
        try {
            Enable-NetFirewallRule -DisplayGroup $grp -ErrorAction Stop | Out-Null
            $LogData.Detalhes += "      -> Grupo '$grp': habilitado."
        } catch {
            $LogData.Detalhes += "      -> Grupo '$grp' não encontrado ou sem alterações: $($_.Exception.Message)"
        }
    }

    $LogData.Detalhes += "[3/3] Configurando TermService para Automatic e iniciando..."
    Set-Service -Name "TermService" -StartupType Automatic -ErrorAction Stop
    Start-Service -Name "TermService" -ErrorAction Stop

    $svc = Get-Service -Name "TermService" -ErrorAction Stop
    $LogData.Detalhes += "      -> Status atual do TermService: $($svc.Status)"
    $LogData.Mensagem = "RDP ativado e liberado no Firewall com sucesso (TermService: $($svc.Status))."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha ao ativar RDP: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}