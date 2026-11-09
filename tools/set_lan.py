"""Make sure OpenCore config.plist files have working wired LAN (Killer E2600 = Realtek 10EC:2600).

Usage: python set_lan.py <config.plist> [<config.plist> ...]
Turns RealtekRTL8111.kext on and marks the Ethernet port built-in. Everything else stays as it is.
"""
import plistlib
import sys

LAN_PATH = "PciRoot(0x0)/Pci(0x1c,0x0)/Pci(0x0,0x0)"


def apply(path):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    kext = [k for k in cfg["Kernel"]["Add"] if k["BundlePath"] == "RealtekRTL8111.kext"]
    if not kext:
        sys.exit(f"{path}: RealtekRTL8111.kext is not in Kernel > Add")
    kext[0]["Enabled"] = True
    cfg["DeviceProperties"]["Add"].setdefault(LAN_PATH, {})["built-in"] = b"\x01"
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(f"{path}\n  RealtekRTL8111.kext = on\n  {LAN_PATH} built-in = 01")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        apply(p)
