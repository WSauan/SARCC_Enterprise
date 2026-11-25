<#
.SYNOPSIS
    Ativa "Turn on PowerShell Script Block Logging".
    Logs em: Event Viewer > Microsoft-Windows-PowerShell/Operational
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Ativar Script Block Logging"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $regPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
    $LogData.Detalhes += "[1/2] Garantindo chave de política '$regPath'..."
    if (-not (Test-Path -LiteralPath $regPath)) {
        New-Item -Path $regPath -Force -ErrorAction Stop | Out-Null
    }

    $LogData.Detalhes += "[2/2] Configurando EnableScriptBlockLogging = 1 (DWORD)..."
    Set-ItemProperty -Path $regPath -Name "EnableScriptBlockLogging" -Value 1 -Type DWord -Force -ErrorAction Stop

    $check = (Get-ItemProperty -Path $regPath -Name "EnableScriptBlockLogging" -ErrorAction Stop).EnableScriptBlockLogging
    $LogData.Detalhes += "      -> EnableScriptBlockLogging = $check (esperado: 1)"
    if ($check -ne 1) {
        throw "Valor lido ($check) difere do esperado (1)."
    }

    $LogData.Mensagem = "Script Block Logging ativado. Logs em Event Viewer > Microsoft-Windows-PowerShell/Operational."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha ao ativar Script Block Logging: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}