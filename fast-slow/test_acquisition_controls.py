"""Independent arithmetic, exposure and custody checks for acquisition controls."""

import copy
import itertools
import json
from collections import Counter

import acquisition_controls as experiment
import pytest


@pytest.mark.parametrize("condition", experiment.CONDITIONS)
def test_corpora_are_real_stable_transitions_without_hidden_inputs(condition):
    tape = experiment.tape(condition)
    assert [len(tape[name]) for name in ("train", "development", "confirmation")] == [
        512,
        128,
        128,
    ]
    signatures = {}
    for phase, records in tape.items():
        signatures[phase] = set()
        for record in records:
            previous, executed = record["inputs"]["previous"]
            present, candidate = record["inputs"]["present"]
            gain = record["audit"]["past_gain"]
            assert set(record["inputs"]) == {"previous", "present"}
            assert (
                record["audit"]["future_gain"] == gain and not record["audit"]["switch"]
            )
            assert 0.25 <= abs(executed) <= 0.5 and 0.25 <= abs(candidate) <= 0.5
            assert present == 0.8 * previous + gain * executed
            actual = 0.8 * present + gain * candidate
            assert record["past"] == [present, present - previous]
            assert record["future"] == [actual, actual - present]
            assert (present - 0.8 * previous) / executed == pytest.approx(gain)
            signatures[phase].add(
                tuple(record["inputs"]["previous"] + record["inputs"]["present"])
            )
        assert len(signatures[phase]) == len(records)
    for first, second in itertools.combinations(signatures.values(), 2):
        assert not first & second


@pytest.mark.parametrize("condition", experiment.CONDITIONS)
def test_every_batch_is_balanced_and_every_epoch_uses_same_corpus_once(condition):
    rows = experiment.tape(condition)["train"]
    batches = experiment.replay(rows)
    assert len(batches) == 512
    cells = len({row["stratum"] for row in rows})
    for batch in batches:
        assert len(batch) == len(set(batch)) == 16
        counts = Counter(rows[index]["stratum"] for index in batch)
        assert len(counts) == cells and set(counts.values()) == {16 // cells}
    for start in range(0, 512, 32):
        counts = Counter(
            index for batch in batches[start : start + 32] for index in batch
        )
        assert counts == Counter(range(512))
    for update, repeats in ((32, 1), (128, 4), (512, 16)):
        assert Counter(
            index for batch in batches[:update] for index in batch
        ) == Counter({i: repeats for i in range(512)})


@pytest.mark.parametrize(
    "layout,patches,weights,shared", [("small", 6, 28, 24), ("interaction", 10, 52, 44)]
)
@pytest.mark.parametrize("prior", experiment.PRIORS)
def test_topology_counts_matched_coefficients_and_candidate_interaction(
    layout, patches, weights, shared, prior
):
    brains = [
        experiment.make_brain(2, arm, layout, prior) for arm in ("ordinary", "observer")
    ]
    matched = experiment.match(*brains, layout)
    assert matched["shared_edges"] == shared
    for arm, brain in zip(("ordinary", "observer"), brains, strict=True):
        assert brain.graph.n_patches == patches and len(brain.weights) == weights
        assert (
            brain.config["parameter_prior"] == prior
            and brain.config["state_prior"] == 0.01
        )
        assert len(experiment.replacement_indices(brain, arm, layout)) == (
            4 if layout == "small" else 8
        )
        assert not any(
            kind == "input" and source == 3 and target < 4
            for kind, source, target in brain.graph.edges
        )
        if layout == "interaction":
            assert all(
                ("input", 3, target) in brain.graph.edges for target in range(4, 8)
            )
            assert all(
                ("state", source, target) in brain.graph.edges
                for source in range(4, 8)
                for target in (8, 9)
            )
            assert not any(
                kind == "input" and target in (8, 9)
                for kind, _, target in brain.graph.edges
            )


def good_queries():
    records = []
    for index in range(128):
        gain = -0.3 if index < 64 else 0.3
        records.append(
            dict(
                kind="forecast",
                gain=gain,
                qualified=True,
                absolute_error=[0.01, 0.02],
                past_errors=[0.1, -0.2],
            )
        )
    for index in range(16):
        gain = -0.3 if index < 8 else 0.3
        for action in (-0.5, 0.5):
            records.append(
                dict(
                    kind="secant", gain=gain, future=[gain * action, 0], qualified=True
                )
            )
    records.extend(dict(kind="full_clamp_diagnostic", qualified=True) for _ in range(8))
    return records


def test_gate_requires_both_heads_every_gain_correct_secant_and_qualification():
    records = good_queries()
    assert experiment.gate_score(records)["passed"]
    bad = copy.deepcopy(records)
    for record in bad[:64]:
        record["absolute_error"][1] = 0.1
    assert not experiment.gate_score(bad)["passed"]
    bad = copy.deepcopy(records)
    bad[159]["future"][0] *= -1
    assert not experiment.gate_score(bad)["passed"]
    bad = copy.deepcopy(records)
    bad.append(dict(kind="full_clamp_diagnostic", qualified=False))
    assert not experiment.gate_score(bad)["passed"]
    assert not experiment.gate_score(records[:-1])["passed"]


def test_selection_is_joint_and_size_then_exposure_then_prior_not_arm_advantage():
    def report(layout, prior, updates):
        spec = dict(
            layout=layout,
            parameter_prior=prior,
            parameters=34 if layout == "small" else 62,
            condition="balanced_mixed",
        )
        return {
            "spec": spec,
            "status": "complete",
            "arms": [
                dict(
                    sources_unchanged=True,
                    status="complete",
                    refusals=0,
                    gates=[dict(update_attempts=u, passed=True) for u in updates],
                )
                for _ in range(2)
            ],
        }

    reports = [
        report("interaction", 0.1, [32]),
        report("small", 0.01, [128]),
        report("small", 0.1, [128]),
    ]
    choice = experiment.selected(reports)
    assert (choice["layout"], choice["parameter_prior"], choice["updates"]) == (
        "small",
        0.1,
        128,
    )
    reports[1]["arms"][0]["gates"][0]["update_attempts"] = 32
    assert experiment.selected([reports[1]]) is None
    assert experiment.selected([]) is None
    reports[2]["arms"][0]["status"] = "censored"
    assert experiment.selected([reports[2]]) is None


def test_freeze_custody_and_pilot_inventory(tmp_path):
    protocol = experiment.freeze(tmp_path)
    assert sum(spec["role"] == "development" for spec in protocol["cases"]) == 12
    assert sum(spec["role"] == "confirmation" for spec in protocol["cases"]) == 16
    assert experiment.freeze(tmp_path) == protocol
    path = tmp_path / "replay-balanced_mixed.json"
    schedule = experiment.base.read(path)
    schedule[0][0] = schedule[0][1]
    experiment.base.atomic(path, schedule)
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        experiment.freeze(tmp_path)


@pytest.mark.parametrize(
    "error",
    [experiment.base.ArmTimeout("fixture timeout"), RuntimeError("fixture error")],
)
def test_failed_admission_restores_founder_and_retains_unknown_work(
    tmp_path, monkeypatch, error
):
    protocol = experiment.freeze(tmp_path)
    spec = protocol["cases"][0]
    founder = (tmp_path / f"founder-{spec['id']}-ordinary.json").read_text()

    def fail(brain, *args, **kwargs):
        brain._state = (0.7,) * 6
        raise error

    monkeypatch.setattr(experiment.Brain, "observe_batch", fail)
    report = experiment.run_arm(tmp_path, spec, "ordinary", protocol, 1)
    assert report["status"] in ("censored", "error")
    assert report["attempted_updates"] == 1 and report["attempted_presentations"] == 16
    assert report["unknown_work_calls"] == 1
    assert report["admissions"] == report["presentations"] == 0 and report["calls"] == 1
    folder = tmp_path / "results" / spec["id"] / "ordinary"
    assert experiment.base.read(folder / "latest.json")["brain"] == founder
    call = json.loads((folder / "calls.jsonl").read_text())
    assert call["before_sha256"] == call["after_sha256"] and call["unknown_work"]


@pytest.mark.parametrize("layout", experiment.LAYOUTS)
def test_real_query_clamps_only_past_and_same_rule_admits_witness_batch(layout):
    brain = experiment.make_brain(2, "observer", layout, 0.1)
    rows = experiment.tape("balanced_mixed")["train"]
    record = rows[0]
    inputs, past = experiment.base.known_query(record)
    before = brain.snapshot()
    result = brain.settle(inputs, targets=past)
    assert result["qualified"] and brain.snapshot() == before
    assert result["state"][2:4] == tuple(record["past"])
    indices = experiment.replay(rows)[0]
    update = brain.observe_batch(
        [experiment.base.witness(rows[i]) for i in indices], source="witness"
    )
    assert (
        update["accepted"]
        and update["source"] == "witness"
        and update["batch_size"] == 16
    )
    assert brain.inspect()["admissions"] == 1
