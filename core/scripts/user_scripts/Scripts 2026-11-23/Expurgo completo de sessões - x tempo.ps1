<#
.SYNOPSIS
    Expurgo completo de sessões: encerra desconectadas + ativas com idle alto.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

# ============================================
# CONFIGURAÇÃO — EDITE AQUI
# ============================================
$IdleThresholdMinutes = 30
$DryRun               = $false
$EncerrarDisc         = $true
$EncerrarIdle         = $true

$UsuariosProtegidos = @(
    "Administrator", "Administrador",
    "adm.wsauan", "adm.ebserh", "adm.bcaitano",
    "adm.michael", "adm.valdemir", "adm.marcos",
    "welber.santos", "bruno.alves3", "marcos.vinycius"
)
# ============================================

$LogData = @{
    Script         = "Expurgo de Sessões (Completo)"
    Inicio         = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador     = $env:COMPUTERNAME
    StatusFinal    = "SUCESSO"
    Modo           = if ($DryRun) { "DRY-RUN" } else { "PRODUÇÃO" }
    EncerradasDisc = 0
    EncerradasIdle = 0
    Ignoradas      = 0
    Erros          = 0
    Detalhes       = @()
    Mensagem       = ""
}

function Get-SessionIdleMinutes {
    param([int]$SessionId)
    try {
        $session = Get-CimInstance -ClassName Win32_PerfRawData_TermService_TerminalServicesSession `
                                   -Filter "SessionId=$SessionId" `
                                   -ErrorAction Stop |
                   Select-Object -First 1

        if ($null -eq $session -or $null -eq $session.SessionIdleTime) {
            return $null
        }

        $idleSeconds = [double]$session.SessionIdleTime / 10000000.0
        return [math]::Round($idleSeconds / 60.0, 1)
    } catch {
        return $null
    }
}

try {
    $LogData.Detalhes += "[1/4] Modo: $($LogData.Modo)"
    $LogData.Detalhes += "[1/4] Threshold idle: $IdleThresholdMinutes min"
    $LogData.Detalhes += "[2/4] Enumerando sessões (quser)..."

    $quserRaw = @(& quser.exe 2>&1)
    if (-not $quserRaw -or $quserRaw.Count -le 1) {
        $LogData.Mensagem = "Nenhuma sessão de usuário encontrada."
    } else {
        $sessoes = @()
        foreach ($linha in ($quserRaw | Select-Object -Skip 1)) {
            $txt = $linha.ToString().Trim()
            if ([string]::IsNullOrWhiteSpace($txt)) { continue }
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

            $state = "Desconhecido"
            if ($linhaLimpa -match '\b(Disc|Descon|Desconectado|Disconnected)\b') {
                $state = "Disc"
            } elseif ($linhaLimpa -match '\b(Active|Ativo)\b') {
                $state = "Active"
            } elseif ($linhaLimpa -match '\b(Listen|Ouvindo|Conn)\b') {
                $state = "Listen"
            } elseif ($linhaLimpa -match '\b(Services|Serviços)\b') {
                $state = "Services"
            }

            $sessoes += [PSCustomObject]@{
                Username  = $username
                SessionId = $sessionId
                State     = $state
            }
        }

        $LogData.Detalhes += "      -> $($sessoes.Count) sessão(ões) encontrada(s)."
        $LogData.Detalhes += "[3/4] Processando logoff..."

        foreach ($sessao in $sessoes) {
            if ($sessao.State -notin @("Disc", "Active")) {
                $LogData.Detalhes += "      SKIP [$($sessao.Username)] id=$($sessao.SessionId) — estado: $($sessao.State)"
                $LogData.Ignoradas++
                continue
            }

            if ($UsuariosProtegidos -contains $sessao.Username) {
                $LogData.Detalhes += "      SKIP [$($sessao.Username)] id=$($sessao.SessionId) — usuário protegido"
                $LogData.Ignoradas++
                continue
            }

            if ($sessao.State -eq "Disc" -and $EncerrarDisc) {
                if ($DryRun) {
                    $LogData.Detalhes += "      DRYRUN [DISC] [$($sessao.Username)] id=$($sessao.SessionId) — logoff NÃO executado"
                } else {
                    try {
                        & logoff.exe $sessao.SessionId 2>&1 | Out-Null
                        Start-Sleep -Milliseconds 500
                        $stillThere = @(& quser.exe 2>&1) | Select-String "\b$($sessao.SessionId)\b"
                        if ($stillThere) {
                            $LogData.Detalhes += "      PARCIAL [DISC] [$($sessao.Username)] id=$($sessao.SessionId) — comando enviado, mas sessão persiste"
                            $LogData.Erros++
                        } else {
                            $LogData.Detalhes += "      LOGOFF [DISC] [$($sessao.Username)] id=$($sessao.SessionId)"
                            $LogData.EncerradasDisc++
                        }
                    } catch {
                        $LogData.Detalhes += "      FALHA [DISC] [$($sessao.Username)] id=$($sessao.SessionId) — $($_.Exception.Message)"
                        $LogData.Erros++
                    }
                }
                continue
            }

            if ($sessao.State -eq "Active" -and $EncerrarIdle) {
                $idleMinutes = Get-SessionIdleMinutes -SessionId $sessao.SessionId
                if ($null -eq $idleMinutes) {
                    $LogData.Detalhes += "      SKIP [ACTIVE] [$($sessao.Username)] id=$($sessao.SessionId) — idle time indisponível"
                    $LogData.Ignoradas++
                    continue
                }

                if ($idleMinutes -ge $IdleThresholdMinutes) {
                    if ($DryRun) {
                        $LogData.Detalhes += "      DRYRUN [IDLE] [$($sessao.Username)] id=$($sessao.SessionId) — idle $idleMinutes min (>= $IdleThresholdMinutes). Logoff NÃO executado"
                    } else {
                        try {
                            & logoff.exe $sessao.SessionId 2>&1 | Out-Null
                            $LogData.Detalhes += "      LOGOFF [IDLE] [$($sessao.Username)] id=$($sessao.SessionId) — idle $idleMinutes min"
                            $LogData.EncerradasIdle++
                        } catch {
                            $LogData.Detalhes += "      FALHA [IDLE] [$($sessao.Username)] id=$($sessao.SessionId) — $($_.Exception.Message)"
                            $LogData.Erros++
                        }
                    }
                } else {
                    $LogData.Detalhes += "      KEEP [ACTIVE] [$($sessao.Username)] id=$($sessao.SessionId) — idle $idleMinutes min (< $IdleThresholdMinutes)"
                    $LogData.Ignoradas++
                }
            }
        }

        $LogData.Detalhes += "[4/4] Resumo:"
        $LogData.Detalhes += "      -> Disc encerradas  : $($LogData.EncerradasDisc)"
        $LogData.Detalhes += "      -> Idle encerradas  : $($LogData.EncerradasIdle)"
        $LogData.Detalhes += "      -> Ignoradas        : $($LogData.Ignoradas)"
        $LogData.Detalhes += "      -> Erros            : $($LogData.Erros)"

        $total = $LogData.EncerradasDisc + $LogData.EncerradasIdle
        if ($total -eq 0) {
            $LogData.Mensagem = "Nenhuma sessão precisou ser encerrada."
        } else {
            $LogData.Mensagem = "Expurgo concluído: $total sessão(ões) encerrada(s) [$($LogData.EncerradasDisc) Disc + $($LogData.EncerradasIdle) Idle]."
        }

        if ($LogData.Erros -gt 0) {
            $LogData.StatusFinal = "ALERTA"
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha crítica: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}