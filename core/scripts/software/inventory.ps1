<#
.SYNOPSIS
    Inventário de softwares no endpoint via Winget / Chocolatey / Registry com reparo UTF-8.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'SilentlyContinue'

function Repair-Mojibake ([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    if ($Text -match 'Ã') {
        try {
            $bytes = [System.Text.Encoding]::GetEncoding(1252).GetBytes($Text)
            return [System.Text.Encoding]::UTF8.GetString($bytes)
        } catch {
            return $Text
        }
    }
    return $Text
}

$Engine = '{{engine}}'
$allSoftware = @()

if ($Engine -eq "Chocolatey") {
    $choco = "C:\ProgramData\chocolatey\bin\choco.exe"
    if (Test-Path $choco) {
        $clist = & $choco list --local-only --limit-output 2>$null
        if (-not $clist) { $clist = & $choco list -r 2>$null }
        if ($null -ne $clist) {
            foreach ($c in $clist) {
                if ([string]::IsNullOrWhiteSpace($c)) { continue }
                $p = $c.ToString().Split('|')
                if ($p.Length -ge 2) {
                    $allSoftware += [PSCustomObject]@{
                        Id        = (Repair-Mojibake $p[0].Trim())
                        Name      = (Repair-Mojibake $p[0].Trim())
                        Version   = $p[1].Trim()
                        Available = ""
                        Origin    = "Chocolatey"
                    }
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
            $lineStr = Repair-Mojibake ($line.ToString())
            if ($lineStr -match "msstore" -or [string]::IsNullOrWhiteSpace($lineStr)) { continue }
            if ($lineStr -match '^Nome' -or $lineStr -match '^Name') {
                $idPos  = $lineStr.IndexOf("Id",   [System.StringComparison]::OrdinalIgnoreCase)
                $verPos = $lineStr.IndexOf("Vers", [System.StringComparison]::OrdinalIgnoreCase)
            }
            if ($lineStr -match '^---') { $start = $true; continue }

            if ($start -and $idPos -gt 0 -and $verPos -gt $idPos -and $lineStr.Length -gt $verPos) {
                $name    = $lineStr.Substring(0, $idPos).Trim()
                $id      = $lineStr.Substring($idPos, $verPos - $idPos).Trim()
                $verRest = $lineStr.Substring($verPos).Trim()
                $parts   = $verRest -split '\s+', 2
                $ver     = if ($parts.Count -ge 1) { $parts[0] } else { "" }
                $disp    = if ($parts.Count -ge 2) { $parts[1].Trim() } else { "" }
                if ($disp -eq "winget") { $disp = "" }

                if ($name -and $id) {
                    $allSoftware += [PSCustomObject]@{
                        Id        = $id
                        Name      = $name
                        Version   = $ver
                        Available = $disp
                        Origin    = "Winget"
                    }
                }
            }
        }
    }

    if ($allSoftware.Count -eq 0) {
        $paths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
        )
        $reg = Get-ItemProperty $paths -ErrorAction SilentlyContinue | Where-Object DisplayName | Sort-Object DisplayName -Unique
        foreach ($item in $reg) {
            if ($item.DisplayName) {
                $cleanName = Repair-Mojibake $item.DisplayName
                $allSoftware += [PSCustomObject]@{
                    Id        = $cleanName
                    Name      = $cleanName
                    Version   = if ($item.DisplayVersion) { $item.DisplayVersion } else { "-" }
                    Available = ""
                    Origin    = "Windows Registry"
                }
            }
        }
    }
}

if ($allSoftware.Count -eq 0) {
    $allSoftware += [PSCustomObject]@{ Id = "Nenhum"; Name = "Nenhum software encontrado"; Version = "-"; Available = ""; Origin = "-" }
}

@{ Pacotes = @($allSoftware | Sort-Object Name -Unique) } | ConvertTo-Json -Depth 5 -Compress