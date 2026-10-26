# Busca eventos em um log específico, filtrando por nível.
# Variáveis: {{log_name}}, {{level}} (ex: "1,2"), {{max_events}}

$logName    = '{{log_name}}'
$levelArr   = "{{level}}" -split ',' | ForEach-Object { [int]$_ }
$maxEvt     = [int]'{{max_events}}'

try {
    $events = Get-WinEvent -FilterHashtable @{
        LogName = $logName
        Level   = $levelArr
    } -MaxEvents $maxEvt -ErrorAction Stop

    $res = @()
    foreach ($e in $events) {
        $res += [PSCustomObject]@{
            ID       = $e.Id
            Data     = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            Nivel    = $e.LevelDisplayName
            Fonte    = $e.ProviderName
            Mensagem = $e.Message
        }
    }
    @{ Data = $res } | ConvertTo-Json -Depth 4 -Compress | Write-Output
} catch {
    @{ Data = @(@{ Erro = $($_.Exception.Message) }) } | ConvertTo-Json -Depth 3 -Compress | Write-Output
}