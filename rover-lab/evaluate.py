"""Run the bounded rover screen and retain every scheduled outcome."""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np

from rover import CADENCE_VERSION, Life, PROTOCOL, digest, source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--confirmation", action="store_true")
    parser.add_argument("--observers", action="store_true",
                        help="add the optional error-reading observer layout as a fifth arm")
    parser.add_argument("--steps", type=int, default=sum(n for _, n in PROTOCOL["phases"]))
    parser.add_argument("--out", type=Path, default=Path("evidence/development"))
    args = parser.parse_args()
    if not 1 <= args.steps <= 3600:
        parser.error("--steps must be between 1 and 3600")
    if args.confirmation and args.seeds:
        parser.error("Confirmation uses the declared reserved seed set")
    seeds = PROTOCOL["confirmation_seeds"] if args.confirmation else args.seeds or PROTOCOL["development_seeds"]
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        parser.error("Output directory must be empty; preserve earlier outcomes")
    freeze = {"protocol": PROTOCOL, "protocol_hash": digest(PROTOCOL), "sources": source_hashes(),
              "seeds": seeds, "steps": args.steps, "observers": args.observers,
              "cadence": CADENCE_VERSION,
              "kind": "reserved_confirmation" if args.confirmation else "development",
              "python": platform.python_version(), "platform": platform.platform(),
              "numpy": np.__version__,
              "timing": "Serial headless process; learning plus candidate settlement and command activation included. Rendering/network excluded."}
    (args.out / "freeze.json").write_text(json.dumps(freeze, indent=2)+"\n")
    outcomes = []
    for seed in seeds:
        started = time.perf_counter()
        life = None
        try:
            life = Life(seed, observers=args.observers)
            for _ in range(args.steps):
                life.tick()
            receipt = life.receipt()
            receipt.update(freeze_hash=digest(freeze), elapsed_seconds=time.perf_counter()-started)
            (args.out / f"seed-{seed}.json").write_text(json.dumps(receipt, separators=(",", ":"), allow_nan=False)+"\n")
            summary = {"seed": seed, "elapsed_seconds": receipt["elapsed_seconds"], "gate": receipt["gate"],
                       "metrics": receipt["metrics"], "bootstrap": receipt["bootstrap"]}
        except Exception as exc:
            # A refusal is an outcome, and must not suppress later scheduled seeds.
            summary = {"seed": seed, "failed": True, "error": f"{type(exc).__name__}: {exc}",
                       "steps_completed": life.step if life else 0,
                       "elapsed_seconds": time.perf_counter()-started, "gate": {"complete": False, "passed": False}}
            failure = {**summary, "freeze_hash": digest(freeze),
                       "partial_transitions": life.rows if life else []}
            (args.out / f"seed-{seed}-failure.json").write_text(json.dumps(failure, indent=2, allow_nan=False)+"\n")
        outcomes.append(summary)
        print(json.dumps(summary), flush=True)
    (args.out / "summary.json").write_text(json.dumps({"freeze_hash": digest(freeze), "outcomes": outcomes}, indent=2)+"\n")
    return int(any(row.get("failed") for row in outcomes))


if __name__ == "__main__":
    raise SystemExit(main())
