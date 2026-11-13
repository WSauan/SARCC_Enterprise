<#
.SYNOPSIS
    Força a atualização de Políticas de Grupo (gpupdate /force) sem travar em prompts de Reboot/Logoff.
.NOTES
    - Responde automaticamente 'N' caso o Windows solicite reinicialização ou logoff interativo.
    - Valida o canal seguro com o Active Directory antes de executar.
    - Retorna JSON estruturado compatível com a Central de Execução e Histórico do SARCC.
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
        $LogData.Detalhes += "[2/4] AVISO: Falha ao validar canal seguro com o DC (tentando gpupdate mesmo assim)..."
    }

    # 2. Registra timestamp anterior do cache local de GPO da Máquina (Registry.pol)
    $regPolPath = "$env:SystemRoot\System32\GroupPolicy\Machine\Registry.pol"
    $polBefore = if (Test-Path -LiteralPath $regPolPath) {
        (Get-Item -LiteralPath $regPolPath -Force).LastWriteTime.ToString('dd/MM/yyyy HH:mm:ss')
    } else { "Ausente" }
    $LogData.Detalhes += "      -> Registry.pol antes da atualização: $polBefore"

    # 3. Executa gpupdate /force respondendo 'N' automaticamente para evitar congelamento em sessão WinRM/WMI
    $LogData.Detalhes += "[3/4] Executando 'gpupdate.exe /force' (timeout de segurança: 90s)..."

    try {
        $oemCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage
        [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding($oemCP)
    } catch {
        [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(850)
    }

    $ psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c echo N | gpupdate.exe /force"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow  = $true
    try {
        $psi.StandardOutputEncoding = [Console]::OutputEncoding
        $psi.StandardErrorEncoding  = [Console]::OutputEncoding
    } catch { }

    $proc = [System.Diagnostics.Process]::Start($psi)
    $completed = $proc.WaitForExit(90000)

    if (-not $completed) {
        try { $proc.Kill() } catch { }
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        throw "O comando gpupdate.exe excedeu o tempo limite de 90 segundos (possível lentidão no SYSVOL/DC)."
    }

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $exitCode = $proc.ExitCode

    # Restaura UTF-8 para o retorno JSON do SARCC
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8

    $rawOutput = "$stdout`n$stderr".Trim()
    $lines = @($rawOutput -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object {
        $_ -and ($_ -notmatch '^(S/N|Y/N|\?)$')
    })

    foreach ($line in $lines) {
        $LogData.Detalhes += "      [gpupdate] $line"
    }

    # 4. Verifica timestamp atualizado do Registry.pol e avalia se há pedido de reboot/logoff
    $polAfter = if (Test-Path -LiteralPath $regPolPath) {
        (Get-Item -LiteralPath $regPolPath -Force).LastWriteTime.ToString('dd/MM/yyyy HH:mm:ss')
    } else { "Ausente" }
    $LogData.Detalhes += "[4/4] Registry.pol após a atualização: $polAfter"

    $needsReboot = ($rawOutput -match '(?i)(reiniciar|restart|reboot|inicialização|startup|logoff|logon)')
    $successMatch = ($rawOutput -match '(?i)(êxito|exito|successfully)')

    if ($exitCode -eq 0 -or $successMatch) {
        if ($needsReboot) {
            $LogData.StatusFinal = "SUCESSO"
            $LogData.Mensagem = "GPO atualizada com sucesso (Nota: políticas de inicialização/software entrarão em vigor no próximo boot)."
        } else {
            $LogData.StatusFinal = "SUCESSO"
            $LogData.Mensagem = "Políticas de Computador e Usuário atualizadas com sucesso."
        }
    } else {
        $LogData.StatusFinal = "ALERTA"
        $LogData.Mensagem = "gpupdate finalizou com código $exitCode. Verifique os detalhes do log."
    }

} catch {
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao atualizar GPO: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}