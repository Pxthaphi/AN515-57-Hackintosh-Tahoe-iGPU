#!/bin/sh
# Boot-time log capture for the Hackintosh: every boot leaves its logs on the EFI partition,
# even when the screen stays black.
#
# Install once, from the installed macOS (Safe Mode is fine):
#   sudo diskutil mount OPENCORE
#   sudo sh /Volumes/OPENCORE/nm_bootlog.sh install
# Every boot then saves to OPENCORE/nm_bootlogs/<boot time>/ (newest 5 boots kept):
#   t90s-*   at 90 s:  state, graphics kernel lines, full kernel log      (quick, in case the system dies later)
#   t300s-*  at 300 s: EVERYTHING: full unified log of the boot, ioreg, all kexts, hardware, panics, text logs
# Collect logs of earlier boots right now instead:  sudo sh /Volumes/OPENCORE/nm_bootlog.sh now [4h]
# Remove:  sudo sh /Volumes/OPENCORE/nm_bootlog.sh uninstall
# Pull on Windows:  esp_logs.ps1 pull
LABEL=com.nullmoth.bootlog
BIN=/usr/local/libexec/nm_bootlog.sh
PLIST=/Library/LaunchDaemons/$LABEL.plist
KEEP=5
MIN_FREE_MB=300
GFX='eventMessage CONTAINS "IGFB" OR eventMessage CONTAINS "AGDP" OR eventMessage CONTAINS "AGDC" OR
     eventMessage CONTAINS "WhateverXe" OR eventMessage CONTAINS "TGL" OR eventMessage CONTAINS "IGPU" OR
     eventMessage CONTAINS "IGAccel" OR eventMessage CONTAINS "IntelAccelerator" OR eventMessage CONTAINS "panic"'

esp_mount() {
    # The Seagate EFI partition is the only volume named OPENCORE.
    [ -d /Volumes/OPENCORE ] || diskutil mount OPENCORE >/dev/null 2>&1
    [ -d /Volumes/OPENCORE ]
}

free_mb() { df -m "$1" | awk 'NR==2 {print $4}'; }

state() {   # $1 = output file
    {
        echo "=== $(date), uptime: $(uptime)"
        sw_vers
        echo "boot-args: $(nvram boot-args 2>/dev/null | cut -f2-)"
        echo "csr-active-config: $(nvram csr-active-config 2>/dev/null | cut -f2-)"
        echo "safe boot: $(sysctl -n kern.safeboot)"
        echo "--- graphics kexts"
        kmutil showloaded 2>/dev/null | grep -iE 'whateverxe|TGL|amfipass|lilu|whatevergreen'
        echo "--- display processes"
        ps -axo pid,etime,comm | grep -E 'WindowServer|loginwindow|displaypolicyd' | grep -v grep
        echo "--- WhateverXe state on the IORegistry root"
        ioreg -p IOService -d 1 -w0 -l 2>/dev/null | grep -E '"(TGL|WhateverXe|Xe|WEX)[A-Za-z0-9]*" ='
    } > "$1" 2>&1
}

# $1 = dir, $2 = file prefix, $3 = log range: "boot" or e.g. "4h"
quick() {
    dir=$1; p=$2; range=$3
    state "$dir/$p-state.txt"
    log show --last "$range" --style compact --predicate "process == \"kernel\" AND ($GFX)" > "$dir/$p-gfx-kernel.txt" 2>&1
    log show --last "$range" --style compact --predicate 'process == "kernel"' 2>&1 | gzip > "$dir/$p-kernel-all.txt.gz"
    sync
}

full() {
    dir=$1; p=$2; range=$3
    # Fast, small items first: a capture cut short by a forced power-off still keeps them.
    state "$dir/$p-state.txt"
    ioreg -lw0 2>/dev/null | gzip > "$dir/$p-ioreg-all.txt.gz"
    kmutil showloaded > "$dir/$p-kexts-loaded.txt" 2>&1
    sync
    log show --last "$range" --style compact --predicate "process == \"kernel\" AND ($GFX)" > "$dir/$p-gfx-kernel.txt" 2>&1
    log show --last "$range" --style compact \
        --predicate 'eventMessage CONTAINS "Previous shutdown cause" OR eventMessage BEGINSWITH "Darwin Kernel Version"' \
        > "$dir/$p-boots.txt" 2>&1
    log show --last "$range" --style compact --predicate 'messageType == error OR messageType == fault' 2>&1 \
        | gzip > "$dir/$p-errors-faults.txt.gz"
    sync
    # Everything macOS logged (all processes, info level) for the range: slowest, so last of the logs.
    log show --last "$range" --style compact --info 2>&1 | gzip > "$dir/$p-unified-all.txt.gz"
    system_profiler -detailLevel full SPHardwareDataType SPDisplaysDataType SPAudioDataType SPUSBDataType \
        SPPCIDataType SPNetworkDataType SPAirPortDataType SPBluetoothDataType SPPowerDataType SPStorageDataType \
        SPNVMeDataType SPExtensionsDataType 2>&1 | gzip > "$dir/$p-system-profiler.txt.gz"
    { pmset -g; echo; pmset -g assertions; echo; pmset -g log | tail -300; } > "$dir/$p-power.txt" 2>&1
    { ifconfig -a; echo; netstat -rn; } > "$dir/$p-network.txt" 2>&1
    { diskutil list; echo; df -h; } > "$dir/$p-disks.txt" 2>&1
    ls -la /Library/Extensions /Library/GPUBundles /Library/LaunchDaemons > "$dir/$p-installed.txt" 2>&1
    pkgutil --pkgs | grep -v '^com\.apple\.' >> "$dir/$p-installed.txt"
    mkdir -p "$dir/$p-reports"
    find /Library/Logs/DiagnosticReports /private/var/db/DiagnosticReports /Users/*/Library/Logs/DiagnosticReports \
         -type f -mtime -2 -size -5000k 2>/dev/null | while read -r f; do cp -X "$f" "$dir/$p-reports/" 2>/dev/null; done
    mkdir -p "$dir/$p-var-log"
    for f in system.log install.log wifi.log nm_bootlog.log; do
        [ -f "/var/log/$f" ] && tail -20000 "/var/log/$f" | gzip > "$dir/$p-var-log/$f.gz"
    done
    sync
}

prune() {
    n=$(ls -1d /Volumes/OPENCORE/nm_bootlogs/*/ 2>/dev/null | wc -l)
    [ "$n" -gt "$KEEP" ] && ls -1d /Volumes/OPENCORE/nm_bootlogs/*/ | sort | head -n $(( n - KEEP )) | while read -r old; do rm -rf "$old"; done
}

run() {
    # kern.boottime looks like "{ sec = 1762410677, usec = 2 } Fri Nov ..."; take sec, not usec.
    boot=$(sysctl -n kern.boottime | sed -E 's/^\{ sec = ([0-9]+),.*/\1/')
    name=$(date -r "$boot" +%Y%m%d-%H%M%S)
    for step in 90 300; do
        up=$(( $(date +%s) - boot ))
        [ "$up" -lt "$step" ] && sleep $(( step - up ))
        esp_mount || continue
        prune
        if [ "$(free_mb /Volumes/OPENCORE)" -lt "$MIN_FREE_MB" ]; then
            echo "$(date): EFI partition has less than $MIN_FREE_MB MB free, skipped" >> /Volumes/OPENCORE/nm_bootlogs/SKIPPED.txt
        else
            dir=/Volumes/OPENCORE/nm_bootlogs/$name
            mkdir -p "$dir"
            if [ "$step" = 90 ]; then quick "$dir" "t${step}s" boot; else full "$dir" "t${step}s" boot; fi
        fi
        diskutil unmount /Volumes/OPENCORE >/dev/null 2>&1
    done
}

case "$1" in
    install)
        [ "$(id -u)" = 0 ] || { echo 'Run with sudo.'; exit 1; }
        mkdir -p /usr/local/libexec
        cp "$0" "$BIN" && chmod 755 "$BIN" && chown root:wheel "$BIN"
        cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key><array><string>/bin/sh</string><string>$BIN</string><string>run</string></array>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>/var/log/nm_bootlog.log</string>
    <key>StandardErrorPath</key><string>/var/log/nm_bootlog.log</string>
</dict>
</plist>
EOF
        chmod 644 "$PLIST" && chown root:wheel "$PLIST"
        launchctl bootstrap system "$PLIST" 2>/dev/null || launchctl load "$PLIST"
        echo "Installed. Every boot now saves logs to OPENCORE/nm_bootlogs/ (at 90 s and 300 s after boot)."
        echo "This boot is being captured too; wait until 5 minutes after boot before restarting."
        ;;
    uninstall)
        [ "$(id -u)" = 0 ] || { echo 'Run with sudo.'; exit 1; }
        launchctl bootout system/$LABEL 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null
        rm -f "$PLIST" "$BIN"
        echo 'Removed. Logs already on OPENCORE/nm_bootlogs/ are kept.'
        ;;
    now)
        [ "$(id -u)" = 0 ] || { echo 'Run with sudo.'; exit 1; }
        esp_mount || { echo 'Cannot mount OPENCORE.'; exit 1; }
        dir=/Volumes/OPENCORE/nm_bootlogs/now-$(date +%Y%m%d-%H%M%S)
        mkdir -p "$dir"
        echo "Collecting everything from the last ${2:-4h} into $dir (a few minutes) ..."
        full "$dir" "last${2:-4h}" "${2:-4h}"
        ls -la "$dir"; df -h /Volumes/OPENCORE
        echo 'DONE. Restart into Windows and run esp_logs.ps1 pull.'
        ;;
    run) run ;;
    *) sed -n '2,15p' "$0" ;;
esac
