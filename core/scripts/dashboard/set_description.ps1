<#
.SYNOPSIS
    Atualiza a Descrição do Computador (Local / Setor) via WMI/CIM e Registro (LanmanServer).
#>
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

$NewDesc = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{{desc_b64}}')).Trim()

$LogData = @{
    Script      = "Alterar Descrição do Computador"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
    Mensagem    = ""
}

try {
    # 1. Atualiza no Registro do LanmanServer (efeito imediato)
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
    Set-ItemProperty -Path $regPath -Name "srvcomment" -Value $NewDesc -Type String -Force -ErrorAction Stop
    $LogData.Detalhes += "Registro LanmanServer (srvcomment) atualizado para: '$NewDesc'"

    # 2. Atualiza na classe WMI/CIM Win32_OperatingSystem
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    Set-CimInstance -InputObject $os -Property @{ Description = $NewDesc } -ErrorAction Stop
    $LogData.Detalhes += "Propriedade Win32_OperatingSystem.Description sincronizada."

    $LogData.Mensagem = "Descrição da máquina alterada com sucesso para: '$NewDesc'"
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Mensagem = "Falha ao alterar descrição: $($_.Exception.Message)"
    $LogData.Detalhes += "ERRO: $($_.Exception.Message)"
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}