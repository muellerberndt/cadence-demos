"""No numerical model calls: native constructors plus synthetic custody tests."""

import copy
import gzip
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "amen_phrase_tested", HERE / "amen_ordinary_phrase.py"
)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
STREAM_PATH = HERE.parents[1] / "cadence-amen/drsn_amen/stream.py"
S = P.stream_module(STREAM_PATH)


@pytest.fixture
def phrase():
    events = np.zeros((P.EVENTS, 71))
    for i, row in enumerate(events):
        row[i % 32] = 1
        row[S.DRUM_ON] = 1
        row[S.DRUM_GAIN] = 0.4
        row[S.NOTE_START + i % 24] = 1
        row[S.BASS_ON] = 1
    return {
        "events": events.tolist(),
        "row_ids": [["train", i] for i in range(P.EVENTS)],
    }


@pytest.fixture
def amen(tmp_path):
    root = tmp_path / "amen"
    (root / "drsn_amen").mkdir(parents=True)
    shutil.copyfile(STREAM_PATH, root / "drsn_amen/stream.py")
    fixture = root / "fixtures/reference-events-v9"
    fixture.mkdir(parents=True)
    names = [S.HELD_OUT[0], "short", "first", "second"]
    arrays = {"crop_profiles": np.ones((32, 3))}
    for name, count in zip(names, [256, 255, 257, 258], strict=True):
        rows = np.zeros((count, 15))
        rows[:, 0] = np.arange(count) % 32
        rows[:, 1] = 0.4
        rows[:, 2] = 3
        arrays[name], arrays[name + "_profiles"] = rows, np.ones((count, 3))
    np.savez_compressed(fixture / "arrays.npz", **arrays)
    receipt = {
        "regions": [{"id": n} for n in names],
        "arrays_sha256": P.sha(fixture / "arrays.npz"),
    }
    receipt["receipt_sha256"] = P.digest(receipt)
    P.write(fixture / "fixture.json", receipt)
    return root


def forbidden(*args, **kwargs):
    raise AssertionError("No numerical model calls are authorized in this test")


def test_native_topology_and_identical_b_c_founders(monkeypatch):
    from cadence import Brain

    for name in ("settle", "observe", "observe_batch"):
        monkeypatch.setattr(Brain, name, forbidden)
    a, b, c = (P.build(arm) for arm in P.ARMS)
    assert P.topology(a, "A") == {
        "patches": 71,
        "inputs": 585,
        "connections": 41535,
        "parameters": 41606,
        "residual_edges": 0,
    }
    assert P.topology(b, "B") == {
        "patches": 135,
        "inputs": 585,
        "connections": 83519,
        "parameters": 83654,
        "residual_edges": 0,
    }
    assert b.snapshot() == c.snapshot()
    assert b.config["device"] == "cpu" and b.config["dtype"] == "float64"
    broken = SimpleNamespace(
        graph=SimpleNamespace(n_inputs=585, n_patches=71, edges=())
    )
    with pytest.raises(ValueError, match="complete-input bypass"):
        P.topology(broken, "A")


def test_lazy_history_exactly_matches_frozen_stream(phrase):
    history, clock, wake, targets = S.stream(np.asarray(phrase["events"]), 8)
    for tick in range(P.EVENTS):
        inputs, target = P.example(phrase, tick, S)
        assert inputs["past"] + inputs["heard"] == history[tick].tolist()
        assert inputs["clock"] == clock[tick].tolist()
        assert inputs["wake"] == wake[tick, 0]
        assert target["event"] == targets[tick].tolist()


def test_current_and_future_labels_cannot_enter_history(phrase):
    original = P.example(phrase, 8, S)[0]
    for tick in range(8, len(phrase["events"])):
        phrase["events"][tick] = [0.2] * 71
    assert P.example(phrase, 8, S)[0] == original
    with pytest.raises(ValueError):
        P.example(phrase, -1, S)


def test_first_eligible_region_and_hard_target_semantics(amen):
    selected = P.select_phrase(amen, S)
    assert selected["region"] == "first" and selected["start"] == 0
    assert selected["row_ids"] == [["first", i] for i in range(256)]
    assert [x["decision"] for x in selected["selection_trace"]] == [
        "held_out",
        "too_short",
        "selected",
    ]
    events = np.asarray(selected["events"])
    assert np.all(events[:, :32].sum(axis=1) == 1)
    assert events[0, S.BASS_HOLD] == 0 and events[1, S.BASS_HOLD] == 1


def test_fixture_arrays_tampering_rejected(amen):
    with (amen / "fixtures/reference-events-v9/arrays.npz").open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="arrays mismatch"):
        P.select_phrase(amen, S)


def test_freeze_is_source_bound_and_has_no_model_calls(amen, tmp_path, monkeypatch):
    from cadence import Brain

    for name in ("settle", "observe", "observe_batch"):
        monkeypatch.setattr(Brain, name, forbidden)
    root = tmp_path / "frozen"
    p = P.freeze(root, amen)
    assert P.bound(root) == p
    assert p["founders"]["B"] == p["founders"]["C"]
    assert p["methods"] == {"A": "observe_batch", "B": "observe_batch", "C": "observe"}
    assert p["training_indices"] == list(range(32))
    assert p["targets"] == "hard" and p["seconds_per_arm"] == 60
    assert P.read(root / "freeze.json")["learning_calls"] == 0
    (root / "phrase.json").write_text("{}")
    with pytest.raises(ValueError, match="phrase changed"):
        P.bound(root)


def journal_row(ordinal, method="settle", accepted=False):
    return {
        "ordinal": ordinal,
        "status": "returned",
        "method": method,
        "phase": "before" if method == "settle" else "train",
        "result": {"accepted": accepted, "work": {"edge_visits": 7}},
    }


def test_returned_prefix_preserves_counters_if_compact_report_lagged(tmp_path):
    row = journal_row(0, "observe", True)
    (tmp_path / "calls.jsonl").write_text(P.encoded(row) + "\n")
    P.write(tmp_path / "current.json", {"status": "started", "ordinal": 0})
    receipt = P.returned_prefix(tmp_path)
    assert receipt["calls"] == receipt["accepted"] == 1
    assert receipt["work"] == {"edge_visits": 7}
    assert not receipt["unknown_call_work"]
    P.write(tmp_path / "current.json", {"status": "started", "ordinal": 1})
    assert P.returned_prefix(tmp_path)["unknown_call_work"]


def test_broken_journal_tail_is_unknown_and_retained(tmp_path):
    path = tmp_path / "calls.jsonl"
    content = P.encoded(journal_row(0)) + '\n{"ordinal":'
    path.write_text(content)
    result = P.returned_prefix(tmp_path)
    assert result["calls"] == 1
    assert result["damaged_tail"] and result["unknown_call_work"]
    assert path.read_text() == content


@pytest.fixture
def mocked_worker(tmp_path, phrase, monkeypatch):
    """Mock public methods, never execute a numerical solve."""
    import cadence

    root = tmp_path / "run"
    root.mkdir()
    P.write(root / "phrase.json", phrase)
    P.save_snapshot(root / "founder.json.gz", "{}")
    config = {
        "sources": {"app/stream.py": {"path": str(STREAM_PATH)}},
        "founders": {a: {"path": "founder.json.gz"} for a in P.ARMS},
        "methods": {"A": "observe_batch", "B": "observe_batch", "C": "observe"},
        "query_indices": [0, 1],
        "training_indices": [0, 1],
        "admission_budget": 8192,
        "query_budget": 2048,
    }
    instances = []

    class FakeBrain:
        def __init__(self):
            self.state, self.admissions = [0], 0
            self.invoked = []
            self.refuse_at = self.raise_at = None
            instances.append(self)

        @classmethod
        def from_snapshot(cls, text):
            return cls()

        def snapshot(self):
            return P.encoded({"state": self.state, "admissions": self.admissions})

        def result(self, method, inputs, targets=None, **kwargs):
            self.invoked.append(
                (method, copy.deepcopy(inputs), copy.deepcopy(targets), kwargs)
            )
            if len(self.invoked) == self.raise_at:
                raise RuntimeError("mock unreturned solve")
            qualified = len(self.invoked) != self.refuse_at
            if method != "settle" and qualified:
                self.admissions += 1
                if method == "observe":
                    self.state = [self.admissions]
            result = {
                "qualified": qualified,
                "reason": "qualified" if qualified else "budget",
                "weights": [self.admissions],
                "biases": [0],
                "outputs": {"event": [0.0] * 71},
                "state": list(self.state),
                "work": {"edge_visits": 7},
                "sweeps": 2,
            }
            if method != "settle":
                result["accepted"] = qualified
            return result

        def settle(self, inputs, **kwargs):
            return self.result("settle", inputs, **kwargs)

        def observe(self, inputs, targets, **kwargs):
            return self.result("observe", inputs, targets, **kwargs)

        def observe_batch(self, examples, **kwargs):
            assert len(examples) == 1
            return self.result("observe_batch", *examples[0], **kwargs)

    monkeypatch.setattr(cadence, "Brain", FakeBrain)
    monkeypatch.setattr(P, "bound", lambda root: config)
    monkeypatch.setattr(P, "topology", lambda *args: {})
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=lambda n: None, set_num_interop_threads=lambda n: None
        ),
    )
    return root, FakeBrain, instances


@pytest.mark.parametrize("arm,expected_state", [("B", [0]), ("C", [2])])
def test_worker_distinguishes_retained_activity_and_pure_queries(
    mocked_worker, arm, expected_state
):
    root, _, instances = mocked_worker
    result = P.worker(root, arm)
    assert (
        result["status"] == "complete"
        and result["calls"] == 6
        and result["accepted"] == 2
    )
    assert instances[0].state == expected_state
    assert all(
        target is None
        for method, _, target, _ in instances[0].invoked
        if method == "settle"
    )
    assert all(
        kwargs["source"] == "estimate"
        for method, _, _, kwargs in instances[0].invoked
        if method != "settle"
    )
    assert result["returned_prefix"]["work"] == {"edge_visits": 42}
    with gzip.open(root / arm / "discarded-latest.json.gz", "rt") as handle:
        assert json.load(handle)["admissions"] == 2


@pytest.mark.parametrize(
    "failure,expected_calls,unknown", [("refuse_at", 3, False), ("raise_at", 2, True)]
)
def test_worker_preserves_refusal_and_unreturned_intent(
    mocked_worker, monkeypatch, failure, expected_calls, unknown
):
    root, fake, _ = mocked_worker
    original = fake.from_snapshot

    def make(text):
        brain = original(text)
        setattr(brain, failure, 3)
        return brain

    monkeypatch.setattr(fake, "from_snapshot", make)
    report = P.worker(root, "B")
    assert report["status"] == "stopped" and report["accepted"] == 0
    assert report["returned_prefix"]["calls"] == expected_calls
    assert report["unknown_call_work"] is unknown


@pytest.mark.parametrize("launch_failure", [False, True])
def test_outer_timeout_retains_all_three_without_retry(
    tmp_path, monkeypatch, launch_failure
):
    p = {"storage_bytes": P.STORAGE_BYTES, "seconds_per_arm": 60}
    monkeypatch.setattr(P, "bound", lambda root: p)
    P.write(tmp_path / "protocol.json", p)
    attempts = []

    def run(command, **kwargs):
        arm = command[-1]
        attempts.append(arm)
        assert kwargs["timeout"] == 60 and kwargs["env"]["OMP_NUM_THREADS"] == "1"
        if launch_failure:
            raise OSError("mock failed process launch")
        directory = tmp_path / arm
        directory.mkdir()
        P.write(directory / "current.json", {"status": "started", "ordinal": 0})
        raise subprocess.TimeoutExpired(command, 60)

    monkeypatch.setattr(P.subprocess, "run", run)
    summary = P.preflight(tmp_path)
    assert attempts == list(P.ARMS)
    expected = "failed" if launch_failure else "censored"
    assert all(
        r["status"] == expected and r["unknown_call_work"] != launch_failure
        for r in summary["arms"]
    )
    assert not summary["preflight_complete"] and not summary["full_study_authorized"]
    with pytest.raises(FileExistsError):
        P.preflight(tmp_path)
