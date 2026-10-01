"""Independent confirmation of the development run's early exposure hypothesis.

Reuses the unchanged shared_innovation arm collector. Freeze before launch.
This tests sample exposure, not equal-compute efficiency or temporal planning.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import platform
import random
import signal
import subprocess
import sys
from pathlib import Path

import self_correction as custody
import shared_innovation as pilot

SEEDS = (61, 67, 71, 73, 79)
DATA_SEED = 20261006


def tape(condition):
    rng = random.Random(DATA_SEED)
    width = pilot.CONDITIONS[condition]

    def row(identity, delta=0.0):
        return pilot.body(
            rng.uniform(-width, width), rng.uniform(-0.4, 0.4), delta, identity
        )

    clean = [row(f"clean:{i}") for i in range(64 * 16)]
    mixed = []
    for i in range(128 * 8):
        delta = rng.uniform(0.03, 0.12)
        positive = row(f"mixed:{2 * i}", delta)
        u, v = positive["inputs"]["u"][0], positive["inputs"]["v"][0]
        mixed.extend([positive, pilot.body(u, v, -delta, f"mixed:{2 * i + 1}")])
    return {
        "clean": clean,
        "mixed": mixed,
        "clean_test": [row(f"clean-test:{i}") for i in range(32)],
        "mixed_test": [
            row(f"mixed-test:{i}", rng.choice((-1, 1)) * rng.uniform(0.03, 0.12))
            for i in range(64)
        ],
    }


def freeze(root, development):
    old = pilot.validate(development)
    if not (development / "execution.json").exists():
        raise ValueError("development run must be finished")
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "data.json", {c: tape(c) for c in pilot.CONDITIONS})
    custody.atomic(root / "founders.json", {str(s): pilot.founders(s) for s in SEEDS})
    custody.atomic(
        root / "input-only-founders.json",
        {str(s): pilot.brain(s, "observer", input_only=True).snapshot() for s in SEEDS},
    )
    protocol = {
        **old,
        "schema": "shared-innovation-confirmation/1",
        "primary_condition": "narrow",
        "primary_checkpoint": 32,
        "required_clean_checks": [0, 32, 128],
        "platform": platform.platform(),
        "sources": pilot.sources(),
        "seeds": SEEDS,
        "data_seed": DATA_SEED,
        "data_sha256": custody.sha(root / "data.json"),
        "founders_sha256": custody.sha(root / "founders.json"),
        "input_only_founders_sha256": custody.sha(root / "input-only-founders.json"),
        "confirmation_source_sha256": custody.sha(Path(__file__)),
        "development_protocol_sha256": custody.sha(development / "protocol.json"),
        "hypothesis_origin": "Development seeds2,7,11,19,29 at mixed32 showed lower observer error, followed by late narrow reversal. This new endpoint is declared BEFORE new seeds/data are run; it does not replace the development mixed128 primary endpoint.",
        "primary_comparison": "NARROW condition only, mixed32 free-H correction MAE, all64 rows and all5 paired seeds. Require ALL arms complete, all admissions accepted/all queries qualified, and all initial/intermediate/final clean-free P/H gates passed. Require mean ordinary-minus-observer MAE>=0.005 and positive in all5 pairs. No eligible-only subset; no hyperparameter selection. This is an exposure advantage, NOT compute efficiency.",
        "secondary_comparisons": "Always report wide mixed32 and BOTH conditions at mixed0 and mixed128, every seed, signed offset bins, cumulative training work and query work. A late reversal or additional work remains explicit even if the primary passes. No exclusive recurrence or generalization claim follows from one body family.",
        "shared_data_boundary": "New training and held-out tape, separate from development. Five initialization seeds share this one new tape; they are not five independent environment draws.",
    }
    custody.atomic(root / "protocol.json", protocol)


def validate(root):
    protocol = pilot.validate(root)
    if protocol["confirmation_source_sha256"] != custody.sha(Path(__file__)):
        raise ValueError("confirmation source changed")
    if protocol["seeds"] != list(SEEDS) or protocol["data_seed"] != DATA_SEED:
        raise ValueError("confirmation design changed")
    return protocol


def launch(root):
    protocol = validate(root)
    path = root / "launch.json"
    if path.exists():
        raise ValueError("preserve the existing launch")
    jobs = [(s, c, a) for s in SEEDS for c in pilot.CONDITIONS for a in pilot.ARMS]
    custody.atomic(path, {"jobs": jobs, **protocol["compute"]})

    def execute(job):
        seed, condition, arm = job
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            str(root),
            "--seed",
            str(seed),
            "--condition",
            condition,
            "--arm",
            arm,
        ]
        with (root / f"{condition}-{arm}-seed{seed}.log").open("x") as log:
            p = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                code, status = p.wait(timeout=pilot.CAP + 5), "returned"
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                code, status = p.wait(), "outer_timeout"
        return {"job": job, "pid": p.pid, "code": code, "status": status}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(execute, jobs))
    custody.atomic(root / "execution.json", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "launch", "run"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--development", type=Path)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--condition", choices=pilot.CONDITIONS)
    parser.add_argument("--arm", choices=pilot.ARMS)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "freeze":
        if args.development is None:
            parser.error("freeze requires --development")
        freeze(root, args.development.resolve())
    elif args.command == "launch":
        launch(root)
    else:
        if None in (args.seed, args.condition, args.arm):
            parser.error("run requires seed, condition and arm")
        validate(root)
        sys.exit(pilot.run(root, args.seed, args.condition, args.arm))
