"""Score the packed brain on World 1, 50 starts per level, into evidence/receipt.json.

    python evaluate.py                       # both start sets, 4 workers
    python evaluate.py --sets fresh --workers 2

A start is the number of idle frames before the first decision (the emulator is deterministic, so
this is what varies where the enemies are). `held`: the 50 starts the brain was picked on, never
trained on. `fresh`: 50 starts it was neither trained nor picked on, read once for the model card.
Brain alone, frozen and greedy, one attempt per start, small Mario, stuck limit 40, cap 900.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

warnings.filterwarnings("ignore", message=".*Gym has been unmaintained.*")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from smb.eye import FRAMES  # noqa: E402
from smb.player import CAP, FRESH, HELD, STUCK, attempt  # noqa: E402
from smb.rom import ROM, payload  # noqa: E402

BRAIN = HERE / "brain" / "brain.npz"
LEVELS = ("1-1", "1-2", "1-3", "1-4")
SETS = {"held": HELD, "fresh": FRESH}
_BRAIN = None


def _one(task):
    global _BRAIN
    warnings.filterwarnings("ignore", message=".*Gym has been unmaintained.*")
    if _BRAIN is None:
        from cadence import Brain
        _BRAIN = Brain.load(str(BRAIN), backend="cpu")
    return dict(attempt(_BRAIN, ROM, task["level"], task["idle"]), set=task["set"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sets", default="held,fresh")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(HERE / "evidence" / "receipt.json"))
    a = ap.parse_args()
    if not ROM.exists():
        sys.exit("No ROM yet: run `python -m smb.rom <your dump>` first.")
    for k in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[k] = "1"
    sets = a.sets.split(",")
    tasks = [dict(set=s, level=L, idle=i) for s in sets for L in LEVELS for i in SETS[s]]
    t0 = time.time()
    with ProcessPoolExecutor(a.workers, mp_context=get_context("spawn")) as ex:
        results = list(ex.map(_one, tasks))
    import cadence
    table = {}
    for s in sets:
        for L in LEVELS:
            rs = [r for r in results if r["set"] == s and r["level"] == L]
            table.setdefault(s, {})[L] = dict(
                starts=len(rs), flags=sum(r["end"] == "flag" for r in rs), died=sum(r["end"] == "died" for r in rs),
                stood_still=sum(r["end"] == "stood still" for r in rs), cap=sum(r["end"] == "cap" for r in rs),
                mean_x=round(sum(r["x"] for r in rs) / max(1, len(rs))))
    receipt = dict(
        brain=dict(file="brain/brain.npz", sha256=hashlib.sha256(BRAIN.read_bytes()).hexdigest()),
        library=f"cadence-net {cadence.__version__}", backend="cpu", python=sys.version.split()[0],
        rom_prg_chr_sha1=hashlib.sha1(payload(ROM)).hexdigest(),
        protocol=dict(frames_per_decision=FRAMES, stuck_limit=STUCK, cap=CAP, greedy=True, frozen=True,
                      start="small Mario at the level's start, the given number of idle frames first"),
        start_sets={s: list(SETS[s]) for s in sets},
        table=table, attempts=results, seconds=round(time.time() - t0), when=time.strftime("%Y-%m-%d %H:%M"))
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps(receipt, indent=1))
    for s in sets:
        print(s, " ".join(f"{L} {table[s][L]['flags']}/{table[s][L]['starts']}" for L in LEVELS))


if __name__ == "__main__":
    main()
