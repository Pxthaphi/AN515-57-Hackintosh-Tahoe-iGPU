# Switch the Intel iGPU between WhateverXe (acceleration) and WhateverGreen (VESA, laggy but known to work),
# on the Seagate EFI partition and in the local build copy.
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wex.ps1 on
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wex.ps1 on -Dvmt   (only if plain "on" fails)
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wex.ps1 on -Trace  (DEBUG kext + display trace logs)
#   ... on -NoLinkFix   (GPU_TICKS patch only, without the eDP link-rate clamp)
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\apply_wex.ps1 off
# "on" also copies the WhateverXe Graphics pkg and its uninstall.sh to WEX\ on the EFI partition (OPENCORE).
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
param([Parameter(Mandatory)][ValidateSet('on', 'off')][string]$Mode, [switch]$Dvmt, [switch]$Trace, [switch]$NoLinkFix)
$ErrorActionPreference = 'Stop'
$ex    = 'D:\Nullmorth-macos\build\extracted'
$dl    = 'D:\Nullmorth-macos\build\downloads\wexgfx040'
$build = 'D:\Nullmorth-macos\build\USB\EFI\OC'
# official 0.7.0 + patches from tools\patch_wex.py: GPU_TICKS skip + eDP link clamp (linkfix);
# -NoLinkFix uses the GPU_TICKS-only build; -Trace uses the DEBUG build of the same release.
$variant = if ($NoLinkFix) { 'WhateverXe-gputicks' } else { 'WhateverXe-linkfix' }
if ($Trace) { $variant += '-DEBUG' }
$wex   = "$ex\$variant\WhateverXe.kext"
$weg   = "$ex\WhateverGreen\WhateverGreen.kext"
$amfi  = if ($Mode -eq 'on') { "$ex\AMFIPass-Mod\AMFIPass.kext" } else { "$ex\AMFIPass\AMFIPass.kext" }
$pkg   = "$dl\WhateverXe-Graphics-0.4.0.pkg"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator.' }
foreach ($need in "$wex\Contents\MacOS\WhateverXe", "$weg\Contents\MacOS\WhateverGreen", "$amfi\Contents\MacOS\AMFIPass", $pkg, "$dl\uninstall.sh") {
    if (-not (Test-Path $need)) { throw "Missing $need" } }
if ($Mode -eq 'on') {
    $want = ((Get-Content "$dl\SHA256SUMS") -match 'WhateverXe-Graphics-0.4.0.pkg' -split '\s+')[0]
    if ((Get-FileHash $pkg -Algorithm SHA256).Hash -ne $want.ToUpper()) { throw "Checksum mismatch: $pkg" }
}

$systemDisk = (Get-Partition -DriveLetter C).DiskNumber
$cand = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' -and $_.Number -ne $systemDisk })
if ($cand.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$d = $cand[0]
$esp = @(Get-Partition -DiskNumber $d.Number | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
if ($esp.Count -ne 1) { throw "Expected one EFI partition on disk $($d.Number), found $($esp.Count)." }

$used = (Get-Volume).DriveLetter
$letter = [char[]]'STUVWXYZ' | Where-Object { $_ -notin $used } | Select-Object -First 1
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_wex_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_wex_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_wex_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    $oc = "${letter}:\EFI\OC"
    if (-not (Test-Path "$oc\config.plist.pre-wex")) { Copy-Item "$oc\config.plist" "$oc\config.plist.pre-wex" }
    foreach ($kexts in "$oc\Kexts", "$build\Kexts") {
        foreach ($k in 'WhateverGreen.kext', 'WhateverXe.kext', 'AMFIPass.kext') {
            if (Test-Path "$kexts\$k") { Remove-Item -Recurse -Force "$kexts\$k" } }
        if ($Mode -eq 'on') { Copy-Item -Recurse $wex "$kexts\WhateverXe.kext" }
        else                { Copy-Item -Recurse $weg "$kexts\WhateverGreen.kext" }
        Copy-Item -Recurse $amfi "$kexts\AMFIPass.kext"
    }
    if ($Mode -eq 'on') {
        New-Item -ItemType Directory -Force "${letter}:\WEX" | Out-Null
        Copy-Item $pkg "${letter}:\WEX\WhateverXe-Graphics-0.4.0.pkg"
        Copy-Item "$dl\uninstall.sh" "${letter}:\WEX\uninstall.sh"
    }
    $pyArgs = @($Mode) + $(if ($Dvmt) { @('--dvmt') } else { @() }) + $(if ($Trace) { @('--trace') } else { @() }) + @("$oc\config.plist", "$build\config.plist")
    python -I "$PSScriptRoot\apply_wex.py" @pyArgs
    if ($LASTEXITCODE -ne 0) { throw "apply_wex.py failed ($LASTEXITCODE)." }
} finally {
    diskpart /s "$env:TEMP\nm_wex_off.txt" | Out-Null
}
python -I "$PSScriptRoot\check_efi.py"
if ($Mode -eq 'on') { Write-Host "WhateverXe kext variant: $variant" -ForegroundColor Cyan }
$bootArgs = (python -I -c "import plistlib;print(plistlib.load(open(r'$build\config.plist','rb'))['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args'])")
if ($bootArgs -match '(^|\s)-x(\s|$)') { Write-Host "`nNote: Safe Mode (-x) is still ON. Run safe_mode.ps1 off for a normal boot." -ForegroundColor Yellow }

if ($Mode -eq 'on') {
    Write-Host "`nWhateverXe is ON (AMFIPass Mod). Only if the WhateverXe Graphics pkg is NOT installed yet, in macOS:" -ForegroundColor Green
    Write-Host '  sudo diskutil mount OPENCORE'
    Write-Host '  sudo installer -pkg /Volumes/OPENCORE/WEX/WhateverXe-Graphics-0.4.0.pkg -target /'
    Write-Host '  then restart. About This Mac > Graphics should show Intel graphics instead of "Display 7 MB".'
} else {
    Write-Host "`nWhateverGreen (VESA) is back ON. If the WhateverXe Graphics pkg was installed, boot once with" -ForegroundColor Green
    Write-Host 'safe_mode.ps1 on, run  sudo bash /Volumes/OPENCORE/WEX/uninstall.sh , then safe_mode.ps1 off.'
}
