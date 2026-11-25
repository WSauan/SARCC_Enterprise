<#
.SYNOPSIS
    Limpeza de cache dos navegadores (Chrome, Edge, Firefox) para todos os perfis.
.NOTES
    - Não requer credenciais (opera apenas em disco local).
    - Pode ser agendado como SYSTEM ou executado via SARCC.
    - Apaga APENAS cache (não cookies, senhas, histórico, favoritos).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

# ============================================
# CONFIGURAÇÃO — EDITE AQUI
# ============================================
$BrowsersToClean     = @("chrome", "edge", "firefox")
$KillRunningBrowsers = $true
$CleanChromeProfiles = $true
# ============================================

$LogData = @{
    Script      = "Limpeza de Cache dos Navegadores"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

$ChromiumCacheSubdirs = @(
    "Cache\Cache_Data",
    "Code Cache",
    "GPUCache",
    "Service Worker\CacheStorage",
    "Service Worker\ScriptCache",
    "Media Cache",
    "ShaderCache",
    "GrShaderCache"
)

$FirefoxCacheSubdirs = @(
    "cache2",
    "startupCache",
    "shader-cache",
    "thumbnails"
)

function Get-Bytes {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return [long]0 }
    try {
        $sum = (Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
                Where-Object { -not $_.PSIsContainer } |
                Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { return [long]0 }
        return [long]$sum
    } catch {
        return [long]0
    }
}

function Format-Size {
    param([long]$Bytes)
    if ($Bytes -lt 1KB) { return "$Bytes B" }
    if ($Bytes -lt 1MB) { return ("{0:N1} KB" -f ($Bytes / 1KB)) }
    if ($Bytes -lt 1GB) { return ("{0:N1} MB" -f ($Bytes / 1MB)) }
    return ("{0:N2} GB" -f ($Bytes / 1GB))
}

function Remove-CachePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        Start-Sleep -Milliseconds 250
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            return $false
        }
    }
}

try {
    $selectedBrowsers = @($BrowsersToClean | ForEach-Object { $_.ToString().Trim().ToLower() } | Where-Object { $_ })

    if ($KillRunningBrowsers) {
        $LogData.Detalhes += "[0/5] Encerrando processos dos navegadores..."
        foreach ($procName in @("chrome", "msedge", "firefox")) {
            try {
                $running = @(Get-Process -Name $procName -ErrorAction SilentlyContinue)
                if ($running.Count -gt 0) {
                    $running | Stop-Process -Force -ErrorAction Stop
                    $LogData.Detalhes += "      -> ${procName}: $($running.Count) processo(s) encerrado(s)."
                }
            } catch {
                $LogData.Detalhes += "      !! Aviso ao encerrar ${procName}: $($_.Exception.Message)"
            }
        }
        Start-Sleep -Seconds 2
    }

    $LogData.Detalhes += "[1/5] Enumerando perfis de usuário..."
    $usuarios = @(Get-ChildItem -Path "C:\Users" -Directory -Force -ErrorAction Stop |
                  Where-Object { $_.Name -notmatch '^(Public|Público|Default|All Users|Default User|Usuário Padrão)$' })
    $LogData.Detalhes += "      -> $($usuarios.Count) perfil(is) encontrado(s)."

    [long]$totalLib = 0
    $totalArquivosIgnorados = 0

    if ($selectedBrowsers -contains "chrome" -or $selectedBrowsers -contains "edge") {
        $LogData.Detalhes += "[2/5] Limpando navegadores Chromium (Chrome/Edge)..."
        $chromiumBrowsers = @(
            @{ Key = "chrome"; Nome = "Chrome"; Pasta = "Google\Chrome\User Data" },
            @{ Key = "edge";   Nome = "Edge";   Pasta = "Microsoft\Edge\User Data" }
        )

        foreach ($user in $usuarios) {
            foreach ($browser in $chromiumBrowsers) {
                if ($selectedBrowsers -notcontains $browser.Key) { continue }

                $userDataPath = Join-Path $user.FullName $browser.Pasta
                if (-not (Test-Path -LiteralPath $userDataPath)) { continue }

                $perfis = @(Get-ChildItem -LiteralPath $userDataPath -Directory -ErrorAction SilentlyContinue |
                            Where-Object { $_.Name -match '^(Default|Profile \d+)$' })

                if (-not $CleanChromeProfiles) {
                    $perfis = @($perfis | Where-Object { $_.Name -eq "Default" })
                }

                foreach ($perfil in $perfis) {
                    foreach ($sub in $ChromiumCacheSubdirs) {
                        $cachePath = Join-Path $perfil.FullName $sub
                        if (Test-Path -LiteralPath $cachePath) {
                            $sizeBefore = Get-Bytes -Path $cachePath
                            if (Remove-CachePath -Path $cachePath) {
                                $totalLib += $sizeBefore
                                $LogData.Detalhes += "      [$($user.Name)] $($browser.Nome) / $($perfil.Name) / $sub : $(Format-Size $sizeBefore)"
                            } else {
                                $totalArquivosIgnorados++
                                $LogData.Detalhes += "      [$($user.Name)] $($browser.Nome) / $($perfil.Name) / $sub : BLOQUEADO"
                            }
                        }
                    }
                }
            }
        }
    }

    if ($selectedBrowsers -contains "firefox") {
        $LogData.Detalhes += "[3/5] Limpando Firefox..."
        foreach ($user in $usuarios) {
            $roots = @(
                (Join-Path $user.FullName "AppData\Roaming\Mozilla\Firefox\Profiles"),
                (Join-Path $user.FullName "AppData\Local\Mozilla\Firefox\Profiles")
            )

            foreach ($root in $roots) {
                if (-not (Test-Path -LiteralPath $root)) { continue }

                $perfis = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)
                foreach ($perfil in $perfis) {
                    foreach ($sub in $FirefoxCacheSubdirs) {
                        $cachePath = Join-Path $perfil.FullName $sub
                        if (Test-Path -LiteralPath $cachePath) {
                            $sizeBefore = Get-Bytes -Path $cachePath
                            if (Remove-CachePath -Path $cachePath) {
                                $totalLib += $sizeBefore
                                $LogData.Detalhes += "      [$($user.Name)] Firefox / $($perfil.Name) / $sub : $(Format-Size $sizeBefore)"
                            } else {
                                $totalArquivosIgnorados++
                                $LogData.Detalhes += "      [$($user.Name)] Firefox / $($perfil.Name) / $sub : BLOQUEADO"
                            }
                        }
                    }
                }
            }
        }
    }

    $LogData.Detalhes += "[4/5] Limpando temporários dos navegadores em Temp..."
    foreach ($user in $usuarios) {
        $tempPath = Join-Path $user.FullName "AppData\Local\Temp"
        if (Test-Path -LiteralPath $tempPath) {
            $temps = @(Get-ChildItem -LiteralPath $tempPath -ErrorAction SilentlyContinue |
                       Where-Object { $_.Name -match '^(?i)(chrome|msedge|firefox|mozilla|crashpad)' })
            foreach ($t in $temps) {
                $sizeBefore = Get-Bytes -Path $t.FullName
                if (Remove-CachePath -Path $t.FullName) {
                    $totalLib += $sizeBefore
                    $LogData.Detalhes += "      [$($user.Name)] Temp / $($t.Name) : $(Format-Size $sizeBefore)"
                } else {
                    $totalArquivosIgnorados++
                }
            }
        }
    }

    $LogData.Detalhes += "[5/5] Resultado final:"
    $LogData.Detalhes += "      -> Total liberado: $(Format-Size $totalLib)"
    if ($totalArquivosIgnorados -gt 0) {
        $LogData.Detalhes += "      -> $totalArquivosIgnorados item(ns) bloqueado(s) (navegador em uso)"
    }

    $LogData.Mensagem = "Limpeza concluída. Total liberado: $(Format-Size $totalLib). Navegadores: $($selectedBrowsers -join ', ')."
    if ($totalArquivosIgnorados -gt 0 -and $totalLib -eq 0) {
        $LogData.StatusFinal = "ALERTA"
    }
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}