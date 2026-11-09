"""Switch Wi-Fi to native AirportItlwm and add Intel Bluetooth, in OpenCore config.plist files.

Usage: python apply_wireless.py on|off <config.plist> [<config.plist> ...]
  on   Wi-Fi: itlwm off, AirportItlwm (laobamac Tahoe build, Darwin 25) on  -> native Wi-Fi menu/Settings
       BT:    BlueToolFixup (BrcmPatchRAM 2.7.2), IntelBluetoothFirmware + IntelBTPatcher (lshbluesky 2.5.3)
              plus the NVRAM keys macOS 12+ needs for a non-Apple internal controller
  off  back to itlwm (HeliPort-style, networks from WiFiConfig) and no Bluetooth kexts
Kext folders are copied/removed by apply_wireless.ps1. The Bluetooth device (8087:0026) sits on HS06,
already mapped as an internal (255) port in UTBMap.
"""
import plistlib
import sys

APPLE_NVRAM = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
BT_NVRAM = {
    "bluetoothExternalDongleFailed": bytes(1),
    "bluetoothInternalControllerInfo": bytes(14),
}
BT_KEXTS = [  # (BundlePath, ExecutablePath, MinKernel), in load order, all after Lilu
    ("BlueToolFixup.kext", "Contents/MacOS/BlueToolFixup", "21.0.0"),
    ("IntelBluetoothFirmware.kext", "Contents/MacOS/IntelBluetoothFirmware", ""),
    ("IntelBTPatcher.kext", "Contents/MacOS/IntelBTPatcher", "21.0.0"),
]


def entry(bundle, exe, mink):
    return {"Arch": "x86_64", "BundlePath": bundle, "Comment": bundle, "Enabled": True,
            "ExecutablePath": exe, "MaxKernel": "", "MinKernel": mink, "PlistPath": "Contents/Info.plist"}


def apply(path, on):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    kexts = cfg["Kernel"]["Add"]
    names = {b for b, _, _ in BT_KEXTS}
    kexts[:] = [k for k in kexts if k["BundlePath"] not in names]
    for k in kexts:
        if k["BundlePath"] == "itlwm.kext":
            k["Enabled"] = not on
        elif k["BundlePath"] == "AirportItlwm.kext":
            k["Enabled"] = on
            if on and not k["MinKernel"].startswith("25"):
                sys.exit(f"{path}: AirportItlwm entry is not limited to Darwin 25 (MinKernel {k['MinKernel']!r})")
    if not any(k["BundlePath"] == "AirportItlwm.kext" for k in kexts):
        sys.exit(f"{path}: no AirportItlwm.kext entry")
    nv_add = cfg["NVRAM"]["Add"][APPLE_NVRAM]
    nv_del = cfg["NVRAM"]["Delete"].setdefault(APPLE_NVRAM, [])
    for key in BT_NVRAM:
        nv_add.pop(key, None)
        if key in nv_del:
            nv_del.remove(key)
    if on:
        kexts += [entry(*k) for k in BT_KEXTS]
        nv_add.update(BT_NVRAM)
        nv_del += list(BT_NVRAM)  # delete-then-add, so OpenCore rewrites them every boot
    # off leaves any copy already written to NVRAM; it is harmless without the Bluetooth kexts.
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    state = {k["BundlePath"]: k["Enabled"] for k in kexts
             if k["BundlePath"] in ("itlwm.kext", "AirportItlwm.kext") or k["BundlePath"] in names}
    print(path)
    for b, e in state.items():
        print(f"  {b} = {'on' if e else 'off'}")
    print("  Bluetooth NVRAM keys:", "set" if on else "removed from config")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("on", "off"):
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        apply(p, sys.argv[1] == "on")
