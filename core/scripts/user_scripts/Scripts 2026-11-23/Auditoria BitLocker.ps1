<#
.SYNOPSIS
    Audita o status de proteção do BitLocker no volume C:.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Auditoria BitLocker"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "[1/1] Consultando status do BitLocker no volume C:..."
    $bdeRaw = & manage-bde.exe -status C: 2>&1
    $exitCode = $LASTEXITCODE

    if ($null -eq $bdeRaw -or $bdeRaw.Count -eq 0) {
        throw "manage-bde.exe não retornou informações para o volume C:."
    }

    $bdeText = ($bdeRaw | ForEach-Object { $_.ToString() }) -join "`n"
    $LogData.Detalhes += $bdeText

    if ($exitCode -ne 0) {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "Auditoria concluída com código $exitCode (verifique o status do volume C:)."
    } elseif ($bdeText -match "(?i)(Protection On|Proteção Ativada|Protecao Ativada)") {
        $LogData.Mensagem = "BitLocker ATIVO no volume C:."
    } elseif ($bdeText -match "(?i)(Protection Off|Proteção Desativada|Protecao Desativada)") {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "BitLocker DESATIVADO no volume C:."
    } else {
        $LogData.Mensagem = "Status do BitLocker coletado para o volume C:."
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha na auditoria do BitLocker: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}