"""Write SSDT-NM-DGPUOFF.aml: power off the RTX 3050 (\\_SB.PC00.PEG1.PEGP) when macOS boots.

There is no iasl here, so this emits the AML bytes of the following ASL directly:

    DefinitionBlock ("", "SSDT", 2, "NMORTH", "DGPUOFF", 0x00001000)
    {
        External (_SB_.PC00.PEG1.PXP_._OFF, MethodObj)    // 0 arguments
        External (_SB_.PC00.PEG1.CPMV, IntObj)
        Scope (\\_SB)
        {
            Device (NMDG)
            {
                Name (_HID, "NMDG0000")
                Name (NMST, Zero)
                Method (_STA, 0, NotSerialized)
                {
                    If (_OSI ("Darwin")) { Return (0x0F) }
                    Return (Zero)
                }
                Method (_UID, 0, NotSerialized) { Return (NMST) }
                Method (_INI, 0, NotSerialized)
                {
                    If (_OSI ("Darwin"))
                    {
                        NMST = One
                        If (CondRefOf (\\_SB.PC00.PEG1.CPMV))
                        {
                            If (\\_SB.PC00.PEG1.CPMV) { NMST |= 4 }
                            \\_SB.PC00.PEG1.CPMV = Zero
                            NMST |= 2
                        }
                        If (CondRefOf (\\_SB.PC00.PEG1.PXP_._OFF)) { \\_SB.PC00.PEG1.PXP_._OFF (); NMST |= 8 }
                    }
                }
            }
        }
    }

PXP_ is the firmware's own RTD3 power resource for the dGPU root port (SSDT "RTD3" in this machine's
ACPI, SysReport SSDT-13: _PR0/_PR3 of PEG1, _OFF = DGOF, DL23, D2OF, POFF). Windows drives the GPU into
D3cold through the same _OFF. _OSI("Darwin") keeps it out of any other OS booted through OpenCore.
Usage: python tools/make_ssdt_dgpu_off.py <out.aml>
"""
import sys


def pkglen(body_len):
    """AML PkgLength that includes its own encoding."""
    for extra in range(4):
        total = body_len + 1 + extra
        if extra == 0 and total < 0x40:
            return bytes([total])
        if extra and total < (1 << (4 + 8 * extra)):
            out = [((extra) << 6) | (total & 0x0F)]
            v = total >> 4
            for _ in range(extra):
                out.append(v & 0xFF)
                v >>= 8
            return bytes(out)
    raise ValueError("package too large")


def pkg(op, body):
    return op + pkglen(len(body)) + body


def namestring(path):
    """'\\_SB_.PC00.PEG1.PXP_._OFF' or 'NMDG' -> AML NameString."""
    root = path.startswith("\\")
    segs = [s.ljust(4, "_").encode() for s in path.lstrip("\\").split(".")]
    for s in segs:
        assert len(s) == 4, s
    prefix = b"\\" if root else b""
    if len(segs) == 1:
        return prefix + segs[0]
    if len(segs) == 2:
        return prefix + b"\x2E" + b"".join(segs)          # DualNamePrefix
    return prefix + b"\x2F" + bytes([len(segs)]) + b"".join(segs)  # MultiNamePrefix


def string(s):
    return b"\x0D" + s.encode() + b"\x00"


OFF = "\\_SB_.PC00.PEG1.PXP_._OFF"
CPMV = "\\_SB_.PC00.PEG1.CPMV"
OMPR = "\\_SB_.PC00.PEG1.PEGP.OMPR"
PS3 = "\\_SB_.PC00.PEG1.PEGP._PS3"
osi_darwin = namestring("_OSI") + string("Darwin")         # _OSI ("Darwin")
NMST = namestring("NMST")


def or_nmst(bit):
    return b"\x7D" + NMST + b"\x0A" + bytes([bit]) + NMST     # Or (NMST, bit, NMST)


def build():
    # v3 (2026-11-07): v2 reported _UID 3: CPMV existed and was already 0, but PXP_ does not exist.
    # SSDT-13 only defines the RTD3 PowerResource PXP_ when hybrid graphics is off
    # (If ((HGMD != 2 && HGMD != 3) || HGST == 0)); this laptop runs Optimus, where the NVIDIA SSDT
    # (SysReport SSDT-15, Scope \_SB.PC00.PEG1.PEGP) does it: _PS3 powers the GPU off through
    # \_SB.PC00.PGOF(1) / HGOF only when OMPR == 3, which the NVIDIA driver normally sets through its
    # Optimus _DSM (NVOP 0x1A). Set OMPR = 3 and call _PS3 (the "Optimus method" of Dortania's
    # SSDT-dGPU-Off). PXP_._OFF is still tried for the non-hybrid BIOS setting.
    # NMST is returned by _UID, which macOS publishes in the IORegistry:
    #   1 _INI ran under Darwin, 2 OMPR set to 3, 4 PXP_._OFF called, 8 PEGP._PS3 called.
    sta = pkg(b"\x14", namestring("_STA") + b"\x00" +
              pkg(b"\xA0", osi_darwin + b"\xA4\x0A\x0F") +   # If (...) { Return (0x0F) }
              b"\xA4\x00")                                     # Return (Zero)
    uid = pkg(b"\x14", namestring("_UID") + b"\x00" + b"\xA4" + NMST)   # Return (NMST)

    def cond(path, body):                                      # If (CondRefOf (path)) { body }
        return pkg(b"\xA0", b"\x5B\x12" + namestring(path) + b"\x00" + body)

    ini = pkg(b"\x14", namestring("_INI") + b"\x00" +
              pkg(b"\xA0", osi_darwin +
                  b"\x70\x01" + NMST +                                         # NMST = One
                  cond(OFF, namestring(OFF) + or_nmst(4)) +                    # PXP_._OFF ()   (non-hybrid)
                  cond(OMPR, b"\x70\x0A\x03" + namestring(OMPR) + or_nmst(2)) +  # OMPR = 3
                  cond(PS3, namestring(PS3) + or_nmst(8))))                    # PEGP._PS3 ()
    dev = pkg(b"\x5B\x82", namestring("NMDG") +
              b"\x08" + namestring("_HID") + string("NMDG0000") +
              b"\x08" + NMST + b"\x00" +                                       # Name (NMST, Zero)
              sta + uid + ini)
    scope = pkg(b"\x10", namestring("\\_SB_") + dev)
    external = (b"\x15" + namestring(OFF) + b"\x08" + b"\x00" +   # External (..., MethodObj), 0 args
                b"\x15" + namestring(PS3) + b"\x08" + b"\x00" +   # External (..., MethodObj), 0 args
                b"\x15" + namestring(OMPR) + b"\x01" + b"\x00")   # External (..., IntObj)
    body = external + scope

    hdr = bytearray(36)
    hdr[0:4] = b"SSDT"
    hdr[4:8] = (36 + len(body)).to_bytes(4, "little")
    hdr[8] = 2                                    # revision
    hdr[10:16] = b"NMORTH"
    hdr[16:24] = b"DGPUOFF\x00"
    hdr[24:28] = (0x1000).to_bytes(4, "little")   # OEM revision
    hdr[28:32] = b"INTL"
    hdr[32:36] = (0x20260930).to_bytes(4, "little")
    table = bytearray(hdr + body)
    table[9] = (-sum(table)) & 0xFF               # checksum
    assert sum(table) & 0xFF == 0
    return bytes(table)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = build()
    open(sys.argv[1], "wb").write(data)
    print(f"wrote {sys.argv[1]} ({len(data)} bytes)")
