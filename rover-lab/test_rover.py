"""Bounded simulator, learning-boundary, persistence and receipt regressions."""
from __future__ import annotations

import copy
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

import models
import rover
from verify import digest, integrate, verify


@pytest.fixture(scope="module")
def prepared():
    # One actual bootstrap is shared; each test restores an independent whole life.
    return rover.Life(seed=17).snapshot()


@pytest.fixture
def life(prepared):
    return rover.Life.from_snapshot(json.loads(json.dumps(prepared)))


def _parameters(model):
    value = model.snapshot()
    if "brain" in value:
        brain = json.loads(value["brain"]) if isinstance(value["brain"], str) else value["brain"]
        return brain["weights"], brain["biases"], value["accepted"], value["presentations"]
    return {key: value[key] for key in ("arrays", "first_moments", "second_moments", "coefficients",
                                      "covariance", "steps", "accepted", "presentations") if key in value}


WALL_FIELDS = {"seconds", "latency_ms", "latencies_ms", "command_age_ms", "command_ages_ms",
               "queue_delay_ms", "queue_delays_ms", "deadline_misses"}


def _without_wall_time(value):
    if isinstance(value, dict):
        return {key: _without_wall_time(item) for key, item in value.items() if key not in WALL_FIELDS}
    if isinstance(value, list):
        return [_without_wall_time(item) for item in value]
    return value


@pytest.mark.parametrize("pose,action,gain", [
    ([0., 0., 0.], [.8, .8], 1.),
    ([1., -2., .4], [-.8, .8], 1.),
    ([0., 0., 0.], [.8, .8], .35),
    ([1., 1., 3.13], [-.4, .8], .5),
    ([1., 2., -.7], [0., 0.], .25),
])
def test_physics_against_independent_wheel_distance_integrator(pose, action, gain):
    expected, motion = integrate(pose, action, gain)
    assert rover.body_motion(action, gain) == pytest.approx(motion)
    assert rover.advance(pose, rover.body_motion(action, gain)) == pytest.approx(expected, abs=1e-12)


def test_weak_right_wheel_veers_clockwise():
    after = rover.advance([0., 0., 0.], rover.body_motion([.8, .8], .35))
    assert after[0] > 0 and after[1] < 0 and after[2] < 0
    assert rover.advance([0., 0., 0.], [.8, 0.]) == pytest.approx([.12, 0., 0.])


def test_frozen_parameters_never_update(life):
    before = _parameters(life.arms["frozen"]["model"])
    life.auto = False
    life.change_phase("weakened")
    for _ in range(4):
        life.tick()
    assert _parameters(life.arms["frozen"]["model"]) == before
    assert all(row["presentations"] == 0 and row["learning"] is False
               for row in life.rows if row["model"] == "frozen")


def test_frozen_control_starts_from_identical_checkpoint(life):
    assert life.arms["cadence"]["model"].snapshot() == life.arms["frozen"]["model"].snapshot()
    assert digest(life.arms["frozen"]["model"].snapshot()) == life.initial_brain_digest


def test_restoration_probe_keeps_new_learning_paused(life):
    life.auto = False
    life.change_phase("weakened")
    life.tick()
    life.tick()
    before = {kind: _parameters(arm["model"]) for kind, arm in life.arms.items()}
    life.change_phase("restored_probe")
    for _ in range(2):
        life.tick()
    assert {kind: _parameters(arm["model"]) for kind, arm in life.arms.items()} == before
    assert all(row["presentations"] == 0 and not row["learning"]
               for row in life.rows if row["phase"] == "restored_probe")
    assert life.wheel_gain == 1.0


def test_model_ports_exclude_teacher_gain_and_task_state():
    for cls in (models.CadenceModel, models.AdaptiveModel, models.MLPModel):
        assert list(inspect.signature(cls.learn).parameters) == ["self", "action", "motion"]
        assert list(inspect.signature(cls.query).parameters) == ["self", "actions"]
        assert list(inspect.signature(cls.activate).parameters) == ["self", "action"]
    model = models.make_model("recursive", 17)
    assert model.brain.inspect()["inputs"] == [{"name": "motors", "shape": [2]}]


def test_forecast_precedes_its_consequence_and_only_past_motion_teaches(life, monkeypatch):
    events = []
    measured_motion = rover.body_motion
    for kind, arm in life.arms.items():
        model = arm["model"]
        original_activate, original_learn = model.activate, model.learn

        def activate(action, *, model_kind=kind, original=original_activate):
            events.append(("forecast", model_kind, list(action)))
            return original(action)

        def learn(action, motion, *, model_kind=kind, original=original_learn):
            events.append(("learn", model_kind, list(action), list(motion)))
            return original(action, motion)

        monkeypatch.setattr(model, "activate", activate)
        monkeypatch.setattr(model, "learn", learn)

    def body(action, gain=1.0):
        events.append(("body", list(action), gain))
        return measured_motion(action, gain)

    monkeypatch.setattr(rover, "body_motion", body)
    life.tick()
    assert not any(event[0] == "learn" for event in events)
    assert [event[0] for event in events] == ["forecast", "body"] * len(life.arms)
    previous = {row["model"]: row for row in life.rows}
    events.clear()
    life.tick()
    for event in events:
        if event[0] == "learn":
            assert event[2] == previous[event[1]]["action"]
            assert event[3] == previous[event[1]]["motion"]
    for kind in life.arms:
        relevant = [event[0] for event in events if len(event) > 1 and event[1] == kind]
        assert relevant == (["forecast"] if kind == "frozen" else ["learn", "forecast"])


def test_refused_learning_witness_stops_the_run(life, monkeypatch):
    life.tick()
    monkeypatch.setattr(life.arms["cadence"]["model"], "learn", lambda action, motion: False)
    with pytest.raises(RuntimeError, match="refused"):
        life.tick()
    assert life.step == 1


def test_json_whole_life_continuation_parity(life):
    life.auto = False
    life.change_phase("weakened")
    for _ in range(3):
        life.tick()
    serialized = json.dumps(life.snapshot(), allow_nan=False, sort_keys=True)
    resumed = rover.Life.from_snapshot(json.loads(serialized))
    assert life.snapshot() == resumed.snapshot()
    for _ in range(4):
        life.tick()
        resumed.tick()
    # Compares all model/optimizer state, replay, pending consequence, targets,
    # events, trajectories, error histories and counters except measured clocks.
    assert _without_wall_time(life.snapshot()) == _without_wall_time(resumed.snapshot())


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(step=-1),
    lambda value: value.update(step=True),
    lambda value: value.update(weak_gain=.1),
    lambda value: value.update(phase="invented"),
    lambda value: value["arms"].pop("frozen"),
    lambda value: value["arms"]["cadence"].update(pose=[0., 0.]),
    lambda value: value["arms"]["cadence"].update(pose=[0., math.nan, 0.]),
    lambda value: value["arms"]["mlp"]["model"]["second_moments"][0][0].__setitem__(0, -1.),
    lambda value: value["arms"]["cadence"].update(replay=[[[0., 0.], [math.inf, 0.]]]),
    lambda value: value["arms"]["cadence"].update(pending=[[0., 0.], [0., 0.], "invented"]),
    lambda value: value.update(rows=[{}]),
])
def test_malformed_checkpoint_is_rejected(prepared, mutation):
    value = copy.deepcopy(prepared)
    mutation(value)
    with pytest.raises((ValueError, TypeError)):
        rover.Life.from_snapshot(value)


@pytest.fixture(scope="module")
def measured_partial_receipt(prepared):
    life = rover.Life.from_snapshot(copy.deepcopy(prepared))
    for _ in range(3):
        life.tick(queue_delay_ms=2.5)
    return life.receipt()


@pytest.fixture
def partial_receipt(measured_partial_receipt):
    return copy.deepcopy(measured_partial_receipt)


def test_independent_receipt_recomputation(partial_receipt):
    result = verify(partial_receipt)
    assert result["verified"]
    assert result["transitions"] == 12
    assert result["gate"] == {"complete": False, "passed": False}


def test_manual_interventions_remain_verifiable_without_a_standard_gate(life):
    life.auto = False
    life.change_phase("weakened")
    life.tick()
    life.weak_gain = .5
    life.change_phase("weakened")
    life.tick()
    life.change_phase("restored_probe")
    life.tick()
    assert verify(life.receipt())["gate"] == {"complete": False, "passed": False}


@pytest.mark.parametrize("mutation", [
    lambda value: value["transitions"][0]["after"].__setitem__(0, 99.),
    lambda value: value["transitions"][0].update(hit=True),
    lambda value: value["transitions"][0].update(prediction=[99., 99.]),
    lambda value: value["transitions"][0].update(command_age_ms=0.),
    lambda value: value["transitions"][1].update(presentations=1),
    lambda value: value["transitions"][1].update(model="cadence"),
    lambda value: value["transitions"].pop(),
    lambda value: value["transitions"][0].update(phase="restored_learning"),
    lambda value: value["metrics"]["cadence"]["normal"].update(distance_integral=0.),
    lambda value: value["bootstrap_witnesses"][0][1].__setitem__(0, .99),
    lambda value: value["bootstrap_schedule"].pop(),
    lambda value: value.update(gate={"complete": True, "passed": True}),
])
def test_tampered_receipt_fails_even_after_rehash(partial_receipt, mutation):
    mutation(partial_receipt)
    partial_receipt["transition_hash"] = digest(partial_receipt["transitions"])
    with pytest.raises(ValueError):
        verify(partial_receipt)


def test_changed_protocol_cannot_be_self_certified(partial_receipt):
    partial_receipt["protocol"] = copy.deepcopy(partial_receipt["protocol"])
    partial_receipt["protocol"]["demonstration_gate"]["weak_success_rate_min"] = 0.
    partial_receipt["protocol_hash"] = digest(partial_receipt["protocol"])
    with pytest.raises(ValueError, match="Protocol"):
        verify(partial_receipt)


def test_cli_skips_metadata_and_previous_verification_output(partial_receipt, tmp_path):
    (tmp_path / "seed-17.json").write_text(json.dumps(partial_receipt))
    for name in ("freeze.json", "summary.json"):
        (tmp_path / name).write_text("{}")
    (tmp_path / "verification.json").write_text('[{"verified":true}]')
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")),
                             *map(str, sorted(tmp_path.glob("*.json")))],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    outputs = json.loads(result.stdout)
    assert len(outputs) == 1 and outputs[0]["verified"]


def test_gate_requires_every_scheduled_transition():
    # Visiting every phase for one tick is not a completed experiment.
    partial = {kind: {phase: {"steps": 1} for phase, _ in rover.PROTOCOL["phases"]}
               for kind in ("cadence", "frozen", "adaptive", "mlp")}
    assert rover.demonstration_gate(partial) == {"complete": False, "passed": False}
