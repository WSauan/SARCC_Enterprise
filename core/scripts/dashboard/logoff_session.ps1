<#
.SYNOPSIS
    Encerra seletivamente a sessão de um usuário específico (Ativo ou Desconectado em 2º plano) via ID ou Username.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$TargetUser = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{username_b64}}')).Trim()
$SessionIdRaw = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{session_id_b64}}')).Trim()

$LogData = @{
    Script      = "Logoff Seletivo ($TargetUser)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $resolvedId = $null
    if ($SessionIdRaw -match '^\d+$') {
        $resolvedId = [int]$SessionIdRaw
    } else {
        $quserLines = @(& quser.exe 2>$null)
        for ($i = 1; $i -lt $quserLines.Count; $i++) {
            $cleanLine = $quserLines[$i].Trim() -replace '^>', ''
            $tokens = @($cleanLine -split '\s+')
            if ($tokens.Count -ge 3) {
                $u = $tokens[0].ToLower()
                $targetLow = $TargetUser.ToLower()
                if ($u -eq $targetLow -or ($u.Length -ge 19 -and $targetLow.StartsWith($u))) {
                    if ($tokens[1] -match '^\d+$') { $resolvedId = [int]$tokens[1]; break }
                    elseif ($tokens[2] -match '^\d+$') { $resolvedId = [int]$tokens[2]; break }
                }
            }
        }
    }

    if ($null -eq $resolvedId) {
        throw "Nenhuma sessão interativa ou desconectada encontrada para o usuário '$TargetUser'."
    }

    $LogData.Detalhes += "Encerrando sessão ID $resolvedId do usuário '$TargetUser'..."
    $proc = Start-Process -FilePath "logoff.exe" -ArgumentList "$resolvedId" -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "O comando logoff.exe retornou código $($proc.ExitCode)."
    }

    $LogData.Mensagem = "Sessão do usuário '$TargetUser' (ID $resolvedId) encerrada com sucesso."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao encerrar sessão de '$TargetUser': $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}