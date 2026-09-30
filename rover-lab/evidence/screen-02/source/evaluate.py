"""Run the bounded rover screen and retain every scheduled outcome."""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from rover import Life, PROTOCOL, digest, source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--confirmation", action="store_true")
    parser.add_argument("--variants", action="store_true")
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
              "seeds": seeds, "steps": args.steps, "variants": args.variants,
              "kind": "reserved_confirmation" if args.confirmation else "development",
              "python": platform.python_version(), "platform": platform.platform(),
              "timing": "Serial headless process; learning plus candidate settlement and command activation included. Rendering/network excluded."}
    (args.out / "freeze.json").write_text(json.dumps(freeze, indent=2)+"\n")
    outcomes = []
    for seed in seeds:
        started = time.perf_counter()
        life = Life(seed, variants=args.variants)
        for _ in range(args.steps):
            life.tick()
        receipt = life.receipt()
        receipt.update(freeze_hash=digest(freeze), elapsed_seconds=time.perf_counter()-started)
        (args.out / f"seed-{seed}.json").write_text(json.dumps(receipt, separators=(",", ":"), allow_nan=False)+"\n")
        summary = {"seed": seed, "elapsed_seconds": receipt["elapsed_seconds"], "gate": receipt["gate"],
                   "metrics": receipt["metrics"], "bootstrap": receipt["bootstrap"]}
        outcomes.append(summary)
        print(json.dumps(summary), flush=True)
    (args.out / "summary.json").write_text(json.dumps({"freeze_hash": digest(freeze), "outcomes": outcomes}, indent=2)+"\n")


if __name__ == "__main__":
    main()
