<#
.SYNOPSIS
    Ativa o Remote Desktop (RDP), altera o registro, libera o Firewall e inicia o serviço.
#>
$LogData = @{ 
    Script = "Ativar RDP (Acesso Remoto)"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes = @() 
}

try {
    $LogData.Detalhes += "Habilitando RDP no Registro (fDenyTSConnections = 0)..."
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -name "fDenyTSConnections" -value 0
    
    $LogData.Detalhes += "Habilitando regras de Firewall (Perfil de Dominio/Privado)..."
    Enable-NetFirewallRule -DisplayGroup "Área de Trabalho Remota" -ErrorAction SilentlyContinue | Out-Null
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue | Out-Null
    
    $LogData.Detalhes += "Iniciando e configurando o serviço TermService como Automatico..."
    Set-Service -Name "TermService" -StartupType Automatic
    Start-Service -Name "TermService" -ErrorAction SilentlyContinue
    
    $LogData.Mensagem = "RDP ativado e liberado no Firewall com sucesso."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}