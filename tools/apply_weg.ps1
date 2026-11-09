# Turn WhateverGreen (with -igfxvesa -wegnoegpu) on or off, on the Seagate EFI partition and in the local build copy.
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_weg.ps1 on
#                        powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_weg.ps1 off
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
# The first run of this or safe_mode.ps1 keeps the Seagate's original config as config.plist.orig next to it.
param([Parameter(Mandatory)][ValidateSet('on', 'off')][string]$Mode)
$ErrorActionPreference = 'Stop'
$src   = 'D:\Nullmorth-macos\build\extracted\WhateverGreen\WhateverGreen.kext'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }
if ($Mode -eq 'on' -and -not (Test-Path "$src\Contents\MacOS\WhateverGreen")) { throw "Missing $src" }

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
$cand = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$d = $cand[0]
$esp = @(Get-Partition -DiskNumber $d.Number | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
if ($esp.Count -ne 1) { throw "Expected one EFI partition on disk $($d.Number), found $($esp.Count)." }

$used = (Get-Volume).DriveLetter
$letter = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used } | Select-Object -First 1
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_weg_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_weg_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_weg_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $oc = "${letter}:\EFI\OC"
    if (-not (Test-Path "$oc\config.plist.orig")) { Copy-Item "$oc\config.plist" "$oc\config.plist.orig" }
    foreach ($kexts in "$oc\Kexts", "$build\Kexts") {
        if (Test-Path "$kexts\WhateverGreen.kext") { Remove-Item -Recurse -Force "$kexts\WhateverGreen.kext" }
        if ($Mode -eq 'on') { Copy-Item -Recurse $src "$kexts\WhateverGreen.kext" }
    }
    python -I "$PSScriptRoot\apply_weg.py" $Mode "$oc\config.plist" "$build\config.plist"
    if ($LASTEXITCODE -ne 0) { throw "apply_weg.py failed ($LASTEXITCODE)." }
} finally {
    diskpart /s "$env:TEMP\nm_weg_off.txt" | Out-Null
}
if ($Mode -eq 'on') {
    Write-Host "`nWhateverGreen is ON. Boot MacHD from the Seagate; the launchd line 'boot-args = ...' should end with -igfxvesa -wegnoegpu." -ForegroundColor Green
} else {
    Write-Host "`nWhateverGreen is OFF. The EFI is back to how it was before apply_weg.ps1 on." -ForegroundColor Green
}
