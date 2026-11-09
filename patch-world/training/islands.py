"""What evolution changed: the founders' genes against the survivors' genes, per evolution run.

    python training/islands.py runs/evolve --nursery runs/nursery --out evidence/islands.json

Reads every ``island*.json`` of a run: its founders (by name, from the nursery), its survivors
and its log. Writes the mean of every gene over founders and over survivors, the survivors'
generations and lineages, and the island logs' intake per moment over time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

GENES = ("width", "depth", "recall", "eta", "eta_critic", "temperature", "lam", "gamma",
         "sensory_scale", "trace_amplitude", "consolidation", "memory_rate", "threshold",
         "tolerance", "need", "heat", "birth", "sense", "speed", "size")


def means(rows: list[dict]) -> dict:
    return {g: round(float(np.mean([float(r["genes"][g]) for r in rows])), 4) for g in GENES}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("runs", type=Path, nargs="+")
    p.add_argument("--nursery", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--founders-dirs", type=Path, nargs="*", default=None,
                   help="founders folders (select's output) that a later round started from")
    p.add_argument("--genes", type=json.loads, nargs="*", default=None,
                   help="per run, the genes evolve --genes set on the founders (JSON; {} for none)")
    a = p.parse_args()
    nursery = {}
    for f in sorted(a.nursery.glob("world*.json")):
        for r in json.loads(f.read_text())["creatures"]:
            nursery[r["name"]] = r
    for f in a.founders_dirs or []:  # a later round started from a select's founders
        for r in json.loads((f / "founders.json").read_text())["founders"]:
            nursery[Path(r["file"]).stem] = r
    report = {}
    for k, run in enumerate(a.runs):
        override = a.genes[k] if a.genes else {}
        islands = [json.loads(f.read_text()) for f in sorted(run.glob("island*.json"))]
        survivors = [s for isl in islands for s in isl["survivors"]]
        founders = [{**nursery[n], "genes": {**nursery[n]["genes"], **override}}
                    for n in islands[0]["founders"]]
        log_t = sorted({row["t"] for isl in islands for row in isl["log"]})
        income = {t: [] for t in log_t}
        generation = {t: [] for t in log_t}
        for isl in islands:
            for row in isl["log"]:
                if row["tally"].get("income_per_moment") is not None:
                    income[row["t"]].append(row["tally"]["income_per_moment"])
                generation[row["t"]].append(row["generation_mean"])
        dead = [d for isl in islands for d in isl["dead"]]
        report[run.name] = {
            "islands": len(islands), "moments": islands[0]["moments"],
            "founders": islands[0]["founders"], "founder_genes_set": override,
            "founder_genes_mean": means(founders),
            "survivors": len(survivors),
            "survivor_genes_mean": means(survivors),
            "survivor_generation_mean": float(np.mean([s["generation"] for s in survivors])),
            "survivor_generation_max": int(max(s["generation"] for s in survivors)),
            "lineages_surviving_per_island": float(np.mean(
                [len({s["lineage"] for s in isl["survivors"]}) for isl in islands])),
            "founder_lineage_shares": {
                n: round(sum(1 for s in survivors if s["founder"] == n) / len(survivors), 3)
                for n in islands[0]["founders"]},
            "reseeded_total": int(sum(isl["log"][-1]["reseeded"] for isl in islands)),
            "income_per_moment_by_t": {str(t): round(float(np.mean(v)), 4) for t, v in income.items() if v},
            "generation_mean_by_t": {str(t): round(float(np.mean(v)), 2) for t, v in generation.items() if v},
            "mean_age_at_death_last_400_per_island": float(np.mean([d["age"] for d in dead])) if dead else None,
            "seconds_max": max(isl["seconds"] for isl in islands),
        }
    text = json.dumps(report, indent=1)
    print(text)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")


if __name__ == "__main__":
    main()
