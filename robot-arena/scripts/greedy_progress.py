"""What a saved brain's greedy policy does on the nursery's own task, without learning:
metres of progress toward the dummy in 3,000 moments and dummies destroyed, beside uniform
random with the same body, and the probe's policy sensitivity. Usage:
    .venv/bin/python scripts/greedy_progress.py <league> <robot> [<robot> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arena.league import League  # noqa: E402
from arena.nursery import run_nursery  # noqa: E402
from arena.probe import fingerprint  # noqa: E402

league = League(sys.argv[1])
print(f"{'robot':13} {'policy':16} {'progress 3k (m)':>15} {'kills':>5} {'sensitivity':>11}")
for name in sys.argv[2:]:
    bp = league.blueprint(name)
    path = league.brain_path(name)
    r = run_nursery(bp, moments=3000, seed=5, policy="frozen", brain_path=path, block=1500)
    fp = fingerprint(bp, path)
    print(f"{name:13} {'greedy, frozen':16} {r['total']['progress_m']:15.1f} {r['total']['kills']:5} {fp['sensitivity']:11.3f}")
    r = run_nursery(bp, moments=3000, seed=5, policy="random", block=1500)
    print(f"{name:13} {'uniform random':16} {r['total']['progress_m']:15.1f} {r['total']['kills']:5}")
