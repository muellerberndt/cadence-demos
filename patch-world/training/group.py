"""Write a founders.json naming a group of brains (for evaluate.py), from a nursery or an evolution run.

    python training/group.py nursery runs/nursery --top 8 --out runs/groups/nursery-top
"""
import argparse, json, shutil
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("kind", choices=("nursery",))
p.add_argument("folder", type=Path)
p.add_argument("--top", type=int, default=8)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
rows = []
for f in sorted(a.folder.glob("world*.json")):
    rows += json.loads(f.read_text())["creatures"]
rows.sort(key=lambda r: -(r["tail_income"] - r["brain_cost"]))
a.out.mkdir(parents=True, exist_ok=True)
out = []
for r in rows[:a.top]:
    shutil.copyfile(a.folder / f"{r['name']}.npz", a.out / f"{r['name']}.npz")
    out.append({"name": r["name"], "file": f"{r['name']}.npz", "genes": r["genes"],
                "structure": r["structure"], "generation": 0})
(a.out / "founders.json").write_text(json.dumps({"founders": out}, indent=1))
print([r["name"] for r in rows[:a.top]])
