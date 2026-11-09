# Download the full macOS Tahoe installer (26.7.2, 25G332, product 142-50020) onto the Seagate's
# exFAT volume TAHOEPKG, for installing from Recovery without a network.
# No admin needed:  powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\get_installer.ps1
# Run it again to resume an interrupted download. Writes only to the TAHOEPKG volume on the Seagate.
$ErrorActionPreference = 'Stop'
$url  = 'https://swcdn.apple.com/content/downloads/38/31/142-50020-A_7SHECS0ACF/ncy3h2j7nwse4aoz0rjot59fp0z9s4yf3o/InstallAssistant.pkg'
$size = 18389893051
$sha1 = 'C7DF65215866C09A8739029C52DCF14A5B93865D'   # Digest from Apple's software update catalog

$disk = @(Get-Disk | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq 'YOUR_DISK_SERIAL' -and $_.BusType -eq 'USB' })
if ($disk.Count -ne 1) { throw 'Seagate disk (serial YOUR_DISK_SERIAL) not found. Plug it in and try again.' }
$vol = @(Get-Partition -DiskNumber $disk[0].Number | Get-Volume -ErrorAction SilentlyContinue |
    Where-Object { $_.FileSystemLabel -eq 'TAHOEPKG' -and $_.FileSystem -eq 'exFAT' -and $_.DriveLetter })
if ($vol.Count -ne 1) { throw 'exFAT volume TAHOEPKG on the Seagate not found (make it in Recovery first).' }
$out = "$($vol[0].DriveLetter):\InstallAssistant.pkg"

$have = if (Test-Path $out) { (Get-Item $out).Length } else { 0 }
if ($vol[0].SizeRemaining + $have -lt $size) { throw "Not enough space on TAHOEPKG: need $([math]::Round($size/1GB,1)) GB." }

if ($have -lt $size) {
    Write-Host "Downloading to $out (resuming at $([math]::Round($have/1GB,2)) GB)..."
    curl.exe -L --fail --retry 20 --retry-delay 5 --retry-all-errors -C - -o $out $url
    if ($LASTEXITCODE -ne 0) { throw "Download stopped (curl $LASTEXITCODE). Run the script again to resume." }
}
if ((Get-Item $out).Length -ne $size) { throw "Wrong size: $((Get-Item $out).Length), expected $size. Delete $out and run again." }

Write-Host 'Checking SHA-1 (takes a few minutes)...'
if ((Get-FileHash $out -Algorithm SHA1).Hash -ne $sha1) { throw "SHA-1 mismatch. Delete $out and run again." }
Write-Host "`nDone: $out is complete and matches Apple's checksum." -ForegroundColor Green
