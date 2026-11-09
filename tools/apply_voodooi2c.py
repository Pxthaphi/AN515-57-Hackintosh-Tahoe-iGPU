"""Point the VoodooInput entry at the VoodooI2C copy (new) or the VoodooPS2 copy (old) in config.plist files.

Usage: python apply_voodooi2c.py on|off <config.plist> [<config.plist> ...]
  on   VoodooInput from VoodooI2C.kext/Contents/PlugIns (1.1.7, ships with the TGL-H VoodooI2C build)
  off  VoodooInput from VoodooPS2Controller.kext/Contents/PlugIns (1.1.6, as before)
Only one VoodooInput may load. The kext folders themselves are swapped by apply_voodooi2c.ps1.
"""
import plistlib
import sys

PS2 = "VoodooPS2Controller.kext/Contents/PlugIns/VoodooInput.kext"
I2C = "VoodooI2C.kext/Contents/PlugIns/VoodooInput.kext"


def apply(path, on):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    kexts = cfg["Kernel"]["Add"]
    entry = next((k for k in kexts if k["BundlePath"] in (PS2, I2C)), None)
    if entry is None:
        sys.exit(f"{path}: no VoodooInput entry")
    entry["BundlePath"] = I2C if on else PS2
    # VoodooInput must load before VoodooI2C; keep it right after Lilu-dependent PS2 core if moving to I2C.
    kexts.remove(entry)
    anchor = "VoodooI2C.kext/Contents/PlugIns/VoodooGPIO.kext" if on else "VoodooPS2Controller.kext"
    pos = next(i for i, k in enumerate(kexts) if k["BundlePath"] == anchor)
    kexts.insert(pos if on else pos + 1, entry)
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(path)
    print("  VoodooInput =", entry["BundlePath"])
    print("  order:", ", ".join(k["BundlePath"].split("/")[-1] for k in kexts if "Voodoo" in k["BundlePath"]))


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("on", "off"):
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        apply(p, sys.argv[1] == "on")
