<#
.SYNOPSIS
    Ativa "Display highly detailed status messages" (VerboseStatus).
    Replica a política de GPO equivalente.
#>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$LogData = @{
    Script      = "Ativar Verbose Status"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }
    Set-ItemProperty -Path $regPath -Name "VerboseStatus" -Value 1 -Type DWord -Force

    $check = (Get-ItemProperty -Path $regPath -Name VerboseStatus -ErrorAction SilentlyContinue).VerboseStatus
    $LogData.Detalhes += "VerboseStatus = $check (esperado: 1)"
    $LogData.Mensagem = "Mensagens detalhadas ativadas. Visível no próximo boot/logon/logoff."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}