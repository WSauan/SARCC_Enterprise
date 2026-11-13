<#
.SYNOPSIS
    Lista todas as impressoras locais e de rede com porta/IP, driver, fila de impressão e status em UTF-8.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$result = @()

$printers = @(Get-Printer -ErrorAction SilentlyContinue)
if ($printers.Count -gt 0) {
    foreach ($p in $printers) {
        $jobs = @(Get-PrintJob -PrinterName $p.Name -ErrorAction SilentlyContinue).Count
        if ($null -eq $jobs -or $jobs -lt 0) {
            $jobs = if ($null -ne $p.JobCount) { [int]$p.JobCount } else { 0 }
        }
        $result += [PSCustomObject]@{
            Name       = [string]$p.Name
            PortName   = [string]$p.PortName
            DriverName = [string]$p.DriverName
            JobCount   = [int]$jobs
            Status     = [string]$p.PrinterStatus
            Shared     = [bool]$p.Shared
        }
    }
} else {
    $wmiPrinters = @(Get-CimInstance -ClassName Win32_Printer -ErrorAction SilentlyContinue)
    foreach ($wp in $wmiPrinters) {
        $statusStr = if ($wp.WorkOffline) { "Offline" } elseif ($wp.PrinterStatus -eq 4) { "Printing" } else { "Normal" }
        $result += [PSCustomObject]@{
            Name       = [string]$wp.Name
            PortName   = [string]$wp.PortName
            DriverName = [string]$wp.DriverName
            JobCount   = if ($null -ne $wp.JobCountSinceLastReset) { [int]$wp.JobCountSinceLastReset } else { 0 }
            Status     = $statusStr
            Shared     = [bool]$wp.Shared
        }
    }
}

@{ Data = @($result) } | ConvertTo-Json -Depth 3 -Compress | Write-Output