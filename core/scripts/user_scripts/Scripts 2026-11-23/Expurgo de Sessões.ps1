<#
.SYNOPSIS
    Encerra sessões de usuários desconectadas silenciosamente e retorna JSON.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$LogData = @{
    Script      = "Expurgo de Sessões"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Encerrados  = 0
    Erros       = 0
    Detalhes    = @()
    Mensagem    = ""
}

try {
    $LogData.Detalhes += "Iniciando verificação de sessões (quser)..."
    $quserOutput = @(& quser.exe 2>&1)

    if (-not $quserOutput -or $quserOutput.Count -le 1) {
        $LogData.Mensagem = "Nenhuma sessão de usuário encontrada."
    } else {
        $sessoes = @()
        foreach ($rawLine in ($quserOutput | Select-Object -Skip 1)) {
            $txt = $rawLine.ToString().Trim()
            if ([string]::IsNullOrWhiteSpace($txt)) { continue }
            $isCurrent = $txt.StartsWith(">")
            $linhaLimpa = $txt.TrimStart('>', ' ')
            $partes = @($linhaLimpa -split '\s+' | Where-Object { $_ -ne '' })
            if ($partes.Count -lt 3) { continue }

            $username = $partes[0]
            $sessionId = $null
            for ($i = 1; $i -lt $partes.Count; $i++) {
                if ($partes[$i] -match '^\d+$') {
                    $sessionId = [int]$partes[$i]
                    break
                }
            }
            if ($null -eq $sessionId) { continue }

            $estado = "Desconhecido"
            if ($linhaLimpa -match '\b(Disc|Descon|Desconectado|Disconnected)\b') {
                $estado = "Disc"
            } elseif ($linhaLimpa -match '\b(Active|Ativo)\b') {
                $estado = "Active"
            }

            $sessoes += [PSCustomObject]@{
                Usuario   = $username
                ID        = $sessionId
                Estado    = $estado
                IsCurrent = $isCurrent
            }
        }

        $sessoesDesconectadas = @($sessoes | Where-Object { $_.Estado -eq "Disc" -and -not $_.IsCurrent })

        if ($sessoesDesconectadas.Count -gt 0) {
            foreach ($sessao in $sessoesDesconectadas) {
                try {
                    & logoff.exe $sessao.ID 2>&1 | Out-Null
                    $LogData.Detalhes += "Sessão encerrada: $($sessao.Usuario) (ID: $($sessao.ID))"
                    $LogData.Encerrados++
                } catch {
                    $LogData.Detalhes += "ERRO ao encerrar $($sessao.Usuario) (ID: $($sessao.ID)): $($_.Exception.Message)"
                    $LogData.Erros++
                }
            }
            if ($LogData.Erros -gt 0) {
                $LogData.StatusFinal = "ALERTA"
            }
            $LogData.Mensagem = "$($LogData.Encerrados) sessão(ões) desconectada(s) encerrada(s). Erros: $($LogData.Erros)."
        } else {
            $LogData.Mensagem = "Nenhuma sessão desconectada para encerrar."
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha crítica no expurgo de sessões: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}