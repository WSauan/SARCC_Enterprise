<#
.SYNOPSIS
    Lista todos os serviços do Windows com codificação UTF-8 preservada.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$s = Get-Service -ErrorAction SilentlyContinue | Select-Object `
    Name, `
    DisplayName, `
    @{Name='Status'; Expression={ $_.Status.ToString() }}

@{ Data = @($s) } | ConvertTo-Json -Depth 3 -Compress | Write-Output