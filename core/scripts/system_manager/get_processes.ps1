<#
.SYNOPSIS
    Lista processos com PID, nome, memória (MB) e CPU (segundos acumulados) com proteção contra valores nulos.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$p = Get-Process -ErrorAction SilentlyContinue | Select-Object `
    Id, `
    ProcessName, `
    @{Name='MemoryMB'; Expression={ if ($null -ne $_.WorkingSet64) { [math]::Round($_.WorkingSet64 / 1MB, 2) } else { 0 } }}, `
    @{Name='CPU';      Expression={ if ($null -ne $_.CPU) { [math]::Round([double]$_.CPU, 2) } else { 0 } }}

@{ Data = @($p) } | ConvertTo-Json -Depth 3 -Compress | Write-Output