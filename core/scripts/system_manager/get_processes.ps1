# Lista processos com PID, nome, memória (MB) e CPU (segundos acumulados).
# Sem variáveis — receita fixa.

$p = Get-Process | Select-Object `
    Id, `
    ProcessName, `
    @{Name='MemoryMB'; Expression={ [math]::Round($_.WorkingSet / 1MB, 2) }}, `
    @{Name='CPU';      Expression={ [math]::Round($_.CPU, 2) }}

@{ Data = @($p) } | ConvertTo-Json -Depth 3 -Compress | Write-Output