# Copy a whole EFI folder (default: the output of tools\build_efi.py) to the Seagate EFI partition.
# The EFI that was there is kept as EFI-prev on the same partition; recovery files, WEX\, nm_*logs stay.
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\deploy_efi.ps1
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\deploy_efi.ps1 -Source D:\Nullmorth-macos\build\EFI-backup-tahoe-working-20261106
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\deploy_efi.ps1 -Previous   (swap EFI and EFI-prev back)
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL).
param([string]$Source = 'D:\Nullmorth-macos\build\USB\EFI', [switch]$Previous)
$ErrorActionPreference = 'Stop'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }
if (-not $Previous) {
    foreach ($need in "$Source\BOOT\BOOTx64.efi", "$Source\OC\OpenCore.efi", "$Source\OC\config.plist") {
        if (-not (Test-Path $need)) { throw "Not an OpenCore EFI folder: missing $need" } }
}

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
$cand = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$d = $cand[0]
$esp = @(Get-Partition -DiskNumber $d.Number | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
if ($esp.Count -ne 1) { throw "Expected one EFI partition on disk $($d.Number), found $($esp.Count)." }

$used = (Get-Volume).DriveLetter
$letter = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used } | Select-Object -First 1
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_dep_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_dep_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_dep_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $root = "${letter}:\"
    if ($Previous) {
        if (-not (Test-Path "${root}EFI-prev\OC\OpenCore.efi")) { throw 'No EFI-prev on the EFI partition.' }
        Rename-Item "${root}EFI" 'EFI-swap'
        Rename-Item "${root}EFI-prev" 'EFI'
        Rename-Item "${root}EFI-swap" 'EFI-prev'
        Write-Host 'Swapped EFI and EFI-prev.' -ForegroundColor Green
    } else {
        if (Test-Path "${root}EFI-prev") { Remove-Item -Recurse -Force "${root}EFI-prev" }
        if (Test-Path "${root}EFI") { Rename-Item "${root}EFI" 'EFI-prev' }
        Copy-Item -Recurse $Source "${root}EFI"
        if (-not (Test-Path "${root}EFI\OC\OpenCore.efi")) { throw 'Copy failed: EFI\OC\OpenCore.efi missing on the EFI partition.' }
        Write-Host "Deployed $Source to the Seagate EFI partition (old one kept as EFI-prev)." -ForegroundColor Green
    }
    $free = ([System.IO.DriveInfo]::new($root)).AvailableFreeSpace
    Write-Host ("EFI partition free space: {0:N0} MB" -f ($free / 1MB))
} finally {
    diskpart /s "$env:TEMP\nm_dep_off.txt" | Out-Null
}
