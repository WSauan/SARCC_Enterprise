<#
.SYNOPSIS
    Limpa impressoras de rede e força a reaplicação da GPO de impressão.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Continue'

$LogData = @{
    Script      = "Reset de Impressoras via GPO"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/4] Removendo impressoras de rede mapeadas (\\servidor\...)..."

    # Remove apenas impressoras de rede (que começam com \\)
    $printers = Get-Printer | Where-Object { $_.Name -like "\\*" }
    $removedCount = 0
    foreach ($prt in $printers) {
        try {
            Remove-Printer -Name $prt.Name -ErrorAction Stop
            $removedCount++
            $LogData.Detalhes += "  -> Removida: $($prt.Name)"
        } catch {
            $LogData.Detalhes += "  !! Falha ao remover $($prt.Name): $($_.Exception.Message)"
        }
    }
    $LogData.Detalhes += "Total de impressoras removidas: $removedCount"

    $LogData.Detalhes += "[2/4] Parando o serviço Spooler..."
    Stop-Service -Name "Spooler" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $LogData.Detalhes += "[3/4] Forçando atualização de GPO (gpupdate)..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "gpupdate.exe"
    $psi.Arguments = "/target:user /force"
    $psi.RedirectStandardInput  = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow  = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    try { $proc.StandardInput.WriteLine("N"); $proc.StandardInput.Flush(); $proc.StandardInput.Close() } catch { }
    if (-not $proc.WaitForExit(60000)) {
        try { $proc.Kill() } catch { }
    }
    $LogData.Detalhes += "  -> Política de usuário atualizada."

    $LogData.Detalhes += "[4/4] Reiniciando o Spooler e aplicando lista..."
    Set-Service -Name "Spooler" -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service -Name "Spooler" -ErrorAction SilentlyContinue

    $LogData.Mensagem = "Reset de GPO de impressoras concluído. Removidas $removedCount impressoras de rede."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha no reset da GPO de impressoras: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}