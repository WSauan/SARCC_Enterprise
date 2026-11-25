<#
.SYNOPSIS
    Limpeza padrão de perfis inativos, pastas TEMP* órfãs, chaves .BAK e arquivos temporários.
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$DiasInatividade = 3
$UsuariosProtegidos = @(
    "Public", "Público", "Publico",
    "Default", "Default User", "defaultuser0", "Usuário Padrão", "Usuario Padrao",
    "All Users", "Todos os Usuários", "Todos os Usuarios",
    "administrator", "administrador", "adm.ebserh", "adm.wsauan", "welber.santos",
    "adm.bcaitano", "adm.michael", "adm.valdemir", "bruno.alves3", "adm.marcos", "marcos.vinycius"
)

$LogData = @{
    Script      = "Limpeza Padrao (Inatividade)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

function Remove-FolderAggressive ([string]$FolderPath) {
    if ([string]::IsNullOrWhiteSpace($FolderPath) -or -not (Test-Path -LiteralPath $FolderPath)) { return $true }
    try {
        $item = Get-Item -LiteralPath $FolderPath -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $false
        }
        Remove-Item -LiteralPath $FolderPath -Recurse -Force -ErrorAction Stop
    } catch {
        try {
            & cmd.exe /c "takeown /f `"$FolderPath`" /r /d y >nul 2>&1 & icacls `"$FolderPath`" /grant *S-1-5-32-544:F /t /c /q >nul 2>&1 & rd /s /q `"$FolderPath`" >nul 2>&1"
        } catch { }
    }
    return (-not (Test-Path -LiteralPath $FolderPath))
}

try {
    $HoraInicioStr = (Get-Date).ToString("HH:mm:ss")
    $DataHoraInicioObj = Get-Date
    $DataCorte = (Get-Date).AddDays(-$DiasInatividade)

    $DiscoInicial = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
    $EspacoLivreInicial = if ($DiscoInicial) { [math]::Round($DiscoInicial.FreeSpace / 1GB, 2) } else { 0 }
    $EspacoTotal = if ($DiscoInicial) { [math]::Round($DiscoInicial.Size / 1GB, 2) } else { 0 }

    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " INICIANDO LIMPEZA REMOTA - HOST: $($env:COMPUTERNAME)"
    $LogData.Detalhes += " Modo de Execucao: Padrao (Corte: $DiasInatividade dias + Expurgo TEMP)"
    $LogData.Detalhes += " Hora de Inicio: $HoraInicioStr"
    $LogData.Detalhes += " Espaco Livre Inicial (C:): $EspacoLivreInicial GB de $EspacoTotal GB"
    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " [1/4] Limpando Lixeira, Temp do Sistema e Chaves .BAK orfas..."

    try { Clear-RecycleBin -Confirm:$false -ErrorAction SilentlyContinue } catch { }
    foreach ($sysTemp in @("$env:SystemRoot\Temp", "$env:SystemDrive\Temp")) {
        if (Test-Path -LiteralPath $sysTemp) {
            Get-ChildItem -LiteralPath $sysTemp -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }

    $regProfileList = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
    $BakRemovidos = 0
    if (Test-Path -LiteralPath $regProfileList) {
        $bakKeys = @(Get-ChildItem -Path $regProfileList -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like "*.bak" })
        foreach ($k in $bakKeys) {
            try {
                Remove-Item -LiteralPath $k.PSPath -Recurse -Force -ErrorAction Stop
                $BakRemovidos++
            } catch {
                $LogData.Detalhes += "      !! Falha ao remover chave .bak '$($k.PSChildName)': $($_.Exception.Message)"
            }
        }
    }
    if ($BakRemovidos -gt 0) {
        $LogData.Detalhes += " -> Removidas $BakRemovidos chave(s) de perfil corrompidas (.bak) no Registro."
    }

    $LogData.Detalhes += " [2/4] Analisando Perfis WMI (Win32_UserProfile)..."
    $TodosPerfisWMI = @(Get-CimInstance Win32_UserProfile -ErrorAction SilentlyContinue)
    $CaminhosCarregados = @{}
    foreach ($p in $TodosPerfisWMI) {
        if ($p.Loaded -eq $true -and -not [string]::IsNullOrWhiteSpace($p.LocalPath)) {
            $CaminhosCarregados[$p.LocalPath.ToLower()] = $true
        }
    }

    $PerfisWMI = @($TodosPerfisWMI | Where-Object {
        ($_.Special -eq $false) -and
        (-not [string]::IsNullOrWhiteSpace($_.LocalPath)) -and
        ($_.LocalPath -notlike "*Public*") -and
        ($_.LocalPath -notmatch "(?i)defaultuser0|Default$")
    })

    $Removidos = 0; $Mantidos = 0; $Protegidos = 0; $TempOrfaosRemovidos = 0

    foreach ($perfil in $PerfisWMI) {
        $CaminhoPerfil = $perfil.LocalPath
        if ([string]::IsNullOrWhiteSpace($CaminhoPerfil)) { continue }

        $NomeUser = Split-Path -Path $CaminhoPerfil -Leaf -ErrorAction SilentlyContinue
        if ([string]::IsNullOrWhiteSpace($NomeUser)) { continue }

        if ($UsuariosProtegidos -contains $NomeUser) {
            $LogData.Detalhes += " [PROTEGIDO] $NomeUser"
            $Protegidos++
            continue
        }

        if ($perfil.Loaded -eq $true) {
            $LogData.Detalhes += " [EM USO] $NomeUser (Sessao ativa - Ignorado)"
            $Mantidos++
            continue
        }

        $IsTempProfile = ($NomeUser -match '^(?i)TEMP(\.|$)')
        $UltimoUso = $perfil.LastUseTime
        $ntUserPath = Join-Path $CaminhoPerfil "NTUSER.DAT"
        if ($null -eq $UltimoUso -and (Test-Path -LiteralPath $ntUserPath)) {
            $UltimoUso = (Get-Item -LiteralPath $ntUserPath -Force -ErrorAction SilentlyContinue).LastWriteTime
        }
        if ($null -eq $UltimoUso -and (Test-Path -LiteralPath $CaminhoPerfil)) {
            $UltimoUso = (Get-Item -LiteralPath $CaminhoPerfil -Force -ErrorAction SilentlyContinue).LastWriteTime
        }

        if ($IsTempProfile -or ($UltimoUso -and ($UltimoUso -lt $DataCorte))) {
            try {
                $perfil | Remove-CimInstance -ErrorAction Stop
                if (Test-Path -LiteralPath $CaminhoPerfil) {
                    $null = Remove-FolderAggressive $CaminhoPerfil
                }
                $LogData.Detalhes += " [REMOVIDO WMI] $NomeUser"
                $Removidos++
            } catch {
                if (Remove-FolderAggressive $CaminhoPerfil) {
                    $LogData.Detalhes += " [REMOVIDO FORCADO] $NomeUser"
                    $Removidos++
                } else {
                    $LogData.Detalhes += " [FALHA AO REMOVER] $NomeUser : $($_.Exception.Message)"
                    $Mantidos++
                }
            }
        } else {
            $userTemp = Join-Path $CaminhoPerfil "AppData\Local\Temp"
            if (Test-Path -LiteralPath $userTemp) {
                Get-ChildItem -LiteralPath $userTemp -Force -ErrorAction SilentlyContinue |
                    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
            }
            $LogData.Detalhes += " [MANTIDO - RECENTE] $NomeUser"
            $Mantidos++
        }
    }

    $LogData.Detalhes += " [3/4] Expurgando pastas temporarias orfas (TEMP*) em C:\Users..."
    $UsersRoot = "$env:SystemDrive\Users"
    if (Test-Path -LiteralPath $UsersRoot) {
        $PastasTemp = @(Get-ChildItem -LiteralPath $UsersRoot -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
            ($_.Name -match '^(?i)TEMP(\.|$)') -and
            (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0)
        })

        foreach ($pasta in $PastasTemp) {
            if ($CaminhosCarregados.ContainsKey($pasta.FullName.ToLower())) {
                $LogData.Detalhes += " [TEMP EM USO] $($pasta.Name) (Ignorado)"
                continue
            }
            if (Remove-FolderAggressive $pasta.FullName) {
                $TempOrfaosRemovidos++
            }
        }
    }
    $LogData.Detalhes += " -> Pastas temporarias orfas (TEMP*) eliminadas: $TempOrfaosRemovidos"

    $DiscoFinal = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
    $EspacoLivreApos = if ($DiscoFinal) { [math]::Round($DiscoFinal.FreeSpace / 1GB, 2) } else { $EspacoLivreInicial }
    $Liberado = [math]::Round(($EspacoLivreApos - $EspacoLivreInicial), 2)
    if ($Liberado -lt 0) { $Liberado = 0 }

    $HoraFinalStr = (Get-Date).ToString("HH:mm:ss")
    $TempoExecucao = (Get-Date) - $DataHoraInicioObj

    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += "                   RELATORIO DE EXECUCAO - GLPI"
    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " Hora Inicial              : $HoraInicioStr"
    $LogData.Detalhes += " Hora Final                : $HoraFinalStr"
    $LogData.Detalhes += " Tempo de Execucao         : $($TempoExecucao.ToString('hh\:mm\:ss'))"
    $LogData.Detalhes += "------------------------------------------------------------------------"
    $LogData.Detalhes += " Espaco Livre Antes        : $EspacoLivreInicial GB"
    $LogData.Detalhes += " Espaco Livre Apos         : $EspacoLivreApos GB"
    $LogData.Detalhes += " Total Liberado            : $Liberado GB"
    $LogData.Detalhes += "------------------------------------------------------------------------"
    $LogData.Detalhes += " Perfis WMI Removidos      : $Removidos"
    $LogData.Detalhes += " Pastas TEMP* Eliminadas   : $TempOrfaosRemovidos"
    $LogData.Detalhes += " Perfis Mantidos           : $Mantidos"
    $LogData.Detalhes += " Perfis Protegidos         : $Protegidos"
    $LogData.Detalhes += "========================================================================"

    $LogData.Mensagem = "Limpeza padrão concluída: $Liberado GB liberado(s) em C: ($Removidos perfil(is) e $TempOrfaosRemovidos pasta(s) TEMP* removida(s))."
} catch {
    $LogData.StatusFinal = "ERRO FATAL"
    $LogData.Mensagem = "Falha crítica na limpeza padrão: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}