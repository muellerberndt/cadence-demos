"""Independent delayed-outcome custody/metric verifier; pure queries, never training.

Run against the original AWS journals with the frozen src on PYTHONPATH.
All thirty planned arms and all censors survive in the compact receipt. Learning
updates are checked for custody/provenance, not numerically replayed.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import delayed_bandit as frozen
import verify_self_correction as common

from cadence import Brain

PIN = "a1da082e54360985eac14250c57bc0457f69b763e71c172eb9c639ba38a97ebc"
SEEDS = (41, 43, 47, 53, 59)
ARMS = ("ordinary", "observer")
DELAYS = (0, 2, 4)
LABELS = ("clean-gate", "policy-before", "clean-retention", "policy-final")
require, same, read, sha = common.require, common.same, common.read, common.sha


def stripped(value):
    """Only declared body ticks and wall timings may differ across delays."""
    ignored = {"issued_tick", "executed_tick", "due_tick", "outcome_tick", "seconds"}
    if isinstance(value, dict):
        return {k: stripped(v) for k, v in value.items() if k not in ignored}
    if isinstance(value, list):
        return [stripped(v) for v in value]
    return value


def fingerprint(value):
    return common.text_sha(json.dumps(stripped(value), sort_keys=True))


def source_and_artifacts(root):
    protocol = read(root / "protocol.json")
    require(sha(Path(frozen.__file__)) == PIN, "reviewed collector source differs")
    identities = dict(protocol["sources"])
    names = [p for p in identities if Path(p).name == "delayed_bandit.py"]
    require(len(names) == 1 and identities.pop(names[0]) == PIN, "collector pin")
    common.source_check({"sources": identities})
    for key, expected in (
        ("seeds", SEEDS),
        ("arms", ARMS),
        ("delays", DELAYS),
        ("updates", {"clean": 64, "mixed": 128}),
    ):
        same(protocol[key], expected, f"protocol {key}")
    require(
        protocol["data_seed"] == 20261005
        and protocol["batch_size"] == 16
        and protocol["parameters"] == 14
        and protocol["patches"] == 4,
        "frozen design",
    )
    same(
        protocol["compute"],
        {
            "arm_seconds": 60,
            "outer_seconds": 65,
            "max_workers": 15,
            "backend": "python",
            "dtype": "float64",
        },
        "compute",
    )
    for name in ("data", "founders"):
        require(sha(root / f"{name}.json") == protocol[f"{name}_sha256"], f"{name} pin")
    data, founders = read(root / "data.json"), read(root / "founders.json")
    same(data, frozen.tape(), "deterministic tape")
    require(set(founders) == {str(s) for s in SEEDS}, "founder inventory")
    signatures = {}
    for phase, count in (
        ("clean", 1024),
        ("mixed", 2048),
        ("clean_test", 64),
        ("policy_test", 128),
    ):
        require(len(data[phase]) == count, "tape count")
        signatures[phase] = set()
        for i, row in enumerate(data[phase]):
            require(row["id"] == f"{phase}:{i}", "row identity")
            require(
                abs(row["u"]) <= 0.8
                and abs(row["v"]) <= (0.08 if phase == "policy_test" else 0.4),
                "input range",
            )
            require(
                row["delta"] == 0
                if phase.startswith("clean")
                else 0.03 <= abs(row["delta"]) <= 0.12,
                "offset range",
            )
            require(
                row["executed_action"] is None
                if phase == "policy_test"
                else row["executed_action"] == i % 2,
                "body action tape",
            )
            signatures[phase].add((row["u"], row["v"]))
        if phase.endswith("test"):
            require(
                not signatures[phase] & (signatures["clean"] | signatures["mixed"]),
                "heldout overlap",
            )
    for seed in SEEDS:
        same(founders[str(seed)], frozen.founders(seed), "matched founder")
        models = [Brain.from_snapshot(founders[str(seed)][a]) for a in ARMS]
        require(
            models[0].weights == models[1].weights
            and models[0].biases == models[1].biases,
            "initial coefficient matching",
        )
        for a, model in zip(ARMS, models, strict=True):
            require(
                model.snapshot() == founders[str(seed)][a]
                and len(model.weights) + len(model.biases) == 14,
                "founder reload/capacity",
            )
    return protocol, data, founders


def call_plan(data):
    plan, decision = [], 0
    for phase, count, offset in (("clean", 64, 0), ("mixed", 128, 64)):
        for update in range(count):
            event = offset + update
            ids = []
            for row in data[phase][update * 16 : (update + 1) * 16]:
                decision += 1
                ids.append(decision)
                plan.append(
                    {
                        "kind": "forecast",
                        "check": "training",
                        "row": row["id"],
                        "event_id": event,
                    }
                )
            plan.append(
                {
                    "kind": "admission",
                    "phase": phase,
                    "update": update + 1,
                    "event_id": event,
                    "decisions": ids,
                }
            )
            plan.append(
                {
                    "kind": "post-update-forecast",
                    "decision_id": ids[0],
                    "event_id": event,
                }
            )
        for label, key in (
            ("clean-gate" if phase == "clean" else "clean-retention", "clean_test"),
            ("policy-before" if phase == "clean" else "policy-final", "policy_test"),
        ):
            for row in data[key]:
                decision += 1
                plan.append(
                    {
                        "kind": "forecast",
                        "check": label,
                        "row": row["id"],
                        "event_id": None,
                    }
                )
    return plan


def journal(path, completed):
    records, partial = [], False
    if not path.exists():
        return records, partial
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except ValueError:
            require(
                not completed and i == len(lines) - 1, "malformed completed journal"
            )
            partial = True
    return records, partial


def qualification(call):
    value = call["stationarity"]
    require(
        type(call["qualified"]) is bool
        and math.isfinite(value)
        and value >= 0
        and call["qualified"] == (value <= 1e-6),
        "qualification",
    )
    require(
        all(type(v) is int and v >= 0 for v in call["work"].values()), "work counters"
    )
    require(math.isfinite(call["seconds"]) and call["seconds"] >= 0, "elapsed")


def check_outcome(decision, execution, outcome, row, call, index, delay):
    """Independent context, executed action, original forecast and due-time checks."""
    base = {
        "decision_id",
        "row",
        "inputs",
        "actual_x",
        "original_forecasts",
        "model_id",
        "event_id",
        "issued_tick",
        "proposed_action",
    }
    require(set(decision) == base, "future outcome leaked into proposal")
    require(
        decision["decision_id"] == index + 1
        and decision["row"] == row["id"]
        and decision["event_id"] == call["event_id"]
        and decision["model_id"] == call["before_sha256"],
        "decision ownership",
    )
    same(decision["inputs"], {"u": [row["u"]], "v": [row["v"]]}, "context boundary")
    require(
        decision["actual_x"] == math.tanh(math.tanh(row["u"])) + row["delta"],
        "actual past",
    )
    forecasts = decision["original_forecasts"]
    require(
        len(forecasts) == 2 and all(math.isfinite(v) for v in forecasts),
        "original forecasts",
    )
    require(
        decision["proposed_action"] == int(forecasts[1] > forecasts[0])
        and decision["issued_tick"] == index * (delay + 1),
        "proposal/time",
    )
    if execution is None:
        require(outcome is None, "outcome without execution")
        return
    require(
        set(execution) == base | {"executed_action", "executed_tick", "due_tick"},
        "execution boundary",
    )
    same(
        {k: execution[k] for k in base}, decision, "execution changed original proposal"
    )
    action = (
        decision["proposed_action"]
        if call["check"].startswith("policy")
        else row["executed_action"]
    )
    require(
        type(execution["executed_action"]) is int
        and execution["executed_action"] == action,
        "actual action",
    )
    require(
        execution["executed_tick"] == decision["issued_tick"]
        and execution["due_tick"] == execution["executed_tick"] + delay,
        "execution due tick",
    )
    if outcome is None:
        return
    require(
        set(outcome)
        == set(execution) | {"outcome_tick", "reward", "original_surprise"},
        "outcome boundary",
    )
    same({k: outcome[k] for k in execution}, execution, "outcome changed ownership")
    reward = (2 * action - 1) * math.tanh(row["v"] + row["delta"])
    require(outcome["outcome_tick"] == execution["due_tick"], "premature/late outcome")
    require(
        outcome["reward"] == reward
        and outcome["original_surprise"] == reward - forecasts[action],
        "original outcome surprise",
    )


def groups(evaluations):
    result = []
    for label in LABELS:
        rows = [r for r in evaluations if r["check"] == label]
        expected = 64 if label.startswith("clean") else 128
        means = {
            f: sum(r[f] for r in rows) / len(rows) if rows else None
            for f in (
                "past_absolute_error",
                "prediction_absolute_error",
                "reward",
                "oracle_regret",
            )
        }
        head = []
        for action in (0, 1):
            subset = [r for r in rows if r["executed_action"] == action]
            head.append(
                sum(r["prediction_absolute_error"] for r in subset) / len(subset)
                if subset
                else None
            )
        gate = (
            (
                len(rows) == expected
                and means["past_absolute_error"] <= 0.03
                and all(v is not None and v <= 0.03 for v in head)
            )
            if label.startswith("clean")
            else None
        )
        result.append(
            {
                "check": label,
                "expected": expected,
                "completed": len(rows),
                "means": means,
                "executed_head_mae": head,
                "clean_gate": gate,
            }
        )
    return result


def witnesses(outcomes):
    return [
        (
            r["inputs"],
            {
                "past": [r["actual_x"]],
                ("q_minus", "q_plus")[r["executed_action"]]: [r["reward"]],
            },
        )
        for r in outcomes
    ]


def verify_arm(root, seed, arm, delay, data, founder, execution, replay=True):
    folder = root / f"{arm}-seed{seed}-delay{delay}"
    if not folder.exists():
        return {
            "seed": seed,
            "arm": arm,
            "delay": delay,
            "status": "missing",
            "eligible": False,
        }, {}
    report = read(folder / "result.json") if (folder / "result.json").exists() else None
    logs, tails = {}, {}
    for name in ("calls", "decisions", "executions", "outcomes", "surprise"):
        logs[name], tails[name] = journal(folder / f"{name}.jsonl", report is not None)
    calls, decisions, executions, outcomes = (
        logs[n] for n in ("calls", "decisions", "executions", "outcomes")
    )
    updates = (
        read(folder / "updates.json") if (folder / "updates.json").exists() else []
    )
    evals = (
        read(folder / "evaluations.json")
        if (folder / "evaluations.json").exists()
        else []
    )
    current = (
        read(folder / "current-call.json")
        if (folder / "current-call.json").exists()
        else None
    )
    plan, lookup = call_plan(data), {r["id"]: r for rows in data.values() for r in rows}
    require(len(calls) <= len(plan), "extra calls")
    before, work, accepted = common.text_sha(founder), Counter(), 0
    custody = {before: 0}
    for i, call in enumerate(calls):
        same({k: call[k] for k in plan[i]}, plan[i], "causal call order")
        require(
            call["status"] == "returned" and call["before_sha256"] == before,
            "call custody",
        )
        qualification(call)
        work.update(call["work"])
        if call["kind"] != "admission" or not call["accepted"]:
            require(call["after_sha256"] == before, "query/refusal mutated brain")
        if call["kind"] == "admission":
            require(call["accepted"] is call["qualified"], "accepted qualification")
            accepted += call["accepted"]
        elif call["accepted"] is not None:
            require(False, "query claimed admission")
        if not call["qualified"]:
            require(i == len(calls) - 1, "continued after refusal")
        before = call["after_sha256"]
        custody[before] = accepted
    unknown = False
    if current:
        if current["status"] == "returned":
            require(bool(calls), "current returned without call")
            same(current, calls[-1], "current receipt")
        else:
            require(len(calls) < len(plan), "pending after full plan")
            same(
                {k: current[k] for k in plan[len(calls)]},
                plan[len(calls)],
                "pending intent",
            )
            require(current["before_sha256"] == before, "pending state")
            require(
                current["status"] in ("started", "interrupted", "not_started_deadline"),
                "pending status",
            )
            unknown = current["status"] in ("started", "interrupted")
            if current["status"] == "interrupted":
                require(
                    current["unknown_work"] is True
                    and current["restored_sha256"] == before,
                    "rollback",
                )
    forecasts = [c for c in calls if c["kind"] == "forecast"]
    require(
        len(outcomes) <= len(executions) <= len(decisions) <= len(forecasts),
        "episode cardinalities",
    )
    require(len(decisions) - len(outcomes) <= 1, "single flight violated")
    for i, decision in enumerate(decisions):
        call = forecasts[i]
        require(call["qualified"], "unqualified decision")
        check_outcome(
            decision,
            executions[i] if i < len(executions) else None,
            outcomes[i] if i < len(outcomes) else None,
            lookup[call["row"]],
            call,
            i,
            delay,
        )
    if report:
        pending = read(folder / "pending.json")
        expected_pending = (
            None
            if len(outcomes) == len(decisions)
            else executions[-1]
            if len(executions) == len(decisions)
            else decisions[-1]
        )
        same(pending, expected_pending, "pending ownership receipt")
    by_id = {r["decision_id"]: r for r in outcomes}
    admissions = [c for c in calls if c["kind"] == "admission"]
    require(len(updates) <= len(admissions), "update details without call")
    for i, call in enumerate(admissions):
        require(
            all(d in by_id for d in call["decisions"]),
            "admission before actual outcomes",
        )
        receipts = [by_id[d] for d in call["decisions"]]
        require(
            all(r["event_id"] == call["event_id"] for r in receipts),
            "witness event ownership",
        )
        if i < len(updates):
            u = updates[i]
            for field in (
                "phase",
                "update",
                "event_id",
                "accepted",
                "qualified",
                "stationarity",
                "after_sha256",
            ):
                same(u[field], call[field], f"update {field}")
            require(
                u["source"] == "witness" and u["batch_size"] == 16,
                "actual witness admission",
            )
            require(
                u["witness_sha256"]
                == frozen.custody.digest(frozen.custody.encoded(witnesses(receipts))),
                "executed-only targets",
            )
    post = [c for c in calls if c["kind"] == "post-update-forecast"]
    require(len(logs["surprise"]) <= len(post), "surprise without query")
    for r, call in zip(logs["surprise"], post):
        outcome = by_id[call["decision_id"]]
        require(
            r["decision_id"] == outcome["decision_id"]
            and r["original_surprise"] == outcome["original_surprise"]
            and r["current_model_id"] == call["before_sha256"],
            "immutable historical surprise",
        )
        require(
            math.isfinite(r["post_update_prediction_error"])
            and len(r["current_internal_errors"]) == 4,
            "post-update diagnostic",
        )
    expected_evals = [c for c in forecasts if c["check"] != "training"]
    require(len(evals) <= len(expected_evals), "extra evaluations")
    decision_by_call = {
        (c["check"], c["row"]): decisions[i]
        for i, c in enumerate(forecasts)
        if i < len(decisions)
    }
    for q, call in zip(evals, expected_evals):
        require(
            (q["check"], q["row"]) == (call["check"], call["row"]), "evaluation prefix"
        )
        d = decision_by_call[(q["check"], q["row"])]
        r, row = by_id[d["decision_id"]], lookup[q["row"]]
        require(
            q["decision_id"] == d["decision_id"] and q["qualified"] is True,
            "evaluation decision",
        )
        require(
            len(q["state"]) == len(q["errors"]) == len(q["predictions"]) == 4,
            "evaluation dimensions",
        )
        same(q["state"][2:4], d["original_forecasts"], "original free heads")
        for field, value in (
            ("executed_action", r["executed_action"]),
            ("reward", r["reward"]),
            ("past_absolute_error", abs(q["state"][1] - r["actual_x"])),
            ("prediction_absolute_error", abs(r["original_surprise"])),
            ("oracle_regret", abs(math.tanh(row["v"] + row["delta"])) - r["reward"]),
            (
                "offset_sign",
                0 if row["delta"] == 0 else (1 if row["delta"] > 0 else -1),
            ),
        ):
            require(q[field] == value, f"evaluation {field}")
        if q["check"].startswith("policy"):
            require(q["state"][1] == r["actual_x"], "actual P clamp")
    summary = groups(evals)
    replayed, reloaded, replay_work = 0, 0, Counter()
    for phase, labels, count in (("clean", LABELS[:2], 64), ("mixed", LABELS[2:], 192)):
        path = folder / f"checkpoint-{phase}.json"
        selected = [q for q in evals if q["check"] in labels]
        if not path.exists():
            require(not selected, "query checkpoint missing")
            continue
        snapshot = path.read_text()
        digest = common.text_sha(snapshot)
        model = Brain.from_snapshot(snapshot)
        require(
            model.snapshot() == snapshot
            and custody.get(digest) == count
            and model.inspect()["admissions"] == count,
            "checkpoint custody",
        )
        reloaded += 1
        for q in selected:
            call = next(
                c
                for c in expected_evals
                if c["check"] == q["check"] and c["row"] == q["row"]
            )
            require(call["before_sha256"] == digest, "checkpoint query identity")
            if replay:
                row = lookup[q["row"]]
                inputs = {"u": [row["u"]], "v": [row["v"]]}
                targets = (
                    {"past": [math.tanh(math.tanh(row["u"])) + row["delta"]]}
                    if q["check"].startswith("policy")
                    else None
                )
                result = model.settle(inputs, targets=targets)
                require(model.snapshot() == snapshot, "pure replay mutated checkpoint")
                for field in ("state", "errors", "predictions", "qualified"):
                    same(result[field], q[field], f"replayed {field}")
                for field in ("stationarity", "reason", "work", "sweeps", "qualified"):
                    same(result[field], call[field], f"replayed call {field}")
                replay_work.update(result["work"])
                replayed += 1
    latest = folder / "last-completed.json"
    require(not report or latest.exists(), "reported arm missing latest checkpoint")
    if latest.exists():
        snapshot = read(latest)
        model = Brain.from_snapshot(snapshot)
        digest = common.text_sha(snapshot)
        require(
            model.snapshot() == snapshot
            and digest in custody
            and model.inspect()["admissions"] == custody[digest],
            "latest custody/reload",
        )
        if report:
            require(
                digest == before == report["checkpoint_sha256"], "final retained state"
            )
        reloaded += 1
    status = report["status"] if report else "incomplete"
    require(
        status in ("complete", "acquisition_failed", "timeout", "error", "incomplete"),
        "status",
    )
    primary = (
        status == "complete"
        and accepted == 192
        and summary[0]["clean_gate"]
        and summary[2]["clean_gate"]
        and summary[3]["completed"] == 128
        and summary[3]["means"]["prediction_absolute_error"] <= 0.03
    )
    if report:
        require(
            report["seed"] == seed
            and report["arm"] == arm
            and report["delay"] == delay,
            "report identity",
        )
        require(
            report["sources_unchanged"] is True
            and report["protocol_sha256"] == sha(root / "protocol.json"),
            "source/protocol receipt",
        )
        same(report["groups"], summary, "metric/gate promotion")
        require(
            report["primary_learning_gate"] is bool(primary), "learning gate promotion"
        )
        require(
            report["issued_decisions"] == len(decisions)
            and report["completed_updates"] == len(updates)
            and report["accepted_updates"] == sum(u["accepted"] for u in updates)
            and report["planned_updates"] == 192,
            "reported counts",
        )
        for name, pin in report["journals"].items():
            require(
                (folder / name).stat().st_size == pin["bytes"]
                and sha(folder / name) == pin["sha256"],
                "journal pin",
            )
        require(
            set(report["journals"]) == {p.name for p in folder.glob("*.jsonl")},
            "journal inventory",
        )
        interrupted_admission = bool(
            current
            and current["kind"] == "admission"
            and current["status"] == "interrupted"
        )
        same(
            report["admission_counts"],
            {
                "started": len(admissions) + interrupted_admission,
                "returned": len(admissions),
                "accepted": accepted,
                "refused": len(admissions) - accepted,
                "interrupted_unknown_work": int(interrupted_admission),
            },
            "admission counters",
        )
        if len(outcomes) == len(decisions):
            require(
                report["body_ticks"] == len(outcomes) * (delay + 1), "body tick count"
            )
        if status == "complete":
            require(
                len(calls) == 3840
                and len(evals) == 384
                and len(updates) == 192
                and len(outcomes) == len(executions) == len(decisions) == 3456
                and len(logs["surprise"]) == 192
                and not unknown
                and accepted == 192,
                "incomplete claimed complete",
            )
            require(report["seconds"] <= 60, "complete over deadline")
        if status == "acquisition_failed":
            require(
                len(updates) == 64
                and summary[0]["completed"] == 64
                and summary[0]["clean_gate"] is False
                and len(evals) == 64,
                "acquisition failure cutoff",
            )
    if execution and execution["status"] == "returned" and execution["code"] == 0:
        require(
            status in ("complete", "acquisition_failed"),
            "successful process without result",
        )
    eligible = (
        status == "complete"
        and bool(execution)
        and execution["status"] == "returned"
        and execution["code"] == 0
        and accepted == 192
        and all(c["qualified"] for c in calls)
        and summary[0]["clean_gate"]
        and summary[2]["clean_gate"]
    )
    trace = {
        name: [fingerprint(r) for r in rows]
        for name, rows in {**logs, "updates": updates, "evaluations": evals}.items()
    }
    return {
        "seed": seed,
        "arm": arm,
        "delay": delay,
        "status": status,
        "eligible": bool(eligible),
        "primary_learning_gate": bool(primary),
        "execution": execution,
        "returned_calls": len(calls),
        "admitted_batches": accepted,
        "outcomes": len(outcomes),
        "refusals": sum(not c["qualified"] for c in calls),
        "unknown_inflight_work": unknown,
        "partial_journal_tails": tails,
        "missing_details": {
            "decisions": len(forecasts) - len(decisions),
            "outcomes": len(decisions) - len(outcomes),
            "updates": len(admissions) - len(updates),
            "evaluations": len(expected_evals) - len(evals),
            "surprise": len(post) - len(logs["surprise"]),
        },
        "groups": summary,
        "returned_work": dict(work),
        "admission_work": dict(
            sum((Counter(c["work"]) for c in admissions), Counter())
        ),
        "replayed_queries": replayed,
        "checkpoints_reloaded": reloaded,
        "replay_work": dict(replay_work),
        "trace_sha256": {name: fingerprint(rows) for name, rows in trace.items()},
    }, trace


def delay_control(cases, traces):
    result = []
    for seed in SEEDS:
        for arm in ARMS:
            rows = [c for c in cases if c["seed"] == seed and c["arm"] == arm]
            exact = all(c["status"] in ("complete", "acquisition_failed") for c in rows)
            for name in (
                "calls",
                "decisions",
                "executions",
                "outcomes",
                "surprise",
                "updates",
                "evaluations",
            ):
                lists = [traces[(seed, arm, d)].get(name, []) for d in DELAYS]
                n = min(map(len, lists))
                require(
                    all(xs[:n] == lists[0][:n] for xs in lists),
                    f"delay changed {name} prefix",
                )
                if exact:
                    require(
                        all(xs == lists[0] for xs in lists),
                        f"delay changed full {name}",
                    )
            result.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "identical_complete_trace": exact,
                    "common_prefix_identical": True,
                    "statuses": {str(c["delay"]): c["status"] for c in rows},
                }
            )
    return result


def comparison(cases):
    pairs = []
    for seed in SEEDS:
        arms = {c["arm"]: c for c in cases if c["seed"] == seed and c["delay"] == 0}
        values = {}
        for arm in ARMS:
            final = next(
                (
                    g
                    for g in arms[arm].get("groups", [])
                    if g["check"] == "policy-final"
                ),
                None,
            )
            values[arm] = (
                final["means"] if final and final["completed"] == 128 else None
            )
        gain = (
            values["ordinary"]["oracle_regret"] - values["observer"]["oracle_regret"]
            if all(values.values())
            else None
        )
        pairs.append(
            {
                "seed": seed,
                "eligible": all(c["eligible"] for c in arms.values()),
                "final": values,
                "ordinary_minus_observer_regret": gain,
            }
        )
    eligible = len(pairs) == 5 and all(p["eligible"] for p in pairs)
    gains = [p["ordinary_minus_observer_regret"] for p in pairs]
    mean = sum(gains) / 5 if all(v is not None for v in gains) else None
    passed = eligible and mean >= 0.005 and all(v > 0 for v in gains)
    return {
        "pairs": pairs,
        "eligible": eligible,
        "independent_init_seeds": 5,
        "delay_repeats_are_not_extra_seeds": True,
        "mean_regret_reduction": mean,
        "criterion_met": bool(passed),
        "efficiency_claim": False,
    }


def verify(root, replay=True):
    started = time.monotonic()
    _, data, founders = source_and_artifacts(root)
    jobs = [(s, a, d) for s in SEEDS for a in ARMS for d in DELAYS]
    launch = read(root / "launch.json")
    same(
        launch,
        {"jobs": jobs, "max_workers": 15, "outer_seconds": 65},
        "launch inventory",
    )
    executions = read(root / "execution.json")
    same([r["job"] for r in executions], jobs, "all thirty process outcomes")
    cases, traces = [], {}
    for job, execution in zip(jobs, executions, strict=True):
        seed, arm, delay = job
        require(
            execution["status"] in ("returned", "outer_timeout"), "execution status"
        )
        result, trace = verify_arm(
            root, seed, arm, delay, data, founders[str(seed)][arm], execution, replay
        )
        cases.append(result)
        traces[job] = trace
    return {
        "valid": True,
        "protocol_sha256": sha(root / "protocol.json"),
        "verifier_sha256": sha(Path(__file__)),
        "helper_sha256": sha(Path(common.__file__)),
        "collector_sha256": PIN,
        "pure_replay_enabled": replay,
        "cases": cases,
        "delay_control": delay_control(cases, traces),
        "secondary_comparison": comparison(cases),
        "totals": {
            "planned_arms": 30,
            "statuses": dict(Counter(c["status"] for c in cases)),
            **{
                k: sum(c.get(k, 0) for c in cases)
                for k in (
                    "returned_calls",
                    "admitted_batches",
                    "replayed_queries",
                    "checkpoints_reloaded",
                )
            },
        },
        "limits": "Numerical learning not replayed. Training forecasts/post-update diagnostics without saved per-admission snapshots are checked for ownership, arithmetic and delay identity, not rerun. Neutral delay is collector memory, not learned temporal credit. Five model seeds share one environment tape.",
        "seconds": time.monotonic() - started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger-only", action="store_true")
    args = parser.parse_args()
    result = verify(args.root.resolve(), not args.ledger_only)
    with args.out.open("x") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "valid": result["valid"],
                "totals": result["totals"],
                "secondary_eligible": result["secondary_comparison"]["eligible"],
                "criterion_met": result["secondary_comparison"]["criterion_met"],
                "seconds": result["seconds"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
