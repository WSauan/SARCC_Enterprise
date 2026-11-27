<#
.SYNOPSIS
    Consulta o status do BitLocker e retorna as chaves de recuperação.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$LogData = @{
    Script      = "Consulta BitLocker"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
    Volumes     = @()
}

try {
    # Verifica se o módulo existe
    if (-not (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue)) {
        throw "O módulo BitLocker não está instalado ou não é suportado nesta edição do Windows."
    }

    $volumes = Get-BitLockerVolume -ErrorAction Stop
    $hasEncrypted = $false

    foreach ($vol in $volumes) {
        $volInfo = [PSCustomObject]@{
            MountPoint       = $vol.MountPoint
            VolumeStatus     = $vol.VolumeStatus.ToString()
            ProtectionStatus = $vol.ProtectionStatus.ToString()
            EncryptionMethod = $vol.EncryptionMethod.ToString()
            RecoveryKey      = "N/A"
        }

        if ($vol.VolumeStatus -eq 'FullyEncrypted' -or $vol.VolumeStatus -eq 'EncryptionInProgress') {
            $hasEncrypted = $true
            # Tenta pegar a chave de recuperação (pode exigir privilégios de Admin)
            if ($vol.KeyProtector) {
                $numericKey = $vol.KeyProtector | Where-Object { $_.KeyProtectorType -eq 'RecoveryPassword' }
                if ($numericKey) {
                    $volInfo.RecoveryKey = $numericKey.RecoveryPassword
                }
            }
        }
        $LogData.Volumes += $volInfo
    }

    if (-not $hasEncrypted) {
        $LogData.Mensagem = "Nenhum volume criptografado com BitLocker foi encontrado."
    } else {
        $LogData.Mensagem = "Status do BitLocker consultado com sucesso."
    }

} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao consultar o BitLocker: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}