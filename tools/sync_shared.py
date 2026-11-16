"""Copy the shared explanation files into every demo's page folder, or check that the copies match.

Each demo names its page folder in its site.json ("page_dir"); the site serves that folder as
/demos/<slug>/ and needs every file inside it, so the shared files are copied, not linked.

    python tools/sync_shared.py          # copy
    python tools/sync_shared.py --check  # exit 1 when a copy differs or is missing
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
FILES = ("cadence-explain.js", "cadence-explain.css", "cadence-help.css", "cadence-palette.js")


def demos() -> list[tuple[Path, dict]]:
    out = []
    for site in sorted(ROOT.glob("*/site.json")):
        out.append((site.parent, json.loads(site.read_text())))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only check that every copy matches")
    args = ap.parse_args()
    bad = []
    for folder, meta in demos():
        page = folder / meta.get("page_dir", "web")
        for name in FILES:
            src, dst = SHARED / name, page / name
            if args.check:
                if not dst.exists() or dst.read_bytes() != src.read_bytes():
                    bad.append(str(dst.relative_to(ROOT)))
            else:
                shutil.copyfile(src, dst)
    if bad:
        print("differs from shared/:", *bad, sep="\n  ")
        return 1
    print("shared files", "match" if args.check else "copied", "in", len(demos()), "demos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
