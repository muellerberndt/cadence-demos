"""Find your Castlevania (U) PRG1 dump and copy it into the integration folder.

    python -m simon.rom ~/roms              # a folder: every .nes file in it is checked
    python -m simon.rom "Castlevania (U) (PRG1).nes"
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .console import GAME, INTEGRATION, ROM_SHA1, rom_sha1


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).expanduser()
    candidates = sorted(source.rglob("*.nes")) if source.is_dir() else [source]
    for path in candidates:
        if rom_sha1(path) == ROM_SHA1:
            target = INTEGRATION / GAME / "rom.nes"
            shutil.copyfile(path, target)
            print(f"copied {path} -> {target}")
            return
    raise SystemExit(f"no Castlevania (U) PRG1 dump found (headerless SHA-1 {ROM_SHA1})")


if __name__ == "__main__":
    main()
