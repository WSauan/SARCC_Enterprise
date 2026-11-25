<#
.SYNOPSIS
    Encerra sessões de usuários desconectadas silenciosamente e retorna JSON.
#>
$LogData = @{
    Script = "Expurgo de Sessões"
    Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Encerrados = 0
    Erros = 0
    Detalhes = @()
    Mensagem = ""
}

try {
    $LogData.Detalhes += "Iniciando verificação de sessões (quser)..."
    $quserOutput = quser 2>$null

    if (-not $quserOutput) {
        $LogData.Mensagem = "Nenhuma sessão de usuário encontrada."
    } else {
        $sessoes = $quserOutput | Select-Object -Skip 1 | ForEach-Object {
            $linha = $_.Trim() -split '\s+'
            if ($linha[0].StartsWith(">")) {
                [PSCustomObject]@{ Usuario = $linha[0].Replace('>',''); ID = $linha[1]; Estado = $linha[2] }
            } else {
                [PSCustomObject]@{ Usuario = $linha[0]; ID = $linha[1]; Estado = $linha[2] }
            }
        }

        $sessoesDesconectadas = $sessoes | Where-Object { $_.Estado -like "*Disc*" -or $_.Estado -like "*Descon*" }

        if ($sessoesDesconectadas) {
            foreach ($sessao in $sessoesDesconectadas) {
                try {
                    logoff $sessao.ID
                    $LogData.Detalhes += "Sessão encerrada: $($sessao.Usuario) (ID: $($sessao.ID))"
                    $LogData.Encerrados++
                } catch {
                    $LogData.Detalhes += "ERRO ao encerrar $($sessao.Usuario): $_"
                    $LogData.Erros++
                }
            }
            $LogData.Mensagem = "$($LogData.Encerrados) sessões desconectadas foram encerradas. Erros: $($LogData.Erros)."
        } else {
            $LogData.Mensagem = "Nenhuma sessão em segundo plano para encerrar."
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha crítica: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}