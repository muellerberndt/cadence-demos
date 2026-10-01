"""Verify the frozen six-case Amen startup campaign without admitting learning.

Checks every prepared row, schedule, returned-call custody and saved checkpoint;
replays all returned free queries and independently checks their flat optima.
Training solves are NOT numerically replayed. Missing/censored arms stay outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import amen_startup_curriculum as C
import numpy as np

from cadence import Brain

COLLECTOR_SHA = "2f3b8974ecf2a9019b336d26eadb74e5442c533b195204f75a7e76b395039718"
PROTOCOL_SHA = "6b04f951dd45372a75f00b693f6fb7fe5288039cf3abddceb8f4dc37729eaffa"


def check(value, message):
    if not value:
        raise ValueError(message)


def snapshot_sha(brain):
    return hashlib.sha256(brain.snapshot().encode()).hexdigest()


def parameter_sha(brain):
    return C.digest({"weights": list(brain.weights), "biases": list(brain.biases)})


def validate_schedule(tapes, lengths, seed):
    """Independently reconstruct row multiset and within-batch replacement rule."""
    total = sum(lengths)
    original = np.random.default_rng(seed).permutation(total)[:4096].reshape(128, 32)
    check(tapes["uniform"] == original.tolist(), "uniform row order")
    pool, offset = [], 0
    for length in lengths:
        pool.extend(range(offset, offset + min(length, 8)))
        offset += length
    rng = np.random.default_rng(np.random.SeedSequence([seed, 20261010]))
    prefix = []
    while len(prefix) < 2048:
        prefix += rng.permutation(pool).tolist()
    expected = original.copy()
    expected[:, 16:] = np.array(prefix[:2048]).reshape(128, 16)
    check(tapes["startup-balanced"] == expected.tolist(), "prefix replacement order")
    counts = {}
    starts = set(np.cumsum([0, *lengths[:-1]]).tolist())
    for arm, rows in tapes.items():
        flat = [i for batch in rows for i in batch]
        counts[arm] = {
            "presentations": len(flat),
            "unique_rows": len(set(flat)),
            "repeated_presentations": len(flat) - len(set(flat)),
            "wake_rows": sum(i in starts for i in flat),
            "prefix_rows": sum(i in set(pool) for i in flat),
            "other_rows": sum(i not in set(pool) for i in flat),
        }
    return counts


def counts(rows, inflight=None):
    returned = [r for r in rows if r["status"] == "returned"]
    unmatched = inflight and not any(r["id"] == inflight["id"] for r in rows)
    attempts = sum(r["kind"] == "admission" for r in rows) + int(
        bool(unmatched and inflight["kind"] == "admission")
    )
    accepted = sum(
        r["kind"] == "admission" and r["result"]["accepted"] for r in returned
    )
    work = {}
    for kind in ("admission", "heldout", "generation"):
        counter = Counter()
        for r in returned:
            if r["kind"] == kind:
                counter.update(r["result"]["work"])
        work[kind] = dict(counter)
    return {
        "returned_calls": len(returned),
        "unknown_calls": len(rows) - len(returned) + int(bool(unmatched)),
        "accepted_admissions": accepted,
        "attempted_admissions": attempts,
        "accepted_presentations": 32 * accepted,
        "attempted_presentations": 32 * attempts,
        "refused_calls": sum(
            not r["result"]["qualified"]
            or (r["kind"] == "admission" and not r["result"]["accepted"])
            for r in returned
        ),
        "work": work,
    }


def eligible(report, derived, outer):
    initial = derived.get("initial_heldout", {})
    final = derived.get("final_heldout", {})
    gen = derived.get("generation", {})
    argmax = gen.get("argmax-0", {})
    gain = initial.get("metrics", {}).get("decoded_all_port_mae", 0) - final.get(
        "metrics", {}
    ).get("decoded_all_port_mae", 1)
    numerical = bool(
        outer.get("exit_code") == 0
        and outer.get("status") not in ("outer_timeout", "launch_error")
        and report.get("status") == "complete"
        and report.get("sources_unchanged")
        and report.get("wall_seconds", 901) < 900
        and derived["attempted_admissions"] == derived["accepted_admissions"] == 128
        and derived["refused_calls"] == derived["unknown_calls"] == 0
        and initial.get("qualified") == final.get("qualified") == 128
        and len(gen) == 5
        and all(v.get("complete") for v in gen.values())
    )
    return numerical, bool(
        numerical
        and gain >= 0.01
        and argmax["drum_fraction"] >= 0.5
        and argmax["bass_fraction"] >= 0.25
    )


class Replay:
    def __init__(self, path, ref):
        text = path.read_text()
        self.brain = Brain.from_snapshot(text)
        check(self.brain.snapshot() == text, f"roundtrip {path.name}")
        ref.flat_check(self.brain, 8)
        self.sha, self.parameters = C.sha(path), parameter_sha(self.brain)
        self.theta = np.zeros((71, 585))
        for (_, source, target), weight in zip(
            self.brain.graph.edges, self.brain.weights, strict=True
        ):
            self.theta[target, source] = weight
        self.calls, self.gap = 0, 0.0

    def query(self, row, values):
        check(
            row["before_sha256"] == row["after_sha256"] == self.sha,
            "free query state custody",
        )
        check(row["inputs_sha256"] == C.digest(values), "free query causal inputs")
        r = self.brain.settle(values)
        check(
            C.digest(C.compact(r)) == C.digest(row["result"]),
            f"exact free replay call {row['id']}",
        )
        check(
            row["result"]["parameters_sha256"] == self.parameters,
            "query parameter hash",
        )
        raw = np.asarray(
            [*values["past"], *values["heard"], *values["clock"], values["wake"]]
        )
        cfg = self.brain.config
        optimum = np.clip(
            np.tanh(self.theta @ raw + self.brain.biases) / (1 + cfg["state_prior"]),
            -cfg["state_bound"],
            cfg["state_bound"],
        )
        gap = float(np.max(np.abs(np.asarray(r["outputs"]["event"]) - optimum)))
        if r["qualified"]:
            check(r["stationarity"] <= cfg["tolerance"], "qualification stationarity")
            check(
                gap <= cfg["tolerance"] / (1 + cfg["state_prior"]) + 1e-11,
                "independent flat optimum",
            )
        self.gap = max(self.gap, gap)
        self.calls += 1
        return r

    def finish(self):
        check(snapshot_sha(self.brain) == self.sha, "pure replay changed brain")


def verify_data(root, p, S, ref):
    fixture, regions, _ = S.load_fixture("soft")
    check(fixture["receipt_sha256"] == p["fixture_receipt"], "fixture receipt")
    ids = [r["id"] for r in fixture["regions"] if r["id"] not in S.HELD_OUT]
    check(
        ids == p["train_regions"] and list(S.HELD_OUT) == p["held_out"], "frozen split"
    )
    check(not set(ids) & set(S.HELD_OUT), "region leakage")
    lengths = [len(regions[r]) for r in ids]
    check(lengths == p["lengths"], "row lengths")
    names = ("history", "clock", "wake", "targets", "origin")
    arrays = [np.load(root / "data" / f"{name}.npy", mmap_mode="r") for name in names]
    offset = 0
    for i, rid in enumerate(ids):
        n = len(regions[rid])
        stream = S.stream(regions[rid], 8)
        for actual, expected in zip(arrays[:4], stream, strict=True):
            check(
                np.array_equal(actual[offset : offset + n], expected),
                f"prepared true row values {rid}",
            )
        check(np.all(arrays[4][offset : offset + n] == i), "prepared row origin")
        offset += n
    check(all(len(a) == offset for a in arrays), "prepared cardinality")
    tapes = C.read(root / "schedules.json")
    for seed in (1103, 1109, 1117):
        exposures = validate_schedule(tapes[str(seed)], lengths, seed)
        for arm, value in exposures.items():
            check(value == p["exposure"][f"{seed}-{arm}"], "exposure receipt")
    held = C.read(root / "heldout.json")
    picks = ref.frozen_picks(regions, S.HELD_OUT, 16, 1103)
    check(picks == p["evaluation_sample"], "original heldout windows")
    expected = []
    for pick in picks:
        events = regions[pick["region"]]
        window = [S.COUNT_IN.copy()]
        for t, truth in enumerate(events[: pick["start"] + pick["rows"]]):
            if t >= pick["start"]:
                expected.append(
                    {
                        "region": pick["region"],
                        "row": t,
                        "inputs": ref.inputs(window, t, 8),
                        "truth": truth.tolist(),
                    }
                )
            window.append(S.executed(truth))
    check(held == expected, "independent causal heldout context")
    starts = np.asarray([regions[r][0] for r in ids])
    prefix = np.concatenate([regions[r][:8] for r in ids])
    startup = {
        "regions": len(ids),
        "prefix_rows": len(prefix),
        "wake_drums": int((starts[:, S.DRUM_ON] > 0.5).sum()),
        "wake_bass": int((starts[:, S.BASS_ON] > 0.5).sum()),
        "prefix_drum_fraction": float((prefix[:, S.DRUM_ON] > 0.5).mean()),
        "prefix_bass_fraction": float((prefix[:, S.BASS_ON] > 0.5).mean()),
    }
    check(startup == p["startup_targets"], "unfiltered startup target counts")
    return held, tapes, arrays, offset


def verify_arm(root, seed, arm, outer, p, held, tape, arrays, S, ref):
    out = root / f"{arm}-seed{seed}"
    if not (out / "report.json").exists():
        check(
            outer.get("status") in ("launch_error", "outer_timeout")
            or outer.get("exit_code") != 0,
            "unexplained missing arm",
        )
        return {
            "seed": seed,
            "arm": arm,
            "status": "missing",
            "numerically_complete": False,
            "smoke_passed": False,
            "outer": outer,
        }
    report = C.read(out / "report.json")
    check((report["seed"], report["arm"]) == (seed, arm), "arm identity")
    rows = (
        [json.loads(line) for line in (out / "calls.jsonl").read_text().splitlines()]
        if (out / "calls.jsonl").exists()
        else []
    )
    inflight = (
        C.read(out / "inflight.json") if (out / "inflight.json").exists() else None
    )
    derived = counts(rows, inflight)
    for key, value in derived.items():
        if key in report:
            check(report[key] == value, f"derived {key}")
    for name, identity in report.get("files", {}).items():
        check(
            C.sha(out / name) == identity["sha256"]
            and (out / name).stat().st_size == identity["bytes"],
            "artifact hash/size",
        )
    if not (out / "initial.json").exists():
        check(report["status"] != "complete", "complete without initial")
        return dict(
            seed=seed,
            arm=arm,
            status=report["status"],
            numerically_complete=False,
            smoke_passed=False,
            **derived,
        )
    initial = Replay(out / "initial.json", ref)
    check(
        initial.sha == p["founders"][str(seed)] == report["initial_sha256"],
        "paired founder",
    )
    final = Replay(out / "final.json", ref) if (out / "final.json").exists() else None
    snapshots = {initial.sha: initial.brain}
    saved = []
    for path in sorted(out.glob("*.json")):
        if path.name not in (
            "initial.json",
            "latest.json",
            "final.json",
        ) and not path.name.startswith("update"):
            continue
        text = path.read_text()
        brain = Brain.from_snapshot(text)
        check(brain.snapshot() == text, "saved snapshot roundtrip")
        ref.flat_check(brain, 8)
        check(
            brain.graph == initial.brain.graph and brain.state == initial.brain.state,
            "admission changed live state or graph",
        )
        snapshots[C.sha(path)] = brain
        saved.append(path.name)
    for cp in report.get("checkpoints", []):
        check(C.sha(out / cp["name"]) == cp["sha256"], "checkpoint receipt")
    expected_meta = [
        {"kind": "heldout", "phase": "newborn", "row": i} for i in range(128)
    ]
    expected_meta += [
        {"kind": "admission", "update": i, "indices": batch}
        for i, batch in enumerate(tape)
    ]
    expected_meta += [
        {"kind": "heldout", "phase": "trained", "row": i} for i in range(128)
    ]
    expected_meta += [
        {"kind": "generation", "mode": mode, "seed": s, "tick": t}
        for mode, s in [
            ("argmax", 0),
            ("sample", 1),
            ("sample", 2),
            ("sample", 3),
            ("sample", 4),
        ]
        for t in range(128)
    ]
    # Qualification failures stop only that generation episode; walk its declared suffix independently.
    position = 0
    current = initial.sha
    admitted = 0
    attempted = 0
    held_predictions = {"newborn": [], "trained": []}
    held_qualified = Counter()
    generated = {}
    windows = {}
    rngs = {}
    last_parameter = initial.parameters
    for i, row in enumerate(rows):
        check(row["id"] == i, "call id")
        check(position < len(expected_meta), "extra call")
        wanted = expected_meta[position]
        check(all(row.get(k) == v for k, v in wanted.items()), f"call order {i}")
        check(row["before_sha256"] == current, "snapshot chain")
        if row["status"] != "returned":
            check(
                i == len(rows) - 1 and row.get("unknown_solver_work"),
                "unknown work suffix",
            )
            break
        result = row["result"]
        check(
            all(isinstance(v, int) and v >= 0 for v in result["work"].values()),
            "invalid work counters",
        )
        if result["qualified"]:
            check(result["stationarity"] <= 1e-6, "qualified stationary gate")
        if row["kind"] == "admission":
            check(
                result["source"] == "witness"
                and result["event_id"] == admitted
                and result["batch_size"] == 32
                and not result["duplicate"],
                "witness admission identity",
            )
            check(result["accepted"] == result["qualified"], "accepted qualification")
            check(
                np.array_equal(np.asarray(result["states"]), arrays[3][row["indices"]]),
                "actual target clamps",
            )
            if not result["accepted"]:
                check(row["after_sha256"] == current, "refusal mutated brain")
            else:
                admitted += 1
                last_parameter = result["parameters_sha256"]
            attempted += 1
            current = row["after_sha256"]
            if current in snapshots:
                b = snapshots[current]
                check(
                    b.inspect()["admissions"] == admitted
                    and b.inspect()["last_event_id"] == admitted - 1,
                    "snapshot admission cursor",
                )
                check(
                    parameter_sha(b) == last_parameter,
                    "saved admission parameter identity",
                )
            if attempted % 32 == 0 and any(
                cp["name"] == f"update{attempted:03}.json"
                for cp in report.get("checkpoints", [])
            ):
                check(
                    C.sha(out / f"update{attempted:03}.json") == current,
                    "checkpoint admission boundary",
                )
        elif row["kind"] == "heldout":
            replay = initial if row["phase"] == "newborn" else final
            check(replay is not None, "trained query without final")
            r = replay.query(row, held[row["row"]]["inputs"])
            held_predictions[row["phase"]].append(
                S.decode(r["outputs"]["event"]).tolist()
            )
            held_qualified[row["phase"]] += int(r["qualified"])
        else:
            key = f"{row['mode']}-{row['seed']}"
            if key not in generated:
                generated[key] = []
                windows[key] = [S.COUNT_IN.copy()]
                rngs[key] = np.random.default_rng(row["seed"])
            check(row["tick"] == len(generated[key]), "generation chronological tick")
            values = ref.inputs(windows[key], row["tick"], 8)
            check(final is not None, "generation without final")
            r = final.query(row, values)
            if r["qualified"]:
                event = S.executed(
                    S.decode(r["outputs"]["event"]),
                    row["mode"],
                    rngs[key],
                    previous=windows[key][-1] if row["mode"] == "sample" else None,
                )
                generated[key].append(event.tolist())
                windows[key].append(event)
            else:
                position += 127 - row["tick"]
        position += 1
    if inflight:
        check(inflight["id"] in (len(rows), len(rows) - 1), "inflight index")
        check(inflight["before_sha256"] == current, "inflight last accepted state")
    if final:
        check(final.sha == current == report["final_sha256"], "final admission custody")
    check(C.sha(out / "latest.json") == current, "last accepted checkpoint")
    check(admitted == derived["accepted_admissions"], "accepted count")
    if current in snapshots:
        check(
            snapshots[current].inspect()["admissions"] == admitted,
            "last snapshot cursor",
        )
    truth = [r["truth"] for r in held]
    for phase, label in (("newborn", "initial_heldout"), ("trained", "final_heldout")):
        pred = held_predictions[phase]
        if len(pred) == 128:
            value = {
                "qualified": held_qualified[phase],
                "metrics": ref.metrics(pred, truth, S),
                "by_region": {
                    name: ref.metrics(
                        [
                            v
                            for v, r in zip(pred, held, strict=True)
                            if r["region"] == name
                        ],
                        [r["truth"] for r in held if r["region"] == name],
                        S,
                    )
                    for name in S.HELD_OUT
                },
            }
            check(value == report[label], "heldout metrics")
            derived[label] = value
    derived["generation"] = {}
    for key, events in generated.items():
        report_gen = report.get("generation", {}).get(key)
        if report_gen is None:
            check(report["status"] != "complete", "missing generation receipt")
            continue
        check(report_gen["events"] == events, "executed event sequence")
        complete = len(events) == 128
        check(report_gen["complete"] == complete, "generation completion")
        if complete:
            e = np.asarray(events)
            value = {
                "complete": True,
                "drum_fraction": float((e[:, S.DRUM_ON] > 0.5).mean()),
                "bass_fraction": float((e[:, S.BASS_ON] > 0.5).mean()),
            }
            check(
                all(report_gen[k] == v for k, v in value.items()), "generation presence"
            )
            check(report_gen["statistics"] == S.statistics(e), "generation statistics")

            def presence(v):
                return {
                    "drum_fraction": float((v[:, S.DRUM_ON] > 0.5).mean()),
                    "bass_fraction": float((v[:, S.BASS_ON] > 0.5).mean()),
                }

            check(
                report_gen["parts"]
                == {"first8": presence(e[:8]), "rest": presence(e[8:])},
                "generation prefix summary",
            )
            check(
                report_gen["per_bar"]
                == [presence(e[i : i + 8]) for i in range(0, 128, 8)],
                "generation bar summary",
            )
            value.update(parts=report_gen["parts"], per_bar=report_gen["per_bar"])
            derived["generation"][key] = value
        else:
            derived["generation"][key] = {"complete": False}
    if "final_heldout" in derived and "initial_heldout" in derived:
        gain = (
            derived["initial_heldout"]["metrics"]["decoded_all_port_mae"]
            - derived["final_heldout"]["metrics"]["decoded_all_port_mae"]
        )
        check(report["heldout_mae_gain"] == gain, "MAE gain")
        derived["heldout_mae_gain"] = gain
    numerical, smoke = eligible(report, derived, outer)
    check(report.get("smoke_passed", False) == smoke, "smoke gate")
    initial.finish()
    if final:
        final.finish()
    return dict(
        seed=seed,
        arm=arm,
        status=report["status"],
        numerically_complete=numerical,
        smoke_passed=smoke,
        wall_seconds=report.get("wall_seconds"),
        replayed_free_calls=initial.calls + (final.calls if final else 0),
        worst_flat_optimum_gap=max(initial.gap, final.gap if final else 0),
        checked_snapshots=saved,
        **derived,
    )


def verify(root, output):
    import torch

    started = time.monotonic()
    torch.set_num_threads(4)
    own_sha = C.sha(__file__)
    check(C.sha(C.__file__) == COLLECTOR_SHA, "collector pin")
    check(C.sha(root / "protocol.json") == PROTOCOL_SHA, "protocol pin")
    p = C.bound(root)
    check(
        p["jobs"]
        == [
            [s, a] for s in (1103, 1109, 1117) for a in ("uniform", "startup-balanced")
        ],
        "all six frozen arms",
    )
    _compose, M, S, _train = C.app_modules(Path(p["app"]))
    ref = C.reference(p["reference_helper"])
    held, tapes, arrays, total = verify_data(root, p, S, ref)
    for seed in (1103, 1109, 1117):
        check(
            snapshot_sha(C.build(M, seed)) == p["founders"][str(seed)],
            "founder reconstruction",
        )
    execution = C.read(root / "execution.json")
    check(
        [[r["seed"], r["arm"]] for r in execution] == p["jobs"], "execution inventory"
    )
    check(
        C.read(root / "planned-cases.json")
        == [{"seed": s, "arm": a, "status": "planned"} for s, a in p["jobs"]],
        "planned inventory",
    )
    results = []
    for outer, (seed, arm) in zip(execution, p["jobs"], strict=True):
        item = verify_arm(
            root, seed, arm, outer, p, held, tapes[str(seed)][arm], arrays, S, ref
        )
        results.append(item)
        print(
            json.dumps(
                {
                    "seed": seed,
                    "arm": arm,
                    "status": item["status"],
                    "smoke_passed": item["smoke_passed"],
                }
            ),
            flush=True,
        )
    baseline = Brain.from_snapshot(
        (Path(p["original_uniform128"]) / "final.json").read_text()
    )
    current_path = root / "uniform-seed1103" / "final.json"
    equal = None
    if current_path.exists():
        current = Brain.from_snapshot(current_path.read_text())
        equal = {
            k: getattr(current, k) == getattr(baseline, k)
            for k in ("weights", "biases", "state", "graph")
        }
        equal.update(
            {
                k: current.inspect()[k] == baseline.inspect()[k]
                for k in ("admissions", "last_event_id")
            }
        )
        check(all(equal.values()), "uniform1103 original128 numeric reproduction")
    paired = []
    for seed in (1103, 1109, 1117):
        u, b = [r for r in results if r["seed"] == seed]
        delta = None
        if "final_heldout" in u and "final_heldout" in b:
            delta = (
                b["final_heldout"]["metrics"]["decoded_all_port_mae"]
                - u["final_heldout"]["metrics"]["decoded_all_port_mae"]
            )
        paired.append(
            {
                "seed": seed,
                "balanced_minus_uniform_mae": delta,
                "uniform_smoke": u["smoke_passed"],
                "balanced_smoke": b["smoke_passed"],
            }
        )
    C.bound(root)
    check(C.sha(__file__) == own_sha, "verifier changed during run")
    receipt = {
        "schema": "amen-startup-verification/1",
        "verified": True,
        "protocol_sha256": PROTOCOL_SHA,
        "collector_sha256": COLLECTOR_SHA,
        "verifier_sha256": own_sha,
        "prepared_rows_checked": total,
        "heldout_rows": 128,
        "uniform1103_matches_original128": equal,
        "results": results,
        "paired": paired,
        "campaign_passed": all(r["numerically_complete"] for r in results)
        and all(r["smoke_passed"] for r in results if r["arm"] == "startup-balanced"),
        "wall_seconds": time.monotonic() - started,
        "scope": "All prepared rows/schedules/source/founder pins, admission target/source/cursor/work custody, every saved checkpoint roundtrip, every returned free query exact numerical replay plus independent flat optima. No numerical learning replay. Reused development corpus/seeds; no listening, browser, musical-quality, architecture or recursive-advantage claim.",
    }
    with output.open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(
        json.dumps(
            {
                "verified": True,
                "campaign_passed": receipt["campaign_passed"],
                "out": str(output),
                "sha256": C.sha(output),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verify(args.root.resolve(), args.out.resolve())
