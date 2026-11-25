<#
.SYNOPSIS
    Reparo avançado de imagem do sistema via DISM RestoreHealth e SFC /scannow.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Reparo Avançado (DISM/SFC)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/2] Iniciando DISM (Cleanup-Image / RestoreHealth)..."
    $dismOut = & DISM.exe /Online /Cleanup-Image /RestoreHealth 2>&1
    $dismExit = $LASTEXITCODE
    $LogData.Detalhes += (($dismOut | ForEach-Object { $_.ToString().Trim() }) -join "`n")

    $LogData.Detalhes += "[2/2] Iniciando SFC (System File Checker)..."
    $sfcOut = & sfc.exe /scannow 2>&1
    $sfcExit = $LASTEXITCODE
    $LogData.Detalhes += (($sfcOut | ForEach-Object { $_.ToString().Trim() }) -join "`n")

    if ($dismExit -ne 0 -or $sfcExit -ne 0) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "DISM/SFC finalizado com códigos DISM=$dismExit e SFC=$sfcExit. Verifique os detalhes."
    } else {
        $LogData.Mensagem = "Reparo DISM e SFC concluído sem erros."
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha no reparo DISM/SFC: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}