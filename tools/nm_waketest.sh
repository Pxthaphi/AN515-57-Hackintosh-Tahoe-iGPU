#!/bin/sh
# Display sleep/wake test with an automatic log capture, so the logs are saved even if the panel
# stays black after waking. Run in the installed macOS:
#   sudo diskutil mount OPENCORE
#   sudo sh /Volumes/OPENCORE/nm_waketest.sh
# 1. 10 s after start the display is put to sleep (pmset displaysleepnow).
# 2. Wait until it is dark, count to 20, then press a key or touch the touchpad to wake it.
# 3. 3 minutes after start, everything is captured to OPENCORE/nm_bootlogs/now-<time>/ (last 20 min).
#    If the screen does not come back, just wait 5 minutes in total, then hold the power button.
HERE=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.'; exit 1; }
[ -f "$HERE/nm_bootlog.sh" ] || { echo "nm_bootlog.sh not found next to this script ($HERE)."; exit 1; }
LOG=/var/log/nm_waketest.log
{
    echo "=== wake test started $(date)"
    pmset -g | grep -E 'displaysleep|sleep|lowpower'
} > "$LOG" 2>&1

# Run the capture from a local copy: the boot-log daemon unmounts OPENCORE after its own snapshot,
# which made the script on the EFI partition unreachable (2026-11-07 test lost its capture).
# nm_bootlog.sh mounts OPENCORE again by itself before writing.
cp "$HERE/nm_bootlog.sh" /var/tmp/nm_bootlog.sh || { echo 'Cannot copy nm_bootlog.sh'; exit 1; }
# Detach the capture so it survives a hung WindowServer / closed Terminal.
nohup sh -c "sleep 180; echo \"capture start \$(date)\" >> $LOG; sh /var/tmp/nm_bootlog.sh now 20m >> $LOG 2>&1; sync; echo \"capture done \$(date)\" >> $LOG; sync" >/dev/null 2>&1 &

echo "Display goes to sleep in 10 seconds. When it is dark, count to 20, then press a key to wake it."
echo "Logs are captured automatically 3 minutes from now (keep the Mac on until then)."
sleep 10
echo "display sleep $(date)" >> "$LOG"
pmset displaysleepnow
