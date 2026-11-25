<#
.SYNOPSIS
    Ativa "Display highly detailed status messages" (VerboseStatus).
    Replica a política de GPO equivalente.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

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
    $LogData.Detalhes += "[1/2] Garantindo chave de registro '$regPath'..."
    if (-not (Test-Path -LiteralPath $regPath)) {
        New-Item -Path $regPath -Force -ErrorAction Stop | Out-Null
    }

    $LogData.Detalhes += "[2/2] Configurando VerboseStatus = 1 (DWORD)..."
    Set-ItemProperty -Path $regPath -Name "VerboseStatus" -Value 1 -Type DWord -Force -ErrorAction Stop

    $check = (Get-ItemProperty -Path $regPath -Name "VerboseStatus" -ErrorAction Stop).VerboseStatus
    $LogData.Detalhes += "      -> VerboseStatus = $check (esperado: 1)"
    if ($check -ne 1) {
        throw "Valor lido ($check) difere do esperado (1)."
    }

    $LogData.Mensagem = "Mensagens detalhadas ativadas. Visível no próximo boot/logon/logoff."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha ao ativar VerboseStatus: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}