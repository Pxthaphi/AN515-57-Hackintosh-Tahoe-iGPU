# Add or update a Wi-Fi network for itlwm, on the Seagate EFI partition and in the local build copy.
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\add_wifi.ps1
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build. The network must be WPA2.
$ErrorActionPreference = 'Stop'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC\Kexts\itlwm.kext\Contents\Info.plist'
$rel   = 'EFI\OC\Kexts\itlwm.kext\Contents\Info.plist'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
$cand = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$d = $cand[0]
$esp = @(Get-Partition -DiskNumber $d.Number | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
if ($esp.Count -ne 1) { throw "Expected one EFI partition on disk $($d.Number), found $($esp.Count)." }

$ssid = (Read-Host 'Wi-Fi name (SSID)').Trim()
if (-not $ssid) { Write-Host 'Cancelled. Nothing was changed.'; return }
$sec = Read-Host 'Wi-Fi password' -AsSecureString
$env:NM_SSID = $ssid
$env:NM_PASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
if ($env:NM_PASS.Length -lt 8 -or $env:NM_PASS.Length -gt 63) {
    Remove-Item Env:NM_PASS, Env:NM_SSID
    throw 'A WPA2 password must be 8-63 characters. Nothing was changed.' }

$used = (Get-Volume).DriveLetter
$letter = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used } | Select-Object -First 1
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_wifi_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_wifi_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_wifi_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    python -I "$PSScriptRoot\add_wifi.py" "${letter}:\$rel" $build
    if ($LASTEXITCODE -ne 0) { throw "add_wifi.py failed ($LASTEXITCODE)." }
} finally {
    Remove-Item Env:NM_PASS, Env:NM_SSID -ErrorAction SilentlyContinue
    diskpart /s "$env:TEMP\nm_wifi_off.txt" | Out-Null
}
Write-Host "`nDone. macOS joins these networks automatically after the next boot from the Seagate disk." -ForegroundColor Green
