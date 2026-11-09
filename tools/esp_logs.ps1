# Move the macOS log collector to and from the Seagate EFI partition (label OPENCORE).
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\esp_logs.ps1 push   # put nm_logs.sh on the EFI partition
#   powershell -ExecutionPolicy Bypass -File D:\Nullmorth-macos\tools\esp_logs.ps1 pull   # copy nm_logs\ back to D:\Nullmorth-macos\build\logs
# Touches only the Seagate disk (serial YOUR_DISK_SERIAL) and D:\Nullmorth-macos\build.
param([Parameter(Mandatory)][ValidateSet('push', 'pull')][string]$Mode)
$ErrorActionPreference = 'Stop'
$dest = 'D:\Nullmorth-macos\build\logs'

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
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nassign letter=$letter" | Set-Content "$env:TEMP\nm_logs_on.txt" -Encoding ASCII
"select disk $($d.Number)`nselect partition $($esp[0].PartitionNumber)`nremove letter=$letter" | Set-Content "$env:TEMP\nm_logs_off.txt" -Encoding ASCII

diskpart /s "$env:TEMP\nm_logs_on.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not open the EFI partition (diskpart $LASTEXITCODE)." }
try {
    if ($Mode -eq 'push') {
        Copy-Item "$PSScriptRoot\nm_logs.sh" "${letter}:\nm_logs.sh" -Force
        Copy-Item "$PSScriptRoot\nm_bootlog.sh" "${letter}:\nm_bootlog.sh" -Force
        Copy-Item "$PSScriptRoot\nm_waketest.sh" "${letter}:\nm_waketest.sh" -Force
        if (Test-Path "${letter}:\wex_logs.sh") { Remove-Item "${letter}:\wex_logs.sh" }
        Write-Host "`nnm_logs.sh and nm_bootlog.sh are on the EFI partition." -ForegroundColor Green
        Write-Host "  Recovery's Terminal:  diskutil mount OPENCORE; sh /Volumes/OPENCORE/nm_logs.sh"
        Write-Host "  Installed macOS (Safe Mode ok):  sudo diskutil mount OPENCORE"
        Write-Host "      sudo sh /Volumes/OPENCORE/nm_bootlog.sh now      (everything from the last 4 hours, now)"
        Write-Host "      sudo sh /Volumes/OPENCORE/nm_bootlog.sh install  (auto-save everything on every boot)"
        try {
            $free = ([System.IO.DriveInfo]::new("${letter}:\")).AvailableFreeSpace
            Write-Host ("  EFI partition free space: {0:N0} MB (each full boot capture needs roughly 20-100 MB)" -f ($free / 1MB))
        } catch { Write-Host '  (could not read the EFI partition free space)' }
    } else {
        $have = @('nm_logs', 'nm_bootlogs', 'SysReport') | Where-Object { Test-Path "${letter}:\$_" }
        if (-not $have) { throw 'No nm_logs, nm_bootlogs or SysReport folder on the EFI partition yet.' }
        # Incremental: a folder already pulled earlier (same name, same total size) is not copied again.
        # Every earlier pull copied the whole EFI log tree, which filled drive D: (2026-11-07).
        function Get-TreeSize($p) { (Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum + 0 }
        $pulled = @{}
        foreach ($old in Get-ChildItem -LiteralPath $dest -Directory -ErrorAction SilentlyContinue) {
            foreach ($top in 'nm_logs', 'SysReport') {
                $p = Join-Path $old.FullName $top
                if (Test-Path -LiteralPath $p) { $pulled["$top|" + (Get-TreeSize $p)] = $true } }
            $nb = Join-Path $old.FullName 'nm_bootlogs'
            if (Test-Path -LiteralPath $nb) {
                foreach ($b in Get-ChildItem -LiteralPath $nb -Directory) { $pulled["boot|$($b.Name)|" + (Get-TreeSize $b.FullName)] = $true } }
        }
        $jobs = @()
        foreach ($top in 'nm_logs', 'SysReport') {
            if ($have -contains $top -and -not $pulled["$top|" + (Get-TreeSize "${letter}:\$top")]) { $jobs += ,@("${letter}:\$top", $top) } }
        if ($have -contains 'nm_bootlogs') {
            foreach ($b in Get-ChildItem -LiteralPath "${letter}:\nm_bootlogs" -Directory) {
                if (-not $pulled["boot|$($b.Name)|" + (Get-TreeSize $b.FullName)]) { $jobs += ,@($b.FullName, "nm_bootlogs\$($b.Name)") } } }
        if (-not $jobs) { Write-Host "`nNothing new on the EFI partition: everything was pulled before." -ForegroundColor Yellow; return }
        $need = ($jobs | ForEach-Object { Get-TreeSize $_[0] } | Measure-Object -Sum).Sum
        $free = ([System.IO.DriveInfo]::new('D:\')).AvailableFreeSpace
        Write-Host ("New logs: {0:N0} MB, free on D: {1:N0} MB" -f ($need / 1MB), ($free / 1MB))
        if ($need + 200MB -gt $free) { throw ("Not enough free space on D: for {0:N0} MB of logs. Free some space first." -f ($need / 1MB)) }
        $to = Join-Path $dest (Get-Date -Format 'yyyyMMdd-HHmmss')
        foreach ($j in $jobs) {
            $target = Join-Path $to $j[1]
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item -Recurse -LiteralPath $j[0] $target
            Write-Host "  copied $($j[1])" }
        Write-Host "`nLogs copied to $to" -ForegroundColor Green
    }
} finally {
    diskpart /s "$env:TEMP\nm_logs_off.txt" | Out-Null
}
