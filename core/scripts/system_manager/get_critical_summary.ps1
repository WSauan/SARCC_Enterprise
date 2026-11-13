<#
.SYNOPSIS
    Retorna os 5 eventos mais recentes de nível Critical/Error dos logs System e Application em UTF-8.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$result = @()

foreach ($logName in @('System', 'Application')) {
    try {
        $events = Get-WinEvent -FilterHashtable @{LogName=$logName; Level=1,2} -MaxEvents 10 -ErrorAction Stop
        foreach ($e in $events) {
            $msg = if ($e.Message) { ($e.Message -replace "`r?`n", " ").Trim() } else { "Sem descrição disponível." }

            $result += [PSCustomObject]@{
                LogName     = $logName
                ID          = $e.Id
                Data        = $e.TimeCreated.ToString('dd/MM HH:mm:ss')
                Nivel       = if ($e.LevelDisplayName) { $e.LevelDisplayName } else { "Erro/Crítico" }
                Fonte       = $e.ProviderName
                Mensagem    = $msg
                TimeCreated = $e.TimeCreated
            }
        }
    } catch { }
}

$top5 = @($result | Sort-Object TimeCreated -Descending | Select-Object -First 5 | Select-Object LogName, ID, Data, Nivel, Fonte, Mensagem)

@{ Data = @($top5) } | ConvertTo-Json -Depth 4 -Compress | Write-Output