"""Summarise a folder of probe runs: python summarize.py <dir with *.jsonl>

One row per run: the population at the end, the mean genome, the lifetime-at-death medians by
patch count, by depth and by observer count, the solve-qualification rates, the symbol statistics
against their chance level, and the reward per tick of creatures that hear against those that do not.
"""

import json
import sys
from pathlib import Path


def load(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.startswith("{")]
    final = next((r for r in rows if r.get("final")), None)
    last = next((r for r in reversed(rows) if not r.get("final")), None)
    return last, final


PATCH_ORDER = {"<20": 0, "20-29": 1, "30-44": 2, "45-64": 3, "65+": 4}


def main(folder):
    files = sorted(Path(folder).glob("*.jsonl"))
    print(f"{'run':28} {'alive':>5} {'age':>4} {'ptch':>5} {'dep':>4} {'obs':>4} {'hor':>4} {'rad':>4} {'spk':>4} {'set':>5} {'lrn':>5} | life by patches (median) | life by depth | life by observers | MI food/nb/kin vs chance | reward hears/deaf")
    for f in files:
        last, final = load(f)
        if not last:
            print(f"{f.stem:28} (no output)")
            continue
        life = final["lifeByPatches"] if final else {}
        by_patches = " ".join(f"{k}:{v['median']}" for k, v in sorted(life.items(), key=lambda kv: PATCH_ORDER.get(kv[0], 9)) if v["n"] >= 30)
        byd = final["lifeByDepth"] if final else {}
        by_depth = " ".join(f"{k}:{v['median']}({v['n']})" for k, v in sorted(byd.items()))
        byo = final.get("lifeByObservers", {}) if final else {}
        by_observers = " ".join(f"{k}:{v['median']}({v['n']})" for k, v in sorted(byo.items()))
        sym = final["symbols"] if final else {}
        mi = " ".join(f"{sym[k]['mi']:.3f}/{sym[k]['chance']:.3f}" for k in ("food", "neighbour", "kin")) if sym else ""
        rw = final["rewardPerTick"] if final else {}
        print(f"{f.stem:28} {last['alive']:>5} {last['age']:>4} {last['patches']:>5} {last['depth']:>4} {last['observers']:>4} {last['horizon']:>4} {last['radius']:>4} {last['speak']:>4} {last.get('settled', ''):>5} {last.get('learned', ''):>5} | {by_patches:24} | {by_depth:20} | {by_observers:20} | {mi:26} | {rw.get('hears')}/{rw.get('deaf')}"
              + ("" if final else "  (running)"))
    print()
    for f in files:
        last, final = load(f)
        if last and final:
            print(f"{f.stem:28} census {last['census']}  horizons {last['horizonHist']}  depths {last['depthHist']}  observers {last['observerHist']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "receipts")
