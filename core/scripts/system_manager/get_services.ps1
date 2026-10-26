# Lista todos os serviços com Name, DisplayName e Status.
# Sem variáveis.

$s = Get-Service | Select-Object `
    Name, `
    DisplayName, `
    @{Name='Status'; Expression={ $_.Status.ToString() }}

@{ Data = @($s) } | ConvertTo-Json -Depth 3 -Compress | Write-Output