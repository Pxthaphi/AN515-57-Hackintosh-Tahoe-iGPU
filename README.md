# Acer Nitro 5 AN515-57 — macOS Tahoe with an accelerated Intel iGPU

OpenCore EFI and tooling for running **macOS Tahoe 26.7.2** on an **Acer Nitro 5 AN515-57**
(i5-11400H Tiger Lake-H, Intel UHD 9A68, RTX 3050 Laptop, muxless), with **Metal acceleration on the
built-in panel through the Intel iGPU**.

This laptop is muxless: the internal panel is wired only to the iGPU. Other AN515-57 EFIs drive the display
through the NVIDIA card, which leaves this variant's panel black. This one uses
[WhateverXe](https://github.com/b00t0x/WhateverXe) 0.7.0 with seven extra binary patches (see
[`tools/patch_wex.py`](tools/patch_wex.py)), and switches the RTX 3050 off.

> macOS runs from an **external USB disk**. The internal NVMe and Windows are never touched, and
> `ScanPolicy` only shows USB devices in the boot picker.

## Status

| Component | Status | Notes |
|---|---|---|
| iGPU UHD 9A68 (internal eDP 1080p 144 Hz) | ✅ Metal accelerated | WhateverXe (patched) + WhateverXe-Graphics 0.4.0 pkg |
| Display sleep / wake | ✅ | "softsleep" patch: the link stays up, only the backlight goes off |
| Backlight + Fn brightness keys | ✅ | SSDT-PNLF + BrightnessKeys |
| RTX 3050 | ⛔ powered off | `SSDT-NM-DGPUOFF` (to keep it on, build with `--keep-dgpu`) |
| Safari / YouTube | ✅ | VA renderer hidden (WEX #23 crash). HEVC may fall back to software decode |
| Wi-Fi (Intel AX1650i CNVi) | ✅ native settings | AirportItlwm Tahoe 2.4.0-alpha. No AirDrop (no Intel AWDL) |
| Bluetooth | ✅ | IntelBluetoothFirmware 2.5.3 (lshbluesky fork) + BlueToolFixup |
| Touchpad ELAN0521 (I2C) | ✅ gestures | VoodooI2C master `6be653a2` (Tiger Lake-H I2C/GPIO, PR #586) |
| Keyboard (PS/2) | ✅ | VoodooPS2 2.3.7 |
| Audio ALC295 | ✅ | AppleALC `layout-id 21` + SimpleHDA (Tahoe removed AppleHDA) |
| Ethernet (Killer E2600) | ⚠️ untested | RealtekRTL8111 + `built-in` property |
| System sleep (S3) | ⚠️ avoid | still retrains the eDP link: use `sudo pmset sleep 0` |
| HDMI | ❓ untested | the author has no external monitor |

SMBIOS: `MacBookPro16,2`. SIP: `csr-active-config` = `0xA43` (required by the WhateverXe Graphics pkg).

## Hardware

| | |
|---|---|
| CPU | Intel Core i5-11400H (Tiger Lake-H) |
| iGPU | Intel UHD Graphics `8086:9A68` (TGL-H GT1) |
| dGPU | NVIDIA RTX 3050 Laptop `10DE:25A2`, muxless |
| Audio | Realtek ALC295 at `PciRoot(0x0)/Pci(0x1f,0x3)` |
| Wi-Fi / BT | Intel AX1650i CNVi `8086:43F0` / USB `8087:0026` |
| LAN | Killer E2600 (Realtek `10EC:2600`) |
| Touchpad | ELAN0521, I2C HID on `8086:43E9`, GPIO `INT34C6` |
| Storage | NVMe in Intel VMD/RAID mode (not used by macOS) |

The i7-11800H variant has a `9A60` iGPU. It should behave the same, but it hasn't been tested with this EFI.

## Using the EFI

1. **Generate your own SMBIOS.** `EFI/OC/config.plist` ships with `CHANGE_ME` placeholders. Run
   [macserial](https://github.com/acidanthera/OpenCorePkg) for `MacBookPro16,2`, then fill in
   `SystemSerialNumber`, `MLB`, `SystemUUID` and `ROM`.
2. **BIOS:** if BitLocker is on, suspend it in Windows first, then disable Secure Boot.
3. Copy `EFI` onto the EFI partition of a USB disk and install macOS Tahoe through Recovery.
   itlwm is included but disabled. To get network access in Recovery, enable it and put your network into its
   `WiFiConfig` (see `tools/add_wifi.ps1`).
4. **After the first boot into macOS**, install
   [WhateverXe-Graphics 0.4.0](https://github.com/b00t0x/WhateverXe-Graphics) (the `.pkg`). It provides the
   Tiger Lake framebuffer and accelerator. Without it there is no acceleration.
   To remove it later, boot Safe Mode (`-x` skips the auxiliary kext collection) and run its `uninstall.sh`.
5. Recommended: `sudo pmset sleep 0`. Display sleep is fine, but full system sleep isn't fixed yet.

**Tested install path:** the author installed with WhateverGreen + `-igfxvesa` (VESA, no acceleration), then
switched to this configuration. A fresh install straight onto this EFI is untested.

### Boot arguments

```
keepsyms=1 debug=0x100 alcid=21 -allow3d -disablegfxfirmware -igfxdvmt
```

- `-allow3d -disablegfxfirmware`: required by WhateverXe.
- `-igfxdvmt` + `framebuffer-patch-enable` / `framebuffer-stolenmem 0000C003` on `PciRoot(0x0)/Pci(0x2,0x0)`:
  the BIOS only pre-allocates 60 MB DVMT ("Insufficient stolen memory").
- `keepsyms=1 debug=0x100`: keeps a panic on screen instead of rebooting. Remove them once you're stable.
- Press `Cmd(Win)+V` in the OpenCore picker for a one-off verbose boot (`PollAppleHotKeys`).

## The WhateverXe patches

`tools/patch_wex.py` patches the **official** WhateverXe 0.7.0 RELEASE/DEBUG binary (symbol based, checked
with LIEF + Capstone; stubs live over Alder Lake-N DSI wrappers that Tiger Lake never calls). The full
reasoning for each patch is in the docstring.

| # | Patch | Problem it fixes |
|---|---|---|
| 1 | `gputicks` | Reading GPU_TICKS `0x2910` hard-hangs TGL-H GT1 at boot (WEX #11) |
| 2 | `linkclamp` | Donor writes `LINK_BW_SET 0x14` (HBR2) but the eDP 1.4 panel's `MAX_LINK_RATE` is `0x0a` (HBR) → black panel |
| 3 | `novarenderer` | Hides `IOVARendererID`: AppleIntelTGLGraphicsVADriver crashes WebKit.GPU / mediaanalysisd (WEX #23) |
| 4 | `keepvdd` | Panel VDD stays on during display sleep (after power-off the panel ignores AUX) |
| 5 | `transclk` | Sets TRANS_CLK_SEL / TRANS_DDI_FUNC_CTL before link training on DDI A |
| 6 | `tglpll` | Applies WEX's TGL DPLL CFGCR table fix also on eDP-only machines |
| 7 | `softsleep` | Display sleep keeps the link up and only switches the backlight off (idea from WEX #37) |

Patch 7 is what made wake work. Patches 4 to 6 were steps along the way and are kept because they're harmless.
`EFI/OC/Kexts/WhateverXe.kext` is the RELEASE build with all seven patches,
SHA-256 `245394112ff4ff549fb295fdfd130301915230270e6c57ab62fa8290736157bb`.

## RTX 3050 off (`SSDT-NM-DGPUOFF`)

Generated by [`tools/make_ssdt_dgpu_off.py`](tools/make_ssdt_dgpu_off.py) (hand-assembled AML, no iasl).
On this firmware `PEG1.PXP_` doesn't exist while Optimus is active, so `_INI` sets `\_SB.PC00.PEG1.PEGP.OMPR = 3`
and calls the firmware's own `PEGP._PS3`. The `_UID` of device `NMDG` reports what happened
(1 = `_INI` ran under Darwin, 2 = OMPR set to 3, 4 = `PXP_._OFF` called, 8 = `PEGP._PS3` called). On a working boot it reads `11`, and no `10de`
device shows up in `ioreg`.

## Tools

The scripts in [`tools/`](tools) are the author's working set. They expect the project at `D:\Nullmorth-macos`
with the downloaded releases under `build\downloads` / `build\extracted` (not included in this repo). Every
PowerShell script that writes to a disk only matches **one USB disk by serial number**: set `YOUR_DISK_SERIAL`
before use.

| Script | Purpose |
|---|---|
| `build_efi.py` | Builds the whole EFI (`--public`, `--trace`, `--keep-dgpu`, `--verbose`, `--debug-oc`) |
| `patch_wex.py` | WhateverXe binary patches |
| `make_ssdt_dgpu_off.py` | dGPU-off SSDT |
| `deploy_efi.ps1` | Copies an EFI to the USB disk's ESP and keeps the previous one as `EFI-prev` |
| `apply_*.ps1/.py`, `esp_kext.ps1`, `esp_lan.ps1`, `safe_mode.ps1`, `add_wifi.ps1` | Toggle individual pieces on the ESP |
| `nm_bootlog.sh`, `nm_waketest.sh`, `nm_logs.sh`, `esp_logs.ps1` | Collect macOS logs onto the ESP and pull them into Windows |
| `prepare_disk.ps1`, `get_installer.ps1` | Partition the USB disk / download the full installer |
| `old-sequoia/` | Scripts from the earlier Sequoia attempt |

## Known issues

- System sleep (S3) retrains the eDP link → black screen. Keep `pmset sleep 0`.
- On the first display wake after boot the screen may stay dark (backlight on) until the next input.
- Shutdown sometimes stalls (shutdownStall reports, not investigated yet).
- No AirDrop with Intel Wi-Fi. Intel Bluetooth on Tahoe can be fragile.
- One upstream report of random freezes on 9A68 (not seen here).

## Credits

- [acidanthera](https://github.com/acidanthera): OpenCore, Lilu, VirtualSMC, AppleALC, VoodooPS2, BrightnessKeys, BlueToolFixup
- [b00t0x/WhateverXe](https://github.com/b00t0x/WhateverXe) and WhateverXe-Graphics (incl. the AMFIPass Mod), and the
  contributors in its issues: Elezorn (`-wex-skip-gputicks`, #11), Thatisjigen (`-wex-no-va-renderer`), #37 (soft display sleep)
- [dhinakg](https://github.com/dhinakg): AMFIPass, USBToolBox
- [VoodooI2C](https://github.com/VoodooI2C/VoodooI2C), [OpenIntelWireless](https://github.com/OpenIntelWireless) (itlwm, IntelBluetoothFirmware)
- [laobamac](https://github.com/laobamac): AirportItlwm Tahoe, SimpleHDA · [lshbluesky](https://github.com/lshbluesky): IntelBluetoothFirmware 2.5.3
- [1Revenger1](https://github.com/1Revenger1): ECEnabler · Mieze: RealtekRTL8111
- [JunoDoesThings/AcerNitro5-AN515-57-Hackintosh](https://github.com/JunoDoesThings/AcerNitro5-AN515-57-Hackintosh): base config, ACPI and USB map
- [ptnzzn/Hackintosh-Acer-Nitro-5-AN515-57](https://github.com/ptnzzn/Hackintosh-Acer-Nitro-5-AN515-57): reference for the RTX 3060 variant

Third-party binaries keep their own licenses: see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
No Apple software is included apart from `HfsPlus.efi` from acidanthera/OcBinaryData.
