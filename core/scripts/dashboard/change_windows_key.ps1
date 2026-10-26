# Injeta uma chave GVLK (KMS) no Windows alvo.
# Variáveis: {{gblk_key}}, {{version_name}}

$key     = '{{gblk_key}}'
$version = '{{version_name}}'

$LogData = @{
    Script      = "Mudança de Chave Windows ($version)"
    Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Computador  = $env:COMPUTERNAME
    StatusFinal = "SUCESSO"
    Detalhes    = @()
}

try {
    $LogData.Detalhes += "Injetando a chave GVLK: $key..."
    $out = cscript.exe C:\Windows\System32\slmgr.vbs /ipk $key 2>&1
    $LogData.Detalhes += ($out -join " ")
    $LogData.Detalhes += "O Windows validará a nova versão com o KMS/AD em segundo plano."
} catch {
    $LogData.StatusFinal = "ERRO"
    $LogData.Detalhes += $_.Exception.Message
} finally {
    $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
}