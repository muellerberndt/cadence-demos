"""Bounded public-Cadence bootstrap in the original JavaScript Patch World body.

Disclosed synthetic teacher, restricted nine-food sensor and single body. This
is not reward discovery, a browser-engine migration or recursive advantage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import signal
import subprocess
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cadence
from cadence import Brain, Cortex

SEEDS = (211, 223, 227, 229, 233)
ARMS = ("flat", "composed", "observer")
CONFIG = {"parameter_prior": 0.1, "tolerance": 1e-6, "settle_budget": 2048}
EPOCHS, BATCH, TICKS, ARM_SECONDS = 20, 16, 96, 60


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded(value) + "\n")
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text())


def sources(core):
    package = Path(cadence.__file__).parent
    result = {"cadence/" + p.name: sha(p) for p in sorted(package.glob("*.py"))}
    for path in (Path(__file__), Path(__file__).with_name("patchworld_body.js"), core):
        result[path.name] = sha(path)
    return result


def node_identity():
    path = Path(shutil.which("node")).resolve()
    return {
        "version": subprocess.check_output([str(path), "--version"], text=True).strip(),
        "binary_sha256": sha(path),
    }


def bound_inputs(root, core):
    protocol = read(root / "protocol.json")
    assert sources(core) == protocol["sources"], "source pin mismatch"
    assert sha(root / "data.json") == protocol["data_sha256"], "data pin mismatch"
    assert node_identity() == protocol["node"], "Node pin mismatch"
    return protocol


def make(arm, seed):
    c = Cortex(seed=seed, **CONFIG)
    food = c.input("food", shape=9)
    if arm == "flat":
        motor = c.column("motor", patches=6, inputs=food)
    else:
        hidden = c.column("perception", patches=2, inputs=food)
        motor = (
            c.column("motor", patches=6, inputs=(food, hidden))
            if arm == "composed"
            else c.observer("motor", patches=6, inputs=food, observes=hidden)
        )
    c.output("action", shape=6, reads=motor)
    return c.build()


def teacher(food):
    # Exact disclosed curriculum from cadence-world/world/settling.py.
    sectors = ((0, 1, 2), (2, 5, 8), (6, 7, 8), (0, 3, 6))
    return [
        math.tanh(1.2 * sum(food[i] for i in sector) - food[4]) for sector in sectors
    ] + [math.tanh(4 * food[4] - 0.2), -0.4]


def examples(n, seed):
    rng, result = random.Random(seed), []
    for i in range(n):
        maximum = 2 if i % 3 else 8
        food = [
            (rng.randrange(maximum + 1) if rng.random() < 0.45 else 0) / 8
            for _ in range(9)
        ]
        result.append([{"food": food}, {"action": teacher(food)}])
    return result


class Body:
    def __init__(self, core, seed, brain=None, journal=None):
        self.journal = journal
        self.process = subprocess.Popen(
            [
                "node",
                str(Path(__file__).with_name("patchworld_body.js")),
                str(core.resolve()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.initial = self.request(
            {
                "op": "init",
                "seed": seed,
                "patches": brain.graph.n_patches if brain else 0,
                "connections": len(brain.graph.edges) if brain else 0,
            }
        )

    def request(self, payload):
        if self.journal:
            write(
                self.journal.with_suffix(".current.json"),
                {"request": payload, "status": "started"},
            )
        self.process.stdin.write(encoded(payload) + "\n")
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        if "error" in reply:
            raise ValueError(reply["error"])
        if self.journal:
            row = {"request": payload, "response": reply, "status": "returned"}
            with self.journal.open("a") as stream:
                stream.write(encoded(row) + "\n")
            write(self.journal.with_suffix(".current.json"), row)
        return reply

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)


def freeze(root, core):
    root.mkdir(parents=True, exist_ok=False)
    data = {
        name: examples(n, seed)
        for name, n, seed in (
            ("train", 96, 641),
            ("development", 24, 643),
            ("heldout", 48, 647),
        )
    }
    write(root / "data.json", data)
    write(
        root / "protocol.json",
        {
            "schema": "patchworld-bootstrap/1",
            "sources": sources(core),
            "node": node_identity(),
            "core_path": str(core.resolve()),
            "data_sha256": sha(root / "data.json"),
            "seeds": SEEDS,
            "arms": ARMS,
            "config": CONFIG,
            "epochs": EPOCHS,
            "batch": BATCH,
            "ticks": TICKS,
            "arm_seconds": ARM_SECONDS,
            "gate": "All heldout queries qualified, action agreement>=.9; all learned native queries qualified and mass conserved. Development recorded only; no early stopping. All15 arms retained.",
            "scope": "Synthetic local teacher estimates, no live teacher or learning. Original JS body unchanged, one organism/popcap1, optional rules off,9food counts/8. Native read/patch/edge/accepted-sweep metabolism remains; offline training/query CPU+work reported separately, not charged retrospectively to body. Random/reflex controls have no learned patch apparatus. This is not browser engine parity, ecology, reproduction, reward discovery or capacity-matched recursive advantage.",
        },
    )


def run_arm(root, core, seed, arm):
    out = root / f"{arm}-seed{seed}"
    out.mkdir()
    protocol = bound_inputs(root, core)
    data = read(root / "data.json")
    brain = make(arm, seed)
    initial = brain.snapshot()
    (out / "initial.json").write_text(initial)
    (out / "latest.json").write_text(initial)
    work, calls, admissions, phase_results = Counter(), 0, 0, {}
    started, status, failure, unknown = time.monotonic(), "complete", None, False
    cpu_started = time.process_time()
    by_kind = {}
    body = None

    def alarm(*_):
        raise TimeoutError("arm allowance")

    def call(kind, inputs, targets=None):
        nonlocal brain, calls, admissions, unknown
        before = brain.snapshot()
        intent = {
            "kind": kind,
            "inputs": inputs,
            "targets": targets,
            "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "status": "started",
        }
        write(out / "current-call.json", intent)
        try:
            result = (
                brain.observe_batch(inputs, source="estimate")
                if kind == "admission"
                else brain.step(inputs)
                if kind == "live"
                else brain.settle(inputs)
            )
        except BaseException:
            brain = Brain.from_snapshot(before)
            unknown = True
            write(
                out / "current-call.json",
                {**intent, "status": "interrupted", "unknown_work": True},
            )
            raise
        calls += 1
        work.update(result["work"])
        by_kind.setdefault(kind, Counter()).update(result["work"])
        admissions += int(kind == "admission" and result["accepted"])
        after = brain.snapshot()
        row = {
            **intent,
            "status": "returned",
            "result": result,
            "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
        }
        with (out / "calls.jsonl").open("a") as stream:
            stream.write(encoded(row) + "\n")
        write(out / "current-call.json", row)
        (out / "latest.json").write_text(after)
        return result

    def evaluate(name):
        rows, correct, qualified = [], 0, 0
        saved = brain.snapshot()
        for inputs, target in data["heldout" if name != "development" else name]:
            r = call("query", inputs)
            chosen = max(range(6), key=r["outputs"]["action"].__getitem__)
            ok = (
                r["qualified"]
                and target["action"][chosen] >= max(target["action"]) - 1e-12
            )
            correct += ok
            qualified += r["qualified"]
            rows.append(
                {
                    "inputs": inputs,
                    "expected": target,
                    "chosen": chosen,
                    "qualified": r["qualified"],
                    "correct": ok,
                }
            )
        assert brain.snapshot() == saved
        return {
            "rows": len(rows),
            "qualified": qualified,
            "correct": correct,
            "agreement": correct / len(rows),
            "details": rows,
        }

    def live(name, snapshot=None):
        nonlocal body, brain
        if snapshot is not None:
            brain = Brain.from_snapshot(snapshot)
        body = Body(
            core, 1000 + seed, brain if snapshot else None, out / f"body-{name}.jsonl"
        )
        rng, frames, refused = random.Random(2000 + seed), [], 0
        saved_parameters = (brain.weights, brain.biases)
        for _ in range(TICKS):
            observation = body.request({"op": "sense"})
            if not observation["alive"]:
                break
            inputs = {"food": [v / 8 for v in observation["food"]]}
            if snapshot is not None:
                result = call("live", inputs)
                qualified = result["qualified"]
                action = (
                    max(range(6), key=result["outputs"]["action"].__getitem__)
                    if qualified
                    else 5
                )
                sweeps = result["sweeps"]
                refused += not qualified
            else:
                qualified, sweeps = True, 0
                action = (
                    rng.randrange(6)
                    if name == "random"
                    else max(range(6), key=teacher(inputs["food"]).__getitem__)
                )
            executed = body.request(
                {
                    "op": "step",
                    "tick": observation["tick"],
                    "action": action,
                    "qualified": qualified,
                    "sweeps": sweeps,
                }
            )
            assert executed["after"]["mass"] == body.initial["initial_mass"]
            frame = {"observation": observation, "executed": executed}
            frames.append(frame)
            with (out / f"live-{name}.jsonl").open("a") as stream:
                stream.write(encoded(frame) + "\n")
        assert (brain.weights, brain.biases) == saved_parameters
        summary = {
            "initial": body.initial,
            "ticks": len(frames),
            "requested": TICKS,
            "refused": refused,
            "terminal": bool(frames and not frames[-1]["executed"]["alive"]),
            "last": frames[-1]["executed"] if frames else None,
        }
        body.close()
        body = None
        return summary

    old_alarm = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, ARM_SECONDS)
    try:
        phase_results["before"] = evaluate("before")
        for epoch in range(EPOCHS):
            order = list(range(len(data["train"])))
            random.Random(seed + epoch).shuffle(order)
            for start in range(0, len(order), BATCH):
                call(
                    "admission",
                    [data["train"][i] for i in order[start : start + BATCH]],
                )
        phase_results["development"] = evaluate("development")
        phase_results["after"] = evaluate("after")
        trained = brain.snapshot()
        (out / "trained.json").write_text(trained)
        assert Brain.from_snapshot(trained).snapshot() == trained
        phase_results["learned_live"] = live("learned", trained)
        phase_results["untrained_live"] = live("untrained", initial)
        phase_results["random_live"] = live("random")
        phase_results["reflex_live"] = live("reflex")
    except TimeoutError:
        status, failure = "timeout", traceback.format_exc()
    except Exception:  # noqa: BLE001 - retain failed outcomes and their traceback
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        if body:
            body.close()
    unchanged = (
        sources(core) == protocol["sources"]
        and sha(root / "data.json") == protocol["data_sha256"]
        and node_identity() == protocol["node"]
    )
    if time.monotonic() - started > ARM_SECONDS:
        status = "timeout"
    if not unchanged:
        status = "source_changed"
    after = phase_results.get("after", {})
    live_result = phase_results.get("learned_live", {})
    passed = (
        status == "complete"
        and admissions == 120
        and after.get("qualified") == 48
        and after.get("agreement", 0) >= 0.9
        and live_result.get("refused") == 0
    )
    report = {
        "seed": seed,
        "arm": arm,
        "status": status,
        "failure": failure,
        "unknown_work": unknown,
        "qualified_acquisition_and_body_gate": passed,
        "accepted_admissions": admissions,
        "calls": calls,
        "work": dict(work),
        "phases": phase_results,
        "seconds": time.monotonic() - started,
        "cpu_seconds": time.process_time() - cpu_started,
        "work_by_kind": {k: dict(v) for k, v in by_kind.items()},
        "sources_unchanged": unchanged,
    }
    write(out / "result.json", report)
    return report


def run(root, core):
    bound_inputs(root, core)
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run_arm, root, core, seed, arm)
            for seed in SEEDS
            for arm in ARMS
        ]
        results = [future.result() for future in futures]
    write(
        root / "summary.json",
        {"outcomes": results, "all_planned_retained": len(results) == 15},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("freeze", "run"))
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--core", type=Path, required=True)
    args = p.parse_args()
    (freeze if args.command == "freeze" else run)(
        args.root.resolve(), args.core.resolve()
    )
