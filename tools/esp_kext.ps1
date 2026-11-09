# Turn kexts on or off by BundlePath, on the Seagate EFI partition and in the local build copy.
# Run as Administrator, for example (switch Wi-Fi to the native Tahoe driver after installing):
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\esp_kext.ps1 off itlwm.kext
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\esp_kext.ps1 on AirportItlwm.kext
# Several kexts: separate them with commas, e.g. IntelBluetoothFirmware.kext,IntelBTPatcher.kext
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
# The first run keeps the Seagate's original config as config.plist.orig next to it.
param(
    [Parameter(Mandatory)][ValidateSet('on', 'off')][string]$Mode,
    [Parameter(Mandatory)][string]$Kexts
)
$ErrorActionPreference = 'Stop'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC\config.plist'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
$cand = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$d = $cand[0]
$esp = @(Get-Partition -DiskNumber $d.Number | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
if ($esp.Count -ne 1) { throw "Expected one EFI partition on disk $($d.Number), found $($esp.Count)." }

$used = (Get-Volume).DriveLetter
$letter = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used } | Select-Object -First 1
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_kext_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_kext_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_kext_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $cfg = "${letter}:\EFI\OC\config.plist"
    if (-not (Test-Path "$cfg.orig")) { Copy-Item $cfg "$cfg.orig" }
    python -I "$PSScriptRoot\set_kext.py" $Mode $Kexts $cfg $build
    if ($LASTEXITCODE -ne 0) { throw "set_kext.py failed ($LASTEXITCODE)." }
} finally {
    diskpart /s "$env:TEMP\nm_kext_off.txt" | Out-Null
}
Write-Host "`nDone: $Kexts = $Mode. Restart and boot macOS from the Seagate." -ForegroundColor Green
