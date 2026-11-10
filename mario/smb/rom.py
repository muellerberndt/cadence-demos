"""Find your own Super Mario Bros. dump and copy it in. The game is not included.

    python -m smb.rom ~/roms          # a .nes file or a folder of them

Each .nes file is checked by the SHA-1 of its PRG and CHR data (the 16-byte iNES header left
out). The dump the brain was raised and measured on has 0c4992fc08d2278697339d3b48066e7b5f943598
(CRC32 9A2DB086). It is copied to rom/smb.nes with a clean header, which .gitignore keeps out of
the repository.

Other Super Mario Bros. dumps (for example No-Intro's "Super Mario Bros. (World)", PRG+CHR CRC32
D445F698) differ from it in their bytes. `--any` accepts one anyway; the brain has not been
checked on it, and its play may differ.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

RAISED_SHA1 = "0c4992fc08d2278697339d3b48066e7b5f943598"
ROM = Path(__file__).resolve().parent.parent / "rom" / "smb.nes"
HEADER = bytes([0x4E, 0x45, 0x53, 0x1A, 2, 1, 0x01, 0]) + bytes(8)  # NROM, 2 x 16 KB PRG, 1 x 8 KB CHR, vertical


def payload(path: Path) -> bytes | None:
    """PRG + CHR of an iNES file, or None if it isn't a Super Mario Bros.-shaped cartridge."""
    b = path.read_bytes()
    if len(b) < 16 or b[:4] != b"NES\x1a":
        return None
    prg, chr_, trainer = b[4] * 16384, b[5] * 8192, 512 if b[6] & 0x04 else 0
    # old dumps carry text (e.g. "DiskDude!") in bytes 7 to 15: then only byte 6 holds the mapper
    mapper = (b[6] >> 4) | ((b[7] & 0xF0) if not any(b[12:16]) else 0)
    if (prg, chr_, mapper) != (32768, 8192, 0):
        return None
    data = b[16 + trainer:16 + trainer + prg + chr_]
    return data if len(data) == prg + chr_ else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="a .nes file or a folder")
    ap.add_argument("--any", action="store_true", help="accept a Super Mario Bros. dump other than the one the brain was raised on")
    a = ap.parse_args(argv)
    p = Path(a.path).expanduser()
    if not p.exists():
        print(f"{p}: no such file or folder")
        return 1
    files = sorted(f for f in p.rglob("*") if f.suffix.lower() == ".nes") if p.is_dir() else [p]
    other = None
    for f in files:
        data = payload(f)
        if data is None:
            continue
        sha = hashlib.sha1(data).hexdigest()
        if sha == RAISED_SHA1:
            ROM.parent.mkdir(exist_ok=True)
            ROM.write_bytes(HEADER + data)
            print(f"{f}: the dump the brain was raised on. Copied to {ROM}")
            return 0
        other = other or (f, sha, data)
    if other and a.any:
        f, sha, data = other
        ROM.parent.mkdir(exist_ok=True)
        ROM.write_bytes(HEADER + data)
        print(f"{f}: PRG+CHR SHA-1 {sha}, not the dump the brain was raised on. Copied to {ROM} (--any): "
              "the brain is unchecked on it.")
        return 0
    if other:
        print(f"{other[0]}: a Super Mario Bros.-shaped dump, PRG+CHR SHA-1 {other[1]}, not the one the brain was "
              f"raised on ({RAISED_SHA1}). Run again with --any to use it anyway.")
    else:
        print("no Super Mario Bros. dump found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
