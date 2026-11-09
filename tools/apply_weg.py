"""Turn WhateverGreen with -igfxvesa -wegnoegpu on or off in OpenCore config.plist files.

Usage: python apply_weg.py on|off <config.plist> [<config.plist> ...]
"on" adds a WhateverGreen.kext entry before AppleALC plus the boot-args below; "off" removes both.
The kext folder itself is copied or deleted by apply_weg.ps1.
"""
import plistlib
import sys

APPLE_NVRAM = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
BUNDLE = "WhateverGreen.kext"
# -igfxvesa: keep the Intel iGPU on the firmware framebuffer without acceleration (how other Tiger Lake laptops install).
# -wegnoegpu: hide the RTX 3050 from macOS until NullMoth is installed.
ARGS = ["-igfxvesa", "-wegnoegpu"]

ENTRY = {
    "Arch": "x86_64",
    "BundlePath": BUNDLE,
    "Comment": BUNDLE,
    "Enabled": True,
    "ExecutablePath": "Contents/MacOS/WhateverGreen",
    "MaxKernel": "",
    "MinKernel": "",
    "PlistPath": "Contents/Info.plist",
}


def apply(path, on):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    kexts = cfg["Kernel"]["Add"]
    kexts[:] = [k for k in kexts if k["BundlePath"] != BUNDLE]
    nv = cfg["NVRAM"]["Add"][APPLE_NVRAM]
    args = [a for a in nv["boot-args"].split() if a not in ARGS]
    if on:
        # After Lilu and VirtualSMC, before AppleALC; WhateverGreen only needs Lilu loaded first.
        pos = next((i for i, k in enumerate(kexts) if k["BundlePath"] == "AppleALC.kext"), 1)
        kexts.insert(pos, dict(ENTRY))
        args += ARGS
    nv["boot-args"] = " ".join(args)
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(path)
    print(f"  WhateverGreen = {'on' if on else 'off'}")
    print(f"  boot-args = {nv['boot-args']}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("on", "off"):
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        apply(p, sys.argv[1] == "on")
