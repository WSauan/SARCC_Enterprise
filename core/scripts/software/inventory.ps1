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
        # NOVO (R07): Uso de JSON em vez de Substring
        $jsonOut = & $wingetCmd list --output json --accept-source-agreements --disable-interactivity 2>$null
        $jsonStr = $jsonOut -join "`n"

        try {
            $parsed = $jsonStr | ConvertFrom-Json
            foreach ($src in $parsed.Sources) {
                foreach ($pkg in $src.Packages) {
                    $allSoftware += [PSCustomObject]@{
                        Id        = $pkg.PackageIdentifier
                        Name      = (Repair-Mojibake $pkg.PackageName)
                        Version   = $pkg.InstalledVersion
                        Available = if ($pkg.AvailableVersion) { $pkg.AvailableVersion } else { "" }
                        Origin    = "Winget"
                    }
                }
            }
        } catch {
            # Se falhar o JSON, cai no fallback do registro
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