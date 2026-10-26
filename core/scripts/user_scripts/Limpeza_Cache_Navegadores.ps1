<#
.SYNOPSIS
    Limpeza de cache dos navegadores (Chrome, Edge, Firefox) para todos os perfis.
.NOTES
    - Não requer credenciais (opera apenas em disco local).
    - Pode ser agendado como SYSTEM ou executado via SARCC.
    - Apaga APENAS cache (não cookies, senhas, histórico, favoritos).
    - Opcional: mata processos dos navegadores antes (força fechamento).
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ============================================
# CONFIGURAÇÃO — EDITE AQUI
# ============================================
$BrowsersToClean    = @("chrome", "edge", "firefox")   # Subconjunto possível
$KillRunningBrowsers = $true                            # Mata os navegadores antes (força fechamento)
$CleanChromeProfiles = $true                            # Se $false, só o perfil "Default"
# ============================================

$LogData = @{
    Script      = "Limpeza de Cache dos Navegadores"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

# Subpastas de cache relativas à raiz de cada perfil Chromium
$ChromiumCacheSubdirs = @(
    "Cache\Cache_Data",
    "Code Cache\js",
    "Code Cache\wasm",
    "GPUCache",
    "Service Worker\CacheStorage",
    "Service Worker\ScriptCache",
    "Media Cache",
    "ShaderCache",
    "GrShaderCache"
)

# Subpastas de cache Firefox (relativas ao perfil)
$FirefoxCacheSubdirs = @(
    "cache2",
    "startupCache",
    "shader-cache",
    "thumbnails"
)

function Get-Bytes {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    try {
        $sum = (Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { return 0 }
        return $sum
    } catch { return 0 }
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
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        # Algumas vezes o Windows bloqueia 1-2 arquivos; tenta de novo
        Start-Sleep -Milliseconds 200
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            return $false
        }
    }
}

try {
    # --- [0/5] Matar navegadores (opcional) ---
    if ($KillRunningBrowsers) {
        $LogData.Detalhes += "[0/5] Encerrando processos dos navegadores..."
        foreach ($proc in @("chrome", "msedge", "firefox")) {
            $running = Get-Process -Name $proc -ErrorAction SilentlyContinue
            if ($running) {
                $running | Stop-Process -Force -ErrorAction SilentlyContinue
                $LogData.Detalhes += "      -> $proc: $($running.Count) processo(s) encerrado(s)."
            }
        }
        Start-Sleep -Seconds 2
    }

    # --- [1/5] Enumerar usuários em C:\Users ---
    $LogData.Detalhes += "[1/5] Enumerando perfis de usuário..."
    $usuarios = Get-ChildItem -Path "C:\Users" -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notmatch '^(Public|Público|Default|All Users|Default User|Usuário Padrão)$' }
    $LogData.Detalhes += "      -> $($usuarios.Count) perfil(is) encontrado(s)."

    $totalLib = 0
    $totalArquivosIgnorados = 0

    # --- [2/5] Chrome + Edge (Chromium) ---
    if ($BrowsersToClean -contains "chrome" -or $BrowsersToClean -contains "edge") {
        $LogData.Detalhes += "[2/5] Limpando navegadores Chromium (Chrome/Edge)..."

        $chromiumBrowsers = @(
            @{ Nome="Chrome"; Pasta="Google\Chrome\User Data" },
            @{ Nome="Edge";   Pasta="Microsoft\Edge\User Data" }
        )

        foreach ($user in $usuarios) {
            foreach ($browser in $chromiumBrowsers) {
                if ($browser.Nome -eq "chrome" -and $BrowsersToClean -notcontains "chrome") { continue }
                if ($browser.Nome -eq "edge"   -and $BrowsersToClean -notcontains "edge")   { continue }

                $userDataPath = Join-Path $user.FullName "$($browser.Pasta)"
                if (-not (Test-Path -LiteralPath $userDataPath)) { continue }

                # Perfis disponíveis: Default, Profile 1, Profile 2...
                $perfis = Get-ChildItem -LiteralPath $userDataPath -Directory -ErrorAction SilentlyContinue |
                          Where-Object { $_.Name -match '^(Default|Profile \d+)$' }

                if (-not $CleanChromeProfiles) {
                    $perfis = $perfis | Where-Object { $_.Name -eq "Default" }
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

    # --- [3/5] Firefox ---
    if ($BrowsersToClean -contains "firefox") {
        $LogData.Detalhes += "[3/5] Limpando Firefox..."

        foreach ($user in $usuarios) {
            # Firefox tem cache em %APPDATA% e às vezes em %LOCALAPPDATA%
            $roots = @(
                (Join-Path $user.FullName "AppData\Roaming\Mozilla\Firefox\Profiles"),
                (Join-Path $user.FullName "AppData\Local\Mozilla\Firefox\Profiles")
            )

            foreach ($root in $roots) {
                if (-not (Test-Path -LiteralPath $root)) { continue }

                $perfis = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue
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

    # --- [4/5] Resumo ---
    $LogData.Detalhes += "[4/5] Limpando temporários dos navegadores em Temp..."
    foreach ($user in $usuarios) {
        # Remove temp files de navegadores em Temp
        $tempPath = Join-Path $user.FullName "AppData\Local\Temp"
        if (Test-Path -LiteralPath $tempPath) {
            $temps = Get-ChildItem -LiteralPath $tempPath -ErrorAction SilentlyContinue |
                     Where-Object { $_.Name -match '^(chrome|msedge|firefox|mozilla|crashpad)' }
            foreach ($t in $temps) {
                $sizeBefore = Get-Bytes -Path $t.FullName
                if (Remove-CachePath -Path $t.FullName) {
                    $totalLib += $sizeBefore
                    $LogData.Detalhes += "      [$($user.Name)] Temp / $($t.Name) : $(Format-Size $sizeBefore)"
                }
            }
        }
    }

    # --- [5/5] Resultado ---
    $LogData.Detalhes += "[5/5] Resultado final:"
    $LogData.Detalhes += "      -> Total liberado: $(Format-Size $totalLib)"
    if ($totalArquivosIgnorados -gt 0) {
        $LogData.Detalhes += "      -> $totalArquivosIgnorados item(ns) bloqueado(s) (navegador em uso)"
    }

    $LogData.Mensagem = "Limpeza concluída. Total liberado: $(Format-Size $totalLib). Navegadores: $($BrowsersToClean -join ', ')."
    if ($totalArquivosIgnorados -gt 0 -and $totalLib -eq 0) {
        $LogData.StatusFinal = "ALERTA"
    }

} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha: $($_.Exception.Message)"
    $LogData.Detalhes += "EXCEÇÃO: $($_.ScriptStackTrace)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
}