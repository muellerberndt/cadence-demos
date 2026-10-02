"""Independently recompute rover evidence from executed transition witnesses.

This verifier deliberately imports neither rover.py nor models.py. It checks
the logged forecasts against their later physical consequences; a receipt is
an integrity/recomputation record, not cryptographic proof of when code ran.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from itertools import product
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
REQUIRED_ARMS = {"cadence", "frozen", "adaptive", "mlp"}
OPTIONAL_ARMS = {"observer"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, name, *, minimum=None):
    _require(type(value) in (int, float) and math.isfinite(value), f"{name} is not finite numeric data")
    _require(minimum is None or value >= minimum, f"{name} is below {minimum}")
    return value


def _counter(value, name):
    _require(type(value) is int and value >= 0, f"{name} is not a nonnegative integer")
    return value


def _vector(value, size, name):
    _require(isinstance(value, list) and len(value) == size, f"{name} has wrong dimension")
    return [_number(item, name) for item in value]


def _equal(actual, expected, context):
    if isinstance(expected, dict):
        _require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"{context}: fields differ")
        for key in expected:
            _equal(actual[key], expected[key], f"{context}.{key}")
    elif isinstance(expected, (list, tuple)):
        _require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), f"{context}: length differs")
        for index, value in enumerate(expected):
            _equal(actual[index], value, f"{context}[{index}]")
    elif type(expected) is bool:
        _require(type(actual) is bool and actual == expected, f"{context}: boolean differs")
    elif type(expected) in (int, float):
        _number(actual, context)
        _require(math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10),
                 f"{context}: {actual!r} != {expected!r}")
    else:
        _require(actual == expected, f"{context}: value differs")


def integrate(pose, action, right_gain, protocol=PROTOCOL):
    """Integrate the two wheel distances with an independent midpoint/sinc form."""
    dt, speed, width = protocol["dt"], protocol["max_speed"], protocol["wheel_base"]
    left_distance, right_distance = action[0] * speed * dt, action[1] * right_gain * speed * dt
    travelled = (left_distance + right_distance) / 2
    rotation = (right_distance - left_distance) / width
    half_rotation = rotation / 2
    chord_factor = math.sin(half_rotation) / half_rotation if half_rotation else 1.0
    heading = pose[2] + half_rotation
    after = [pose[0] + travelled * chord_factor * math.cos(heading),
             pose[1] + travelled * chord_factor * math.sin(heading),
             (pose[2] + rotation + math.pi) % (2 * math.pi) - math.pi]
    motion = [(action[0] + action[1] * right_gain) / 2,
              (action[1] * right_gain - action[0]) / 2]
    return after, motion


def _phase_at(step):
    boundary = 0
    for phase, budget in PROTOCOL["phases"]:
        if step < boundary + budget:
            return phase, step - boundary
        boundary += budget
    # Live mode can continue the last phase. Such a run is outside the gate.
    return PROTOCOL["phases"][-1][0], step - boundary + PROTOCOL["phases"][-1][1]


def _targets(seed, count):
    rng = random.Random(seed + 91000)
    targets = []
    for _ in range(count):
        radius = rng.uniform(1.8, 2.7)
        angle = rng.uniform(-0.85, 0.85)
        targets.append([radius * math.cos(angle), radius * math.sin(angle)])
    return targets


def _blank():
    return {"steps": 0, "targets": 0, "attempts": 0, "distance_integral": 0.0,
            "squared_prediction_error": 0.0, "learning_presentations": 0,
            "latencies_ms": [], "command_ages_ms": [], "queue_delays_ms": [],
            "deadline_misses": 0}


def _summaries(raw):
    result = {}
    for kind, phases in raw.items():
        result[kind] = {}
        for phase, row in phases.items():
            item = {key: value for key, value in row.items() if not isinstance(value, list)}
            item["success_rate"] = row["targets"] / max(1, row["attempts"])
            item["prediction_rmse"] = math.sqrt(row["squared_prediction_error"] / max(1, row["steps"]))
            for field in ("latencies_ms", "command_ages_ms", "queue_delays_ms"):
                values = sorted(row[field])
                item[field.replace("_ms", "_p95_ms")] = values[math.ceil(.95 * len(values)) - 1] if values else 0
            result[kind][phase] = item
    return result


def _gate(metrics, automatic):
    budgets = dict(PROTOCOL["phases"])
    complete = automatic and all(set(phases) == set(budgets) and all(
        phases[phase]["steps"] == budget for phase, budget in budgets.items()) for phases in metrics.values())
    if not complete:
        return {"complete": False, "passed": False}
    live, frozen = metrics["cadence"], metrics["frozen"]
    spec = PROTOCOL["demonstration_gate"]
    ratio = live["weakened"]["distance_integral"] / max(1e-12, frozen["weakened"]["distance_integral"])
    checks = {
        "normal_targets": live["normal"]["success_rate"] >= spec["normal_success_rate_min"],
        "recovery_distance": ratio <= spec["weak_distance_integral_ratio_max"],
        "weak_targets": live["weakened"]["success_rate"] >= spec["weak_success_rate_min"],
        "latency": all(row["command_ages_p95_ms"] <= spec["control_p95_ms_max"] for row in live.values()),
        "deadlines": sum(row["deadline_misses"] for row in live.values()) / max(
            1, sum(row["steps"] for row in live.values())) <= spec["deadline_miss_fraction_max"],
    }
    return {"complete": True, "passed": all(checks.values()), "checks": checks,
            "weak_distance_ratio": ratio, "scope": "Demonstration versus frozen Cadence only"}


def verify(receipt):
    """Return recomputed metrics/gate, raising ValueError on inconsistent evidence."""
    try:
        return _verify(receipt)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError(f"Malformed rover receipt: {error}") from error


def _verify(receipt):
    _require(isinstance(receipt, dict) and receipt.get("schema") == "rover-evidence-v2", "Unknown receipt schema")
    _require(receipt["protocol"] == PROTOCOL and receipt["protocol_hash"] == digest(PROTOCOL), "Protocol differs from declared protocol")
    rows = receipt["transitions"]
    _require(isinstance(rows, list) and receipt["transition_hash"] == digest(rows), "Transition hash mismatch")
    steps = _counter(receipt["steps"], "steps")
    seed = _counter(receipt["seed"], "seed")
    gain = _number(receipt["weak_gain"], "weak_gain")
    _require(PROTOCOL["declared_gain_range"][0] <= gain <= PROTOCOL["declared_gain_range"][1], "Wheel gain outside declared range")
    automatic = receipt.get("auto", True)
    _require(type(automatic) is bool, "auto must be boolean")
    kinds = set(receipt["metrics"])
    _require(kinds in (REQUIRED_ARMS, REQUIRED_ARMS | OPTIONAL_ARMS), "Incomplete or unknown comparison arms")
    _require(len(rows) == steps * len(kinds), "Missing or duplicate transitions")
    _require(set(receipt["bootstrap"]) == kinds, "Bootstrap arm set differs")
    witnesses = receipt["bootstrap_witnesses"]
    actions = [list(action) for action in product(PROTOCOL["action_levels"], repeat=2)]
    _require(isinstance(witnesses, list) and len(witnesses) == len(actions), "Missing bootstrap witnesses")
    for index, (witness, action) in enumerate(zip(witnesses, actions)):
        _require(isinstance(witness, (list, tuple)) and len(witness) == 2, "Malformed bootstrap witness")
        _equal(witness[0], action, f"bootstrap action {index}")
        _, motion = integrate([0., 0., 0.], action, 1.)
        _equal(witness[1], motion, f"bootstrap measured motion {index}")
    rng = random.Random(seed + 20000)
    order, schedule = list(range(len(actions))), []
    for _ in range(PROTOCOL["bootstrap_epochs"]):
        rng.shuffle(order)
        schedule.extend(order)
    _equal(receipt["bootstrap_schedule"], schedule, "shared bootstrap schedule")
    for kind, bootstrap in receipt["bootstrap"].items():
        _equal(bootstrap["experiences"], PROTOCOL["bootstrap_experiences"], f"{kind} bootstrap experiences")
        _equal(bootstrap["presentations"], PROTOCOL["bootstrap_experiences"] * PROTOCOL["bootstrap_epochs"], f"{kind} bootstrap budget")
        _number(bootstrap["seconds"], f"{kind} bootstrap time", minimum=0)
        _number(bootstrap["training_grid_rmse"], f"{kind} bootstrap error", minimum=0)
        _counter(bootstrap["parameters"], f"{kind} parameter count")
    _require(isinstance(receipt["sources"], dict) and bool(receipt["sources"]), "Missing implementation pins")
    for name, value in {**receipt["sources"], "initial_brain": receipt["initial_brain_digest"]}.items():
        _require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), f"Invalid digest: {name}")
    raw = {kind: {} for kind in kinds}
    states = {kind: {"after": [0., 0., 0.], "target": None, "reached": False,
                     "phase": None, "phase_step": -1} for kind in kinds}
    targets = _targets(seed, 2048)
    order = []
    last_global_phase_step = None
    last_global_phase = None
    for step in range(steps):
        batch = rows[step * len(kinds):(step + 1) * len(kinds)]
        _require({row["model"] for row in batch} == kinds, f"Step {step}: missing or duplicate arms")
        this_order = [row["model"] for row in batch]
        if not order:
            order = this_order
        _require(this_order == order, f"Step {step}: arm execution order changed")
        expected_phase, expected_phase_step = _phase_at(step)
        if not automatic:
            expected_phase = batch[0]["phase"]
            expected_phase_step = batch[0].get("phase_step", 0 if expected_phase != last_global_phase else last_global_phase_step + 1)
        _require(expected_phase in dict(PROTOCOL["phases"]), f"Step {step}: unknown phase")
        _counter(expected_phase_step, "phase_step")
        if not automatic and last_global_phase_step is not None and expected_phase_step:
            _require(expected_phase == last_global_phase and expected_phase_step == last_global_phase_step + 1,
                     f"Step {step}: undeclared phase/reset discontinuity")
        episode_start = expected_phase_step % PROTOCOL["episode_steps"] == 0
        boundary = expected_phase_step == 0
        expected_gain = gain if expected_phase == "weakened" else 1.0
        if not automatic and expected_phase == "weakened":
            expected_gain = _number(batch[0]["right_gain"], "manual wheel gain")
            _require(PROTOCOL["declared_gain_range"][0] <= expected_gain <= PROTOCOL["declared_gain_range"][1],
                     f"Step {step}: manual wheel gain outside declared range")
        for row in batch:
            kind = row["model"]
            context = f"step {step}/{kind}"
            _counter(row["step"], context + " step")
            _equal(row["step"], step, context + " step")
            _equal(row["phase"], expected_phase, context + " phase")
            if "phase_step" in row:
                _counter(row["phase_step"], context + " phase_step")
                _equal(row["phase_step"], expected_phase_step, context + " phase_step")
            _equal(row["right_gain"], expected_gain, context + " wheel gain")
            _equal(row["episode_start"], episode_start, context + " episode start")
            state = states[kind]
            before = _vector(row["before"], 3, context + " before")
            after = _vector(row["after"], 3, context + " after")
            action = _vector(row["action"], 2, context + " action")
            prediction = _vector(row["prediction"], 2, context + " prediction")
            _require(all(value in PROTOCOL["action_levels"] for value in action), context + ": command outside action grid")
            if episode_start or boundary:
                state["reached"] = False
                expected_before = [0., 0., 0.]
            else:
                expected_before = state["after"]
            if episode_start:
                state["target"] = targets[(step // PROTOCOL["episode_steps"]) % len(targets)]
            _equal(before, expected_before, context + " continuity")
            _equal(row["target"], state["target"], context + " target schedule")
            if state["reached"]:
                _equal(action, [0., 0.], context + " reached target must stop")
            expected_after, motion = integrate(before, action, expected_gain)
            _equal(after, expected_after, context + " physical pose")
            _equal(row["motion"], motion, context + " measured motion")
            distance = math.hypot(after[0] - state["target"][0], after[1] - state["target"][1])
            hit = not state["reached"] and distance <= PROTOCOL["target_radius"]
            _equal(row["hit"], hit, context + " hit")
            learning = kind != "frozen" and expected_phase != "restored_probe"
            _equal(row["learning"], learning, context + " learning flag")
            presentations = (1 + int(step > 1)) if learning and step and state["phase"] != "restored_probe" else 0
            _counter(row["presentations"], context + " presentations")
            _equal(row["presentations"], presentations, context + " admitted experience budget")
            latency = _number(row["latency_ms"], context + " latency", minimum=0)
            queue = _number(row["queue_delay_ms"], context + " queue", minimum=0)
            age = _number(row["command_age_ms"], context + " age", minimum=0)
            _equal(age, latency + queue, context + " complete command age")
            record = raw[kind].setdefault(expected_phase, _blank())
            record["steps"] += 1
            record["targets"] += int(hit)
            record["attempts"] += int(episode_start)
            record["distance_integral"] += distance * PROTOCOL["dt"]
            record["squared_prediction_error"] += sum((predicted - actual)**2 for predicted, actual in zip(prediction, motion)) / 2
            record["learning_presentations"] += presentations
            record["latencies_ms"].append(latency)
            record["command_ages_ms"].append(age)
            record["queue_delays_ms"].append(queue)
            record["deadline_misses"] += int(age > PROTOCOL["dt"] * 1000)
            state.update(after=after, reached=state["reached"] or hit, phase=expected_phase,
                         phase_step=expected_phase_step)
        last_global_phase, last_global_phase_step = expected_phase, expected_phase_step
    metrics = _summaries(raw)
    _equal(receipt["metrics"], metrics, "metrics")
    gate = _gate(metrics, automatic)
    _equal(receipt["gate"], gate, "demonstration gate")
    return {"verified": True, "steps": steps, "arms": len(kinds), "transitions": len(rows),
            "protocol_hash": receipt["protocol_hash"], "transition_hash": receipt["transition_hash"],
            "metrics": metrics, "gate": gate,
            "boundary": "Recomputed witness integrity, physics, error, targets, timing and gate. No authenticity or superiority claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Evidence receipt files (default: evidence/*.json)")
    arguments = parser.parse_args()
    paths = arguments.paths or sorted((HERE / "evidence").glob("*.json"))
    results = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
            metadata = path.name in {"freeze.json", "summary.json", "verification.json"}
            verification_output = isinstance(data, list) and data and all(
                isinstance(item, dict) and "verified" in item for item in data)
            if metadata or verification_output:
                continue
            result = verify(data)
            if "freeze_hash" in data:
                freeze_path = path.with_name("freeze.json")
                freeze = json.loads(freeze_path.read_text())
                _equal(data["freeze_hash"], digest(freeze), "freeze digest")
                for field in ("protocol", "protocol_hash", "sources", "steps"):
                    _equal(data[field], freeze[field], f"frozen {field}")
                _require(data["seed"] in freeze["seeds"], "Receipt seed was not scheduled")
                _require(result["arms"] == (5 if freeze["observers"] else 4), "Comparison arms differ from freeze")
                archive = path.parent / "source"
                if archive.is_dir():
                    for name, expected_hash in freeze["sources"].items():
                        source = (archive / name).resolve()
                        _require(source.is_relative_to(archive.resolve()), "Unsafe source archive path")
                        _equal(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash,
                               f"archived source {name}")
                    result["source_archive_verified"] = len(freeze["sources"])
            results.append({"file": str(path), **{key: value for key, value in result.items() if key != "metrics"}})
        except (OSError, ValueError, KeyError, TypeError) as error:
            results.append({"file": str(path), "verified": False, "error": str(error)})
    if not results:
        parser.error("No rover evidence receipts found")
    print(json.dumps(results, indent=2, allow_nan=False))
    return 0 if all(result["verified"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
