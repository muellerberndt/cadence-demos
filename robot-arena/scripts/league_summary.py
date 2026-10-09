"""How a league's robots behave, from league.json: per robot the early and late thirds of its
fights (place, damage dealt, weapon hits, moments burning, closing share, aroused share,
learning sweeps), the winners, the ring time and the wall time. Usage:
    .venv/bin/python scripts/league_summary.py <league> [last N fights]
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

root = Path(sys.argv[1])
L = json.loads((root / "league.json").read_text())
fights = L["fights"][-int(sys.argv[2]):] if len(sys.argv) > 2 else L["fights"]
ids = {f["id"] for f in fights}
robots = L["robots"]
winners = [f["results"][0]["name"] for f in fights]
sim = sum(f["moments"] for f in fights) * 0.05
wall = sum(f.get("seconds") or 0 for f in fights)
print(f"{len(fights)} fights, {len(set(winners))} different winners, winner changed {sum(1 for a, b in zip(winners, winners[1:]) if a != b)} times; "
      f"ring time {sim / 60:.1f} min in {wall / 60:.1f} min wall ({sim / wall if wall else 0:.1f}x); mean fight {st.mean(f['moments'] for f in fights):.0f} moments")
random_wins = sum(1 for w in winners if robots.get(w, {}).get("policy") == "random")
print(f"wins by random twins: {random_wins}")
print()
head = f"{'robot':15} {'policy':7} {'fights':>6} {'place e→l':>11} {'dealt e→l':>11} {'hits e→l':>10} {'burn e→l':>10} {'closing e→l':>12} {'calm e→l':>10} {'sweeps/fight':>12} {'elo':>6}"
print(head)
for n, e in sorted(robots.items(), key=lambda kv: -kv[1]["elo"]):
    h = [r for r in e["history"] if r["fight"] in ids]
    if not h:
        continue
    k = max(1, len(h) // 3)
    early, late = h[:k], h[-k:]
    m = lambda rows, key: st.mean(r.get(key, 0) or 0 for r in rows)
    print(f"{n:15} {e['policy']:7} {len(h):6} {m(early, 'place'):5.2f}→{m(late, 'place'):4.2f} {m(early, 'dealt'):5.0f}→{m(late, 'dealt'):4.0f} "
          f"{m(early, 'hits'):4.0f}→{m(late, 'hits'):4.0f} {m(early, 'burn'):4.0f}→{m(late, 'burn'):4.0f} "
          f"{m(early, 'closing_share'):5.2f}→{m(late, 'closing_share'):4.2f} {1 - m(early, 'aroused_share'):4.2f}→{1 - m(late, 'aroused_share'):4.2f} "
          f"{m(h, 'learning_sweeps'):12.0f} {e['elo']:6.0f}")
