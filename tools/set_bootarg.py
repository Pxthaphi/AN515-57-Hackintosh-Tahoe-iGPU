"""Add or remove one boot-arg in OpenCore config.plist files.

Usage: python set_bootarg.py add|remove <arg> <config.plist> [<config.plist> ...]
Other boot-args are kept as they are.
"""
import plistlib
import sys

APPLE_NVRAM = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def edit(path, action, arg):
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    nv = cfg["NVRAM"]["Add"][APPLE_NVRAM]
    args = nv["boot-args"].split()
    if action == "add" and arg not in args:
        args.append(arg)
    elif action == "remove":
        args = [a for a in args if a != arg]
    nv["boot-args"] = " ".join(args)
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    print(path)
    print(f"  boot-args = {nv['boot-args']}")


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("add", "remove"):
        sys.exit(__doc__)
    for p in sys.argv[3:]:
        edit(p, sys.argv[1], sys.argv[2])
