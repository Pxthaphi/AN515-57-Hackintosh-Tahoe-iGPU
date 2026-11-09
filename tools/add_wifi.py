"""Add or update a Wi-Fi network in itlwm's WiFiConfig. Reads NM_SSID and NM_PASS from the environment.

Usage: python add_wifi.py <Info.plist> [<Info.plist> ...]
Existing networks are kept. Passwords are never printed.
"""
import os
import plistlib
import sys


def add(path, ssid, password):
    with open(path, "rb") as f:
        info = plistlib.load(f)
    nets = info["IOKitPersonalities"]["itlwm"].setdefault("WiFiConfig", {})
    key = next((k for k, v in nets.items() if v.get("ssid") == ssid), None)
    if key is None:
        n = 1
        while f"WiFi_{n}" in nets:
            n += 1
        key = f"WiFi_{n}"
    nets[key] = {"ssid": ssid, "password": password}
    with open(path, "wb") as f:
        plistlib.dump(info, f)
    print(path)
    for k in sorted(nets, key=lambda x: int(x.split("_")[1])):
        print(f"  {k}: {nets[k]['ssid']}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        add(p, os.environ["NM_SSID"], os.environ["NM_PASS"])
