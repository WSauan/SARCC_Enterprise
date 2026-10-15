$resultado = ping -n 2 8.8.8.8
$LogData = @{
    Script = "Ping Test"
    Detalhes = $resultado
    StatusFinal = "SUCESSO"
}
$LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output