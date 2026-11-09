"""Binary-patch an official WhateverXe 0.7.0 kext (RELEASE or DEBUG) for the Acer Nitro 5 AN515-57 (TGL-H GT1 9A68).

Patch 1, gputicks: GPU_TICKS (0x2910) reads return 0.
  Same effect as Elezorn's `-wex-skip-gputicks` (b00t0x/WhateverXe issue #11), always on: reading 0x2910
  hard-hangs TGL-H GT1 (9A60 / 9A68) during boot.
  At XE::wrapTGLRegisterRead(void *access, unsigned long reg):
      if (reg == 0x2910) return 0;

Patch 2, linkclamp: keep LINK_BW_SET within the eDP panel's MAX_LINK_RATE.
  The panel is eDP 1.4: DPCD 12 0a c4 (MAX_LINK_RATE 0x0a = HBR 2.7 Gbps, 4 lanes) plus a
  SUPPORTED_LINK_RATES table that also lists 5.4 Gbps. getDPCDInfo folds that table into port+0xf (0x14),
  AGDC then picks 0x14 x2, and the donor writes LINK_BW_SET = 0x14 instead of using LINK_RATE_SET, so
  clock recovery fails on every lane and the panel goes black. The firmware link is 0x0a x4.
  (AppleIntelDisplayPath::getLinkConfig also never reports the current bitRate - "Bringup TODO".)
  SetStreamConfig -> AppleIntelPort::setLinkConfig stores AGDC's choice at port+0x558 and sets port+0x116;
  setupPort then programs PLL, M/N and training from port+0x55a (rate) / port+0x563 (lanes).
  At XE::wrapTGLModeTiming(controller, fb, timing), which hwSetMode calls before setupClocks/setupPort:
      path = fb[0x3FD8] == -1 ? fb[0x49F0] : fb[0x4A08];  port = path[0x3648];
      if (port && *port[0x548] == 0 /* DDI A */) port[0xf] = min(port[0xf], EDP_MAX_LINK_BW);
      if (... && port[0x116] /* AGDC config set */ && port[0x55a] > EDP_MAX_LINK_BW) {
          port[0x55a] = EDP_MAX_LINK_BW;               // rate  = MAX_LINK_RATE (0x0a)
          if (port[0x11]) port[0x563] = port[0x11];    // lanes = panel maximum (4)
      }
  Offsets are from AppleIntelTGLGraphicsFramebuffer 16.0.32 (Graphics 0.4.0): getDPCDInfo, setupPort,
  setLinkConfig, and WEX 0.7.0's own wrapTGLModeTiming.

Patch 3, novarenderer: same as Thatisjigen's `-wex-no-va-renderer` (WhateverXe branch pr/video-optin-0.7.0),
  always on. AppleIntelTGLGraphicsVADriver crashes at +0x1336f3 (NULL write) in
  AVFPixelProcess_PrepareToTransferImages for any VTPixelTransferSession: Safari's WebKit.GPU on YouTube,
  mediaanalysisd in a loop (WEX issue #23). Hiding IOVARendererID stops it; H.264 keeps hardware decode,
  HEVC in VTDecoderXPCService may fall back to software.
  At XE::wrapTGLAcceleratorStart(that, provider):  that->removeProperty("IOVARendererID");

Patch 4, keepvdd: PP_CONTROL writes keep PANEL_POWER_ON, so display sleep never powers the eDP panel off
  (after the donor's own power-on the panel ignores AUX and the wake modeset fails).
  At XE::wrapTGLRegisterWrite(access, reg, value):  if (reg == 0xC7204) value |= 1;

Patch 5, transclk: before link training on DDI A, set TRANS_CLK_SEL_A = port A and TRANS_DDI_FUNC_CTL_A to
  the firmware's value (Tiger Lake trains through the transcoder; the donor sets these only afterwards).

Patch 6, tglpll: apply WEX's own "r319" fix of the donor's combo PLL register tables (ICL DPLL CFGCR
  0x164000/0x164004 -> TGL 0x164284/0x164288, AppleIntelTGLGraphicsFramebuffer+0x9A0E8) on this
  eDP-only laptop too. WEX applies it only when an HDMI backend is wired (tglHDMIB, XE+0xfe2), so
  without it the donor's enableClocks reads and writes the HBR divisors to ICL addresses and the real
  DPLL0 relocks after display sleep without them: every lane fails clock recovery (2026-11-07 test 5:
  no CFGCR access in the trace, TGLHDMIComboPLLReady missing). The table patch is WEX's own lookup
  patch; this only removes the HDMI condition (the jcc after the "TGLPlatformNVRAMABIReady" property).

Patch 7, softsleep: display sleep keeps the eDP link up and only switches the backlight off (see
  softsleep_body). Test 6 (2026-11-07) showed the donor's retrain fails clock recovery even with a correct
  PLL; b00t0x/WhateverXe #37 (same panel class) found every retrain variant fails and fixed it this way.

All stubs live over XE::wrapDSISetPowerState (MIPI DSI only, Alder Lake-N; never used on Tiger Lake).
Addresses come from the symbol table; displaced instructions are decoded and checked to be position
independent, and no patched range may hold a relocation. Needs the lief and capstone packages.
Usage:
  python tools/patch_wex.py <WhateverXe.kext in> <WhateverXe.kext out> [gputicks,linkclamp,novarenderer]
"""
import hashlib
import shutil
import site
import struct
import sys
from pathlib import Path

sys.path.append(site.getusersitepackages())
import capstone  # noqa: E402
import lief  # noqa: E402

# MIPI DSI (Alder Lake-N) wrappers: only routed/called by the DSI backend, never on Tiger Lake.
CAVES = ["__ZN2XE20wrapDSISetPowerStateEP9IOServicej",
         "__ZN2XE16wrapDSISetStreamEP9IOServiceS1_P8OSObjectPKv",
         "__ZN2XE25wrapDSIGetModeInformationEP9IOServiceiPv",
         "__ZN2XE21wrapDSISetDisplayModeEP9IOServiceii",
         # Only called by XE::bindDSIResources <- XE::wrapAlderLakeNPowerInit (Alder Lake-N DSI).
         "__ZN2XE16probeDSICommandsEP9IOService"]


class Asm:
    """Tiny label-aware emitter for hand-encoded x86-64."""

    def __init__(self):
        self.code, self.labels, self.fix = bytearray(), {}, []

    def emit(self, hexbytes):
        self.code += bytes.fromhex(hexbytes)

    def jcc(self, opcode2, label):          # 0F xx rel32
        self.code += bytes([0x0F, opcode2]) + b"\0\0\0\0"
        self.fix.append((len(self.code) - 4, label))

    def label(self, name):
        self.labels[name] = len(self.code)

    def done(self):
        for at, name in self.fix:
            self.code[at:at + 4] = struct.pack("<i", self.labels[name] - (at + 4))
        return bytes(self.code)


JE, JNE, JBE = 0x84, 0x85, 0x86

# This panel's DPCD MAX_LINK_RATE (0x001): 0x0a = HBR 2.7 Gbps. It is an eDP 1.4 sink whose
# SUPPORTED_LINK_RATES table (0x010) also lists 5.4 Gbps; those rates may only be selected through
# LINK_RATE_SET (0x115), which the donor does not implement, so LINK_BW_SET must stay <= 0x0a.
# HBR x4 = 8.64 Gbps covers 1920x1080@144 (354.73 MHz x 24 bpp = 8.51 Gbps), as the firmware uses.
EDP_MAX_LINK_BW = 0x0A


def gputicks_body():
    # Byte-identical to the build already tested on the machine.
    return bytes.fromhex("4881fe10290000"   # cmp rsi, 0x2910
                         "7503"             # jne +3
                         "31c0"             # xor eax, eax
                         "c3")              # ret


def linkclamp_body():
    a = Asm()
    a.emit("4885f6"); a.jcc(JE, "out")               # test rsi,rsi            (fb)
    a.emit("8b86d83f0000")                           # mov eax,[rsi+0x3FD8]
    a.emit("83f8ff")                                 # cmp eax,-1
    a.emit("488b8ef0490000")                         # mov rcx,[rsi+0x49F0]    (flags kept)
    a.emit("7407")                                   # je +7
    a.emit("488b8e084a0000")                         # mov rcx,[rsi+0x4A08]
    a.emit("4885c9"); a.jcc(JE, "out")               # test rcx,rcx            (path)
    a.emit("488b8948360000")                         # mov rcx,[rcx+0x3648]    (port)
    a.emit("4885c9"); a.jcc(JE, "out")
    a.emit("488b8148050000")                         # mov rax,[rcx+0x548]     (port config)
    a.emit("4885c0"); a.jcc(JE, "out")
    a.emit("833800"); a.jcc(JNE, "out")              # cmp dword [rax],0       (DDI A only)
    a.emit("b0%02x" % EDP_MAX_LINK_BW)               # mov al, MAX_LINK_RATE (LINK_BW_SET-usable max)
    a.emit("38410f7603")                             # cmp [rcx+0xf],al ; jbe +3
    a.emit("88410f")                                 # mov [rcx+0xf],al        (max reported to AGDC / setupPort fallback)
    a.emit("80b91601000000"); a.jcc(JE, "out")       # cmp byte [rcx+0x116],0  (AGDC config present)
    a.emit("38815a050000"); a.jcc(JBE, "out")        # cmp [rcx+0x55a],al ; requested <= max -> keep
    a.emit("88815a050000")                           # mov [rcx+0x55a],al      (rate = max)
    a.emit("0fb64111")                               # movzx eax,byte [rcx+0x11] (sink max lanes)
    a.emit("84c0"); a.jcc(JE, "out")
    a.emit("888163050000")                           # mov [rcx+0x563],al      (lanes = max)
    a.label("out")
    return a.done()


def novarenderer_body():
    # that->removeProperty("IOVARendererID") at IntelAccelerator::start entry (rdi = that, rsi = provider).
    # IORegistryEntry::removeProperty(const char *) is vptr+0x2a0 (from the donor framebuffer's vtable
    # relocations; WEX's own setProperty calls at +0x268/+0x278 match the same layout).
    name = b"IOVARendererID\0"
    code = bytearray()
    code += bytes([0xEB, len(name)]) + name   # jmp over the string
    code += bytes.fromhex("575652")           # push rdi; push rsi; push rdx   (keeps 16-byte alignment)
    code += bytes.fromhex("488b07")           # mov rax, [rdi]                 (vtable)
    lea_at = len(code)
    code += bytes.fromhex("488d35") + struct.pack("<i", 2 - (lea_at + 7))   # lea rsi, [rip -> string]
    code += bytes.fromhex("ff90a0020000")     # call [rax + 0x2a0]             (removeProperty(const char *))
    code += bytes.fromhex("5a5e5f")           # pop rdx; pop rsi; pop rdi
    return bytes(code)


def keepvdd_body():
    # XE::wrapTGLRegisterWrite(void *access, unsigned long reg, uint32_t value): rsi = reg, edx = value.
    # PP_CONTROL (0xC7204) keeps PANEL_POWER_ON (bit 0): display sleep then only drops the backlight
    # (bit 2 + PWM). Seen 2026-11-07: after the donor powers the panel off (0x62) and on again (0x63),
    # PP_STATUS reports on but every AUX transaction to the panel times out for 6 s, so the wake
    # modeset can never train the link and WindowServer is killed by the watchdog.
    return bytes.fromhex("4881fe04720c00"   # cmp rsi, 0xC7204
                         "7503"             # jne +3
                         "83ca01")          # or edx, 1


REGWRITE = "__ZN2XE20wrapTGLRegisterWriteEPvmj"
REGREAD = "__ZN2XE19wrapTGLRegisterReadEPvm"


def transclk_body(va=0, syms=None):
    # XE::wrapTGLPortTraining(void *port, void *request): runs at AppleIntelPort::linkTraining entry.
    # Tiger Lake moved DP_TP_CTL into the transcoder, so the transcoder clock (TRANS_CLK_SEL) and
    # TRANS_DDI_FUNC_CTL must point at the port BEFORE link training (Linux tgl_ddi_pre_enable_dp
    # steps 7.a/7.b). The donor programs both only after training, which works at boot only because
    # the firmware left them set; after display sleep it has cleared them, the training pattern has no
    # clock and the panel sees nothing (all lanes 00). For DDI A, restore the firmware's values first:
    #   TRANS_CLK_SEL_A (0x46140) = 0x10000000  (port A)
    #   TRANS_DDI_FUNC_CTL_A (0x60400) = 0x0A010006 (DDI A, DP SST, 8 bpc, x4 = the GOP's 0x8A010006 without
    #   the enable bit, like Linux intel_ddi_config_transcoder_func; the donor sets enable with the pipe)
    # via WhateverXe's own wrapTGLRegisterWrite(access = port+0x578, reg, value).
    a = Asm()
    a.emit("575653")                              # push rdi; push rsi; push rbx   (16-byte aligned)
    a.emit("488b8748050000")                      # mov rax, [rdi+0x548]   port config
    a.emit("4885c0"); a.jcc(JE, "out")
    a.emit("833800"); a.jcc(JNE, "out")           # DDI A only
    a.emit("488b9f78050000")                      # mov rbx, [rdi+0x578]   register access manager
    a.emit("4885db"); a.jcc(JE, "out")
    # Only when TRANS_DDI_FUNC_CTL_A is disabled: never touch a running transcoder (boot/fast training).
    a.emit("4889df")                              # mov rdi, rbx
    a.emit("be00040600")                          # mov esi, 0x60400
    call_at = len(a.code)
    target = syms[REGREAD] if syms else 0
    a.emit("e8" + ((target - (va + call_at + 5)) & 0xFFFFFFFF).to_bytes(4, "little").hex())  # call RegisterRead
    a.emit("85c0"); a.jcc(0x88, "out")            # test eax,eax ; js out   (bit 31 = enabled)
    for reg, val in ((0x46140, 0x10000000), (0x60400, 0x0A010006)):
        a.emit("4889df")                          # mov rdi, rbx
        a.emit("be" + reg.to_bytes(4, "little").hex())   # mov esi, reg
        a.emit("ba" + val.to_bytes(4, "little").hex())   # mov edx, value
        call_at = len(a.code)
        target = syms[REGWRITE] if syms else 0
        a.emit("e8" + ((target - (va + call_at + 5)) & 0xFFFFFFFF).to_bytes(4, "little").hex())  # call
    a.label("out")
    a.emit("5b5e5f")                              # pop rbx; pop rsi; pop rdi
    return a.done()


# AppleIntelTGLGraphicsFramebuffer 16.0.0 (WhateverXe-Graphics 0.4.0): AppleIntelFramebuffer::prepareToExitWake
# (Wake -> Doze, i.e. display sleep) calls AppleIntelFramebuffer::disableDisplay(false) at +0x25332; the
# return address is +0x25337, whose 8 code bytes are unique in the donor.
SOFTSLEEP_RET_LOW12 = 0x337
SOFTSLEEP_RET_BYTES = bytes.fromhex("48ff0522310b0048")


def softsleep_body(va=0, syms=None):
    # XE::wrapTGLFBDisable(void *fb, bool) wraps AppleIntelFramebuffer::disableDisplay(bool).
    # Display sleep only (called from prepareToExitWake): keep pipe, transcoder, PLL and the trained eDP
    # link running and only clear EDP_BLC_ENABLE (PP_CONTROL bit 2) so the panel goes dark. Wake then gets
    # the donor's native "Partial modeset" (as at boot) instead of retraining, which fails clock recovery
    # on every lane on Tiger Lake (b00t0x/WhateverXe #37: same 1080p144 HBR x4 signature; its
    # -wex-tgl-edp-softsleep does the same and is confirmed on 9A49). Every other caller (setDisplayMode,
    # recoverDPLink, hwShutdown, freeDisplayResources, setupDisplayTiming) still disables normally.
    a = Asm()
    a.emit("488b0424")                                   # mov rax, [rsp]          return address
    a.emit("89c1")                                       # mov ecx, eax
    a.emit("81e1ff0f0000")                               # and ecx, 0xfff
    a.emit("81f9" + SOFTSLEEP_RET_LOW12.to_bytes(4, "little").hex()); a.jcc(JNE, "cont")
    a.emit("48b9" + SOFTSLEEP_RET_BYTES.hex())           # mov rcx, <code bytes at the return site>
    a.emit("483908"); a.jcc(JNE, "cont")                 # cmp [rax], rcx
    a.emit("53")                                         # push rbx               (16-byte aligned)
    a.emit("488b87d0010000")                             # mov rax, [rdi+0x1d0]   controller
    a.emit("4885c0"); a.jcc(JE, "out")
    a.emit("488b98400c0000")                             # mov rbx, [rax+0xc40]   register access manager
    a.emit("4885db"); a.jcc(JE, "out")
    for kind in ("read", "write"):
        a.emit("4889df")                                 # mov rdi, rbx
        a.emit("be04720c00")                             # mov esi, 0xC7204       PP_CONTROL
        if kind == "write":
            a.emit("83e0fb")                             # and eax, ~4            EDP_BLC_ENABLE off
            a.emit("89c2")                               # mov edx, eax
        call_at = len(a.code)
        target = (syms[REGREAD if kind == "read" else REGWRITE]) if syms else 0
        a.emit("e8" + ((target - (va + call_at + 5)) & 0xFFFFFFFF).to_bytes(4, "little").hex())
    a.label("out")
    a.emit("5b")                                         # pop rbx
    a.emit("c3")                                         # ret                    skip disableDisplay
    a.label("cont")
    return a.done()


PATCHES = {
    # name: (target symbol, body builder). Stubs are packed into relocation-free space of the cave,
    # gputicks first so its location matches earlier builds.
    "gputicks": ("__ZN2XE19wrapTGLRegisterReadEPvm", gputicks_body),
    "linkclamp": ("__ZN2XE17wrapTGLModeTimingEPvS0_S0_", linkclamp_body),
    "novarenderer": ("__ZN2XE23wrapTGLAcceleratorStartEP9IOServiceS1_", novarenderer_body),
    "keepvdd": (REGWRITE, keepvdd_body),
    "transclk": ("__ZN2XE19wrapTGLPortTrainingEPvS0_", transclk_body),
    "softsleep": ("__ZN2XE16wrapTGLFBDisableEPvb", softsleep_body),
}
NEEDS_ADDR = {transclk_body, softsleep_body}


def tglpll_gate(data, binary, rel, md):
    """NOP the `if (tglHDMIB)` jcc in XE::processKextFull that guards the donor PLL table patch."""
    needle = b"TGLPlatformNVRAMABIReady\0"
    st = bytes(data).find(needle)
    if st < 0 or data[st - 1] != 0:
        sys.exit("tglpll: property string not found")
    seg = [s for s in binary.segments if s.file_offset <= st < s.file_offset + s.file_size][0]
    sva = st - seg.file_offset + seg.virtual_address
    text = binary.get_section("__text")
    lo = text.virtual_address
    tb = bytes(data[file_offset(binary, lo):file_offset(binary, lo) + text.size])
    xrefs = [lo + i for i in range(len(tb) - 7)
             if tb[i] in (0x48, 0x4C) and tb[i + 1] == 0x8D and (tb[i + 2] & 0xC7) == 5
             and lo + i + 7 + struct.unpack_from("<i", tb, i + 3)[0] == sva]
    if len(xrefs) != 1:
        sys.exit(f"tglpll: expected one reference to the property string, found {len(xrefs)}")
    start = file_offset(binary, xrefs[0])
    ins = list(md.disasm(bytes(data[start:start + 80]), xrefs[0]))
    for k, i in enumerate(ins[:-1]):
        if i.mnemonic in ("cmp", "test") and i.op_str.startswith("byte ptr [") and "+ 0xfe2]" in i.op_str:
            j = ins[k + 1]
            if j.mnemonic not in ("je", "jne") or j.size != 6 or j.bytes[0] != 0x0F:
                sys.exit(f"tglpll: unexpected branch after the HDMI check: {j.mnemonic} {j.op_str}")
            # The skipped block must start with the ICL table constant (0x164000).
            nxt = bytes(data[file_offset(binary, j.address + 6):file_offset(binary, j.address + 6) + 64])
            if struct.pack("<I", 0x164000) not in nxt:
                sys.exit("tglpll: block after the branch does not build the PLL table")
            if any(a in rel for a in range(j.address, j.address + 6)):
                sys.exit("tglpll: branch overlaps a relocation")
            off = file_offset(binary, j.address)
            data[off:off + 6] = b"\x90" * 6
            print(f"tglpll: {i.mnemonic} {i.op_str} at {i.address:#x}; NOP {j.mnemonic} {j.op_str} at {j.address:#x}")
            return
    sys.exit("tglpll: HDMI check (byte [reg + 0xfe2]) not found after the property string")


def relocations(raw, binary):
    d = binary.dynamic_symbol_command
    out = set()
    for off, n in ((d.external_relocation_offset, d.nb_external_relocations),
                   (d.local_relocation_offset, d.nb_local_relocations)):
        for k in range(n):
            addr, _info = struct.unpack_from("<iI", raw, off + 8 * k)
            out.update(range(addr, addr + 8))
    return out


def file_offset(binary, vaddr):
    seg = binary.segment_from_virtual_address(vaddr)
    return vaddr - seg.virtual_address + seg.file_offset


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    wanted = (sys.argv[3] if len(sys.argv) > 3 else "gputicks,linkclamp,novarenderer,keepvdd,transclk,tglpll,softsleep").split(",")
    exe_rel = Path("Contents/MacOS/WhateverXe")
    raw = (src / exe_rel).read_bytes()
    data = bytearray(raw)
    print("input sha256:", hashlib.sha256(raw).hexdigest())
    b = lief.parse(str(src / exe_rel))
    syms = {s.name: s.value for s in b.symbols if s.value}
    rel = relocations(raw, b)
    caves = [[syms[c], min(v for v in syms.values() if v > syms[c])] for c in CAVES]  # [next free, end]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    for name in [n for n in PATCHES if n in wanted]:
        target, body = PATCHES[name]
        entry_va = syms[target]
        entry = file_offset(b, entry_va)
        displaced, size = [], 0
        for ins in md.disasm(bytes(data[entry:entry + 32]), entry_va):
            if ins.bytes[0] == 0xE9 and size == 0:
                sys.exit(f"{name}: entry already starts with a jmp: already patched?")
            if "rip" in ins.op_str or set(ins.groups) & {capstone.CS_GRP_JUMP, capstone.CS_GRP_CALL, capstone.CS_GRP_RET}:
                sys.exit(f"{name}: cannot displace position-dependent instruction: {ins.mnemonic} {ins.op_str}")
            displaced.append(ins)
            size += ins.size
            if size >= 5:
                break
        length = len(body()) + size + 5
        for cave in caves:
            cave_va = cave[0]
            while cave_va + length <= cave[1] and any(a in rel for a in range(cave_va, cave_va + length)):
                cave_va += 1
            if cave_va + length <= cave[1]:
                cave[0] = cave_va + length + 1
                break
        else:
            sys.exit(f"{name}: no relocation-free space of {length} bytes in any cave")
        stub = bytearray(body(cave_va, syms) if body in NEEDS_ADDR else body())
        stub += data[entry:entry + size]
        stub += b"\xe9" + struct.pack("<i", (entry_va + size) - (cave_va + len(stub) + 5))
        for va, n, what in ((entry_va, size, "entry"), (cave_va, len(stub), "stub")):
            if any(a in rel for a in range(va, va + n)):
                sys.exit(f"{name}: {what} range overlaps a relocation; refusing to patch")
        cave = file_offset(b, cave_va)
        data[cave:cave + len(stub)] = stub
        data[entry:entry + size] = b"\xe9" + struct.pack("<i", cave_va - (entry_va + 5)) + b"\x90" * (size - 5)
        print(f"{name}: entry {entry_va:#x} -> stub {cave_va:#x} ({len(stub)} bytes); displaced: "
              + "; ".join(f"{i.mnemonic} {i.op_str}" for i in displaced))

    if "tglpll" in wanted:
        tglpll_gate(data, b, rel, md)

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / exe_rel).write_bytes(data)
    print("output sha256:", hashlib.sha256(data).hexdigest())
    print("wrote", dst)


if __name__ == "__main__":
    main()
