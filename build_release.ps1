<#
.SYNOPSIS
    Script oficial de Build e Empacotamento do SARCC Enterprise.
    Le a versao de core/version.py, valida CHANGELOG.md e testes unitarios,
    compila via PyInstaller e monta o pacote de distribuicao.
#>
param(
    [string]$Version = "",
    [switch]$SkipChangelogCheck
)

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = "Continue"

# Caracteres Unicode imunes a falta de BOM no PowerShell 5.1
$c_a_til  = [char]0x00E3 # ã
$c_a_ag   = [char]0x00E1 # á
$c_c_ced  = [char]0x00E7 # ç
$c_I_ag   = [char]0x00CD # Í

# 0. Leitura automatica da versao a partir de core/version.py
$VersionFile = Join-Path $PSScriptRoot "core\version.py"
$DetectedVersion = ""
if (Test-Path $VersionFile) {
    $verContent = Get-Content -Path $VersionFile -Raw -Encoding UTF8
    if ($verContent -match '__version__\s*=\s*["'']([^"'']+)["'']') {
        $DetectedVersion = $Matches[1].Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    if ([string]::IsNullOrWhiteSpace($DetectedVersion)) {
        Write-Host "ERRO: N${c_a_til}o foi poss${[char]0x00ED}vel detectar __version__ em core\version.py e -Version n${c_a_til}o foi informado." -ForegroundColor Red
        exit 1
    }
    $Version = $DetectedVersion
    Write-Host "Vers${c_a_til}o detectada automaticamente em core\version.py: v$Version" -ForegroundColor Gray
} elseif (-not [string]::IsNullOrWhiteSpace($DetectedVersion) -and $Version -ne $DetectedVersion) {
    Write-Host "ERRO: Diverg${[char]0x00EA}ncia de vers${c_a_til}o! Par${[char]0x00E2}metro -Version '$Version' difere de core\version.py ('$DetectedVersion')." -ForegroundColor Red
    exit 1
}

# Validacao da presenca da versao no CHANGELOG.md
$ChangelogFile = Join-Path $PSScriptRoot "CHANGELOG.md"
if (-not $SkipChangelogCheck) {
    if (-not (Test-Path $ChangelogFile)) {
        Write-Host "ERRO: Arquivo CHANGELOG.md n${c_a_til}o encontrado na raiz do projeto." -ForegroundColor Red
        exit 1
    }
    $changelogText = Get-Content -Path $ChangelogFile -Raw -Encoding UTF8
    $escapedVer = [regex]::Escape($Version)
    if ($changelogText -notmatch "\[\s*v?$escapedVer\s*\]") {
        Write-Host "ERRO: A vers${c_a_til}o 'v$Version' ainda n${c_a_til}o est${c_a_ag} documentada no CHANGELOG.md!" -ForegroundColor Red
        Write-Host "Atualize o CHANGELOG.md antes de gerar a build (ou use -SkipChangelogCheck para ignorar)." -ForegroundColor Yellow
        exit 1
    }
}

$DateStamp = (Get-Date).ToString("yyyyMMdd")
$ExeName = "SARCC_v${Version}_${DateStamp}"
$ReleaseFolder = Join-Path $PSScriptRoot "releases\$ExeName"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " INICIANDO EMPACOTAMENTO: $ExeName" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Validacao dos Testes Automatizados antes do Build
Write-Host "`n[1/5] Executando bateria de testes (pytest)..." -ForegroundColor Yellow
& python generate_manifest.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Falha ao gerar o manifest.json dos scripts." -ForegroundColor Red
    exit 1
}

& pytest -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: O empacotamento foi abortado porque um ou mais testes falharam!" -ForegroundColor Red
    exit 1
}

# 2. Verifica se o PyInstaller esta instalado no ambiente virtual (.venv)
Write-Host "`n[2/5] Verificando PyInstaller..." -ForegroundColor Yellow
& python -c "import PyInstaller" >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller n${c_a_til}o encontrado na .venv. Instalando automaticamente..." -ForegroundColor Gray
    & python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRO: Falha ao instalar o PyInstaller." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "PyInstaller localizado com sucesso." -ForegroundColor Green
}

# 3. Limpeza de builds temporarios anteriores
Write-Host "`n[3/5] Limpando cache de compila${c_c_ced}${c_a_til}o anterior..." -ForegroundColor Yellow
$ErrorActionPreference = "Stop"
if (Test-Path "$PSScriptRoot\build") { Remove-Item "$PSScriptRoot\build" -Recurse -Force }
if (Test-Path "$PSScriptRoot\dist")  { Remove-Item "$PSScriptRoot\dist" -Recurse -Force }
if (Test-Path "$PSScriptRoot\$ExeName.spec") { Remove-Item "$PSScriptRoot\$ExeName.spec" -Force }

# 4. Compilacao do Executavel com PyInstaller
Write-Host "`n[4/5] Compilando execut${c_a_ag}vel '$ExeName.exe' (Aguarde 1 a 2 minutos)..." -ForegroundColor Yellow
$ErrorActionPreference = "Continue"
$pyArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--uac-admin",
    "--name", $ExeName,
    "--icon", "logo.ico",
    "--add-data", "logo.ico;.",
    "--add-data", "logo.png;.",
    "--add-data", "core/scripts;core/scripts",
    "--add-data", "gui/theme;gui/theme",
    "main.py"
)
& python @pyArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Falha durante a compila${c_c_ced}${c_a_til}o com o PyInstaller." -ForegroundColor Red
    exit 1
}

# 5. Montagem da Pasta de Distribuicao (Portatil e Completa)
Write-Host "`n[5/5] Montando pacote final em: $ReleaseFolder" -ForegroundColor Yellow
$ErrorActionPreference = "Stop"
if (Test-Path $ReleaseFolder) { Remove-Item $ReleaseFolder -Recurse -Force }
New-Item -ItemType Directory -Path $ReleaseFolder -Force | Out-Null
New-Item -ItemType Directory -Path "$ReleaseFolder\data" -Force | Out-Null

# Copia o executavel compilado
Copy-Item -Path "$PSScriptRoot\dist\$ExeName.exe" -Destination "$ReleaseFolder\$ExeName.exe" -Force

# Copia dependencias externas e scripts para garantir funcionamento 100% portatil
foreach ($file in @("logo.ico", "logo.png", "vncviewer.exe", "options.vnc")) {
    if (Test-Path "$PSScriptRoot\$file") {
        Copy-Item -Path "$PSScriptRoot\$file" -Destination "$ReleaseFolder\$file" -Force
    }
}
if (Test-Path "$PSScriptRoot\core\scripts") {
    New-Item -ItemType Directory -Path "$ReleaseFolder\core" -Force | Out-Null
    Copy-Item -Path "$PSScriptRoot\core\scripts" -Destination "$ReleaseFolder\core\scripts" -Recurse -Force
}

# Gera arquivo ZIP pronto para backup/distribuicao
$ZipPath = "$PSScriptRoot\releases\$ExeName.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$ReleaseFolder\*" -DestinationPath $ZipPath -Force

# Limpa pastas temporarias do PyInstaller na raiz
Remove-Item "$PSScriptRoot\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$PSScriptRoot\dist" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$PSScriptRoot\$ExeName.spec" -Force -ErrorAction SilentlyContinue

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " EMPACOTAMENTO CONCLU${c_I_ag}DO COM SUCESSO!" -ForegroundColor Green
Write-Host " Execut${c_a_ag}vel : $ReleaseFolder\$ExeName.exe" -ForegroundColor Green
Write-Host " Pacote ZIP : $ZipPath" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green