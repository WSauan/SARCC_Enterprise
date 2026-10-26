# Força logoff de TODAS as sessões via WMI.
# Flags=4 → Logoff forçado (Win32Shutdown).

$LogData = @{
    Script      = "Ação de Energia (Forçar Logoff)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
}

try {
    $LogData.Detalhes += "Disparando comando de Forçar Logoff remoto..."
    Invoke-CimMethod -ClassName Win32_OperatingSystem -MethodName Win32Shutdown -Arguments @{Flags=4} | Out-Null
    $LogData.Detalhes += "Comando enviado com sucesso à camada OS (Kernel)."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}