"""Measured differential-drive experience and shared model-based control.

The body alone receives wheel gain. Models see executed commands and measured
motion. Supplied controller coefficients are hand-set controls/candidate genes;
there is no evolution experiment or settled motor-policy claim in this app.

The Cadence arms run on the population solver of cadence-net 0.70.0. The
default brain couples its populations through live states. The optional
observer arm adds exact prediction-error readback inside the same settlement.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import time
from itertools import product
from pathlib import Path

from models import CADENCE_VERSION, make_model, model_from_snapshot
from checkpoint import validate_life_data

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
ACTIONS = [list(a) for a in product(PROTOCOL["action_levels"], repeat=2)]
LABELS = {"cadence": "Cadence · learning", "frozen": "Cadence · frozen",
          "adaptive": "Adaptive estimator", "mlp": "Small MLP",
          "observer": "Cadence · with observers"}
COLORS = {"cadence": "#8de0c6", "frozen": "#efae85", "adaptive": "#9bbdf3",
          "mlp": "#ccb0e9", "observer": "#90b6b4"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def source_hashes():
    from cadence.experimental import equilibrium
    paths = [(name, HERE / name) for name in ("models.py", "rover.py", "evaluate.py", "protocol.json", "checkpoint.py")]
    solver = Path(equilibrium.__file__).parent
    paths += [(f"cadence-net=={CADENCE_VERSION}/experimental/equilibrium/{p.name}", p)
              for p in sorted(solver.glob("*.py"))]
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths}


LOADED_SOURCES = source_hashes()


def require_current_sources():
    if source_hashes() != LOADED_SOURCES:
        raise ValueError("Rover sources changed while running; restart the application before saving evidence")


def clamp(value, low, high):
    return max(low, min(high, value))


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def body_motion(action, right_gain=1.0):
    left, right = action[0], right_gain * action[1]
    return [(left + right) / 2, (right - left) / 2]


def advance(pose, motion, dt=None):
    """Exact constant-wheel-speed integration in metres and radians."""
    dt = PROTOCOL["dt"] if dt is None else dt
    v = motion[0] * PROTOCOL["max_speed"]
    w = motion[1] * 2 * PROTOCOL["max_speed"] / PROTOCOL["wheel_base"]
    x, y, theta = pose
    turn = w * dt
    if abs(w) < 1e-10:
        x, y = x + v * dt * math.cos(theta), y + v * dt * math.sin(theta)
    else:
        x += v / w * (math.sin(theta + turn) - math.sin(theta))
        y -= v / w * (math.cos(theta + turn) - math.cos(theta))
    return [x, y, wrap(theta + turn)]


def select_action(pose, target, predictions):
    """A heading-aware inverse-dynamics controller shared by every model."""
    dx, dy = target[0] - pose[0], target[1] - pose[1]
    distance = math.hypot(dx, dy)
    angle = wrap(math.atan2(dy, dx) - pose[2])
    config = PROTOCOL["controller"]
    desired_v = max(config["minimum_speed"], config["forward_speed"] * min(1.0, distance)) * max(0.0, math.cos(angle))
    desired_w = clamp(config["heading_gain"] * angle, -2.8, 2.8)
    desired_turn = desired_w * PROTOCOL["wheel_base"] / (2 * PROTOCOL["max_speed"])
    scores = [(p[0] - desired_v) ** 2 + config["turn_weight"] * (p[1] - desired_turn) ** 2
              + 0.001 * (a[0] ** 2 + a[1] ** 2) for a, p in zip(ACTIONS, predictions)]
    return ACTIONS[min(range(len(scores)), key=scores.__getitem__)][:]


def route(seed, count=2048):
    rng = random.Random(seed + 91000)
    result = []
    for _ in range(count):
        radius, angle = rng.uniform(1.8, 2.7), rng.uniform(-0.85, 0.85)
        result.append([radius * math.cos(angle), radius * math.sin(angle)])
    return result


def empty_metrics():
    return {"steps": 0, "targets": 0, "attempts": 0, "distance_integral": 0.0,
            "squared_prediction_error": 0.0, "learning_presentations": 0,
            "latencies_ms": [], "command_ages_ms": [], "queue_delays_ms": [],
            "deadline_misses": 0}


def summarize(metrics):
    result = {}
    for phase, row in metrics.items():
        value = {k: v for k, v in row.items() if not isinstance(v, list)}
        steps = row["steps"]
        value["success_rate"] = row["targets"] / max(1, row["attempts"])
        value["prediction_rmse"] = math.sqrt(row["squared_prediction_error"] / max(1, steps))
        for key in ("latencies_ms", "command_ages_ms", "queue_delays_ms"):
            data = sorted(row[key])
            value[key.replace("_ms", "_p95_ms")] = data[min(len(data)-1, math.ceil(.95*len(data))-1)] if data else 0
        result[phase] = value
    return result


class Life:
    """One serial owner for all models, bodies, witnesses and counters."""
    def __init__(self, seed=17, weak_gain=None, observers=False, progress=None):
        self.seed = int(seed)
        self.weak_gain = PROTOCOL["weak_gain"] if weak_gain is None else float(weak_gain)
        if not .25 <= self.weak_gain <= .5:
            raise ValueError("Wheel strength must be between 0.25 and 0.50")
        self.step = 0
        self.phase = "normal"
        self.auto = True
        self.phase_start = 0
        self.targets = route(self.seed)
        self.events = []
        self.rows = []
        self.arms = {}
        self.bootstrap = {}
        self.observers = observers
        rng = random.Random(self.seed + 20000)
        experiences = [(a[:], body_motion(a)) for a in ACTIONS]
        # Only measured transitions teach: these commands were executed in the body.
        order = list(range(len(experiences)))
        schedule = []
        for _ in range(PROTOCOL["bootstrap_epochs"]):
            rng.shuffle(order)
            schedule.extend(order)
        self.bootstrap_witnesses = copy.deepcopy(experiences)
        self.bootstrap_schedule = schedule[:]
        kinds = ["cadence", "adaptive", "mlp"] + (["observer"] if observers else [])
        for index, kind in enumerate(kinds):
            if progress:
                progress(f"Bootstrapping {LABELS[kind]}")
            started = time.perf_counter()
            model = make_model("coupled" if kind == "cadence" else kind, self.seed)
            for witness in schedule:
                if not model.learn(*experiences[witness]):
                    raise RuntimeError(f"{kind} refused a bootstrap motion witness")
            predictions = model.query(ACTIONS)
            rmse = math.sqrt(sum(sum((p[j]-y[j])**2 for j in range(2))/2
                                 for p, (_, y) in zip(predictions, experiences)) / len(experiences))
            self.bootstrap[kind] = {"experiences": len(experiences), "presentations": len(schedule),
                                    "seconds": time.perf_counter()-started, "training_grid_rmse": rmse,
                                    "parameters": model.parameters()}
            self.arms[kind] = self._arm(kind, model)
        frozen = model_from_snapshot(self.arms["cadence"]["model"].snapshot())
        self.arms = {"cadence": self.arms["cadence"], "frozen": self._arm("frozen", frozen),
                     **{k: v for k, v in self.arms.items() if k != "cadence"}}
        self.bootstrap["frozen"] = dict(self.bootstrap["cadence"])
        self.initial_brain_digest = digest(frozen.snapshot())
        self.events.append({"step": 0, "text": "Identical Cadence checkpoint. Normal wheels. Shared target schedule."})

    def _arm(self, kind, model):
        return {"model": model, "pose": [0., 0., 0.], "target": self.targets[0][:],
                "trail": [[0., 0.]], "targets": 0, "attempts": 0, "reached": False,
                "prediction_error": 0., "error_history": [], "command": [0., 0.],
                "motion": [0., 0.], "latency_ms": 0., "deadline_misses": 0,
                "metrics": {}, "replay": [], "pending": None, "learning": kind != "frozen"}

    @property
    def wheel_gain(self):
        return self.weak_gain if self.phase == "weakened" else 1.0

    def change_phase(self, phase):
        if phase not in {"normal", "weakened", "restored_probe", "restored_learning"}:
            raise ValueError("Unknown phase")
        self.phase, self.phase_start = phase, self.step
        # Task resets pose at declared phase/episode boundaries; brains and replay persist.
        for arm in self.arms.values():
            arm["pose"], arm["trail"], arm["reached"] = [0., 0., 0.], [[0., 0.]], False
        labels = {"normal": "Normal wheels", "weakened": "Right wheel weakened; learners receive motion only",
                  "restored_probe": "Wheels restored; learning paused for immediate retention probe",
                  "restored_learning": "Original wheels; learning resumed"}
        self.events.append({"step": self.step, "text": labels[phase]})

    def _automatic_phase(self):
        if not self.auto:
            return
        boundary = 0
        for phase, length in PROTOCOL["phases"]:
            if self.step == boundary and self.phase != phase:
                self.change_phase(phase)
            boundary += length

    def tick(self, queue_delay_ms=0.):
        tick_started = time.perf_counter()
        self._automatic_phase()
        phase_step = self.step - self.phase_start
        episode_start = phase_step % PROTOCOL["episode_steps"] == 0
        target_index = (self.step // PROTOCOL["episode_steps"]) % len(self.targets)
        for kind, arm in self.arms.items():
            started = time.perf_counter()
            arm_queue_ms = queue_delay_ms + (started - tick_started)*1000
            model = arm["model"]
            metrics = arm["metrics"].setdefault(self.phase, empty_metrics())
            learning = kind != "frozen" and self.phase != "restored_probe"
            arm["learning"] = learning
            # Admit the last consequence before choosing the next command. This work
            # and replay are included in the sensing-to-command timer.
            presentations = 0
            if arm["pending"] is not None:
                action, motion, admitted_phase = arm["pending"]
                # A restoration probe may not learn even the transition before it.
                if learning and admitted_phase != "restored_probe":
                    if not model.learn(action, motion):
                        raise RuntimeError(f"{kind} refused an executed motion witness")
                    presentations += 1
                    if arm["replay"]:
                        replay = arm["replay"][(self.step * 7) % len(arm["replay"])]
                        if not model.learn(*replay):
                            raise RuntimeError(f"{kind} refused a replay witness")
                        presentations += 1
                arm["replay"].append([action[:], motion[:]])
                arm["replay"] = arm["replay"][-PROTOCOL["replay_window"]:]
            if episode_start:
                arm["pose"], arm["trail"], arm["reached"] = [0., 0., 0.], [[0., 0.]], False
                arm["target"] = self.targets[target_index][:]
                arm["attempts"] += 1
                metrics["attempts"] += 1
            before = arm["pose"][:]
            if arm["reached"]:
                action = [0., 0.]
            else:
                predictions = model.query(ACTIONS)
                action = select_action(before, arm["target"], predictions)
            predicted = model.activate(action)
            elapsed = (time.perf_counter()-started)*1000
            actual = body_motion(action, self.wheel_gain)
            after = advance(before, actual)
            distance = math.dist(after[:2], arm["target"])
            hit = not arm["reached"] and distance <= PROTOCOL["target_radius"]
            arm["reached"] |= hit
            arm["targets"] += int(hit)
            mse = sum((predicted[j]-actual[j])**2 for j in range(2))/2
            arm["prediction_error"] = math.sqrt(mse)
            arm["error_history"] = (arm["error_history"] + [math.sqrt(mse)])[-180:]
            arm["pose"], arm["command"], arm["motion"] = after, action, actual
            arm["trail"] = (arm["trail"] + [after[:2]])[-600:]
            arm["latency_ms"] = elapsed
            age = elapsed + arm_queue_ms
            missed = age > 1000 * PROTOCOL["dt"]
            arm["deadline_misses"] += int(missed)
            arm["pending"] = [action[:], actual[:], self.phase]
            metrics["steps"] += 1
            metrics["targets"] += int(hit)
            metrics["distance_integral"] += distance * PROTOCOL["dt"]
            metrics["squared_prediction_error"] += mse
            metrics["learning_presentations"] += presentations
            metrics["latencies_ms"].append(elapsed)
            metrics["command_ages_ms"].append(age)
            metrics["queue_delays_ms"].append(arm_queue_ms)
            metrics["deadline_misses"] += int(missed)
            self.rows.append({"step": self.step, "model": kind, "phase": self.phase, "phase_step": phase_step,
                              "before": before, "after": after, "target": arm["target"][:],
                              "action": action, "prediction": predicted, "motion": actual,
                              "right_gain": self.wheel_gain, "hit": hit, "episode_start": episode_start,
                              "learning": learning, "presentations": presentations,
                              "latency_ms": elapsed, "queue_delay_ms": arm_queue_ms,
                              "command_age_ms": age})
        self.step += 1

    def state(self):
        models = []
        for kind, arm in self.arms.items():
            item = {k: copy.deepcopy(v) for k, v in arm.items()
                    if k not in {"model", "metrics", "replay", "pending", "reached"}}
            item.update(id=kind, label=LABELS[kind], color=COLORS[kind],
                        activity=arm["model"].activity(), phase_metrics=summarize(arm["metrics"]))
            models.append(item)
        labels = {"normal": "Normal wheels", "weakened": "Right wheel weakened",
                  "restored_probe": "Restored · retention probe", "restored_learning": "Restored · relearning"}
        return {"ready": True, "error": None, "step": self.step, "sim_time": round(self.step*PROTOCOL["dt"], 2),
                "phase": self.phase, "phase_label": labels[self.phase], "wheel_gain": self.wheel_gain,
                "weak_gain": self.weak_gain, "seed": self.seed, "auto": self.auto,
                "engine": f"cadence-net {CADENCE_VERSION}, population solver, "
                          + ("state-coupled populations and an observer arm" if self.observers
                             else "state-coupled populations"),
                "models": models, "events": self.events[-12:], "protocol": PROTOCOL}

    def snapshot(self):
        require_current_sources()
        arms = {kind: {**copy.deepcopy({k: v for k, v in arm.items() if k != "model"}),
                       "model": arm["model"].snapshot()} for kind, arm in self.arms.items()}
        return {"schema": "rover-life-v2", "protocol_hash": digest(PROTOCOL), "sources": source_hashes(),
                **{k: copy.deepcopy(getattr(self, k)) for k in ("seed", "weak_gain", "step", "phase", "auto",
                   "phase_start", "targets", "events", "rows", "bootstrap", "bootstrap_witnesses", "bootstrap_schedule", "observers", "initial_brain_digest")},
                "arms": arms}

    @classmethod
    def from_snapshot(cls, data):
        require_current_sources()
        if data.get("schema") != "rover-life-v2" or data.get("protocol_hash") != digest(PROTOCOL):
            raise ValueError("Checkpoint schema or protocol differs from this demo")
        if data.get("sources") != source_hashes():
            raise ValueError("Checkpoint belongs to different rover source files")
        # JSON roundtrip rejects unsupported values and detaches caller-owned data.
        data = json.loads(json.dumps(data, allow_nan=False))
        validate_life_data(data)
        obj = cls.__new__(cls)
        for key in ("seed", "weak_gain", "step", "phase", "auto", "phase_start", "targets", "events", "rows",
                    "bootstrap", "bootstrap_witnesses", "bootstrap_schedule", "observers", "initial_brain_digest"):
            setattr(obj, key, data[key])
        # JSON member order has no meaning; execution order is part of the runtime.
        order = ("cadence", "frozen", "adaptive", "mlp", "observer")
        obj.arms = {key: data["arms"][key] for key in order if key in data["arms"]}
        if set(obj.arms) != ({"cadence", "frozen", "adaptive", "mlp", "observer"}
                            if obj.observers else {"cadence", "frozen", "adaptive", "mlp"}):
            raise ValueError("Checkpoint model set is incomplete")
        for arm in obj.arms.values():
            arm["model"] = model_from_snapshot(arm["model"])
        return obj

    def receipt(self):
        require_current_sources()
        metrics = {kind: summarize(arm["metrics"]) for kind, arm in self.arms.items()}
        return {"schema": "rover-evidence-v2", "cadence": CADENCE_VERSION, "seed": self.seed, "weak_gain": self.weak_gain,
                "steps": self.step, "auto": self.auto, "protocol": PROTOCOL, "protocol_hash": digest(PROTOCOL),
                "sources": source_hashes(), "bootstrap": self.bootstrap,
                "bootstrap_witnesses": self.bootstrap_witnesses, "bootstrap_schedule": self.bootstrap_schedule,
                "initial_brain_digest": self.initial_brain_digest,
                "metrics": metrics, "events": self.events, "transitions": self.rows,
                "transition_hash": digest(self.rows), "gate": demonstration_gate(metrics, auto=self.auto),
                "boundary": "Simulated odometry, learned dynamics, supplied heading controller. No superiority, retention, physical-robot or useful-observer claim."}


def demonstration_gate(metrics, *, auto=True):
    live, frozen = metrics.get("cadence", {}), metrics.get("frozen", {})
    required = {p for p, _ in PROTOCOL["phases"]}
    if not auto or not required.issubset(live) or not required.issubset(frozen) or any(
        arm.get(phase, {}).get("steps") != length
        for arm in metrics.values() for phase, length in PROTOCOL["phases"]
    ):
        return {"complete": False, "passed": False}
    spec = PROTOCOL["demonstration_gate"]
    weak, control = live["weakened"], frozen["weakened"]
    ratio = weak["distance_integral"] / max(1e-12, control["distance_integral"])
    checks = {"normal_targets": live["normal"]["success_rate"] >= spec["normal_success_rate_min"],
              "recovery_distance": ratio <= spec["weak_distance_integral_ratio_max"],
              "weak_targets": weak["success_rate"] >= spec["weak_success_rate_min"],
              "latency": all(v["command_ages_p95_ms"] <= spec["control_p95_ms_max"] for v in live.values()),
              "deadlines": sum(v["deadline_misses"] for v in live.values()) / max(1,sum(v["steps"] for v in live.values())) <= spec["deadline_miss_fraction_max"]}
    return {"complete": True, "passed": all(checks.values()), "checks": checks,
            "weak_distance_ratio": ratio, "scope": "Demonstration versus frozen Cadence only"}
