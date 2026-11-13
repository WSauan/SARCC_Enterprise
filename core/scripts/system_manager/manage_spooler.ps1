<#
.SYNOPSIS
    Gerencia o Spooler de Impressão e impressoras remotas (Flush Spooler, Limpar Fila Individual e Remover Impressora).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$action = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{action_b64}}'))
$printerName = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{printer_b64}}'))

$LogData = @{
    Script      = "Manutenção de Impressão ($action)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    switch ($action) {
        "flush_spooler" {
            $SpoolFolder = "$env:SystemRoot\System32\spool\PRINTERS"
            $LogData.Detalhes += "Parando serviço Spooler e processos auxiliares (splwow64)..."
            Stop-Service -Name "Spooler" -Force -ErrorAction Stop
            Stop-Process -Name "splwow64" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2

            $removedFiles = 0
            if (Test-Path -LiteralPath $SpoolFolder) {
                $files = @(Get-ChildItem -LiteralPath $SpoolFolder -File -Force -ErrorAction SilentlyContinue)
                foreach ($f in $files) {
                    try {
                        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
                        $removedFiles++
                    } catch {
                        $LogData.Detalhes += "Aviso ao remover '$($f.Name)': $($_.Exception.Message)"
                    }
                }
            }

            Set-Service -Name "Spooler" -StartupType Automatic -ErrorAction SilentlyContinue
            Start-Service -Name "Spooler" -ErrorAction Stop
            Start-Sleep -Seconds 1
            $svc = Get-Service -Name "Spooler" -ErrorAction SilentlyContinue

            $LogData.Detalhes += "Arquivos de spool (.SHD/.SPL) eliminados: $removedFiles"
            $LogData.Detalhes += "Status atual do serviço Spooler: $($svc.Status)"
            $LogData.Mensagem = "Spooler destravado e reiniciado com sucesso ($removedFiles arquivo(s) órfão(s) removido(s))."
        }

        "clear_printer_queue" {
            if ([string]::IsNullOrWhiteSpace($printerName)) {
                throw "Nome da impressora não informado."
            }
            $LogData.Detalhes += "Limpando fila de impressão de: '$printerName'"
            $jobs = @(Get-PrintJob -PrinterName $printerName -ErrorAction SilentlyContinue)
            $count = $jobs.Count

            if ($count -gt 0) {
                foreach ($j in $jobs) {
                    Remove-PrintJob -InputObject $j -ErrorAction SilentlyContinue
                }
            } else {
                $wmiPrinter = Get-CimInstance -ClassName Win32_Printer -Filter "Name = '$($printerName.Replace("'", "''"))'" -ErrorAction SilentlyContinue
                if ($wmiPrinter) {
                    $null = Invoke-CimMethod -InputObject $wmiPrinter -MethodName CancelAllJobs -ErrorAction SilentlyContinue
                }
            }

            $LogData.Detalhes += "Trabalhos cancelados na fila: $count"
            $LogData.Mensagem = "Fila da impressora '$printerName' limpa com sucesso ($count trabalho(s) removido(s))."
        }

        "remove_printer" {
            if ([string]::IsNullOrWhiteSpace($printerName)) {
                throw "Nome da impressora não informado."
            }
            $LogData.Detalhes += "Removendo impressora: '$printerName'"
            Remove-Printer -Name $printerName -ErrorAction Stop
            $LogData.Mensagem = "Impressora '$printerName' removida com sucesso."
        }

        default {
            throw "Ação de impressão desconhecida: $action"
        }
    }
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha na operação de impressão ($action): $($_.Exception.Message)"
    $LogData.Detalhes += "Erro: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    @{ Data = @($LogData) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
}