<#
.SYNOPSIS
    Busca eventos em um log específico tratando silenciosamente quando não há ocorrências.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$logName  = '{{log_name}}'
$levelArr = @("{{level}}" -split ',' | ForEach-Object { [int]$_.Trim() })
$maxEvt   = [int]'{{max_events}}'

try {
    $events = Get-WinEvent -FilterHashtable @{
        LogName = $logName
        Level   = $levelArr
    } -MaxEvents $maxEvt -ErrorAction Stop

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