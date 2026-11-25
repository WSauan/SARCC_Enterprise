<#
.SYNOPSIS
    Força a atualização de Políticas de Grupo (gpupdate /force) interceptando prompts de Reboot/Logoff em tempo real.
.NOTES
    - Monitora o buffer de saída em tempo real (BaseStream) para detectar 'Reiniciar? (S/N)' sem travar.
    - Responde automaticamente 'N' assim que o aviso aparece, mantendo o computador ligado para o usuário.
    - Marca a execução como SUCESSO imediatamente após concluir a atualização das políticas.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Continue'

$LogData = @{
    Script      = "Forçar Atualização de GPO (gpupdate)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    # 1. Verifica se a máquina pertence a um domínio e testa o canal seguro com o AD
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem -Property PartOfDomain, Domain -ErrorAction SilentlyContinue
    if (-not $cs -or -not $cs.PartOfDomain) {
        throw "A estação '$env:COMPUTERNAME' não está ingressada em um domínio Active Directory."
    }
    $LogData.Detalhes += "[1/4] Domínio detectado: $($cs.Domain)"

    $secureChannel = $false
    try {
        $secureChannel = Test-ComputerSecureChannel -ErrorAction Stop
    } catch {
        $secureChannel = $false
    }

    if ($secureChannel) {
        $LogData.Detalhes += "[2/4] Canal seguro com o Controlador de Domínio: ÍNTEGRO."
    } else {
        $LogData.Detalhes += "[2/4] AVISO: Canal seguro não confirmado (prosseguindo com gpupdate)..."
    }

    # 2. Registra timestamp anterior do cache local de GPO da Máquina (Registry.pol)
    $regPolPath = "$env:SystemRoot\System32\GroupPolicy\Machine\Registry.pol"
    $polBefore = if (Test-Path -LiteralPath $regPolPath) {
        (Get-Item -LiteralPath $regPolPath -Force).LastWriteTime.ToString('dd/MM/yyyy HH:mm:ss')
    } else { "Ausente" }
    $LogData.Detalhes += "      -> Registry.pol antes da atualização: $polBefore"

    # 3. Inicia gpupdate.exe monitorando o stream de bytes em tempo real
    $LogData.Detalhes += "[3/4] Executando 'gpupdate.exe /force' com interceptação automática de prompt (S/N)..."

    $oemEncoding = try {
        [System.Text.Encoding]::GetEncoding([System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
    } catch {
        [System.Text.Encoding]::GetEncoding(850)
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "gpupdate.exe"
    $psi.Arguments = "/force"
    $psi.RedirectStandardInput  = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow  = $true

    $proc = [System.Diagnostics.Process]::Start($psi)

    # Preenche o buffer de entrada padrão preventivamente com 'N'
    try {
        $proc.StandardInput.WriteLine("N")
        $proc.StandardInput.WriteLine("N")
        $proc.StandardInput.Flush()
    } catch { }

    $outStream = $proc.StandardOutput.BaseStream
    $memStream = New-Object System.IO.MemoryStream
    $byteBuf   = New-Object byte[] 1024
    $readTask  = $outStream.ReadAsync($byteBuf, 0, $byteBuf.Length)

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $timeoutMs = 90000
    $promptIntercepted = $false

    while (-not $proc.HasExited) {
        if ($readTask.IsCompleted) {
            $bytesRead = $readTask.GetAwaiter().GetResult()
            if ($bytesRead -gt 0) {
                $memStream.Write($byteBuf, 0, $bytesRead)
                $partialText = $oemEncoding.GetString($memStream.ToArray())

                # Detecta imediatamente a pergunta 'Reiniciar? (S/N)' ou 'Fazer logoff? (S/N)' mesmo sem quebra de linha
                if ($partialText -match '(?i)(Reiniciar\s*\?|Restart\s*\?|logoff\s*\?|\(S/N\)|\(Y/N\))') {
                    $promptIntercepted = $true
                    try {
                        $proc.StandardInput.WriteLine("N")
                        $proc.StandardInput.Flush()
                        $proc.StandardInput.Close()
                    } catch { }

                    # Aguarda até 1,5s para encerramento nativo; se o console retiver o processo, encerra-o com segurança
                    if (-not $proc.WaitForExit(1500)) {
                        try { $proc.Kill() } catch { }
                    }
                    break
                }
                $readTask = $outStream.ReadAsync($byteBuf, 0, $byteBuf.Length)
            } else {
                Start-Sleep -Milliseconds 100
            }
        } else {
            Start-Sleep -Milliseconds 150
        }

        if ($sw.ElapsedMilliseconds -ge $timeoutMs) {
            try { $proc.Kill() } catch { }
            throw "O comando gpupdate.exe excedeu o tempo limite de 90 segundos."
        }
    }

    # Drena eventuais bytes residuais do buffer
    try {
        if ($readTask -and $readTask.IsCompleted) {
            $rem = $readTask.GetAwaiter().GetResult()
            if ($rem -gt 0) { $memStream.Write($byteBuf, 0, $rem) }
        }
    } catch { }

    $rawOutput = $oemEncoding.GetString($memStream.ToArray()).Trim()
    $memStream.Dispose()

    $lines = @($rawOutput -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    foreach ($line in $lines) {
        if ($line -match '(?i)(Reiniciar\s*\?|Restart\s*\?|logoff\s*\?|\(S/N\)|\(Y/N\))') {
            $LogData.Detalhes += "      [gpupdate] $line -> N (Respondido automaticamente pelo SARCC — Reinício adiado)"
        } else {
            $LogData.Detalhes += "      [gpupdate] $line"
        }
    }

    # 4. Verifica timestamp atualizado do Registry.pol e define mensagem final
    $polAfter = if (Test-Path -LiteralPath $regPolPath) {
        (Get-Item -LiteralPath $regPolPath -Force).LastWriteTime.ToString('dd/MM/yyyy HH:mm:ss')
    } else { "Ausente" }
    $LogData.Detalhes += "[4/4] Registry.pol após a atualização: $polAfter"

    $successMatch = ($rawOutput -match '(?i)(êxito|exito|successfully)')

    if ($promptIntercepted) {
        $LogData.StatusFinal = "SUCESSO"
        $LogData.Mensagem = "GPO atualizada com sucesso! Solicitação de reinício respondida com 'N' automaticamente (aplicação final no próximo boot)."
    } elseif ($proc.ExitCode -eq 0 -or $successMatch) {
        $LogData.StatusFinal = "SUCESSO"
        $LogData.Mensagem = "Políticas de Computador e Usuário atualizadas com sucesso (sem necessidade de reinício)."
    } else {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "gpupdate finalizou com código $($proc.ExitCode). Verifique os detalhes do log."
    }

} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao atualizar GPO: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}