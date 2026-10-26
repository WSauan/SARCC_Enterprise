<#
.SYNOPSIS
    Verifica atualizações disponíveis via Winget ou Chocolatey.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

$Engine = '{{engine}}'
$outdatedPkgs = @{}

if ($Engine -eq "Chocolatey") {
    $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
    if (Test-Path $choco) {
        $cout = & $choco outdated -r 2>$null
        if ($null -ne $cout) {
            foreach ($c in $cout) {
                if ([string]::IsNullOrWhiteSpace($c)) { continue }
                $p = $c.Split('|')
                if ($p.Length -ge 3) { $outdatedPkgs[$p[0].Trim()] = $p[2].Trim() }
            }
        }
    }
} else {
    $wingetCmd = (Get-Command winget -ErrorAction SilentlyContinue).Source
    if (-not $wingetCmd) { $wingetCmd = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" }
    if (-not (Test-Path $wingetCmd)) { $wingetCmd = (Get-ChildItem "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe" | Select-Object -First 1).FullName }

    if ($wingetCmd -and (Test-Path $wingetCmd)) {
        $out = @(& $wingetCmd upgrade --nowarn --accept-source-agreements --disable-interactivity 2>$null)
        $start = $false; $idPos = -1; $verPos = -1; $availPos = -1
        
        foreach ($line in $out) {
            if ($null -eq $line) { continue }
            $lineStr = $line.ToString()
            if ($lineStr -match "msstore" -or [string]::IsNullOrWhiteSpace($lineStr)) { continue }
            
            if ($lineStr -match '^Nome' -or $lineStr -match '^Name') {
                $idPos    = $lineStr.IndexOf("Id", [System.StringComparison]::OrdinalIgnoreCase)
                $verPos   = $lineStr.IndexOf("Vers", [System.StringComparison]::OrdinalIgnoreCase)
                $availPos = $lineStr.IndexOf("Disp", [System.StringComparison]::OrdinalIgnoreCase)
                if ($availPos -eq -1) { $availPos = $lineStr.IndexOf("Avail", [System.StringComparison]::OrdinalIgnoreCase) }
            }
            if ($lineStr -match '^---') { $start = $true; continue }
            
            if ($start -and $idPos -gt 0 -and $verPos -gt $idPos -and $availPos -gt $verPos) {
                $id = $lineStr.Substring($idPos, $verPos - $idPos).Trim()
                $rest = $lineStr.Substring($availPos).Trim()
                $avail = ($rest -split '\s+')[0] 
                if ($id -and $avail) { $outdatedPkgs[$id] = $avail }
            }
        }
    }
}

@{ Atualizacoes = $outdatedPkgs } | ConvertTo-Json -Depth 5 -Compress