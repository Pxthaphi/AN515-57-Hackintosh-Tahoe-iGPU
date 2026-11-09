#!/bin/sh
# Install macOS from the full installer next to this script, from macOS Recovery's Terminal:
#   sh /Volumes/INSTALLER/install.sh            (target volume MacHD)
#   sh /Volumes/INSTALLER/install.sh OtherName  (another APFS volume name)
# Works from any mount point of the INSTALLER partition. Output is also saved to install.log beside this script.
# No internet needed: everything comes from InstallAssistant.pkg (verified against Apple's checksums on Windows).
HERE=$(cd "$(dirname "$0")" && pwd)
NAME="${1:-MacHD}"

main() {
    PKG="$HERE/InstallAssistant.pkg"
    TARGET="/Volumes/$NAME"
    APP="$TARGET/Applications/Install macOS Sequoia.app"

    echo "=== $(date) ==="
    echo "Script folder: $HERE"
    ls -la /Volumes "$HERE"
    diskutil list

    if [ ! -f "$PKG" ]; then
        echo "ERROR: not found: $PKG"; return 1
    fi
    if [ ! -d "$TARGET" ]; then
        echo "$TARGET is not mounted; trying to mount it ..."
        diskutil mount "$NAME"
    fi
    if [ ! -d "$TARGET" ]; then
        echo "ERROR: volume $TARGET not found."
        echo "In Disk Utility, erase the MACOS volume as APFS with the name $NAME, then run this again."
        return 1
    fi

    if [ ! -d "$APP" ]; then
        echo "[1/2] Unpacking the installer app onto $TARGET (about 10-20 min on the USB HDD) ..."
        installer -pkg "$PKG" -target "$TARGET" -verboseR || { echo "ERROR: installer failed (see above)."; return 1; }
    fi
    if [ ! -x "$APP/Contents/Resources/startosinstall" ]; then
        echo "ERROR: installer app not found at: $APP"; ls -la "$TARGET/Applications"; return 1
    fi

    echo "[2/2] Starting the macOS installer on $TARGET. The Mac restarts by itself when ready."
    echo "      After each restart: F12 -> Seagate -> pick 'macOS Installer', later '$NAME'."
    "$APP/Contents/Resources/startosinstall" --agreetolicense --volume "$TARGET"
    echo "startosinstall exit code: $?"
}

main 2>&1 | tee -a "$HERE/install.log"
