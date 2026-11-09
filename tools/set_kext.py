"""Enable or disable kexts by BundlePath in OpenCore config.plist files.

Usage: python set_kext.py on|off <BundlePath>[,<BundlePath>...] <config.plist> [<config.plist> ...]
Only the Enabled flag changes; the kext files stay where they are.
"""
import plistlib
import sys


def toggle(path, on, bundles):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    found = [k for k in cfg["Kernel"]["Add"] if k["BundlePath"] in bundles]
    missing = set(bundles) - {k["BundlePath"] for k in found}
    if missing:
        sys.exit(f"{path}: not in Kernel > Add: {', '.join(sorted(missing))}")
    for k in found:
        k["Enabled"] = on
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(path)
    for k in found:
        print(f"  {k['BundlePath']} = {'on' if k['Enabled'] else 'off'}")


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("on", "off"):
        sys.exit(__doc__)
    names = sys.argv[2].split(",")
    for p in sys.argv[3:]:
        toggle(p, sys.argv[1] == "on", names)
