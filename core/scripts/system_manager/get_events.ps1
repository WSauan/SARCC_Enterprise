<#
.SYNOPSIS
    Busca eventos em um log específico com suporte a filtro de nível, IDs de reinicialização inesperada e janela temporal.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$logName   = '{{log_name}}'
$levelRaw  = '{{level}}'.Trim()
$idsRaw    = '{{event_ids}}'.Trim()
$startRaw  = '{{start_time}}'.Trim()
$endRaw    = '{{end_time}}'.Trim()
$maxEvt    = [int]'{{max_events}}'

if ([string]::IsNullOrWhiteSpace($logName)) {
    $logName = "System"
}

$filterHash = @{
    LogName = $logName
}

if (-not [string]::IsNullOrWhiteSpace($idsRaw)) {
    $idList = @($idsRaw -split '[\s,;]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
    if ($idList.Count -gt 0) {
        $filterHash["Id"] = $idList
    }
} elseif (-not [string]::IsNullOrWhiteSpace($levelRaw)) {
    $levelArr = @($levelRaw -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
    if ($levelArr.Count -gt 0) {
        $filterHash["Level"] = $levelArr
    }
}

if (-not [string]::IsNullOrWhiteSpace($startRaw)) {
    try {
        $filterHash["StartTime"] = [datetime]::Parse($startRaw)
    } catch { }
}

if (-not [string]::IsNullOrWhiteSpace($endRaw)) {
    try {
        $filterHash["EndTime"] = [datetime]::Parse($endRaw)
    } catch { }
}

try {
    $events = Get-WinEvent -FilterHashtable $filterHash -MaxEvents $maxEvt -ErrorAction Stop

    $res = @()
    foreach ($e in $events) {
        $res += [PSCustomObject]@{
            LogName  = $logName
            ID       = $e.Id
            Data     = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            Nivel    = if ($e.LevelDisplayName) { $e.LevelDisplayName } else { "Nível $($e.Level)" }
            Fonte    = $e.ProviderName
            Mensagem = if ($e.Message) { $e.Message } else { "Sem mensagem detalhada." }
        }
    }
    @{ Data = @($res) } | ConvertTo-Json -Depth 4 -Compress | Write-Output
} catch {
    if ($_.FullyQualifiedErrorId -match "NoMatchingEventsFound" -or $_.Exception.Message -match "Nenhum evento|No events were found") {
        @{ Data = @() } | ConvertTo-Json -Depth 3 -Compress | Write-Output
    } else {
        @{ Data = @(@{ Erro = $_.Exception.Message }) } | ConvertTo-Json -Depth 3 -Compress | Write-Output
    }
}