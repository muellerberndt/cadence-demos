"""Source-bound replay of every recorded Freeway bootstrap solve and body step.

No new teaching rows, selection, or training result is produced. Numerical
replay is checked against immutable saved checkpoints and result hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import atari_flat_bootstrap as a
import numpy as np

from cadence import Brain


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def same(left, right, message):
    check(a.digest(left) == a.digest(right), message)


def snapshot_sha(brain):
    return hashlib.sha256(brain.snapshot().encode()).hexdigest()


def ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def episode_flags(episode, trace, refused):
    actual = (
        (trace[-1]["terminated"], trace[-1]["truncated"]) if trace else (False, False)
    )
    same((episode["terminated"], episode["truncated"]), actual, "native end flags")
    check(episode["refused"] == refused, "native refusal")
    check(episode["censored"] == (not actual[0]), "native censor")


def gate(report, episodes, baselines, held, returned, unknown):
    teachers = {row["seed"]: row for row in baselines if row["baseline"] == "teacher"}
    admissions = [r for r in returned if r["kind"] == "admission"]
    qualified = all(r["result"]["qualified"] for r in returned)
    return bool(
        report["status"] == "complete"
        and report["sources_unchanged"]
        and len(admissions) == 64
        and all(r["result"]["accepted"] for r in admissions)
        and qualified
        and not unknown
        and len(held) == 512
        and sum(r["correct"] for r in held) / 512 >= 0.95
        and [r["seed"] for r in episodes] == list(a.PLAY_SEEDS)
        and all(
            r["terminated"]
            and not r["truncated"]
            and not r["refused"]
            and r["return"] > 0
            and teachers[r["seed"]]["terminated"]
            and not teachers[r["seed"]]["truncated"]
            and r["return"] >= 0.8 * teachers[r["seed"]]["return"]
            for r in episodes
        )
    )


def verify_collection(root):
    protocol = a.bound_protocol(root)
    collection = read(root / "collection.json")
    check(
        collection["protocol_sha256"] == a.sha(root / "protocol.json"),
        "collection protocol",
    )
    check(
        collection["data_sha256"] == a.sha(root / "data.npz"), "collection array hash"
    )
    same(collection["meanings"], ["NOOP", "UP", "DOWN"], "action encoding")
    with np.load(root / "data.npz") as data:
        arrays = {name: data[name].copy() for name in data.files}
    train = np.concatenate([arrays[f"x{s}"] for s in a.TRAIN_SEEDS])
    check(np.array_equal(arrays["mean"], train.mean(0)), "train-only mean")
    check(
        np.array_equal(arrays["scale"], np.maximum(train.std(0), 0.05)),
        "train-only scale",
    )
    check(len(collection["records"]) == 1536, "complete collection")
    env = a.make_env()
    cursor = 0
    try:
        for seed in (*a.TRAIN_SEEDS, a.HELD_SEED):
            obs = a.start(env, seed)
            previous, last = None, 0
            for tick in range(a.ROWS):
                r = collection["records"][cursor]
                cursor += 1
                x, previous = a.features(obs, previous, last, 3)
                same(
                    (r["seed"], r["tick"], r["executed_action"]),
                    (seed, tick, 1),
                    "collection identity",
                )
                check(
                    r["observation_sha256"] == a.array_sha(obs),
                    "collection actual preframe",
                )
                check(
                    np.array_equal(x, arrays[f"x{seed}"][tick]), "collection features"
                )
                check(r["features_sha256"] == a.array_sha(x), "collection feature hash")
                check(int(arrays[f"a{seed}"][tick]) == 1, "executed witness action")
                obs, reward, term, trunc, _ = env.step(1)
                check(
                    r["next_observation_sha256"] == a.array_sha(obs),
                    "collection actual nextframe",
                )
                same(
                    (r["reward"], r["terminated"], r["truncated"]),
                    (float(reward), bool(term), bool(trunc)),
                    "collection native outcome",
                )
                last = 1
        baselines = read(root / "baselines.json")
        same(
            [(r["seed"], r["baseline"]) for r in baselines],
            [(s, b) for s in a.PLAY_SEEDS for b in ("teacher", "noop")],
            "baseline inventory",
        )
        for original in baselines:
            replayed = a.native_episode(
                env, original["seed"], baseline=original["baseline"]
            )
            for key in (
                "seed",
                "baseline",
                "return",
                "decisions",
                "terminated",
                "truncated",
                "censored",
                "refused",
            ):
                same(original[key], replayed[key], f"baseline {key}")
            for old, new in zip(original["actions"], replayed["actions"], strict=True):
                same(
                    {
                        k: v
                        for k, v in old.items()
                        if k != "observation_to_action_seconds"
                    },
                    {
                        k: v
                        for k, v in new.items()
                        if k != "observation_to_action_seconds"
                    },
                    "baseline body trace",
                )
    finally:
        env.close()
    return protocol, baselines


def verify_arm(root_string, seed):
    import torch

    torch.set_num_threads(1)
    root, out = Path(root_string), Path(root_string) / f"seed{seed}"
    protocol = a.bound_protocol(root)
    report = read(out / "report.json")
    check(report["seed"] == seed, "report identity")
    check(report["protocol_sha256"] == a.sha(root / "protocol.json"), "arm protocol")
    check(
        report["collection_sha256"] == a.sha(root / "collection.json"), "arm collection"
    )
    for name, record in report["files"].items():
        check(
            a.sha(out / name) == record["sha256"]
            and (out / name).stat().st_size == record["bytes"],
            f"artifact {name}",
        )
    brain = Brain.from_snapshot(
        (out / "initial.json").read_text(), device="cpu", dtype="float64"
    )
    check(snapshot_sha(brain) == report["initial_sha256"], "initial checkpoint")
    check(brain.snapshot() == a.make_brain(seed).snapshot(), "declared founder")
    with np.load(root / "data.npz") as data:
        mean, scale = data["mean"], data["scale"]
        train = a.normalize(
            np.concatenate([data[f"x{s}"] for s in a.TRAIN_SEEDS]), mean, scale
        )
        actions = np.concatenate([data[f"a{s}"] for s in a.TRAIN_SEEDS])
        held = a.normalize(data[f"x{a.HELD_SEED}"], mean, scale)
        targets = data[f"a{a.HELD_SEED}"]
    rows = ledger(out / "calls.jsonl")
    transitions = (
        ledger(out / "transitions.jsonl")
        if (out / "transitions.jsonl").exists()
        else []
    )
    body_rows = {(r["seed"], r["tick"]): r for r in transitions}
    check(len(body_rows) == len(transitions), "duplicate native execution")
    records = {"newborn": [], "trained": []}
    counts, work, native_counts = Counter(), {}, Counter()
    consumed, refused_native = set(), set()
    current_seed, previous, last, obs = None, None, 0, None
    env = a.make_env()
    try:
        for index, row in enumerate(rows):
            check(row["id"] == index, "call ordinal")
            check(row["before_sha256"] == snapshot_sha(brain), "call before snapshot")
            if row["status"] != "returned":
                check(
                    index == len(rows) - 1 and row["unknown_solver_work"],
                    "interrupted suffix",
                )
                continue
            kind = row["kind"]
            if kind == "admission":
                update = row["update"]
                check(update == counts["admission"], "admission order")
                same(
                    row["indices"],
                    protocol["schedule"][update],
                    "exact common row schedule",
                )
                examples = [
                    (
                        {"visible": train[j].tolist()},
                        {"motor": a.action_targets(actions[j], 3)},
                    )
                    for j in row["indices"]
                ]
                result = a.admit(brain, examples, update)
                check(
                    result["source"] == "witness" and result["event_id"] == update + 1,
                    "actual action witness event",
                )
                if (update + 1) % 16 == 0:
                    check(
                        snapshot_sha(brain)
                        == a.sha(out / f"update{update + 1:03}.json"),
                        "checkpoint exact replay",
                    )
            elif kind == "heldout":
                phase, i = row["phase"], row["row"]
                check(i == len(records[phase]), "heldout row order")
                x = held[i]
                check(
                    row["inputs_sha256"] == a.array_sha(x), "heldout free query input"
                )
                result = brain.settle({"visible": x.tolist()})
                records[phase].append(
                    {
                        "correct": bool(
                            result["qualified"]
                            and int(np.argmax(result["outputs"]["motor"]))
                            == int(targets[i])
                        ),
                        "qualified": result["qualified"],
                    }
                )
            elif kind == "native":
                play_seed, tick = row["seed"], row["tick"]
                if play_seed != current_seed:
                    check(
                        play_seed == a.PLAY_SEEDS[len(native_counts)],
                        "native seed order",
                    )
                    current_seed, previous, last = play_seed, None, 0
                    obs = a.start(env, play_seed)
                check(tick == native_counts[play_seed], "native tick order")
                x, previous = a.features(obs, previous, last, 3)
                x = a.normalize(x, mean, scale)
                check(
                    row["observation_sha256"] == a.array_sha(obs),
                    "actual native observation",
                )
                check(row["inputs_sha256"] == a.array_sha(x), "native causal input")
                result = brain.settle({"visible": x.tolist()})
                execution = body_rows.get((play_seed, tick))
                if result["qualified"] and execution is not None:
                    consumed.add((play_seed, tick))
                    chosen = int(np.argmax(result["outputs"]["motor"]))
                    check(
                        execution["executed_action"] == chosen,
                        "body executed qualified choice",
                    )
                    check(
                        execution["observation_sha256"] == a.array_sha(obs),
                        "transition preframe",
                    )
                    obs, reward, term, trunc, _ = env.step(chosen)
                    same(
                        (
                            execution["reward"],
                            execution["terminated"],
                            execution["truncated"],
                        ),
                        (float(reward), bool(term), bool(trunc)),
                        "native actual reward/termination",
                    )
                    check(
                        execution["next_observation_sha256"] == a.array_sha(obs),
                        "transition nextframe",
                    )
                    last = chosen
                else:
                    if not result["qualified"]:
                        refused_native.add(play_seed)
                    check(
                        execution is None
                        and (not result["qualified"] or report["status"] != "complete"),
                        "no fabricated transition after refusal",
                    )
                native_counts[play_seed] += 1
            else:
                raise ValueError(f"unknown call kind {kind}")
            same(
                a.compact_result(result),
                row["result"],
                "all result fields and parameter hash exactly replay",
            )
            check(snapshot_sha(brain) == row["after_sha256"], "call after snapshot")
            counts[kind] += 1
            work.setdefault(kind, Counter()).update(result["work"])
    finally:
        env.close()
    check(consumed == set(body_rows), "every recorded body transition replayed")
    for phase in ("newborn", "trained"):
        key = "initial_heldout" if phase == "newborn" else "final_heldout"
        if key in report:
            found = records[phase]
            check(len(found) == 512, "complete heldout gate")
            same(
                report[key]["agreement"],
                sum(r["correct"] for r in found) / 512,
                "heldout agreement",
            )
            same(
                report[key]["qualified"],
                sum(r["qualified"] for r in found),
                "heldout qualifications",
            )
    returned = [r for r in rows if r["status"] == "returned"]
    unknown = len(rows) - len(returned)
    if (out / "inflight.json").exists():
        pending = read(out / "inflight.json")
        unknown += int(not any(r["id"] == pending["id"] for r in rows))
    check(report["unknown_calls"] == unknown, "unknown call count")
    check(report["returned_calls"] == len(returned), "returned call count")
    refused = sum(
        not r["result"]["qualified"]
        or (r["kind"] == "admission" and not r["result"]["accepted"])
        for r in returned
    )
    check(report["refused_calls"] == refused, "refused call count")
    attempts = sum(r["kind"] == "admission" for r in rows)
    check(
        report["attempted_updates"] == attempts
        and report["attempted_row_presentations"] == 16 * attempts,
        "attempted exposure",
    )
    accepted = sum(
        r["kind"] == "admission" and r["result"]["accepted"] for r in returned
    )
    check(report["accepted_updates"] == accepted, "admission count")
    check(report["accepted_row_presentations"] == 16 * accepted, "accepted exposure")
    same(
        report["work"],
        {kind: dict(work.get(kind, {})) for kind in ("admission", "heldout", "native")},
        "work totals",
    )
    same(
        report["query_latency_all_phases"],
        a.latency([r["seconds"] for r in rows if r["kind"] != "admission"]),
        "all phase query latency",
    )
    for episode in report["episodes"]:
        raw = read(out / f"play{episode['seed']}.json")
        same(
            {k: v for k, v in raw.items() if k != "actions"}, episode, "episode receipt"
        )
        trace = [r for r in transitions if r["seed"] == episode["seed"]]
        same(trace, raw["actions"], "episode body ledger")
        check(len(trace) == episode["decisions"], "native decisions")
        check(len(trace) <= a.PLAY_LIMIT, "native body budget")
        episode_flags(episode, trace, episode["seed"] in refused_native)
        same(sum(r["reward"] for r in trace), episode["return"], "native return sum")
        same(
            episode["latency"],
            a.latency([r["observation_to_action_seconds"] for r in trace]),
            "native total dispatch latency",
        )
    if report["status"] == "complete":
        check(
            not (out / "inflight.json").exists()
            and not (out / "body-inflight.json").exists(),
            "complete custody",
        )
        check(
            counts["admission"] == 64 and counts["heldout"] == 1024,
            "complete call inventory",
        )
        check(
            snapshot_sha(brain) == a.sha(out / "final.json") == report["final_sha256"],
            "final snapshot/pure native replay",
        )
        check(
            a.sha(out / "latest.json") == report["final_sha256"],
            "latest accepted snapshot",
        )
    expected_gate = gate(
        report,
        report["episodes"],
        read(root / "baselines.json"),
        records["trained"],
        returned,
        report["unknown_calls"],
    )
    check(report["passed"] == expected_gate, "independent outcome gate")
    return {
        "seed": seed,
        "status": report["status"],
        "passed": expected_gate,
        "exact_replayed_calls": len(returned),
        "replayed_admissions": accepted,
        "replayed_body_transitions": len(transitions),
        "newborn": report.get("initial_heldout"),
        "trained": report.get("final_heldout"),
        "episodes": report["episodes"],
        "all_query_latency": report["query_latency_all_phases"],
        "work": report["work"],
        "refused_calls": report["refused_calls"],
        "unknown_calls": report["unknown_calls"],
        "report_sha256": a.sha(out / "report.json"),
    }


def verify(root, out):
    began = time.perf_counter()
    protocol, baselines = verify_collection(root)
    execution = read(root / "execution.json")
    same([r["seed"] for r in execution], a.MODEL_SEEDS, "all planned arms retained")
    with ProcessPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(verify_arm, [str(root)] * 3, a.MODEL_SEEDS))
    check(protocol["sources"] == a.sources(), "sources unchanged after replay")
    receipt = {
        "verified": True,
        "protocol_sha256": a.sha(root / "protocol.json"),
        "verifier_sha256": a.sha(__file__),
        "collection_rows_replayed": 1536,
        "baseline_episodes_replayed": 6,
        "baselines": [
            {
                k: r[k]
                for k in (
                    "seed",
                    "baseline",
                    "return",
                    "decisions",
                    "terminated",
                    "truncated",
                )
            }
            for r in baselines
        ],
        "outcomes": outcomes,
        "all_three_pass": all(r["passed"] for r in outcomes),
        "seconds": time.perf_counter() - began,
        "scope": "Exact replay of collection and native ALE outcomes, every returned public numerical solve including admissions, all recorded checkpoint identities, result fields/parameter hashes, gates/work/latencies. This verifies constant-UP routine acquisition only, not visual strategy or reward learning.",
    }
    a.write(out, receipt)
    print(
        json.dumps(
            {
                "verified": True,
                "all_three_pass": receipt["all_three_pass"],
                "seconds": receipt["seconds"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verify(args.root.resolve(), args.out.resolve())
