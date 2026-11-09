"""Sanity-check the built EFI against OpenCore's Sample.plist and the files on disk."""
import plistlib
from pathlib import Path

EFI = Path(r"D:\Nullmorth-macos\build\USB\EFI\OC")
SAMPLE = Path(r"D:\Nullmorth-macos\build\extracted\OpenCore\Docs\Sample.plist")


def walk(sample, cfg, path, problems):
    """Report dict keys missing from or unknown to the config, recursively (dicts only)."""
    if not isinstance(sample, dict) or not isinstance(cfg, dict):
        return
    for k, v in sample.items():
        if k.startswith("#"):
            continue
        if k not in cfg:
            problems.append(f"MISSING  {path}/{k}  (sample default: {v!r})")
        else:
            walk(v, cfg[k], f"{path}/{k}", problems)
    for k in cfg:
        if not k.startswith("#") and k not in sample:
            problems.append(f"UNKNOWN  {path}/{k}")


# Sections whose dict keys are user data (device paths, GUIDs), not schema.
FREEFORM = {"/DeviceProperties/Add", "/DeviceProperties/Delete", "/NVRAM/Add", "/NVRAM/Delete", "/NVRAM/LegacySchema"}


def main():
    cfg = plistlib.loads((EFI / "config.plist").read_bytes())
    sample = plistlib.loads(SAMPLE.read_bytes())

    problems = []
    walk(sample, cfg, "", problems)
    problems = [p for p in problems if not any(p.split()[1].startswith(f + "/") for f in FREEFORM)]

    for e in cfg["Kernel"]["Add"]:
        b = EFI / "Kexts" / e["BundlePath"]
        if not (b / e["PlistPath"]).is_file():
            problems.append(f"KEXT     plist missing: {e['BundlePath']}")
        if e["ExecutablePath"] and not (b / e["ExecutablePath"]).is_file():
            problems.append(f"KEXT     binary missing: {e['BundlePath']}/{e['ExecutablePath']}")
    for d in cfg["UEFI"]["Drivers"]:
        if not (EFI / "Drivers" / d["Path"]).is_file():
            problems.append(f"DRIVER   missing: {d['Path']}")
    for t in cfg["Misc"]["Tools"]:
        if not (EFI / "Tools" / t["Path"]).is_file():
            problems.append(f"TOOL     missing: {t['Path']}")
    for a in cfg["ACPI"]["Add"]:
        if a["Enabled"] and not (EFI / "ACPI" / a["Path"]).is_file():
            problems.append(f"ACPI     missing: {a['Path']}")

    # Wired LAN: Killer E2600 is Realtek 10EC:2600, driven by RealtekRTL8111.
    rtl = [e for e in cfg["Kernel"]["Add"] if e["BundlePath"] == "RealtekRTL8111.kext"]
    if not rtl or not rtl[0]["Enabled"]:
        problems.append("LAN      RealtekRTL8111.kext missing or disabled")
    else:
        info = plistlib.loads((EFI / "Kexts" / "RealtekRTL8111.kext" / "Contents" / "Info.plist").read_bytes())
        match = " ".join(p.get("IOPCIMatch", "") for p in info["IOKitPersonalities"].values())
        if "0x260010ec" not in match.lower():
            problems.append("LAN      RealtekRTL8111.kext does not match Killer E2600 (10EC:2600)")
    if "built-in" not in cfg["DeviceProperties"]["Add"].get("PciRoot(0x0)/Pci(0x1c,0x0)/Pci(0x0,0x0)", {}):
        problems.append("LAN      Ethernet port not marked built-in (run set_lan.py)")

    on_disk = {p.name for p in (EFI / "Kexts").iterdir()}
    used = {e["BundlePath"].split("/")[0] for e in cfg["Kernel"]["Add"]}
    for extra in sorted(on_disk - used):
        problems.append(f"KEXT     on disk but not in config: {extra}")

    print("\n".join(problems) if problems else "No problems found.")


if __name__ == "__main__":
    main()
