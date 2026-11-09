# Erase ONLY the Seagate FreeAgent GoFlex USB disk and lay it out for OpenCore + macOS.
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\prepare_disk.ps1
#
# Layout written:  [EFI System, FAT32, 2 GB "OPENCORE": EFI + Tahoe recovery + Extras]
#                  [exFAT "MACOS": rest, erased to APFS in Recovery's Disk Utility before installing]
# Safety: refuses to run unless exactly one disk matches name + USB bus + size, and that disk is not the boot/system disk.
# Pass -Confirm ERASE to skip the typed prompt (useful when the keyboard layout is not English).
param([string]$Confirm = '')
$ErrorActionPreference = 'Stop'
$src = 'D:\Nullmorth-macos\build\USB'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }
foreach ($need in "$src\EFI\BOOT\BOOTx64.efi", "$src\EFI\OC\OpenCore.efi", "$src\com.apple.recovery.boot\BaseSystem.dmg") {
    if (-not (Test-Path $need)) { throw "Missing $need - build the EFI and download the recovery first." } }
$cfg = Get-Content "$src\EFI\OC\config.plist" -Raw
if ($cfg -match '<string>CHANGE_ME</string>') { throw 'config.plist still has CHANGE_ME placeholders (SMBIOS serial/MLB).' }
$wifi = Get-Content "$src\EFI\OC\Kexts\itlwm.kext\Contents\Info.plist" -Raw
if ($wifi -match '<string>CHANGE_ME</string>') { Write-Host 'Note: no Wi-Fi network in itlwm yet; Recovery will need the LAN cable (or run add_wifi.ps1 afterwards).' -ForegroundColor Yellow }

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
# Match by serial: Windows reports the GoFlex as "FreeAgent GoFlex" or "USB 3.0 Cable" depending on the adapter.
$cand = @(Get-Disk | Where-Object {
    $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.FriendlyName -like 'Seagate*' -and $_.BusType -eq 'USB' -and
    $_.Size -gt 400GB -and $_.Size -lt 520GB -and -not $_.IsBoot -and -not $_.IsSystem -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw "Expected exactly one Seagate USB disk with serial YOUR_DISK_SERIAL, found $($cand.Count). Nothing was changed." }
$d = $cand[0]

Write-Host "`nTarget disk:" -ForegroundColor Yellow
$d | Format-List Number, FriendlyName, SerialNumber, BusType, @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}
Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue | Format-Table PartitionNumber, DriveLetter, @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}} -AutoSize
Write-Host "Windows disk (C:) is disk $systemDisk - it will NOT be touched." -ForegroundColor Green
if (-not $Confirm) { $Confirm = Read-Host "Type ERASE to wipe disk $($d.Number) ($($d.FriendlyName))" }
if ($Confirm.Trim() -ne 'ERASE') { Write-Host "Cancelled (got '$Confirm'). Nothing was changed."; return }

$used = (Get-Volume).DriveLetter
$free = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used }
$esp = $free[0]
@"
select disk $($d.Number)
clean
convert gpt
create partition efi size=2048
format quick fs=fat32 label=OPENCORE
assign letter=$esp
create partition primary
format quick fs=exfat label=MACOS
"@ | Set-Content "$env:TEMP\nm_diskpart.txt" -Encoding ASCII
# Re-check right before the destructive step, in case disks changed while waiting for input.
$again = Get-Disk -Number $d.Number
if ($again.SerialNumber -ne $d.SerialNumber -or $again.Number -eq $systemDisk) { throw 'Disk changed. Aborting.' }
diskpart /s "$env:TEMP\nm_diskpart.txt"
if ($LASTEXITCODE -ne 0) { throw "diskpart failed ($LASTEXITCODE)." }

robocopy $src "${esp}:\" /E /NFL /NDL /NJH /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Copy failed (robocopy $LASTEXITCODE)." }
Copy-Item "$PSScriptRoot\nm_logs.sh" "${esp}:\nm_logs.sh"  # log collector for Recovery, see esp_logs.ps1
Get-ChildItem "${esp}:\" | Format-Table Name -AutoSize
"select volume $esp`nremove letter=$esp" | Set-Content "$env:TEMP\nm_diskpart2.txt" -Encoding ASCII
diskpart /s "$env:TEMP\nm_diskpart2.txt" | Out-Null
Write-Host "`nDone. The Seagate disk now holds OpenCore + Tahoe recovery. Windows disk untouched." -ForegroundColor Green
Write-Host "If Windows later asks to FORMAT a partition on this disk, click CANCEL." -ForegroundColor Yellow
