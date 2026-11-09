"""Per-season readings of a nursery: berries eaten in each summer and each winter of a life.

    python training/seasons.py runs/nursery [runs/nursery-b ...]

The nursery records every 1,000 moments; with seasons of 1,500 moments one window per season
lies wholly inside it (the last 1,000 moments of each winter, the first 1,000 of each summer).
"""
import json
import sys
from pathlib import Path

import numpy as np

SEASON = 1500


def per_season(rows):
    winters, summers, income = [], [], []
    for r in rows:
        w, s = [], []
        for x in r["curve"]:
            start = x["t"] - 1000
            k, off = divmod(start, SEASON)
            if off + 1000 <= SEASON:
                (w if k % 2 else s).append(x["berry_winter"] if k % 2 else x["berry_summer"])
        winters.append(w)
        summers.append(s)
        income.append([x["gained"] for x in r["curve"]])
    n = min(len(w) for w in winters)
    m = min(len(s) for s in summers)
    return (np.array([w[:n] for w in winters]), np.array([s[:m] for s in summers]),
            np.array(income))


def summary(folder: Path) -> dict:
    rows = []
    for f in sorted(Path(folder).glob("world*.json")):
        rows += json.loads(f.read_text())["creatures"]
    w, s, inc = per_season(rows)
    pairs = {}
    for r in rows:
        pairs.setdefault((r["world"], r["pair"]), {})["on" if r["genes"]["recall"] else "off"] = r
    diffs = [p["on"]["tail_nuts"] - p["off"]["tail_nuts"] for p in pairs.values() if len(p) == 2]
    worlds = sorted(Path(folder).glob("world*.json"))
    rules = json.loads(worlds[0].read_text())["rules"]
    return {"folder": Path(folder).name, "creatures": len(rows),
            "senses": {"nausea": rules.get("nausea_sense", False), "cold": rules.get("temperature_sense", False)},
            "winter_berries_per_1000_each_winter": [round(float(x), 3) for x in w.mean(0)],
            "summer_berries_per_1000_each_summer": [round(float(x), 3) for x in s.mean(0)],
            "intake_per_1000_first_5000": round(float(inc[:, :5].mean()), 2),
            "intake_per_1000_last_5000": round(float(inc[:, -5:].mean()), 2),
            "recall_pairs": len(diffs),
            "recall_on_minus_off_nuts_per_1000_last_5000": round(float(np.mean(diffs)), 3) if diffs else None}


if __name__ == "__main__":
    if sys.argv[1] == "--out":
        out = Path(sys.argv[2])
        out.write_text(json.dumps([summary(Path(f)) for f in sys.argv[3:]], indent=1) + "\n")
        print(out.read_text())
        raise SystemExit
    for folder in sys.argv[1:]:
        rows = []
        for f in sorted(Path(folder).glob("world*.json")):
            rows += json.loads(f.read_text())["creatures"]
        w, s, inc = per_season(rows)
        print(folder, len(rows), "creatures")
        print("  winter berries per 1000 (each winter):", np.round(w.mean(0), 2).tolist())
        print("  summer berries per 1000 (each summer):", np.round(s.mean(0), 2).tolist())
        print("  intake per 1000, first and last 5 windows:", round(inc[:, :5].mean(), 1), round(inc[:, -5:].mean(), 1))
        top = sorted(rows, key=lambda r: -(r["tail_income"] - r["brain_cost"]))[:8]
        wt, st, _ = per_season(top)
        print("  top-8 winter:", np.round(wt.mean(0), 2).tolist())
        print("  top-8 summer:", np.round(st.mean(0), 2).tolist())
        print("  top-8 tail intake per moment:", round(np.mean([r["tail_income"] for r in top]), 3))
