"""Supervised attractor acquisition through the unchanged PRIVATE repair kernel.

State cycles are unsupported by the public Cortex builder. This experiment
does not change that API and does not demonstrate residual-observer advantage.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import random
import signal
import time
import traceback
from collections import Counter
from pathlib import Path

import self_correction as custody
from cadence._repair import Graph, settle

import cadence

SEEDS = (149, 151, 157, 163, 167)
REGIMES = ((0.9, 0.6), (0.98, 0.6), (0.98, 0.8))
ARMS = ("cycle", "flat", "history")
DELAYS = (1, 8, 128)
CONFIG = {
    "state_prior": 0.01,
    "parameter_prior": 0.1,
    "tolerance": 1e-10,
    "budget": 2048,
    "state_bound": 1.0,
    "parameter_bound": 4.0,
    "step": 1.0,
    "backtracks": 32,
}
ARM_SECONDS, CAMPAIGN_SECONDS = 20, 180


def sources():
    package = Path(cadence.__file__).resolve().parent
    return {
        str(p.resolve()): custody.sha(p)
        for p in sorted(
            [*package.rglob("*.py"), Path(__file__), Path(custody.__file__)]
        )
    }


def graph(arm):
    second = (
        ("state", 0, 0)
        if arm == "cycle"
        else ("input", 2 if arm == "history" else 1, 0)
    )
    return Graph(3 if arm == "history" else 2, 1, (("input", 0, 0), second))


def initial(seed):
    rng = random.Random(seed)
    return [rng.uniform(-0.1, 0.1) for _ in range(3)]


def tape():
    rng = random.Random(20261010)
    batches = []
    for batch in range(64):
        signs = [-1, 1] * 4
        rng.shuffle(signs)
        rows = []
        for episode, sign in enumerate(signs):
            identity = f"batch{batch}:episode{episode}"
            rows.extend(
                (
                    {
                        "episode": identity,
                        "tick": 0,
                        "cue": sign,
                        "body_bit": sign,
                        "phase": "write",
                    },
                    {
                        "episode": identity,
                        "tick": 1,
                        "cue": 0,
                        "body_bit": sign,
                        "phase": "hold",
                    },
                )
            )
        batches.append(rows)
    return batches


def inputs(arm, cue, body_bit):
    raw = (float(cue), float(abs(cue)))
    return (*raw, float(body_bit)) if arm == "history" else raw


def scalar(u, x, cue_weight, gain, bias, alpha=0.01):
    p = math.tanh(cue_weight * u + gain * x + bias)
    e, d = x - p, 1 - p * p
    return {
        "prediction": p,
        "error": e,
        "energy": 0.5 * (e * e + alpha * x * x),
        "gradient": e * (1 - gain * d) + alpha * x,
        "hessian": (1 - gain * d) ** 2 + 2 * e * gain * gain * p * d + alpha,
    }


def threshold():
    """Exact stationarity quadratic, followed by a numerical saddle location."""
    alpha = CONFIG["state_prior"]

    def branch(t):
        p, d = math.tanh(t), 1 - math.tanh(t) ** 2
        a, b = p * d / t, d + p / t
        discriminant = b * b - 4 * a * (1 + alpha)
        if discriminant < 0:
            return math.inf
        g = 2 * (1 + alpha) / (b + math.sqrt(discriminant))
        return g if 0 < t / g <= 1 and g <= 4 else math.inf

    samples = [(branch(i / 1000), i / 1000) for i in range(1, 4001)]
    _, center = min(samples)
    left, right = center - 0.001, center + 0.001
    for _ in range(80):
        a, b = left + (right - left) / 3, right - (right - left) / 3
        if branch(a) < branch(b):
            right = b
        else:
            left = a
    t = (left + right) / 2
    gain, state = branch(t), t / branch(t)
    audit = scalar(0, state, 0, gain, 0)
    eps = 1e-5
    numerical_hessian = (
        scalar(0, state + eps, 0, gain, 0)["gradient"]
        - scalar(0, state - eps, 0, gain, 0)["gradient"]
    ) / (2 * eps)
    assert abs(audit["gradient"]) < 1e-10 and abs(audit["hessian"]) < 2e-7
    assert abs(audit["hessian"] - numerical_hessian) < 2e-8
    return {
        "derivation": "At u=b=0 set t=g*x, p=tanh(t), d=sech²(t). Dividing dE/dx by x gives (1+alpha)-g*(d+p/t)+g²*p*d/t. Nonzero stationary states lie on this exact quadratic. Numerically minimize its admissible lower-g branch, then verify original gradient/Hessian. This is a numerical saddle estimate, not an interval-certified bound or global-minimum proof.",
        "gain": gain,
        "state": state,
        "audit": audit,
        "finite_difference_hessian": numerical_hessian,
        "teacher_implications": [
            {
                "write_target": write,
                "hold_target": hold,
                "zero_error_gain": math.atanh(hold) / hold,
                "zero_error_cue_weight": math.atanh(write)
                - write * math.atanh(hold) / hold,
            }
            for write, hold in REGIMES
        ],
    }


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    custody.atomic(root / "tape.json", tape())
    custody.atomic(root / "founders.json", {str(s): initial(s) for s in SEEDS})
    custody.atomic(root / "threshold.json", threshold())
    custody.atomic(
        root / "protocol.json",
        {
            "schema": "learned-private-cycle/1",
            "sources": sources(),
            "seeds": SEEDS,
            "regimes": REGIMES,
            "arms": ARMS,
            "config": CONFIG,
            "tape_sha256": custody.sha(root / "tape.json"),
            "founders_sha256": custody.sha(root / "founders.json"),
            "threshold_sha256": custody.sha(root / "threshold.json"),
            "initialization": "All live states zero. All3 arms use identical small uniform[-.1,.1] paired arrays, including self/presence/history coefficient. No engineered recurrent gain.",
            "topology": "PRIVATE Graph only: cycle cue+selfstate+bias; flat cue+presence+bias; history cue+causal last-cue bit+bias. Each1patch/3parameters. Presence abs(cue) is visible raw information available in all arms; cycle can infer it from cue. History additionally stores/provides ONE external memory scalar; it is an information/custody positive control, not a matched internal-memory result. Flat retains native state too.",
            "training": "64 balanced16row batch admissions. Actual body episodes generate cue±1 thenblank and targets signed write/hold magnitude. Independent batch rows ALL start atzero, targets clamp private row states, only parameters commit. Batches carry NO temporal state or delayed credit. This intentionally tests whether supervised self-clamped attractor fitting transfers to subsequent FREE chronological memory. Teacher outputs never count as free acquisition.",
            "evaluation": "After learning, freeze parameters. Both cue signs start fromzero, freely write; delays1/8/128 each restart from that same qualified written state, then chronologically retain every qualified blank state. From128blank state freely apply opposite cue and128moreblanks. State-only zeroing is an explicit intervention while bodybit/history stay unchanged; separately full-reset bodybit/history/state tozero thenblank. No hidden teaching-state initialization or query clamp.",
            "gates": "Each arm must complete64 qualified parameter admissions and all planned free queries with frozen parameters. A usable memory bit requires signed response>=.25 for BOTH writes, all holds at1/8/128, opposite-cue overwrite and subsequent holds; cold/full-reset neutral abs(state)<=.05. Absolute target errors are separately reported; bit memory is not a claim of exact amplitude acquisition. Per regime all5 cycle arms and all5 history controls must pass, and every15arm run must complete/qualify; report flat controls and every failed seed. State-only erasure diagnostics are not task-success scores.",
            "limits": {
                "arm_seconds": ARM_SECONDS,
            "serial_campaign_start_window_seconds": CAMPAIGN_SECONDS,
            "campaign_cutoff": "Do not start an arm unless its full20-second allowance remains in the180-second start window. Final custody bookkeeping may finish after the window; actual elapsed time is reported. This is not an independently enforced outer hard deadline.",
                "arms": 45,
                "training_batches_per_arm": 64,
                "blank_delays": DELAYS,
                "expected_queries_per_arm": 539,
            },
            "scope": "Hypothesis for learned native-state cycles versus acyclic state retention. Not public-API support, residual-observer advantage, learned delayed credit or planning. Neutral zero has lower global energy; nonzero memory is metastability, not proof of the globally minimal equilibrium. Regimes .9/.6 and.98/.6 remain controls; .98/.8 was added BEFORE training from the scalar saddle analysis, not selected from successful outcomes.",
        },
    )


def validate(root):
    p = custody.read(root / "protocol.json")
    assert p["sources"] == sources()
    for key, name in (
        ("tape_sha256", "tape.json"),
        ("founders_sha256", "founders.json"),
        ("threshold_sha256", "threshold.json"),
    ):
        assert p[key] == custody.sha(root / name)
    return p


def bit_gate(records, complete):
    scored = [r for r in records if r["scored"]]
    bits = [r for r in scored if r["expected"] != 0]
    neutral = [r for r in scored if r["expected"] == 0]
    return (
        complete
        and len(records) == 539
        and bool(bits)
        and bool(neutral)
        and all(r["state"] * (1 if r["expected"] > 0 else -1) >= 0.25 for r in bits)
        and all(abs(r["state"]) <= 0.05 for r in neutral)
    )


def projected_stationarity(state, gradient):
    bound = CONFIG["state_bound"]
    return abs(state - max(-bound, min(bound, state - gradient)))


def run_arm(root, seed, regime, arm):
    write, hold = REGIMES[regime]
    out = root / f"regime{regime}-{arm}-seed{seed}"
    out.mkdir(exist_ok=False)
    parameters = custody.read(root / "founders.json")[str(seed)]
    weights, biases, state = tuple(parameters[:2]), (parameters[2],), (0.0,)
    initial_parameters = (*weights, *biases)
    g = graph(arm)
    started, calls, accepted = time.monotonic(), 0, 0
    work, records = Counter(), []
    status, failure, unknown = "complete", None, False
    trained = None

    def snapshot():
        return {
            "graph": dataclasses.asdict(g),
            "config": CONFIG,
            "weights": weights,
            "biases": biases,
            "state": state,
            "admissions": accepted,
            "source_identity_sha256": source_digest,
        }

    sources_identity = custody.read(root / "protocol.json")["sources"]
    source_digest = custody.digest(custody.encoded(sources_identity))

    def journal(record):
        with (out / "calls.jsonl").open("a") as stream:
            stream.write(custody.encoded(record) + "\n")

    def alarm(*_):
        raise TimeoutError("arm deadline")

    old_alarm = signal.signal(signal.SIGALRM, alarm)

    def call(values, *, identity, clamps=None, batch_size=1, learn=False):
        nonlocal weights, biases, state, accepted, calls, unknown
        before = snapshot()
        initial_state = (0.0,) * batch_size if learn else state
        intent = {
            "identity": identity,
            "learn": learn,
            "inputs": values,
            "source": "witness" if learn else "free-query",
            "initial_state": initial_state,
            "clamps": clamps or {},
            "batch_size": batch_size,
            "before": before,
            "status": "started",
        }
        custody.atomic(out / "current-call.json", intent)
        remaining = ARM_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            custody.atomic(
                out / "current-call.json", {**intent, "status": "not_started_deadline"}
            )
            raise TimeoutError("deadline before solve")
        tick = time.perf_counter()
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            result = settle(
                g,
                values,
                initial_state,
                weights,
                biases,
                clamps=clamps,
                learn=learn,
                _batch_size=batch_size,
                **CONFIG,
            )
        except Exception as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            unknown = True
            custody.atomic(
                out / "current-call.json",
                {
                    **intent,
                    "status": "interrupted",
                    "unknown_work": True,
                    "seconds": time.perf_counter() - tick,
                    "error": repr(exc),
                    "restored": snapshot(),
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        calls += 1
        work.update(result["work"])
        if result["qualified"]:
            if learn:
                weights, biases = tuple(result["weights"]), tuple(result["biases"])
                accepted += 1
            else:
                state = tuple(result["state"])
        retained = snapshot()
        record = {
            **intent,
            "status": "returned",
            "seconds": time.perf_counter() - tick,
            "result": {k: v for k, v in result.items() if k != "energy_history"},
            "energy_history_sha256": custody.digest(
                custody.encoded(result["energy_history"])
            ),
            "energy_history_length": len(result["energy_history"]),
            "retained_sha256": custody.digest(custody.encoded(retained)),
        }
        journal(record)
        custody.atomic(out / "current-call.json", record)
        custody.atomic(out / "last-completed.json", retained)
        if not result["qualified"]:
            assert retained == before
            raise RuntimeError(f"Unqualified {identity}: {result['reason']}")
        if learn:
            assert state == before["state"]
        else:
            assert weights == before["weights"] and biases == before["biases"]
            x = state[0]
            if arm == "cycle":
                audit = scalar(values[0], x, *weights, biases[0])
            else:
                feature = values[2] if arm == "history" else values[1]
                p = math.tanh(weights[0] * values[0] + weights[1] * feature + biases[0])
                audit = {
                    "prediction": p,
                    "error": x - p,
                    "energy": 0.5 * ((x - p) ** 2 + CONFIG["state_prior"] * x * x),
                    "gradient": x - p + CONFIG["state_prior"] * x,
                }
            assert (
                projected_stationarity(x, audit["gradient"])
                <= CONFIG["tolerance"] * 1.0001
            )
            assert abs(audit["energy"] - result["energy"]) < 1e-13
        return result

    def reset(value, identity):
        nonlocal state
        journal(
            {
                "identity": identity,
                "state_intervention": True,
                "from": state,
                "to": [value],
            }
        )
        state = (value,)

    def query(cue, bit, identity, expected, scored=True):
        result = call(inputs(arm, cue, bit), identity=identity)
        record = {
            "identity": identity,
            "cue": cue,
            "body_bit": bit,
            "state": result["state"][0],
            "expected": expected,
            "absolute_error": abs(result["state"][0] - expected),
            "scored": scored,
            "qualified": result["qualified"],
            "work": result["work"],
        }
        records.append(record)
        return result["state"][0]

    try:
        for event, rows in enumerate(custody.read(root / "tape.json")):
            values = tuple(
                v for r in rows for v in inputs(arm, r["cue"], r["body_bit"])
            )
            clamps = {
                i: r["body_bit"] * (write if r["phase"] == "write" else hold)
                for i, r in enumerate(rows)
            }
            call(
                values,
                identity=f"batch{event}",
                clamps=clamps,
                batch_size=16,
                learn=True,
            )
        trained = snapshot()
        custody.atomic(out / "trained.json", trained)
        query(0, 0, "cold-neutral", 0)
        for sign in (-1, 1):
            reset(0, f"fresh-trial:{sign}")
            written = query(sign, sign, f"write:{sign}", sign * write)
            held = None
            for delay in DELAYS:
                reset(written, f"fork-qualified-write:{sign}:delay{delay}")
                for step in range(1, delay + 1):
                    held = query(0, sign, f"hold:{sign}:{delay}:{step}", sign * hold)
            reset(held, f"overwrite-start:{sign}")
            query(-sign, -sign, f"overwrite:{sign}", -sign * write)
            for step in range(1, 129):
                query(0, -sign, f"overwritten-hold:{sign}:{step}", -sign * hold)
            reset(0, f"state-only-erasure:{sign}")
            query(
                0,
                -sign,
                f"erased-state-history-retained:{sign}",
                -sign * hold,
                scored=False,
            )
            reset(0, f"full-body-history-state-reset:{sign}")
            query(0, 0, f"full-reset-neutral:{sign}", 0)
        assert (*weights, *biases) == (*trained["weights"], *trained["biases"])
    except TimeoutError as exc:
        status, failure = "timeout", str(exc)
    except Exception:  # noqa: BLE001 - Preserve every failed arm.
        status, failure = "error", traceback.format_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        custody.atomic(out / "last-completed.json", snapshot())
        custody.atomic(out / "queries.json", records)
        scored = [r for r in records if r["scored"]]
        complete = (
            status == "complete"
            and accepted == 64
            and len(records) == 539
            and not unknown
        )
        bits = [r for r in scored if r["expected"] != 0]
        passed = bit_gate(records, complete)
        unchanged = sources() == sources_identity
        journal_path = out / "calls.jsonl"
        journal_manifest = (
            {"bytes": journal_path.stat().st_size, "sha256": custody.sha(journal_path)}
            if journal_path.exists()
            else None
        )
        if time.monotonic() - started > ARM_SECONDS:
            status, failure, complete, passed = (
                "timeout",
                failure or "deadline during bookkeeping",
                False,
                False,
            )
        if not unchanged:
            status, failure, complete, passed = "error", "Source drift", False, False
        report = {
            "seed": seed,
            "regime": regime,
            "arm": arm,
            "status": status,
            "failure": failure,
            "complete": complete,
            "bit_memory_gate": passed,
            "accepted_admissions": accepted,
            "returned_calls": calls,
            "queries": len(records),
            "unknown_work": unknown,
            "seconds": time.monotonic() - started,
            "work": dict(work),
            "initial_parameters": initial_parameters,
            "trained_parameters": [*trained["weights"], *trained["biases"]]
            if trained
            else None,
            "free_target_mae": sum(r["absolute_error"] for r in scored) / len(scored)
            if scored
            else None,
            "minimum_signed_response": min(
                (r["state"] * (1 if r["expected"] > 0 else -1) for r in bits),
                default=None,
            ),
            "erasure_diagnostics": [r for r in records if not r["scored"]],
            "sources_unchanged": unchanged,
            "journal": journal_manifest,
            "final_snapshot_sha256": custody.digest(custody.encoded(snapshot())),
        }
        custody.atomic(out / "result.json", report)
    return report


def run(root):
    validate(root)
    if (root / "execution.json").exists():
        raise ValueError("Preserve the prior campaign")
    started = time.monotonic()
    reports = []
    for seed in SEEDS:
        for regime in range(len(REGIMES)):
            for arm in ARMS:
                if CAMPAIGN_SECONDS - (time.monotonic() - started) < ARM_SECONDS:
                    reports.append(
                        {
                            "seed": seed,
                            "regime": regime,
                            "arm": arm,
                            "status": "not_started_deadline",
                            "complete": False,
                            "bit_memory_gate": False,
                        }
                    )
                else:
                    reports.append(run_arm(root, seed, regime, arm))
                custody.atomic(root / "execution.json", reports)
    conclusions = []
    for regime in range(len(REGIMES)):
        cases = [r for r in reports if r["regime"] == regime]
        eligible = len(cases) == 15 and all(r["complete"] for r in cases)
        conclusions.append(
            {
                "regime": regime,
                "eligible": eligible,
                "cycle_and_history_all_five_pass": eligible
                and all(r["bit_memory_gate"] for r in cases if r["arm"] != "flat"),
                "by_arm_pass_counts": {
                    arm: sum(r["bit_memory_gate"] for r in cases if r["arm"] == arm)
                    for arm in ARMS
                },
            }
        )
    custody.atomic(
        root / "summary.json",
        {
            "planned_arms": 45,
            "outcomes": reports,
            "conclusions": conclusions,
            "seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    (freeze if args.command == "freeze" else run)(args.root.resolve())
