# Wi-Fi + Bluetooth for macOS Tahoe, on the Seagate EFI partition and in the local build copy.
#   on : native Wi-Fi (AirportItlwm Tahoe, laobamac v2.4.0-alpha 7204c69) instead of itlwm, and Intel
#        Bluetooth (IntelBluetoothFirmware + IntelBTPatcher 2.5.3 by lshbluesky, BlueToolFixup 2.7.2 by
#        acidanthera) with the NVRAM keys macOS 12+ needs.  Both then appear in System Settings.
#   off: back to itlwm and no Bluetooth kexts.
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wireless.ps1 on
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wireless.ps1 off
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
param([Parameter(Mandatory)][ValidateSet('on', 'off')][string]$Mode)
$ErrorActionPreference = 'Stop'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC'
$bt = @{
    'BlueToolFixup.kext'          = 'D:\Nullmorth-macos\build\extracted\BrcmPatchRAM\BlueToolFixup.kext'
    'IntelBluetoothFirmware.kext' = 'D:\Nullmorth-macos\build\downloads\intelbt-2.5.3\x\IntelBluetoothFirmware.kext'
    'IntelBTPatcher.kext'         = 'D:\Nullmorth-macos\build\downloads\intelbt-2.5.3\x\IntelBTPatcher.kext'
}
foreach ($p in $bt.Values) { if (-not (Test-Path "$p\Contents\Info.plist")) { throw "Missing $p" } }

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
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_wl_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_wl_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_wl_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $oc = "${letter}:\EFI\OC"
    if (-not (Test-Path "$oc\config.plist.pre-wireless")) { Copy-Item "$oc\config.plist" "$oc\config.plist.pre-wireless" }
    foreach ($kexts in "$oc\Kexts", "$build\Kexts") {
        if (-not (Test-Path "$kexts\AirportItlwm.kext\Contents\MacOS\AirportItlwm")) { throw "AirportItlwm.kext missing in $kexts" }
        foreach ($k in $bt.Keys) {
            if (Test-Path "$kexts\$k") { Remove-Item -Recurse -Force "$kexts\$k" }
            if ($Mode -eq 'on') { Copy-Item -Recurse $bt[$k] "$kexts\$k" }
        }
    }
    python -I "$PSScriptRoot\apply_wireless.py" $Mode "$oc\config.plist" "$build\config.plist"
    if ($LASTEXITCODE -ne 0) { throw "apply_wireless.py failed ($LASTEXITCODE)." }
} finally {
    diskpart /s "$env:TEMP\nm_wl_off.txt" | Out-Null
}
python -I "$PSScriptRoot\check_efi.py"
if ($Mode -eq 'on') {
    Write-Host "`nWi-Fi (AirportItlwm) and Bluetooth are ON. In macOS use the Wi-Fi and Bluetooth menus / System Settings." -ForegroundColor Green
} else {
    Write-Host "`nBack to itlwm; Bluetooth kexts removed." -ForegroundColor Green
}
