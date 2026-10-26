<#
.SYNOPSIS
    Inventário de softwares no endpoint via Winget (Bypass AppX Alias).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$Engine = '{{engine}}'
$allSoftware = @()

if ($Engine -eq "Chocolatey") {
    $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
    if (Test-Path $choco) {
        $clist = & $choco list -lo -r 2>$null
        if ($null -ne $clist) {
            foreach ($c in $clist) {
                if ([string]::IsNullOrWhiteSpace($c)) { continue }
                $p = $c.Split('|')
                if ($p.Length -ge 2) {
                    $allSoftware += [PSCustomObject]@{ Id = $p[0].Trim(); Name = $p[0].Trim(); Version = $p[1].Trim(); Origin = "Chocolatey" }
                }
            }
        }
    }
} else {
    $wingetCmd = $null
    
    $realApp = Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($realApp) { $wingetCmd = $realApp.FullName }

    if (-not $wingetCmd) {
        $candidate = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
        if (Test-Path $candidate) { $wingetCmd = $candidate }
    }

    if ($wingetCmd -and (Test-Path $wingetCmd)) {
        $out = @(& $wingetCmd list --nowarn --accept-source-agreements --disable-interactivity 2>$null)
        $start = $false; $idPos = -1; $verPos = -1
        
        foreach ($line in $out) {
            if ($null -eq $line) { continue }
            $lineStr = $line.ToString()
            if ($lineStr -match "msstore" -or [string]::IsNullOrWhiteSpace($lineStr)) { continue }
            if ($lineStr -match '^Nome' -or $lineStr -match '^Name') {
                $idPos  = $lineStr.IndexOf("Id",   [System.StringComparison]::OrdinalIgnoreCase)
                $verPos = $lineStr.IndexOf("Vers", [System.StringComparison]::OrdinalIgnoreCase)
            }
            if ($lineStr -match '^---') { $start = $true; continue }
            
            if ($start -and $idPos -gt 0 -and $verPos -gt $idPos) {
                $name    = $lineStr.Substring(0, $idPos).Trim()
                $id      = $lineStr.Substring($idPos, $verPos - $idPos).Trim()
                $verRest = $lineStr.Substring($verPos).Trim()
                $parts   = $verRest -split '\s+', 2
                $ver     = if ($parts.Count -ge 1) { $parts[0] } else { "" }
                $disp    = if ($parts.Count -ge 2) { $parts[1].Trim() } else { "" }
                
                if ($name -and $id) {
                    $allSoftware += [PSCustomObject]@{ Id = $id; Name = $name; Version = $ver; Available = $disp; Origin = "Winget" }
                }
            }
        }
    }

    if ($allSoftware.Count -eq 0) {
        $paths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
        $reg = Get-ItemProperty $paths -ErrorAction SilentlyContinue | Where-Object DisplayName | Sort-Object DisplayName -Unique
        foreach ($item in $reg) {
            if ($item.DisplayName) {
                $allSoftware += [PSCustomObject]@{ Id = $item.DisplayName; Name = $item.DisplayName; Version = if ($item.DisplayVersion) { $item.DisplayVersion } else { "-" }; Origin = "Windows Registry" }
            }
        }
    }
}

if ($allSoftware.Count -eq 0) { $allSoftware += [PSCustomObject]@{ Id = "Nenhum"; Name = "Nenhum software encontrado"; Version = "-"; Origin = "-" } }
@{ Pacotes = @($allSoftware | Sort-Object Name -Unique) } | ConvertTo-Json -Depth 5 -Compress