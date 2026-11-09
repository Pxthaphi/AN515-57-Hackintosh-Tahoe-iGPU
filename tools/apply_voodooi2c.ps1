# Switch the touchpad driver between VoodooI2C master 6be653a2 (adds Tiger Lake-H I2C 8086:43E8.. and
# GPIO INT34C6, VoodooI2C PR #586, built by the project's own CI) and the 2.9.1 release used so far.
# The 2.9.1 release does not match this laptop's I2C controller (touchpad ELAN0521 on I2C1 = 8086:43E9).
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_voodooi2c.ps1 on
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_voodooi2c.ps1 off
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
param([Parameter(Mandatory)][ValidateSet('on', 'off')][string]$Mode)
$ErrorActionPreference = 'Stop'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC'
$src = if ($Mode -eq 'on') { 'D:\Nullmorth-macos\build\downloads\voodooi2c-6be653a2\rel' } else { 'D:\Nullmorth-macos\build\extracted\VoodooI2C' }
foreach ($k in 'VoodooI2C.kext', 'VoodooI2CHID.kext') {
    if (-not (Test-Path "$src\$k\Contents\Info.plist")) { throw "Missing $src\$k" } }

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
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_i2c_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_i2c_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_i2c_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $oc = "${letter}:\EFI\OC"
    if (-not (Test-Path "$oc\config.plist.pre-i2c")) { Copy-Item "$oc\config.plist" "$oc\config.plist.pre-i2c" }
    foreach ($kexts in "$oc\Kexts", "$build\Kexts") {
        foreach ($k in 'VoodooI2C.kext', 'VoodooI2CHID.kext') {
            if (Test-Path "$kexts\$k") { Remove-Item -Recurse -Force "$kexts\$k" }
            Copy-Item -Recurse "$src\$k" "$kexts\$k"
        }
    }
    python -I "$PSScriptRoot\apply_voodooi2c.py" $Mode "$oc\config.plist" "$build\config.plist"
    if ($LASTEXITCODE -ne 0) { throw "apply_voodooi2c.py failed ($LASTEXITCODE)." }
} finally {
    diskpart /s "$env:TEMP\nm_i2c_off.txt" | Out-Null
}
python -I "$PSScriptRoot\check_efi.py"
if ($Mode -eq 'on') {
    Write-Host "`nVoodooI2C master (Tiger Lake-H) is ON. Restart into macOS and try the touchpad." -ForegroundColor Green
} else {
    Write-Host "`nVoodooI2C 2.9.1 is back." -ForegroundColor Green
}
