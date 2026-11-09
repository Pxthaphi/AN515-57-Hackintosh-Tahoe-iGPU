# Third-party notices

`EFI/` contains unmodified third-party binaries plus one modified binary
(`EFI/OC/Kexts/WhateverXe.kext`, patched with `tools/patch_wex.py`). Each component remains under its
upstream license. See the linked repositories for the full terms and the source code.

| Component | Version | Upstream |
|---|---|---|
| OpenCore (BOOTx64.efi, OpenCore.efi, OpenRuntime.efi, OpenUsbKbDxe.efi, OpenShell.efi) | 1.0.8 | https://github.com/acidanthera/OpenCorePkg |
| HfsPlus.efi | — | https://github.com/acidanthera/OcBinaryData |
| Lilu | 1.7.2 | https://github.com/acidanthera/Lilu |
| VirtualSMC, SMCProcessor, SMCBatteryManager | 1.3.8 | https://github.com/acidanthera/VirtualSMC |
| AppleALC | 1.9.8 | https://github.com/acidanthera/AppleALC |
| VoodooPS2Controller | 2.3.7 | https://github.com/acidanthera/VoodooPS2 |
| BrightnessKeys | 1.0.3 | https://github.com/acidanthera/BrightnessKeys |
| BlueToolFixup (BrcmPatchRAM) | 2.7.2 | https://github.com/acidanthera/BrcmPatchRAM |
| WhateverXe (**modified**) | 0.7.0 | https://github.com/b00t0x/WhateverXe |
| AMFIPass (Mod, from WhateverXe-Graphics extras) | 1.4.1 | https://github.com/b00t0x/WhateverXe-Graphics |
| ECEnabler | 1.0.6 | https://github.com/1Revenger1/ECEnabler |
| USBToolBox, UTBMap | 1.2.0 | https://github.com/USBToolBox/kext |
| VoodooI2C, VoodooI2CHID (master `6be653a2` CI build) | 2.9.1 | https://github.com/VoodooI2C/VoodooI2C |
| itlwm | 2.3.0 | https://github.com/OpenIntelWireless/itlwm |
| AirportItlwm (Tahoe) | 2.4.0-alpha `7204c69` | https://github.com/laobamac/itlwm |
| IntelBluetoothFirmware, IntelBTPatcher | 2.5.3 | https://github.com/lshbluesky/IntelBluetoothFirmware |
| SimpleHDA | 1.0.0 | https://github.com/laobamac/SimpleHDA |
| RealtekRTL8111 | 3.0.0 | https://github.com/Mieze/RTL8111_driver_for_OS_X |
| ACPI SSDT-EC/PLUG/PNLF/USB-Reset/XOSI, UTBMap | — | https://github.com/JunoDoesThings/AcerNitro5-AN515-57-Hackintosh |

## WhateverXe license

The modified `WhateverXe.kext` is distributed under its original license:

```
Copyright (c) 2018, vit9696

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

```
