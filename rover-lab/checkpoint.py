"""Bounded validation of application state before constructing restored models."""

from __future__ import annotations

import json
import math
from pathlib import Path

PHASES = {"normal", "weakened", "restored_probe", "restored_learning"}
BASE_ARMS = {"cadence", "frozen", "adaptive", "mlp"}
COUNTS = {"steps", "targets", "attempts", "learning_presentations", "deadline_misses"}
TOTALS = {"distance_integral", "squared_prediction_error"}
TIMINGS = {"latencies_ms", "command_ages_ms", "queue_delays_ms"}
PROTOCOL = json.loads((Path(__file__).resolve().parent / "protocol.json").read_text())


def _require(condition, message):
    if not condition:
        raise ValueError(f"Invalid rover checkpoint: {message}")


def _fields(value, names, label):
    _require(isinstance(value, dict) and set(names) <= value.keys(), f"{label} fields")


def _number(value, label, low=None, high=None, *, integer=False):
    _require(type(value) is int if integer else type(value) in (int, float), label)
    _require(type(value) is int or math.isfinite(value), label)
    _require(low is None or value >= low, label)
    _require(high is None or value <= high, label)


def _vector(value, size, label, bound=None):
    _require(isinstance(value, list) and len(value) == size, label)
    for coordinate in value:
        _number(coordinate, label, -bound if bound is not None else None, bound)


def _witness(value, label, *, pending=False):
    _require(isinstance(value, list) and len(value) == (3 if pending else 2), label)
    _vector(value[0], 2, f"{label} action", 0.8)
    _vector(value[1], 2, f"{label} motion", 0.8)
    if pending:
        _require(isinstance(value[2], str) and value[2] in PHASES, f"{label} phase")


def validate_life_data(data):
    """Raise ValueError for malformed state; model/source identity is checked later."""
    try:
        json.dumps(data, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError("Invalid rover checkpoint: finite JSON data required") from error
    _fields(data, {"schema", "protocol_hash", "sources", "seed", "weak_gain", "step",
                  "phase", "auto", "phase_start", "targets", "events", "rows", "bootstrap",
                  "observers", "initial_brain_digest", "arms", "bootstrap_witnesses",
                  "bootstrap_schedule"}, "life")
    _require(data["schema"] == "rover-life-v2", "schema")
    _number(data["seed"], "seed", 0, integer=True)
    _number(data["weak_gain"], "wheel gain", 0.25, 0.5)
    _number(data["step"], "step", 0, 3600, integer=True)
    _number(data["phase_start"], "phase start", 0, data["step"], integer=True)
    _require(isinstance(data["phase"], str) and data["phase"] in PHASES, "phase")
    _require(type(data["auto"]) is bool and type(data["observers"]) is bool, "mode flags")
    arms = BASE_ARMS | ({"observer"} if data["observers"] else set())
    _require(isinstance(data["arms"], dict) and set(data["arms"]) == arms, "arm set")
    _require(isinstance(data["bootstrap"], dict) and set(data["bootstrap"]) == arms, "bootstrap set")
    witnesses = data["bootstrap_witnesses"]
    witness_count = PROTOCOL["bootstrap_experiences"]
    _require(isinstance(witnesses, list) and len(witnesses) == witness_count, "bootstrap witnesses")
    for witness in witnesses:
        _witness(witness, "bootstrap witness")
    schedule = data["bootstrap_schedule"]
    _require(isinstance(schedule, list) and len(schedule) == PROTOCOL["bootstrap_epochs"] * witness_count, "bootstrap schedule")
    for index in schedule:
        _number(index, "bootstrap schedule index", 0, witness_count - 1, integer=True)
    _require(isinstance(data["targets"], list) and len(data["targets"]) == 2048, "route length")
    for target in data["targets"]:
        _vector(target, 2, "route target")
    for key in ("protocol_hash", "initial_brain_digest"):
        value = data[key]
        _require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), key)
    _require(isinstance(data["sources"], dict) and bool(data["sources"]), "sources")
    for name, value in data["sources"].items():
        _require(isinstance(name, str) and isinstance(value, str) and len(value) == 64
                 and all(c in "0123456789abcdef" for c in value), "source digest")
    _require(isinstance(data["events"], list) and len(data["events"]) <= 10000, "events")
    for event in data["events"]:
        _fields(event, {"step", "text"}, "event")
        _number(event["step"], "event step", 0, data["step"], integer=True)
        _require(isinstance(event["text"], str) and len(event["text"]) <= 2000, "event text")
    for kind, arm in data["arms"].items():
        _fields(arm, {"model", "pose", "target", "trail", "targets", "attempts", "reached",
                      "prediction_error", "error_history", "command", "motion", "latency_ms",
                      "deadline_misses", "metrics", "replay", "pending", "learning"}, "arm")
        _require(isinstance(arm["model"], dict), "model state")
        expected_kind = "coupled" if kind in {"cadence", "frozen"} else kind
        _require(arm["model"].get("kind") == expected_kind, "model kind")
        _vector(arm["pose"], 3, "pose")
        _vector(arm["target"], 2, "target")
        _vector(arm["command"], 2, "command", 0.8)
        _vector(arm["motion"], 2, "motion", 0.8)
        _require(type(arm["reached"]) is bool and type(arm["learning"]) is bool, "arm flags")
        for key in ("prediction_error", "latency_ms"):
            _number(arm[key], key, 0)
        for key in ("targets", "attempts", "deadline_misses"):
            _number(arm[key], key, 0, data["step"], integer=True)
        _require(arm["targets"] <= arm["attempts"], "completed targets exceed attempts")
        _require(isinstance(arm["trail"], list) and 1 <= len(arm["trail"]) <= 600, "trail length")
        for point in arm["trail"]:
            _vector(point, 2, "trail point")
        _require(isinstance(arm["error_history"], list) and len(arm["error_history"]) <= 180, "error history")
        for error in arm["error_history"]:
            _number(error, "historical error", 0)
        _require(isinstance(arm["replay"], list) and len(arm["replay"]) <= 12, "replay length")
        for witness in arm["replay"]:
            _witness(witness, "replay")
        if arm["pending"] is not None:
            _witness(arm["pending"], "pending", pending=True)
        _require(isinstance(arm["metrics"], dict) and set(arm["metrics"]) <= PHASES, "metric phases")
        for metrics in arm["metrics"].values():
            _fields(metrics, COUNTS | TOTALS | TIMINGS, "metrics")
            for key in COUNTS:
                _number(metrics[key], key, 0, integer=True)
            for key in TOTALS:
                _number(metrics[key], key, 0)
            _require(metrics["targets"] <= metrics["attempts"] <= metrics["steps"] <= data["step"], "metric counts")
            _require(metrics["deadline_misses"] <= metrics["steps"] and metrics["learning_presentations"] <= 2 * metrics["steps"], "metric work")
            for key in TIMINGS:
                _require(isinstance(metrics[key], list) and len(metrics[key]) == metrics["steps"], "metric timing length")
                for duration in metrics[key]:
                    _number(duration, "timing", 0)
        for key in ("steps", "targets", "attempts", "deadline_misses"):
            expected = data["step"] if key == "steps" else arm[key]
            _require(sum(row[key] for row in arm["metrics"].values()) == expected, f"aggregate {key}")
        bootstrap = data["bootstrap"][kind]
        _fields(bootstrap, {"experiences", "presentations", "seconds", "training_grid_rmse", "parameters"}, "bootstrap")
        for key in ("experiences", "presentations", "parameters"):
            _number(bootstrap[key], key, 0, integer=True)
        for key in ("seconds", "training_grid_rmse"):
            _number(bootstrap[key], key, 0)
    _require(isinstance(data["rows"], list) and len(data["rows"]) == data["step"] * len(arms), "transition count")
    seen = set()
    for index, row in enumerate(data["rows"]):
        _fields(row, {"step", "model", "phase", "phase_step", "before", "after", "target", "action", "prediction",
                      "motion", "right_gain", "hit", "episode_start", "learning", "presentations",
                      "latency_ms", "queue_delay_ms", "command_age_ms"}, "transition")
        if index % len(arms) == 0:
            seen.clear()
        _require(type(row["step"]) is int and row["step"] == index // len(arms), "transition order")
        _number(row["phase_step"], "transition phase step", 0, row["step"], integer=True)
        _require(isinstance(row["model"], str) and row["model"] in arms - seen, "transition model")
        seen.add(row["model"])
        _require(isinstance(row["phase"], str) and row["phase"] in PHASES, "transition phase")
        for key, size in (("before", 3), ("after", 3), ("target", 2), ("prediction", 2)):
            _vector(row[key], size, key)
        for key in ("action", "motion"):
            _vector(row[key], 2, key, 0.8)
        for key in ("hit", "episode_start", "learning"):
            _require(type(row[key]) is bool, key)
        _number(row["presentations"], "presentations", 0, 2, integer=True)
        _number(row["right_gain"], "recorded gain", 0.25, 1.0)
        for key in ("latency_ms", "queue_delay_ms", "command_age_ms"):
            _number(row[key], key, 0)
