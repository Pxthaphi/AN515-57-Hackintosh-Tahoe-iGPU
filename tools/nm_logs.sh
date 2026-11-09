#!/bin/sh
# Collect logs from the installed macOS so they can be read on Windows. Run from macOS Recovery's Terminal:
#   sh /Volumes/OPENCORE/nm_logs.sh         # crash/panic reports and text logs (small, fast)
#   sh /Volumes/OPENCORE/nm_logs.sh full    # also pack the raw unified log (larger, a few minutes)
# Reads the "<name> - Data" volume of the installed macOS. Writes only to nm_logs/ beside this script.
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/nm_logs"

find_data() {
    for v in /Volumes/*" - Data"; do
        [ -d "$v/private/var/db/diagnostics" ] && { echo "$v"; return 0; }
    done
    return 1
}

main() {
    echo "=== $(date) ==="
    DATA=$(find_data)
    if [ -z "$DATA" ]; then
        echo "ERROR: no '<name> - Data' volume with logs is mounted."
        echo "Open Disk Utility, select the macOS volume's Data volume, click Mount, then run this again."
        ls /Volumes
        return 1
    fi
    echo "Data volume: $DATA"

    echo "[1/3] Crash and panic reports"
    mkdir -p "$OUT/reports"
    find "$DATA/Library/Logs/DiagnosticReports" "$DATA/private/var/db/DiagnosticReports" \
         "$DATA/private/var/root/Library/Logs/DiagnosticReports" "$DATA/Users" \
         -type f \( -name '*.ips' -o -name '*.panic' -o -name '*.crash' -o -name '*.hang' -o -name '*.spin' \) \
         -size -2000k 2>/dev/null | while read -r f; do
        echo "  $f"; cp -X "$f" "$OUT/reports/"
    done

    echo "[2/3] Text logs"
    L="$DATA/private/var/log"
    ls -laR "$L" > "$OUT/var_log_listing.txt" 2>&1
    for f in system.log wifi.log displaypolicyd.stdout.log; do cp -X "$L/$f" "$OUT/" 2>/dev/null; done
    tail -5000 "$L/install.log" > "$OUT/install_tail.log" 2>/dev/null
    mkdir -p "$OUT/launchd"
    cp -X "$L"/com.apple.xpc.launchd/launchd.log* "$OUT/launchd/" 2>/dev/null
    ls -la "$DATA/Library/Logs" > "$OUT/library_logs_listing.txt" 2>&1

    if [ "$1" = "full" ]; then
        echo "[3/3] Packing the raw unified log (a few minutes on the USB HDD) ..."
        D="$DATA/private/var/db"
        if tar -czf "$OUT/unifiedlog.tar.gz" -C "$D" diagnostics uuidtext; then
            ls -la "$OUT/unifiedlog.tar.gz"
        else
            echo "Packing failed (EFI partition full?); removing the partial file."
            rm -f "$OUT/unifiedlog.tar.gz"
        fi
    else
        echo "[3/3] Skipped the raw unified log (run with 'full' to include it)."
    fi
    df -h "$HERE"
    echo "DONE. Restart into Windows and run esp_logs.ps1 pull."
}

rm -rf "$OUT"
mkdir -p "$OUT"
main "$1" 2>&1 | tee "$OUT/collect.log"
