# Retorna os 5 eventos mais recentes de nível Critical/Error dos logs
# System e Application. Alimenta o painel de resumo no topo da aba.
# Sem variáveis.

$ErrorActionPreference = 'SilentlyContinue'
$result = @()

foreach ($logName in @('System', 'Application')) {
    try {
        $events = Get-WinEvent -FilterHashtable @{LogName=$logName; Level=1,2} `
                               -MaxEvents 10 -ErrorAction Stop
        foreach ($e in $events) {
            $msg = if ($e.Message) {
                $m = $e.Message -replace "`r?`n", " "
                if ($m.Length -gt 200) { $m.Substring(0, 200) + "..." } else { $m }
            } else { "" }

            $result += [PSCustomObject]@{
                LogName     = $logName
                ID          = $e.Id
                Data        = $e.TimeCreated.ToString('dd/MM HH:mm:ss')
                Nivel       = $e.LevelDisplayName
                Fonte       = $e.ProviderName
                Mensagem    = $msg
                TimeCreated = $e.TimeCreated
            }
        }
    } catch { }
}

$top5 = $result | Sort-Object TimeCreated -Descending | Select-Object -First 5

@{ Data = @($top5) } | ConvertTo-Json -Depth 4 -Compress