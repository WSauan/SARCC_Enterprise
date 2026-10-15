$DiasInatividade = 3
$UsuariosProtegidos = @("Public", "default", "defaultuser0", "administrator", "administrador", "adm.ebserh", "adm.wsauan", "welber.santos", "adm.bcaitano", "adm.michael", "adm.valdemir", "bruno.alves3", "adm.marcos", "marcos.vinycius")

$LogData = @{ Script = "Limpeza Padrao (Inatividade)"; Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Computador = $env:COMPUTERNAME; StatusFinal = "SUCESSO"; Detalhes = @() }

try {
    $HoraInicioStr = (Get-Date).ToString("HH:mm:ss")
    $DataHoraInicioObj = Get-Date
    
    $DiscoInicial = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $EspacoLivreInicial = [math]::Round($DiscoInicial.FreeSpace / 1GB, 2)
    $EspacoTotal = [math]::Round($DiscoInicial.Size / 1GB, 2)

    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " INICIANDO LIMPEZA REMOTA - HOST: $($env:COMPUTERNAME)"
    $LogData.Detalhes += " Modo de Execucao: Padrao (Corte: $DiasInatividade dias)"
    $LogData.Detalhes += " Hora de Inicio: $HoraInicioStr"
    $LogData.Detalhes += " Espaco Livre Inicial (C:): $EspacoLivreInicial GB de $EspacoTotal GB"
    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " Limpando Lixeira e Temporarios antigos..."
    
    Clear-RecycleBin -Confirm:$false -ErrorAction SilentlyContinue
    Get-ChildItem -Path "$env:SystemRoot\Temp", "$env:SystemDrive\Temp" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $DataCorte = (Get-Date).AddDays(-$DiasInatividade)
    $PerfisWMI = Get-CimInstance Win32_UserProfile | Where-Object { ($_.Special -eq $false) -and ($_.LocalPath -notlike "*Public*") -and ($_.LocalPath -notmatch "defaultuser0|Default") }

    $Removidos = 0; $Mantidos = 0; $Protegidos = 0

    foreach ($perfil in $PerfisWMI) {
        $NomeUser = Split-Path $perfil.LocalPath -Leaf

        if ($UsuariosProtegidos -contains $NomeUser) {
            $LogData.Detalhes += " $NomeUser (Perfil Protegido)"
            $Protegidos++
            continue
        }
        if ($perfil.Loaded -eq $true) {
            $LogData.Detalhes += " $NomeUser (Em Uso - Ignorado)"
            $Mantidos++
            continue
        }

        $UltimoUso = $perfil.LastUseTime
        if ($null -eq $UltimoUso -and (Test-Path "$($perfil.LocalPath)\NTUSER.DAT")) { 
            $UltimoUso = (Get-Item "$($perfil.LocalPath)\NTUSER.DAT" -Force).LastWriteTime 
        }

        if ($UltimoUso -and ($UltimoUso -lt $DataCorte)) {
            try {
                $perfil | Remove-CimInstance -ErrorAction Stop
                $LogData.Detalhes += " $NomeUser (REMOVIDO)"
                $Removidos++
            } catch {
                $LogData.Detalhes += " $($NomeUser) (FALHA AO REMOVER)"
                $Mantidos++
            }
        } else {
            $LogData.Detalhes += " $NomeUser (Acesso Recente - Mantido)"
            $Mantidos++
        }
    }

    $DiscoFinal = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $EspacoLivreApos = [math]::Round($DiscoFinal.FreeSpace / 1GB, 2)
    $Liberado = $EspacoLivreApos - $EspacoLivreInicial
    if ($Liberado -lt 0) { $Liberado = 0 }

    $HoraFinalStr = (Get-Date).ToString("HH:mm:ss")
    $TempoExecucao = (Get-Date) - $DataHoraInicioObj

    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += "                   RELATORIO DE EXECUCAO - GLPI"
    $LogData.Detalhes += "========================================================================"
    $LogData.Detalhes += " Hora Inicial       : $HoraInicioStr"
    $LogData.Detalhes += " Hora Final         : $HoraFinalStr"
    $LogData.Detalhes += " Tempo de Execucao  : $($TempoExecucao.ToString('hh\:mm\:ss'))"
    $LogData.Detalhes += "------------------------------------------------------------------------"
    $LogData.Detalhes += " Espaco Livre Antes : $EspacoLivreInicial GB"
    $LogData.Detalhes += " Espaco Livre Apos  : $EspacoLivreApos GB"
    $LogData.Detalhes += " Total Liberado     : $Liberado GB"
    $LogData.Detalhes += "------------------------------------------------------------------------"
    $LogData.Detalhes += " Perfis Removidos   : $Removidos"
    $LogData.Detalhes += " Perfis Mantidos    : $Mantidos"
    $LogData.Detalhes += " Perfis Protegidos  : $Protegidos"
    $LogData.Detalhes += "========================================================================"

} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += "Falha critica: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}