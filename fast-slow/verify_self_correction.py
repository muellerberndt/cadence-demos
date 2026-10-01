"""Read-only custody/metric verification; never reruns learning or declares advantage.

Run with the frozen Cadence package on PYTHONPATH:
    python verify_self_correction.py --root /path/to/five-seed-campaign

The JSON result always retains all five planned seeds. Exit 1 means invalid
evidence; missing/censored runs remain inconclusive and do not imply invalidity.
Sources may be relocated, but their full relative file inventory must match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import self_correction as frozen

import cadence
from cadence import Brain

SEEDS = (2, 7, 11, 19, 29)
ARMS = ("ordinary", "observer")
SWITCHES = (23, 51, 82, 109)
HORIZONS = (1, 2, 4, 8)
THRESHOLD = 0.03
COLLECTOR_SHA = "1cd811d01a04d42166e360d0ddeac3c03670d6239cde5a5c38fb9625df94fc38"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def same(actual, expected, label):
    # Normalize tuples without silently tolerating changed numeric results.
    require(
        json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True),
        label,
    )


def source_check(protocol):
    package = Path(cadence.__file__).resolve().parent
    local = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*.py")}
    recorded = {}
    collector = []
    for filename, value in protocol["sources"].items():
        path = Path(filename)
        if path.name == "self_correction.py":
            collector.append(value)
        else:
            parts = path.parts
            require("cadence" in parts, "unrecognized source path")
            key = "/".join(
                parts[len(parts) - 1 - tuple(reversed(parts)).index("cadence") + 1 :]
            )
            require(key not in recorded, "duplicate source path")
            recorded[key] = value
    require(
        collector == [COLLECTOR_SHA], "collector was not the reviewed frozen source"
    )
    require(
        sha(Path(frozen.__file__)) == COLLECTOR_SHA, "local collector source differs"
    )
    same(recorded, local, "Cadence source inventory or bytes differ")


def verify_tape(tape):
    # Deterministic regeneration is source-bound; arithmetic and causality below
    # are checked separately from the producer's row/metric helpers.
    same(tape, frozen.make_tape(), "tape differs from the frozen random stream")
    for phase, count in (("train", 512), ("gate", 16), ("test", 128)):
        rows = tape[phase]
        require(len(rows) == count, "wrong tape length")
        for i, row in enumerate(rows):
            require(row["id"] == f"{phase}:{i}" and row["index"] == i, "row identity")
            x0, a0 = row["inputs"]["previous"]
            x1, a1 = row["inputs"]["present"]
            require(0.25 <= abs(a0) <= 0.5 and 0.25 <= abs(a1) <= 0.5, "action range")
            old, new = row["audit"]["past_gain"], row["audit"]["future_gain"]
            require(old in (-0.3, 0.3) and new in (-0.3, 0.3), "gain range")
            require(x1 == 0.8 * x0 + old * a0, "observed body transition")
            same(row["past"], [x1, x1 - x0], "known past witness")
            actual = 0.8 * x1 + new * a1
            same(row["future"], [actual, actual - x1], "future witness arithmetic")
            oracle = 0.8 * x1 + ((x1 - 0.8 * x0) / a0) * a1
            require(
                row["audit"]["causal_absolute_error"] == abs(oracle - actual),
                "causal oracle",
            )
            if i and phase != "gate":
                prev = rows[i - 1]
                same([x0, a0], prev["inputs"]["present"], "history continuity")
                require(x1 == prev["future"][0], "observation precedes forecast")
        if phase == "test":
            same(
                [r["index"] for r in rows if r["audit"]["switch"]],
                SWITCHES,
                "switch positions",
            )


def expected_calls():
    sequence = []
    for batch in range(32):
        indices = list(range(batch * 16, batch * 16 + 16))
        sequence.extend(("forecast", "train", i, [i]) for i in indices)
        sequence.append(("admission", "train", batch, indices))
    sequence.extend(("forecast", "gate", i, [i]) for i in range(16))
    for i in range(128):
        sequence.append(("forecast", "test", i, [i]))
        if i in SWITCHES:
            sequence.append(("forecast", "probe", i + 1, [i + 1]))
        sequence.append(("admission", "test", i, [i]))
    return sequence


def work(calls):
    totals = Counter()
    for c in calls:
        totals.update(c.get("result", {}).get("work", {}))
    return {
        "calls": len(calls),
        "work": dict(totals),
        "solver_seconds": sum(c.get("seconds", 0) for c in calls),
        "interrupted_calls": sum(c["status"] == "interrupted" for c in calls),
        "errored_calls": sum(c["status"] == "error" for c in calls),
        "unknown_work_calls": sum(c.get("unknown_solver_work", False) for c in calls),
        "refusals": sum(c.get("result", {}).get("qualified") is False for c in calls),
        "admissions": sum(c.get("result", {}).get("accepted") is True for c in calls),
    }


def mae(calls):
    errors = [c["position_error"] for c in calls if c.get("position_error") is not None]
    return {
        "planned_or_observed": len(calls),
        "qualified": len(errors),
        "position_mae": sum(errors) / len(errors) if errors else None,
        "complete": bool(calls) and len(errors) == len(calls),
    }


def recovery(calls):
    forecasts = {
        c["index"]: c for c in calls if c["phase"] == "test" and c["kind"] == "forecast"
    }
    result = []
    for s, stop in zip(SWITCHES, (*SWITCHES[1:], 128), strict=True):
        windows = {}
        for h in HORIZONS:
            indices = list(range(s + 1, s + h + 1))
            values = mae([forecasts[i] for i in indices if i in forecasts])
            values.update(
                indices=indices,
                expected=h,
                complete=values["complete"] and values["planned_or_observed"] == h,
            )
            windows[str(h)] = values
        recovered = None
        for last in range(s + 3, stop):
            triple = [forecasts.get(i, {}) for i in range(last - 2, last + 1)]
            if all(
                c.get("position_error") is not None and c["position_error"] <= THRESHOLD
                for c in triple
            ):
                beginning, end = forecasts[s]["ordinal"], forecasts[last]["ordinal"]
                consumed = [c for c in calls if beginning < c["ordinal"] <= end]
                recovered = {
                    "first_index": last - 2,
                    "confirmed_at": last,
                    "forecasts_since_first_informed": last - s,
                    "work_scope": "post-surprise observation, excluding first surprise forecast",
                    **work(consumed),
                    "including_first_forecast": work([forecasts[s], *consumed]),
                }
                break
        first = forecasts.get(s)
        result.append(
            {
                "switch": s,
                "first_informed_forecast": s + 1,
                "unavoidable_first_error": None
                if first is None
                else {
                    "position_error": first.get("position_error"),
                    "qualified": first.get("result", {}).get("qualified"),
                    "causal_oracle_error": first.get("causal_oracle_error"),
                },
                "windows": windows,
                "recovered": recovered,
            }
        )
    return result


def verify_call(c, expected, tape, before, admissions):
    kind, phase, index, indices = expected
    same(
        [c["kind"], c["phase"], c["index"], c["indices"]],
        expected,
        "causal call sequence",
    )
    rows = tape["test" if phase == "probe" else phase]
    same(c["row_ids"], [rows[i]["id"] for i in indices], "row ownership")
    require(c["before_brain_sha256"] == before, "broken state custody chain")
    require(math.isfinite(c["seconds"]) and c["seconds"] >= 0, "call elapsed time")
    if c["status"] != "returned":
        require(c["status"] in ("interrupted", "error"), "unknown call status")
        require(
            c.get("unknown_solver_work") is True and "result" not in c,
            "interrupted work must remain unknown",
        )
        require(
            c["after_brain_sha256"] == before, "failed call did not restore snapshot"
        )
        return before, admissions
    r = c["result"]
    qualified = r["qualified"]
    require(
        type(qualified) is bool and math.isfinite(r["stationarity"]),
        "qualification fields",
    )
    require(qualified == (r["stationarity"] <= 1e-6), "full stationarity qualification")
    require(
        all(type(v) is int and v >= 0 for v in r["work"].values()),
        "invalid returned work",
    )
    if kind == "forecast" or not qualified:
        require(c["after_brain_sha256"] == before, "query/refusal changed brain")
    if kind == "admission":
        require(
            r["accepted"] is qualified and r["source"] == "witness",
            "admission qualification/provenance",
        )
        require(r["event_id"] == admissions, "admission ID skipped or duplicated")
        if phase == "train":
            require(r["batch_size"] == 16, "batch exposure count")
            states, outputs = r["states"], r["outputs"]
        else:
            states, outputs = [r["state"]], [r["outputs"]]
        require(len(states) == len(outputs) == len(indices), "admission row count")
        for row_index, state, output in zip(indices, states, outputs, strict=True):
            row = rows[row_index]
            same(state[2:6], row["past"] + row["future"], "actual witness state clamps")
            same(
                output,
                {"past": row["past"], "future": row["future"]},
                "actual witness output clamps",
            )
        admissions += int(qualified)
    else:
        row = rows[index]
        same(r["outputs"]["past"], row["past"], "known past query clamp")
        same(r["state"][2:4], row["past"], "known past state clamp")
        same(r["outputs"]["future"], r["state"][4:6], "future is patch state")
        for axis, field in enumerate(("position_error", "displacement_error")):
            error = (
                abs(r["outputs"]["future"][axis] - row["future"][axis])
                if qualified
                else None
            )
            require(c[field] == error, "forecast error differs from actual outcome")
        require(
            c["causal_oracle_error"] == row["audit"]["causal_absolute_error"],
            "oracle error differs",
        )
        same(c["retrospective_error"], r["errors"][2:4], "residual readback receipt")
    return c["after_brain_sha256"], admissions


def verify_arm(out, arm, protocol, tape, founder):
    folder = out / arm
    if not folder.exists():
        return {"arm": arm, "status": "missing", "eligible": False}
    report = read(folder / "report.json") if (folder / "report.json").exists() else None
    raw = (
        (folder / "calls.jsonl").read_text()
        if (folder / "calls.jsonl").exists()
        else ""
    )
    calls, partial_line = [], False
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        try:
            calls.append(json.loads(line))
        except json.JSONDecodeError:
            require(
                report is None and i == len(lines) - 1, "malformed completed ledger"
            )
            partial_line = True
    sequence = expected_calls()
    require(len(calls) <= len(sequence), "excess calls")
    before, admissions = text_sha(founder), 0
    custody = {-1: (before, 0)}
    for i, c in enumerate(calls):
        require(c["ordinal"] == i, "ledger ordinal gap")
        require(i == len(calls) - 1 or c["status"] == "returned", "calls after failure")
        before, admissions = verify_call(c, sequence[i], tape, before, admissions)
        custody[i] = (before, admissions)
    inflight_path = folder / "inflight.json"
    unlogged_call = False
    if inflight_path.exists():
        inflight = read(inflight_path)
        ordinal = inflight["ordinal"]
        require(
            ordinal in (len(calls), len(calls) - 1) and 0 <= ordinal < len(sequence),
            "inflight ordinal",
        )
        kind, phase, index, indices = sequence[ordinal]
        same(
            [
                inflight["kind"],
                inflight["phase"],
                inflight["index"],
                inflight["indices"],
            ],
            [kind, phase, index, indices],
            "inflight causal order",
        )
        require(
            inflight["before_brain_sha256"] == custody[ordinal - 1][0],
            "inflight state custody",
        )
        unlogged_call = ordinal == len(calls)
    checkpoint_paths = sorted(folder.glob("checkpoint-*.json"))
    if (folder / "latest.json").exists():
        checkpoint_paths.append(folder / "latest.json")
    latest = None
    for path in checkpoint_paths:
        checkpoint = read(path)
        require(checkpoint["ordinal"] in custody, "checkpoint lacks matching ledger")
        expected_hash, expected_admissions = custody[checkpoint["ordinal"]]
        require(
            checkpoint["brain_sha256"]
            == text_sha(checkpoint["brain"])
            == expected_hash,
            "checkpoint state/hash mismatch",
        )
        brain = Brain.from_snapshot(checkpoint["brain"])
        require(
            brain.snapshot() == checkpoint["brain"],
            "checkpoint canonical reload differs",
        )
        require(
            checkpoint["admissions"]
            == brain.inspect()["admissions"]
            == expected_admissions,
            "checkpoint admission mismatch",
        )
        if path.name == "latest.json":
            latest = checkpoint
    gate = mae([c for c in calls if c["phase"] == "gate"])
    gate["passed"] = (
        gate["planned_or_observed"] == 16
        and gate["complete"]
        and gate["position_mae"] <= THRESHOLD
    )
    metrics, totals = recovery(calls), work(calls)
    if report is not None:
        require(
            report["arm"] == arm and report["seed"] == protocol["seed"],
            "arm report identity",
        )
        for field, path in (
            ("protocol_sha256", out / "protocol.json"),
            ("tape_sha256", out / "tape.json"),
            ("ledger_sha256", folder / "calls.jsonl"),
            ("latest_sha256", folder / "latest.json"),
        ):
            require(report[field] == sha(path), f"report {field}")
        require(report["sources_unchanged"] is True, "source changed during run")
        same(report["gate"], gate, "gate metric mismatch")
        same(report["recovery"], metrics, "recovery metric mismatch")
        recovery_indices = {i for s in SWITCHES for i in range(s + 1, s + 9)}
        groups = {
            "all": calls,
            "training": [c for c in calls if c["phase"] == "train"],
            "gate": [c for c in calls if c["phase"] == "gate"],
            "test_unavoidable": [
                c for c in calls if c["phase"] == "test" and c["index"] in SWITCHES
            ],
            "test_recovery_first8": [
                c
                for c in calls
                if c["phase"] == "test" and c["index"] in recovery_indices
            ],
            "test_stable_or_late": [
                c
                for c in calls
                if c["phase"] == "test"
                and c["index"] not in recovery_indices
                and c["index"] not in SWITCHES
            ],
            "before_admission_probes": [c for c in calls if c["phase"] == "probe"],
        }
        same(
            report["groups"],
            {k: work(v) for k, v in groups.items()},
            "work group mismatch",
        )
        indexed = {item["file"] for item in report["checkpoints"]}
        require(
            indexed == {p.name for p in checkpoint_paths if p.name != "latest.json"},
            "checkpoint inventory differs",
        )
        for item in report["checkpoints"]:
            require(
                item["sha256"] == sha(folder / item["file"]), "checkpoint file digest"
            )
            require(
                item["ordinal"] == read(folder / item["file"])["ordinal"],
                "checkpoint index ordinal",
            )
        require(
            latest is not None and latest["brain_sha256"] == before,
            "latest did not preserve accepted state",
        )
        status = report["status"]
        require(status in ("complete", "censored", "error"), "report status")
        if status == "complete":
            require(
                len(calls) == len(sequence) and totals["unknown_work_calls"] == 0,
                "incomplete ledger claimed complete",
            )
            require(
                not inflight_path.exists(),
                "complete arm retains unfinished bookkeeping",
            )
    else:
        status = "incomplete"
    return {
        "arm": arm,
        "status": status,
        "eligible": status == "complete" and gate["passed"] and totals["refusals"] == 0,
        "gate": gate,
        "work": totals,
        "recovery": metrics,
        "checkpoints_reloaded": len(checkpoint_paths),
        "partial_ledger_tail": partial_line,
        "inflight_present": inflight_path.exists(),
        "unlogged_call_work_unknown": unlogged_call,
    }


def verify_case(out):
    protocol = read(out / "protocol.json")
    seed = protocol["seed"]
    require(
        seed in SEEDS and protocol["schema"] == "cadence-self-correction/1",
        "protocol identity",
    )
    same(protocol["campaign_seeds"], SEEDS, "campaign seed selection")
    same(
        protocol["arm_order"],
        ARMS if SEEDS.index(seed) % 2 == 0 else ARMS[::-1],
        "arm order",
    )
    source_check(protocol)
    require(
        protocol["arm_seconds"] == 120 and protocol["process_seconds"] == 360,
        "resource ceilings differ",
    )
    same(
        protocol["test"],
        {
            "rows": 128,
            "switches": SWITCHES,
            "horizons": HORIZONS,
            "forecast_before_each_admission": True,
            "post_outcome_before_admission_probes": True,
        },
        "test contract differs",
    )
    same(
        protocol["training"],
        {
            "rows": 512,
            "batches": 32,
            "batch_size": 16,
            "forecast_every_row_before_its_batch_admission": True,
        },
        "training contract differs",
    )
    require(
        protocol["source"] == "witness"
        and protocol["gate"]["rows"] == 16
        and protocol["gate"]["position_mae_max"] == THRESHOLD
        and protocol["gate"]["requires_all_qualified"] is True
        and protocol["gate"]["learning"] is False,
        "gate/provenance contract differs",
    )
    tape = read(out / "tape.json")
    require(protocol["tape_sha256"] == sha(out / "tape.json"), "tape file digest")
    verify_tape(tape)
    schedule = {
        "train": [list(range(i, i + 16)) for i in range(0, 512, 16)],
        "gate": list(range(16)),
        "test": list(range(128)),
    }
    require(
        protocol["schedule_sha256"] == sha(out / "schedule.json"), "schedule digest"
    )
    same(read(out / "schedule.json"), schedule, "schedule differs")
    founders, brains = {}, {}
    for arm in ARMS:
        path = out / f"founder-{arm}.json"
        require(sha(path) == protocol["founders"][arm], "founder file digest")
        founders[arm] = path.read_text()
        brain = brains[arm] = Brain.from_snapshot(founders[arm])
        require(
            brain.snapshot()
            == founders[arm]
            == frozen.make_brain(seed, arm).snapshot(),
            "initialization differs from frozen seed",
        )
        require(
            brain.graph.n_inputs == 4
            and brain.graph.n_patches == 6
            and len(brain.weights) + len(brain.biases) == 34,
            "capacity differs",
        )
        same(dict(brain.config), protocol["config"], "configuration differs")
        same(brain.graph.edges, protocol["graphs"][arm], "graph differs")
    left, right = (
        dict(zip(brains[a].graph.edges, brains[a].weights, strict=True)) for a in ARMS
    )
    shared = left.keys() & right.keys()
    require(
        len(shared) == 24 and all(left[e] == right[e] for e in shared),
        "shared coefficients differ",
    )
    for src in range(2):
        for dst in (4, 5):
            require(
                left[("state", src, dst)] == right[("residual", src + 2, dst)],
                "replacement coefficient differs",
            )
    same(brains[ARMS[0]].biases, brains[ARMS[1]].biases, "bias matching")
    arms = [verify_arm(out, arm, protocol, tape, founders[arm]) for arm in ARMS]
    eligible = all(a["eligible"] for a in arms)
    if (out / "report.json").exists():
        report = read(out / "report.json")
        require(
            report["seed"] == seed and report["sources_unchanged"] is True,
            "case report identity",
        )
        require(
            report["protocol_sha256"] == sha(out / "protocol.json"),
            "case protocol digest",
        )
        require(
            report["verdict"]
            == ("comparison_eligible" if eligible else "inconclusive"),
            "case eligibility differs",
        )
        require(
            report["status"]
            == (
                "complete"
                if all(a["status"] == "complete" for a in arms)
                else "incomplete"
            ),
            "case status differs",
        )
        same(
            report["arms"],
            [read(out / a / "report.json") for a in protocol["arm_order"]],
            "embedded arm report differs",
        )
    process_censor = None
    if (out / "process-timeout.json").exists():
        process_censor = read(out / "process-timeout.json")
        require(
            process_censor["status"] == "censored" and process_censor["seconds"] == 360,
            "outer process censor receipt",
        )
        require(
            process_censor["protocol_sha256"] == sha(out / "protocol.json"),
            "outer process censor protocol",
        )
        eligible = False
    return {
        "seed": seed,
        "verification": "verified",
        "verdict": "comparison_eligible" if eligible else "inconclusive",
        "arms": arms,
        "process_censor": process_censor,
    }


def verify_campaign(root):
    by_seed = {}
    for path in sorted(root.rglob("protocol.json")):
        try:
            seed = read(path)["seed"]
        except (ValueError, KeyError):
            seed = "unreadable"
        by_seed.setdefault(seed, []).append(path.parent)
    cases = []
    for seed in SEEDS:
        paths = by_seed.get(seed, [])
        if not paths:
            cases.append(
                {"seed": seed, "verification": "missing", "verdict": "inconclusive"}
            )
            continue
        try:
            require(
                len(paths) == 1,
                "multiple runs for the same seed; do not select a survivor",
            )
            cases.append(verify_case(paths[0]))
        except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
            cases.append(
                {
                    "seed": seed,
                    "verification": "invalid",
                    "verdict": "inconclusive",
                    "reason": str(error),
                }
            )
    extras = [
        str(path)
        for seed, paths in by_seed.items()
        if seed not in SEEDS
        for path in paths
    ]
    return {
        "schema": "cadence-self-correction-verification/1",
        "cases": cases,
        "unexpected_cases": extras,
        "valid": not extras and not any(c["verification"] == "invalid" for c in cases),
        "verdict": "comparison_eligible"
        if all(c["verdict"] == "comparison_eligible" for c in cases) and not extras
        else "inconclusive",
        "limits": "Custody and metric verification, not replay of every numerical solve or an advantage claim; all five paired seeds retained.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = verify_campaign(args.root)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
