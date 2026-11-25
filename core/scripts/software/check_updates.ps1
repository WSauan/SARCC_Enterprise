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
        $cout = & $choco outdated --limit-output 2>$null
        if ($null -ne $cout) {
            foreach ($c in $cout) {
                if ([string]::IsNullOrWhiteSpace($c)) { continue }
                $p = $c.ToString().Split('|')
                if ($p.Length -ge 3) { $outdatedPkgs[$p[0].Trim()] = $p[2].Trim() }
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
        $jsonOut = & $wingetCmd upgrade --include-unknown --output json --accept-source-agreements --disable-interactivity 2>$null
        $jsonStr = $jsonOut -join "`n"

        try {
            $parsed = $jsonStr | ConvertFrom-Json
            foreach ($src in $parsed.Sources) {
                foreach ($pkg in $src.Packages) {
                    if ($pkg.AvailableVersion) {
                        $outdatedPkgs[$pkg.PackageIdentifier] = $pkg.AvailableVersion
                    }
                }
            }
        } catch {
            # Se o JSON falhar, retorna vazio
        }
    }
}

@{ Atualizacoes = $outdatedPkgs } | ConvertTo-Json -Depth 5 -Compress