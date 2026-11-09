# Finish the USB files: hotspot Wi-Fi for itlwm, a fresh SMBIOS serial, and the Sequoia recovery image.
# Run in a normal (non-admin) PowerShell:  powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\finish_setup.ps1
# Touches only D:\Nullmorth-macos\build\USB. Nothing on C:, D: or E: outside that folder.
$ErrorActionPreference = 'Stop'
$usb  = 'D:\Nullmorth-macos\build\USB'
$oc   = "$usb\EFI\OC"
$pkg  = 'D:\Nullmorth-macos\build\extracted\OpenCore\Utilities'

Write-Host "`n[1/3] Phone hotspot for macOS Recovery (Samsung USB tethering does not work in macOS)" -ForegroundColor Cyan
$ssid = Read-Host 'Hotspot name (SSID)'
$sec  = Read-Host 'Hotspot password' -AsSecureString
$env:NM_SSID = $ssid
$env:NM_PASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
python -I -c @"
import os, plistlib
p = r'$oc\Kexts\itlwm.kext\Contents\Info.plist'
d = plistlib.load(open(p, 'rb'))
d['IOKitPersonalities']['itlwm']['WiFiConfig'] = {'WiFi_1': {'ssid': os.environ['NM_SSID'], 'password': os.environ['NM_PASS']}}
plistlib.dump(d, open(p, 'wb'))
print('itlwm WiFiConfig set for', repr(os.environ['NM_SSID']))
"@
Remove-Item Env:NM_PASS, Env:NM_SSID

Write-Host "`n[2/3] New serial / MLB for MacBookPro16,2" -ForegroundColor Cyan
$line = (& "$pkg\macserial\macserial.exe" -m MacBookPro16,2 -g -n 1 | Select-String '\|' | Select-Object -First 1).Line
$serial, $mlb = $line.Split('|') | ForEach-Object { $_.Trim() }
if (-not $serial -or -not $mlb) { throw "macserial output not understood: $line" }
$env:NM_SERIAL = $serial; $env:NM_MLB = $mlb
python -I -c @"
import os, plistlib
p = r'$oc\config.plist'
c = plistlib.load(open(p, 'rb'))
g = c['PlatformInfo']['Generic']
g['SystemSerialNumber'] = os.environ['NM_SERIAL']; g['MLB'] = os.environ['NM_MLB']
plistlib.dump(c, open(p, 'wb'))
print('Serial', g['SystemSerialNumber'], 'MLB', g['MLB'])
"@

Write-Host "`n[3/3] Downloading macOS Sequoia recovery from Apple (~1 GB)" -ForegroundColor Cyan
$rec = "$usb\com.apple.recovery.boot"
New-Item -ItemType Directory -Force $rec | Out-Null
Push-Location $env:TEMP
python -I "$pkg\macrecovery\macrecovery.py" -b Mac-7BA5B2D9E42DDD94 -m 00000000000000000 -o $rec download
Pop-Location
Get-ChildItem $rec | Format-Table Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}} -AutoSize
Write-Host "Done. Next: run prepare_disk.ps1 as Administrator." -ForegroundColor Green
