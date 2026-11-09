"""Build an OpenCore EFI for Acer Nitro 5 AN515-57 (Tahoe, external USB disk).

Base: JunoDoesThings' AN515-57 config (reached Recovery on real hardware).
Keeps its ACPI/Booter setup, fixes hardware mismatches, updates OpenCore to the
downloaded release, and hardens the boot picker so it only sees USB devices.
The serial/MLB/UUID/ROM and itlwm Wi-Fi networks of an existing build are kept.

State as of 2026-11-06 (everything below tested on the machine):
  - iGPU UHD 9A68 accelerated: WhateverXe 0.7.0 + tools/patch_wex.py (gputicks, linkclamp, novarenderer),
    WhateverXe Graphics 0.4.0 pkg installed in macOS, AMFIPass Mod, DVMT 60 MB fix
  - touchpad: VoodooI2C master 6be653a2 (Tiger Lake-H I2C/GPIO), Wi-Fi: AirportItlwm Tahoe,
    Bluetooth: IntelBluetoothFirmware/IntelBTPatcher 2.5.3 (lshbluesky) + BlueToolFixup 2.7.2

Usage: python build_efi.py [--verbose] [--i2c-polling] [--debug-oc] [--trace] [--keep-dgpu] [--public] [--out DIR]
  --verbose      add -v (text boot)                      default: Apple logo boot
  --i2c-polling  add -vi2c-force-polling (touchpad)      default: GPIO interrupts
  --debug-oc     OpenCore DEBUG binaries + Misc/Debug/SysReport (dumps ACPI etc. to the ESP once)
  --trace        WhateverXe DEBUG build + -wexdbg -wex-display-trace (display/link-training records)
  --keep-dgpu    leave the RTX 3050 powered (no SSDT-NM-DGPUOFF)
  --out DIR      write somewhere else than D:\\Nullmorth-macos\\build\\USB\\EFI
  --public       do not copy this machine's serial/MLB/UUID/ROM or Wi-Fi networks (shareable EFI)
"""
import argparse
import plistlib
import shutil
import uuid
import os
from pathlib import Path

PROJECT = Path(r"D:\Nullmorth-macos")
JUNO = PROJECT / "EFI" / "EFI" / "EFI"
EX = PROJECT / "build" / "extracted"
DL = PROJECT / "build" / "downloads"
OC_RELEASE = EX / "OpenCore" / "X64" / "EFI"
OC_DEBUG = EX / "OpenCore-DEBUG" / "X64" / "EFI"
OUT = PROJECT / "build" / "USB" / "EFI"
I2C = DL / "voodooi2c-6be653a2" / "rel"     # VoodooI2C master CI build: adds Tiger Lake-H (PR #586)
IBT = DL / "intelbt-2.5.3" / "x"            # lshbluesky IntelBluetoothFirmware 2.5.3 (Tahoe)

# ALC295: layout 21 = "Acer Nitro 5 Spin (NP515-51)". Fallbacks to try via alcid=: 28, 13, 77
LAYOUT_ID = 21

# -allow3d -disablegfxfirmware: required by WhateverXe; -igfxdvmt: BIOS DVMT is 60 MB ("Insufficient stolen memory").
# debug=0x100 keepsyms=1: a panic stays on screen with symbols instead of rebooting.
BOOT_ARGS = "keepsyms=1 debug=0x100 alcid=21 -allow3d -disablegfxfirmware -igfxdvmt"

APPLE_NVRAM = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
# macOS 12+ only enables a non-Apple internal Bluetooth controller with these (IntelBluetoothFirmware FAQ).
BT_NVRAM = {"bluetoothExternalDongleFailed": bytes(1), "bluetoothInternalControllerInfo": bytes(14)}

DGPU_SSDT = "SSDT-NM-DGPUOFF.aml"

IGPU_PATH = "PciRoot(0x0)/Pci(0x2,0x0)"
# WhateverXe DVMT fix for a 60 MB pre-allocation (with -igfxdvmt).
IGPU_PROPS = {"framebuffer-patch-enable": bytes.fromhex("01000000"), "framebuffer-stolenmem": bytes.fromhex("0000C003")}

# Only boot from USB devices; only APFS and EFI System Partitions.
# FS_LOCK | DEVICE_LOCK | ALLOW_FS_APFS | ALLOW_FS_ESP | ALLOW_DEVICE_USB
SCAN_POLICY = 0x1 | 0x2 | 0x100 | 0x400 | 0x200000

TAHOE = {"min": "25.0.0", "max": "25.99.99"}

# Killer E2600 (from Windows: PCIROOT(0)#PCI(1C00)#PCI(0000)). built-in makes macOS treat it as the
# internal Ethernet port, which App Store/iCloud expect.
LAN_PATH = "PciRoot(0x0)/Pci(0x1c,0x0)/Pci(0x0,0x0)"

# (source kext dir, BundlePath, ExecutablePath or "" for codeless, options)
KEXTS = [
    (EX / "Lilu" / "Lilu.kext", "Lilu.kext", "Contents/MacOS/Lilu", {}),
    (EX / "VirtualSMC" / "Kexts" / "VirtualSMC.kext", "VirtualSMC.kext", "Contents/MacOS/VirtualSMC", {}),
    (EX / "VirtualSMC" / "Kexts" / "SMCProcessor.kext", "SMCProcessor.kext", "Contents/MacOS/SMCProcessor", {}),
    (EX / "VirtualSMC" / "Kexts" / "SMCBatteryManager.kext", "SMCBatteryManager.kext", "Contents/MacOS/SMCBatteryManager", {}),
    (EX / "ECEnabler" / "ECEnabler.kext", "ECEnabler.kext", "Contents/MacOS/ECEnabler", {}),
    # Fn brightness keys: the EC raises _Qxx events that Notify the panel device; BrightnessKeys turns them
    # into brightness key presses (the backlight itself already works through WhateverXe + SSDT-PNLF).
    (EX / "BrightnessKeys" / "BrightnessKeys.kext", "BrightnessKeys.kext", "Contents/MacOS/BrightnessKeys", {}),
    # Official WhateverXe 0.7.0 RELEASE + tools/patch_wex.py; never together with WhateverGreen.
    (EX / "WhateverXe-linkfix" / "WhateverXe.kext", "WhateverXe.kext", "Contents/MacOS/WhateverXe", {}),
    (EX / "AppleALC" / "AppleALC.kext", "AppleALC.kext", "Contents/MacOS/AppleALC", {}),
    # Tahoe ships without AppleHDA; SimpleHDA restores it for AppleALC. Must load after AppleALC.
    (EX / "SimpleHDA" / "SimpleHDA-Tahoe-v1.0.0-RELEASE" / "SimpleHDA.kext", "SimpleHDA.kext", "Contents/MacOS/SimpleHDA", TAHOE),
    (EX / "USBToolBox" / "USBToolBox.kext", "USBToolBox.kext", "Contents/MacOS/USBToolBox", {}),
    (JUNO / "OC" / "Kexts" / "UTBMap.kext", "UTBMap.kext", "", {}),
    # Keyboard is PS/2; touchpad is I2C (ELAN0521), so only the PS/2 keyboard plugin is used.
    (EX / "VoodooPS2" / "VoodooPS2Controller.kext", "VoodooPS2Controller.kext", "Contents/MacOS/VoodooPS2Controller", {}),
    (None, "VoodooPS2Controller.kext/Contents/PlugIns/VoodooPS2Keyboard.kext", "Contents/MacOS/VoodooPS2Keyboard", {}),
    # Touchpad ELAN0521 is I2C HID on I2C1 = 8086:43E9 (Tiger Lake-H); VoodooI2C 2.9.1 does not match it.
    # VoodooInput is loaded once, from VoodooI2C (1.1.7; the VoodooPS2 copy is 1.1.6).
    (I2C / "VoodooI2C.kext", "VoodooI2C.kext/Contents/PlugIns/VoodooInput.kext", "Contents/MacOS/VoodooInput", {}),
    (None, "VoodooI2C.kext/Contents/PlugIns/VoodooGPIO.kext", "Contents/MacOS/VoodooGPIO", {}),
    (None, "VoodooI2C.kext/Contents/PlugIns/VoodooI2CServices.kext", "Contents/MacOS/VoodooI2CServices", {}),
    (None, "VoodooI2C.kext", "Contents/MacOS/VoodooI2C", {}),
    (I2C / "VoodooI2CHID.kext", "VoodooI2CHID.kext", "Contents/MacOS/VoodooI2CHID", {}),
    # Killer E2600 is Realtek 10EC:2600, listed in RealtekRTL8111 v3.0.0 (Tahoe support).
    (EX / "RealtekRTL8111" / "RealtekRTL8111-V3.0.0" / "Release" / "RealtekRTL8111.kext", "RealtekRTL8111.kext", "Contents/MacOS/RealtekRTL8111", {}),
    # itlwm (networks from WiFiConfig) kept for Recovery: esp_kext.ps1 on itlwm.kext / off AirportItlwm.kext.
    (EX / "itlwm" / "itlwm.kext", "itlwm.kext", "Contents/MacOS/itlwm", {"enabled": False}),
    # Native Wi-Fi for the installed Tahoe (laobamac build 7204c69).
    (EX / "AirportItlwm-Tahoe" / "AirportItlwm.kext", "AirportItlwm.kext", "Contents/MacOS/AirportItlwm", TAHOE),
    # AMFIPass 1.4.1 Mod (WhateverXe-Graphics/extras): required by WhateverXe Graphics; not upstream AMFIPass.
    (EX / "AMFIPass-Mod" / "AMFIPass.kext", "AMFIPass.kext", "Contents/MacOS/AMFIPass", {}),
    # Intel Bluetooth 8087:0026 on HS06 (UTBMap internal port). 2.5.x includes the Sequoia IOGMD panic fix.
    (EX / "BrcmPatchRAM" / "BlueToolFixup.kext", "BlueToolFixup.kext", "Contents/MacOS/BlueToolFixup", {"min": "21.0.0"}),
    (IBT / "IntelBluetoothFirmware.kext", "IntelBluetoothFirmware.kext", "Contents/MacOS/IntelBluetoothFirmware", {}),
    (IBT / "IntelBTPatcher.kext", "IntelBTPatcher.kext", "Contents/MacOS/IntelBTPatcher", {"min": "21.0.0"}),
]

DRIVERS = ["OpenRuntime.efi", "HfsPlus.efi", "OpenUsbKbDxe.efi"]


def kext_entry(bundle, exe, opts):
    return {
        "Arch": "x86_64",
        "BundlePath": bundle,
        "Comment": bundle.split("/")[-1],
        "Enabled": opts.get("enabled", True),
        "ExecutablePath": exe,
        "MaxKernel": opts.get("max", ""),
        "MinKernel": opts.get("min", ""),
        "PlistPath": "Contents/Info.plist",
    }


def driver_entry(name):
    return {"Arguments": "", "Comment": name, "Enabled": True, "LoadEarly": False, "Path": name}


def previous_identity():
    """SMBIOS identity and Wi-Fi networks from the current build, so a rebuild keeps them."""
    generic, wifi = {}, None
    cfg_path = OUT / "OC" / "config.plist"
    if cfg_path.is_file():
        with open(cfg_path, "rb") as f:
            old = plistlib.load(f)["PlatformInfo"]["Generic"]
        if old.get("SystemSerialNumber") not in (None, "", "CHANGE_ME"):
            generic = {k: old[k] for k in ("SystemSerialNumber", "MLB", "SystemUUID", "ROM")}
    itlwm_path = OUT / "OC" / "Kexts" / "itlwm.kext" / "Contents" / "Info.plist"
    if itlwm_path.is_file():
        with open(itlwm_path, "rb") as f:
            nets = plistlib.load(f)["IOKitPersonalities"]["itlwm"].get("WiFiConfig", {})
        if nets and all(v.get("ssid") != "CHANGE_ME" for v in nets.values()):
            wifi = nets
    return generic, wifi


def set_itlwm_networks(kext_dir, networks):
    """Replace the sample networks shipped in itlwm's Info.plist; add_wifi.ps1 can add more later."""
    plist_path = kext_dir / "Contents" / "Info.plist"
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)
    info["IOKitPersonalities"]["itlwm"]["WiFiConfig"] = networks or {
        "WiFi_1": {"ssid": "CHANGE_ME", "password": "CHANGE_ME"}
    }
    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)


def add_missing_keys(cfg, sample):
    """Juno's config predates OpenCore 1.0.8; fill keys added since then with Sample.plist defaults."""
    for k, v in sample.items():
        if k.startswith("#"):
            continue
        if k not in cfg:
            cfg[k] = v
        elif isinstance(v, dict) and isinstance(cfg[k], dict):
            add_missing_keys(cfg[k], v)


def main():
    ap = argparse.ArgumentParser(description="Build the AN515-57 OpenCore EFI.")
    ap.add_argument("--verbose", action="store_true", help="add -v")
    ap.add_argument("--i2c-polling", action="store_true", help="add -vi2c-force-polling")
    ap.add_argument("--debug-oc", action="store_true", help="OpenCore DEBUG binaries + SysReport")
    ap.add_argument("--trace", action="store_true", help="WhateverXe DEBUG + display trace")
    ap.add_argument("--keep-dgpu", action="store_true", help="no SSDT-NM-DGPUOFF")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--public", action="store_true", help="placeholder serials/Wi-Fi (for sharing)")
    args = ap.parse_args()
    kexts = [(EX / "WhateverXe-linkfix-DEBUG" / "WhateverXe.kext", *k[1:]) if args.trace and k[1] == "WhateverXe.kext" else k
             for k in KEXTS]
    out = args.out
    OC_PKG = OC_DEBUG if args.debug_oc else OC_RELEASE

    generic, wifi = ({}, None) if args.public else previous_identity()
    if out.exists():
        shutil.rmtree(out)
    (out / "BOOT").mkdir(parents=True)
    oc = out / "OC"
    for sub in ("ACPI", "Drivers", "Kexts", "Tools", "Resources"):
        (oc / sub).mkdir(parents=True)

    # OpenCore binaries from the downloaded release (must all be the same version).
    for name in ("BOOTx64.efi", ".contentFlavour", ".contentVisibility"):
        shutil.copy2(OC_PKG / "BOOT" / name, out / "BOOT" / name)
    for name in ("OpenCore.efi", ".contentFlavour", ".contentVisibility"):
        shutil.copy2(OC_PKG / "OC" / name, oc / name)
    for name in DRIVERS:
        src = EX / ".." / "downloads" / name if name == "HfsPlus.efi" else OC_PKG / "OC" / "Drivers" / name
        shutil.copy2(src, oc / "Drivers" / name)
    shutil.copy2(OC_PKG / "OC" / "Tools" / "OpenShell.efi", oc / "Tools" / "OpenShell.efi")

    # ACPI tables from Juno's EFI (PC00/PR00 paths match this machine).
    for aml in (JUNO / "OC" / "ACPI").glob("*.aml"):
        shutil.copy2(aml, oc / "ACPI" / aml.name)

    # RTX 3050 off in macOS (tools/make_ssdt_dgpu_off.py): calls the firmware's own \_SB.PC00.PEG1.PXP_._OFF.
    if not args.keep_dgpu:
        shutil.copy2(PROJECT / "build" / "acpi" / "custom" / DGPU_SSDT, oc / "ACPI" / DGPU_SSDT)

    for src, bundle, _, _ in kexts:
        if src is not None:
            shutil.copytree(src, oc / "Kexts" / src.name)
    set_itlwm_networks(oc / "Kexts" / "itlwm.kext", wifi)

    with open(JUNO / "OC" / "config.plist", "rb") as f:
        cfg = plistlib.load(f)
    with open(EX / "OpenCore" / "Docs" / "Sample.plist", "rb") as f:
        sample = plistlib.load(f)
    for section in ("Booter", "Kernel", "Misc", "UEFI"):
        add_missing_keys(cfg[section], sample[section])
    cfg["Misc"]["Serial"].pop("Custom", None)  # unused with Override=false; not in 1.0.8 sample

    # NullMoth installer BAR rule (1401 "nullmoth-installer-bar").
    cfg["Booter"]["Quirks"]["ResizeAppleGpuBars"] = 0

    # HDA lives at 00:1f.3 on this machine, not 00:1b.0.
    cfg["DeviceProperties"]["Add"] = {
        "PciRoot(0x0)/Pci(0x1f,0x3)": {"layout-id": LAYOUT_ID.to_bytes(4, "little")},
        LAN_PATH: {"built-in": b"\x01"},
        IGPU_PATH: dict(IGPU_PROPS),
    }

    acpi_add = [a for a in cfg["ACPI"]["Add"] if a.get("Path") != DGPU_SSDT]
    if not args.keep_dgpu:
        acpi_add.append({"Comment": "RTX 3050 off in macOS (PEG1.PXP_._OFF)", "Enabled": True, "Path": DGPU_SSDT})
    cfg["ACPI"]["Add"] = acpi_add

    cfg["Kernel"]["Add"] = [kext_entry(b, e, o) for _, b, e, o in kexts]
    cfg["Kernel"]["Quirks"]["XhciPortLimit"] = False

    boot = cfg["Misc"]["Boot"]
    boot["HideAuxiliary"] = False
    boot["Timeout"] = 10
    # Win+V (Cmd+V) at the picker boots verbose once, Win+S single user, Shift safe mode: no EFI edit needed.
    boot["PollAppleHotKeys"] = True

    sec = cfg["Misc"]["Security"]
    sec["ScanPolicy"] = SCAN_POLICY
    sec["SecureBootModel"] = "Disabled"

    # Keep only OpenShell; drop CleanNvram and other tools that can touch firmware state.
    shell = next(t for t in cfg["Misc"]["Tools"] if t["Path"] == "OpenShell.efi")
    cfg["Misc"]["Tools"] = [shell]

    nv = cfg["NVRAM"]["Add"][APPLE_NVRAM]
    boot_args = (("-v " if args.verbose else "") + BOOT_ARGS + (" -vi2c-force-polling" if args.i2c_polling else "")
                 + (" -wexdbg -wex-display-trace" if args.trace else ""))
    nv["boot-args"] = boot_args
    nv["csr-active-config"] = bytes.fromhex("430A0000")  # 0xA43: covers WhateverXe's 0x803, NullMoth-tested
    nv.update(BT_NVRAM)
    delete = cfg["NVRAM"]["Delete"].setdefault(APPLE_NVRAM, [])
    delete += [k for k in BT_NVRAM if k not in delete]  # delete-then-add: rewritten every boot

    # SysReport (DEBUG OpenCore only) writes ACPI/SMBIOS/audio dumps to <ESP>\SysReport on the next boot.
    cfg["Misc"]["Debug"]["SysReport"] = bool(args.debug_oc)

    # Never reuse the serials that shipped with Juno's EFI; keep this machine's own identity across rebuilds.
    gen = cfg["PlatformInfo"]["Generic"]
    gen["SystemProductName"] = "MacBookPro16,2"
    gen["SystemSerialNumber"] = "CHANGE_ME"
    gen["MLB"] = "CHANGE_ME"
    gen["SystemUUID"] = str(uuid.uuid4()).upper()
    gen["ROM"] = os.urandom(6)
    gen.update(generic)

    # No ResetNvramEntry: clearing NVRAM can remove the Windows boot entry.
    cfg["UEFI"]["Drivers"] = [driver_entry(d) for d in DRIVERS]

    with open(oc / "config.plist", "wb") as f:
        plistlib.dump(cfg, f)

    print(f"EFI written to {out}  (OpenCore {'DEBUG + SysReport' if args.debug_oc else 'RELEASE'})")
    print(f"boot-args = {boot_args}")
    print(f"ScanPolicy = {SCAN_POLICY} (0x{SCAN_POLICY:X})")
    print(f"SMBIOS identity: {'kept from previous build' if generic else 'NEW - run macserial (finish_setup.ps1)'}")
    print(f"itlwm Wi-Fi: {', '.join(v['ssid'] for v in wifi.values()) + ' (kept)' if wifi else 'none - run add_wifi.ps1'}")


if __name__ == "__main__":
    main()
