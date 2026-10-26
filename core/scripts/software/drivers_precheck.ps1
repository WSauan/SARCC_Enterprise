# Pré-checagem de drivers (Multi-categoria)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Stop'

try {
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin   = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    $Sys = Get-CimInstance -ClassName Win32_ComputerSystem
    $Manuf = $Sys.Manufacturer.Trim()
    $Model = $Sys.Model.Trim()

    $CategoriesStr = '{{category}}'
    $Categories = $CategoriesStr -split ','
    
    $Drivers = Get-WindowsDriver -Online

    $MatchedCount = 0
    foreach ($drv in $Drivers) {
        $ClassName = $drv.ClassName
        $Match = $false
        foreach ($cat in $Categories) {
            $catTrimmed = $cat.Trim()
            if ($catTrimmed -eq "Camera_Image" -and $ClassName -match "(?i)^(Camera|Image)$") { $Match = $true; break }
            elseif ($ClassName -match "(?i)^$catTrimmed$") { $Match = $true; break }
        }
        if ($Match) { $MatchedCount++ }
    }

    @{
        Status = "OK"
        Manuf  = $Manuf
        Model  = $Model
        Count  = $MatchedCount
    } | ConvertTo-Json -Compress
} catch {
    $msgOriginal = $_.Exception.Message
    $msgAmigavel = $msgOriginal
    if ($msgOriginal -match "eleva|elevação|elevation|privilégio|privilege") {
        $msgAmigavel = "O comando Get-WindowsDriver exige que o SARCC seja executado como Administrador."
    }
    @{
        Status = "ERRO"
        Msg    = $msgAmigavel
    } | ConvertTo-Json -Compress
}