"""Tabulate the nursery runs: the last curve row of each, then the assays where they exist.

    python tools/compare_runs.py runs/n1-s1 runs/n1-s1-topo ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KEYS = ("lesson", "block_x", "block_y", "hand_x", "hand_y", "held", "order", "joints", "gripper", "sweeps", "ms")


def main(paths: list[str]) -> None:
    print("| run | " + " | ".join(KEYS) + " |")
    print("|" + " --- |" * (len(KEYS) + 1))
    for p in paths:
        d = Path(p)
        curve = d / "curve.json"
        if not curve.exists():
            print(f"| {d.name} | (no curve yet) |")
            continue
        rows = json.loads(curve.read_text())["curve"]
        last = rows[-1]
        print(f"| {d.name} | " + " | ".join(str(last.get(k, "")) for k in KEYS) + " |")
    print()
    for p in paths:
        d = Path(p)
        summary = d / "summary.json"
        if not summary.exists():
            continue
        s = json.loads(summary.read_text()).get("assays", {})
        if not s:
            continue
        g, gd = s.get("glance", {}), s.get("glance_dark", {})
        print(f"{d.name}: glance block {g.get('block_x')}/{g.get('block_y')} hand {g.get('hand_x')}/{g.get('hand_y')} "
              f"held {g.get('held')} order {g.get('order')} joints {g.get('joints')} | dark block {gd.get('block_x')}/{gd.get('block_y')} "
              f"hand {gd.get('hand_x')}/{gd.get('hand_y')} order {gd.get('order')} joints {gd.get('joints')}")
        for arm in ("reach", "reach_dark", "reach_caregiver", "reach_random"):
            r = s.get(arm, {})
            print(f"    {arm:16s} success {r.get('success')} decisions {r.get('decisions_median')} final {r.get('final_distance_median')}")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(str(p) for p in Path("runs").glob("n1-*") if p.is_dir()))
