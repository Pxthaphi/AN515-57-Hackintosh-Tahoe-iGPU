"""Switch OpenCore config.plist files between WhateverXe (Intel iGPU acceleration) and WhateverGreen (VESA).

Usage: python apply_wex.py on|off [--dvmt] <config.plist> [<config.plist> ...]
  on     remove WhateverGreen and -igfxvesa -wegnoegpu; add WhateverXe after Lilu and -allow3d -disablegfxfirmware
  --dvmt also add -igfxdvmt and the 60 MB DVMT framebuffer properties (only if "on" alone hangs or shows no accel)
  --trace add -wexdbg -wex-display-trace (use with the DEBUG WhateverXe kext; apply_wex.ps1 -Trace does both)
  off    back to WhateverGreen with -igfxvesa -wegnoegpu (the state that reached the desktop)
Kext folders (WhateverXe, WhateverGreen, AMFIPass Mod/upstream) are swapped by apply_wex.ps1.
csr-active-config stays 0xA43: it already contains every bit of the 0x803 WhateverXe asks for.
"""
import plistlib
import sys

APPLE_NVRAM = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
IGPU = "PciRoot(0x0)/Pci(0x2,0x0)"

WEG = "WhateverGreen.kext"
WEX = "WhateverXe.kext"
WEG_ARGS = ["-igfxvesa", "-wegnoegpu"]
WEX_ARGS = ["-allow3d", "-disablegfxfirmware"]
DVMT_ARGS = ["-igfxdvmt"]
# With the DEBUG WhateverXe build: detailed display / link-training trace in the kernel log.
TRACE_ARGS = ["-wexdbg", "-wex-display-trace"]
DVMT_PROPS = {"framebuffer-patch-enable": bytes.fromhex("01000000"),
              "framebuffer-stolenmem": bytes.fromhex("0000C003")}


def entry(bundle, exe):
    return {"Arch": "x86_64", "BundlePath": bundle, "Comment": bundle, "Enabled": True,
            "ExecutablePath": exe, "MaxKernel": "", "MinKernel": "", "PlistPath": "Contents/Info.plist"}


def apply(path, on, dvmt, trace=False):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    kexts = cfg["Kernel"]["Add"]
    kexts[:] = [k for k in kexts if k["BundlePath"] not in (WEG, WEX)]
    nv = cfg["NVRAM"]["Add"][APPLE_NVRAM]
    args = [a for a in nv["boot-args"].split() if a not in WEG_ARGS + WEX_ARGS + DVMT_ARGS + TRACE_ARGS]
    props = cfg["DeviceProperties"]["Add"]
    props.pop(IGPU, None)

    # Lilu plugin: after Lilu/VirtualSMC, before AppleALC (same slot WhateverGreen used). Never both at once.
    pos = next((i for i, k in enumerate(kexts) if k["BundlePath"] == "AppleALC.kext"), 1)
    if on:
        kexts.insert(pos, entry(WEX, "Contents/MacOS/WhateverXe"))
        args += WEX_ARGS
        if dvmt:
            args += DVMT_ARGS
            props[IGPU] = dict(DVMT_PROPS)
        if trace:
            args += TRACE_ARGS
    else:
        kexts.insert(pos, entry(WEG, "Contents/MacOS/WhateverGreen"))
        args += WEG_ARGS
    nv["boot-args"] = " ".join(args)

    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(path)
    print(f"  graphics  = {'WhateverXe' + (' + DVMT 60MB' if on and dvmt else '') if on else 'WhateverGreen (VESA)'}")
    print(f"  boot-args = {nv['boot-args']}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    dvmt, trace = "--dvmt" in argv, "--trace" in argv
    argv = [a for a in argv if a not in ("--dvmt", "--trace")]
    if len(argv) < 2 or argv[0] not in ("on", "off"):
        sys.exit(__doc__)
    for p in argv[1:]:
        apply(p, argv[0] == "on", dvmt, trace)
