"""Positions and tron/absearch.py's values on them, for tests/parity_search.mjs.

    python tests/make_search_fixture.py tests/fixtures/search.json

Positions: games of the packed flat brain (reset, greedy) against voronoi, voronoi2 and voronoi3
from seeds 9,500,000+, every 3rd position; at each, the search's move and values for seat 0 at
depths 1 to 4, without a prior and with the brain's move as the prior (+8).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from cadence import Brain  # noqa: E402
from phasec import OPP  # noqa: E402
from tron import absearch, r3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402

brain = Brain.load(str(ROOT / "web" / "pack" / "flat" / "brain" / "brain.npz"), backend="cpu")
pol = r3.policy(brain, "field")
cases = []
for g, opp in enumerate(["voronoi", "voronoi2", "voronoi3"] * 2):
    s = 9_500_000 + g
    a, dr = Arena(24, seed=s), mulberry32(s)
    t = 0
    while not a.over:
        m = pol(a, 0)
        if t % 3 == 0:
            case = {"grid": list(a.grid), "heads": [list(h) for h in a.heads], "headings": list(a.headings), "prior": m, "runs": []}
            for depth in (1, 2, 3, 4):
                for prior, bonus in ((-1, 0), (m, 8)):
                    mv, vals = absearch.search(a, 0, depth, prior, bonus)
                    case["runs"].append({"depth": depth, "prior": prior, "bonus": bonus, "move": int(mv), "values": [int(v) for v in vals]})
            cases.append(case)
        a.step((m, OPP[opp](a, 1, dr)))
        t += 1
Path(sys.argv[1]).write_text(json.dumps({"n": 24, "cases": cases}))
print(len(cases), "positions")
