"""Find and download the full macOS installer (InstallAssistant.pkg) from Apple's software update catalog.

  python fetch_installer.py list                                # show available Sequoia installers
  python fetch_installer.py download <product> <dir> [--fancy]  # resumable multi-connection download + chunklist verify

<dir> may be "auto" to use the volume labelled INSTALLER. --fancy draws a coloured multi-line
status for cmd (download_macos.cmd uses it); without it the status is one plain ASCII line.

Everything comes from Apple's own servers (swscan/swcdn.apple.com), the same ones Recovery uses.
"""
import gzip
import hashlib
import json
import os
import plistlib
import re
import struct
import sys
import threading
import time
import urllib.request

CATALOG = ("https://swscan.apple.com/content/catalogs/others/"
           "index-15-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-10.10-10.9"
           "-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog.gz")
UA = {"User-Agent": "Software%20Update (unknown version) CFNetwork/807.0.1 Darwin/16.0.0 (x86_64)"}
CONNECTIONS = 4
PIECE = 8 * 1024 * 1024  # bytes per work unit; small so a dropped connection loses little


def fetch(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def sequoia_products():
    raw = fetch(CATALOG).read()
    cat = plistlib.loads(gzip.decompress(raw))
    found = []
    for pid, p in cat["Products"].items():
        ids = p.get("ExtendedMetaInfo", {}).get("InstallAssistantPackageIdentifiers", {})
        if "macOSSequoia" not in ids.get("SharedSupport", ""):
            continue
        pkg = next((x for x in p.get("Packages", []) if x["URL"].endswith("InstallAssistant.pkg")), None)
        if not pkg:
            continue
        dist = fetch(p["Distributions"]["English"]).read().decode("utf-8", "replace")
        ver = re.search(r"<key>VERSION</key>\s*<string>([^<]+)", dist)
        build = re.search(r"<key>BUILD</key>\s*<string>([^<]+)", dist)
        found.append({
            "product": pid,
            "version": ver.group(1) if ver else "?",
            "build": build.group(1) if build else "?",
            "posted": str(p.get("PostDate", ""))[:10],
            "size_gb": round(pkg["Size"] / 1e9, 2),
            "url": pkg["URL"],
            "size": pkg["Size"],
            "chunklist": pkg.get("IntegrityDataURL"),
        })
    found.sort(key=lambda x: [int(n) if n.isdigit() else 0 for n in x["version"].split(".")], reverse=True)
    return found


def parse_chunklist(data):
    """Apple chunklist: 36-byte header, then (uint32 size, 32-byte SHA-256) per chunk."""
    magic, _hdr, _ver, _cm, _sm, _pad, count, off, _sig = struct.unpack("<4sIBBBBQQQ", data[:36])
    if magic != b"CNKL":
        raise ValueError("not a chunklist")
    chunks = []
    for i in range(count):
        size, digest = struct.unpack("<I32s", data[off + i * 36: off + (i + 1) * 36])
        chunks.append((size, digest))
    return chunks


SPINNER = "|/-\\"
BAR = 30


def progress_line(tick, label, have, total, rate=None):
    """One status line: spinner, bar, GB done/total, percent, then speed + time left when downloading."""
    frac = have / total if total else 0
    fill = int(frac * BAR)
    # ASCII only: the Thai console codepage (cp874) cannot encode block characters.
    line = (f"\r {SPINNER[tick % len(SPINNER)]} {label} [{'#' * fill}{'-' * (BAR - fill)}] "
            f"{frac * 100:5.1f}%  {have / 1e9:5.2f}/{total / 1e9:.2f} GB")
    if rate is not None:
        left = (total - have) / rate if rate > 0 else 0
        line += f"  left {(total - have) / 1e9:5.2f} GB  {rate / 1e6:4.2f} MB/s  ETA {int(left // 3600)}h{int(left % 3600 // 60):02d}m"
    return line + "   "


def fmt_eta(seconds):
    return f"{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m"


class PlainDisplay:
    """Single \\r-updated ASCII line (PowerShell, redirected output)."""

    def message(self, text):
        print(text, flush=True)

    def update(self, tick, label, have, total, rate=None, retries=0):
        note = f"  retries {retries}" if retries else ""
        print(progress_line(tick, label, have, total, rate) + note, end="", flush=True)

    def finish(self):
        print(flush=True)


class FancyDisplay:
    """Coloured three-line status redrawn in place with ANSI escapes (cmd / Windows Terminal)."""
    SPIN = "▖▘▝▗"
    PARTS = " ▏▎▍▌▋▊▉"
    WIDTH = 40
    C = {"cyan": "\x1b[96m", "green": "\x1b[92m", "dim": "\x1b[90m", "yellow": "\x1b[93m",
         "magenta": "\x1b[95m", "red": "\x1b[91m", "bold": "\x1b[1m", "off": "\x1b[0m"}

    def __init__(self, title):
        self.title = title
        self.drawn = False
        sys.stdout.write("\x1b[?25l")  # hide cursor while redrawing

    def message(self, text):
        print(f"  {text}", flush=True)

    def bar(self, frac):
        cells = frac * self.WIDTH
        full = int(cells)
        part = self.PARTS[int((cells - full) * 8)] if full < self.WIDTH else ""
        empty = self.WIDTH - full - (1 if part else 0)
        c = self.C
        return f"{c['green']}{'█' * full}{part}{c['dim']}{'░' * empty}{c['off']}"

    def update(self, tick, label, have, total, rate=None, retries=0):
        c = self.C
        frac = have / total if total else 0
        stats = f"{have / 1e9:5.2f} / {total / 1e9:.2f} GB"
        if rate is not None:
            left = (total - have) / rate if rate > 0 else 0
            stats += (f"  {c['dim']}•{c['off']}  left {(total - have) / 1e9:.2f} GB"
                      f"  {c['dim']}•{c['off']}  {c['yellow']}{rate / 1e6:.2f} MB/s{c['off']}"
                      f"  {c['dim']}•{c['off']}  ETA {c['magenta']}{fmt_eta(left)}{c['off']}")
        if retries:
            stats += f"  {c['dim']}•{c['off']}  {c['red']}retries {retries}{c['off']}"
        lines = [
            f"  {c['cyan']}{self.SPIN[tick % len(self.SPIN)]}{c['off']} {c['bold']}{label}{c['off']} {self.title}",
            f"    {self.bar(frac)}  {c['bold']}{frac * 100:5.1f}%{c['off']}",
            f"    {stats}",
        ]
        out = "\x1b[3F" if self.drawn else ""  # back to the first of our three lines
        out += "".join(f"\x1b[2K{line}\n" for line in lines)
        sys.stdout.write(out)
        sys.stdout.flush()
        self.drawn = True

    def finish(self):
        self.drawn = False
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def enable_ansi():
    """Turn on VT escape processing for this console; False if not a console or not supported."""
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    handle = k32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(k32.SetConsoleMode(handle, mode.value | 0x0004))


def find_volume(label):
    """Drive root of the volume with this label, e.g. 'T:\\'."""
    import ctypes
    import string
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        name = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(root, name, 261, None, None, None, None, 0):
            if name.value.upper() == label:
                return root
    sys.exit(f"No volume labelled {label} found. Is the Seagate disk plugged in?")


def download(product, outdir, fancy=False):
    info = next((x for x in sequoia_products() if x["product"] == product), None)
    if not info:
        sys.exit(f"Product {product} not found in Apple's catalog.")
    if outdir.lower() == "auto":
        outdir = find_volume("INSTALLER")
    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, "InstallAssistant.pkg")
    state_path = dest + ".progress.json"
    verified_path = dest + ".verified"
    total = info["size"]
    sys.stdout.reconfigure(errors="replace")
    title = f"macOS {info['version']} ({info['build']})"
    display = FancyDisplay(title) if fancy and enable_ansi() else PlainDisplay()
    try:
        _download(info, dest, state_path, verified_path, total, title, display)
    finally:
        display.finish()


def _download(info, dest, state_path, verified_path, total, title, display):
    display.message(f"{title}, {info['size_gb']} GB -> {dest}")

    if os.path.exists(verified_path) and os.path.exists(dest) and os.path.getsize(dest) == total:
        display.message("Already downloaded and verified. Ready to install.")
        return

    pieces = list(range(0, total, PIECE))
    done = set()
    if os.path.exists(state_path) and os.path.exists(dest):
        done = set(json.load(open(state_path))["done"])
        display.message(f"Resuming: {len(done)}/{len(pieces)} pieces already here.")
    else:
        # No preallocation: on exFAT Windows would zero-fill the whole 15 GB first.
        open(dest, "wb").close()
        with open(state_path, "w") as f:
            json.dump({"done": []}, f)

    lock = threading.Lock()
    todo = [p for p in pieces if p not in done]
    have = [sum(min(PIECE, total - p) for p in done)]  # bytes on disk, including pieces in flight
    retries = [0]
    start, start_have = time.time(), have[0]

    def save():
        with open(state_path, "w") as f:
            json.dump({"done": sorted(done)}, f)

    def worker():
        fh = open(dest, "r+b")
        while True:
            with lock:
                if not todo:
                    break
                p = todo.pop(0)
            end = min(p + PIECE, total) - 1
            attempt = 0
            while True:
                attempt += 1
                partial = 0
                try:
                    with fetch(info["url"], {"Range": f"bytes={p}-{end}"}, timeout=60) as r:
                        fh.seek(p)
                        while True:
                            b = r.read(256 * 1024)
                            if not b:
                                break
                            fh.write(b)
                            partial += len(b)
                            with lock:
                                have[0] += len(b)
                    if partial != end - p + 1:
                        raise IOError("short read")
                    fh.flush()
                    with lock:
                        done.add(p)
                        save()
                    break
                except Exception:  # mobile data drops are expected; undo this piece's count and retry
                    with lock:
                        have[0] -= partial
                        retries[0] += 1
                    time.sleep(min(30, 2 * attempt))
        fh.close()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONNECTIONS)]
    for t in threads:
        t.start()
    tick = 0
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.25)
            tick += 1
            el = time.time() - start
            rate = (have[0] - start_have) / el if el > 1 else 0
            display.update(tick, "Downloading", have[0], total, rate, retries[0])
    except KeyboardInterrupt:
        display.finish()
        display.message("\nStopped. Run the same command again to continue from here.")
        os._exit(1)
    display.finish()

    display.message("Verifying against Apple's checksums (reads the whole file; a few minutes on a USB HDD) ...")
    chunks = parse_chunklist(fetch(info["chunklist"]).read())
    if sum(s for s, _ in chunks) != total:
        sys.exit("Chunklist size does not match the package. Not verified.")
    bad, pos = set(), 0
    with open(dest, "rb") as f:
        for i, (size, digest) in enumerate(chunks):
            if hashlib.sha256(f.read(size)).digest() != digest:
                # Every piece this chunk overlaps must be fetched again.
                bad.update(range(pos // PIECE * PIECE, pos + size, PIECE))
            pos += size
            if i % 4 == 0 or i == len(chunks) - 1:
                display.update(i, "Verifying  ", pos, total)
    display.finish()
    if bad:
        done.difference_update(bad)
        save()
        sys.exit(f"{len(bad)} piece(s) failed verification. Run the same command again to re-download them.")
    os.remove(state_path)
    open(verified_path, "w").write(f"{info['version']} {info['build']}\n")
    display.message("OK: file matches Apple's checksums. Ready to install.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        for x in sequoia_products():
            print(f"{x['product']:>14}  macOS {x['version']:<8} {x['build']:<8} posted {x['posted']}  {x['size_gb']} GB")
    elif len(sys.argv) in (4, 5) and sys.argv[1] == "download":
        download(sys.argv[2], sys.argv[3], fancy="--fancy" in sys.argv[4:])
    else:
        print(__doc__)
