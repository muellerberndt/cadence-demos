"""Construction, custody, work selection and endpoint tests without training."""

import copy

import pytest
import work_matched_innovation as experiment


@pytest.mark.parametrize("seed", experiment.SEEDS)
def test_exact_public_founder_mapping(seed):
    founders = experiment.base.founders(seed)
    a, b = (
        experiment.Brain.from_snapshot(founders[arm]) for arm in experiment.base.ARMS
    )
    assert a.weights == b.weights and a.biases == b.biases
    assert len(a.weights) + len(a.biases) == 9


def test_fresh_balanced_tape_and_future_boundary():
    data = experiment.tape()
    assert data == experiment.tape()
    assert experiment.DATA_SEED == 20261007
    assert len(data["clean"]) == 64 * 16 and len(data["mixed"]) == 128 * 16
    for a, b in zip(data["mixed"][::2], data["mixed"][1::2], strict=True):
        assert a["inputs"] == b["inputs"] and a["delta"] == -b["delta"]
        assert abs(a["inputs"]["u"][0]) <= 0.2
    original = data["mixed_test"][0]
    changed = {**original, "actual_y": [0.99], "delta": 0.999}
    assert experiment.base.query(original) == experiment.base.query(changed)
    train = {
        tuple(r["inputs"][p][0] for p in ("u", "v"))
        for phase in ("clean", "mixed")
        for r in data[phase]
    }
    test = {
        tuple(r["inputs"][p][0] for p in ("u", "v"))
        for phase in ("clean_test", "mixed_test")
        for r in data[phase]
    }
    assert not train & test


@pytest.mark.parametrize(
    "target,expected",
    [(10, 32), (320, 32), (350, 35), (480, 48), (481, None), (None, None)],
)
def test_first_whole_admission_crossing_is_work_only(target, expected):
    selected = next(
        (n for n in range(1, 129) if experiment.crossing(n, n * 10, target)), None
    )
    assert selected == expected
    assert not experiment.crossing(31, 1000000, target)
    assert not experiment.crossing(49, 1000000, target)


def reports(root, *, ordinary32=0.03, ordinary_matched=0.028, observer32=0.02):
    experiment.custody.atomic(
        root / "execution.json",
        [
            {"seed": seed, "arm": arm, "status": "returned", "code": 0}
            for seed in experiment.SEEDS
            for arm in experiment.base.ARMS
        ],
    )
    for seed in experiment.SEEDS:
        for arm in experiment.base.ARMS:
            folder = root / f"{arm}-seed{seed}"
            folder.mkdir(exist_ok=True)
            groups = []
            for update, mae in (
                (32, observer32 if arm == "observer" else ordinary32),
                (36, ordinary_matched),
                (128, 0.04 if arm == "observer" else 0.01),
            ):
                groups.append(
                    {
                        "check": f"mixed{update}",
                        "group": "correction",
                        "qualified_only_mae": {"future": mae},
                    }
                )
            experiment.custody.atomic(
                folder / "result.json",
                {
                    "eligible": True,
                    "ordinary_crossing": 36 if arm == "ordinary" else None,
                    "groups": groups,
                },
            )


def test_unchanged_threshold_both_comparators_and_late_reversal(tmp_path):
    reports(tmp_path)
    result = experiment.comparison(tmp_path)
    assert result["primary_pass"]
    assert all(r["observer128"] > r["ordinary128"] for r in result["rows"])
    reports(tmp_path, ordinary32=0.024, ordinary_matched=0.03)
    assert not experiment.comparison(tmp_path)["primary_pass"]
    reports(tmp_path, ordinary32=0.03, ordinary_matched=0.024)
    assert not experiment.comparison(tmp_path)["primary_pass"]


def test_no_eligible_subset_or_mean_only_win(tmp_path):
    reports(tmp_path)
    path = tmp_path / f"ordinary-seed{experiment.SEEDS[0]}" / "result.json"
    report = experiment.custody.read(path)
    report["eligible"] = False
    experiment.custody.atomic(path, report)
    result = experiment.comparison(tmp_path)
    assert not result["all_pairs_eligible"] and not result["primary_pass"]
    assert all(v is None for v in result["mean_mae_reductions"].values())
    assert result["rows"][0]["ordinary128"] == 0.01
    reports(tmp_path, ordinary32=0.06)
    report = experiment.custody.read(path)
    report["groups"][0]["qualified_only_mae"]["future"] = 0.019
    experiment.custody.atomic(path, report)
    assert not experiment.comparison(tmp_path)["primary_pass"]


def test_outer_timeout_vetoes_apparently_complete_report(tmp_path):
    reports(tmp_path)
    path = tmp_path / "execution.json"
    execution = experiment.custody.read(path)
    execution[0].update(status="outer_timeout", code=-9)
    experiment.custody.atomic(path, execution)
    result = experiment.comparison(tmp_path)
    assert not result["primary_pass"] and not result["all_pairs_eligible"]
    assert result["rows"][0]["observer128"] == 0.04


@pytest.mark.parametrize("outcome", ("interrupted", "refused"))
def test_attempt_work_and_failures_cannot_be_promoted(tmp_path, monkeypatch, outcome):
    root = tmp_path / "frozen"
    experiment.freeze(root)
    before = experiment.custody.read(root / "founders.json")["83"]["ordinary"]

    def no_training(self, examples, *, event_id, source):
        assert event_id == 0 and source == "witness" and len(examples) == 16
        if outcome == "interrupted":
            raise TimeoutError("synthetic; no learning")
        return {
            "qualified": False,
            "accepted": False,
            "reason": "synthetic_refusal",
            "stationarity": 1.0,
            "sweeps": 2,
            "work": {"edge_visits": 123},
            "event_id": event_id,
            "source": source,
            "batch_size": 16,
        }

    monkeypatch.setattr(experiment.Brain, "observe_batch", no_training)
    assert experiment.run(root, 83, "ordinary") == 1
    folder = root / "ordinary-seed83"
    result = experiment.custody.read(folder / "result.json")
    assert not result["eligible"] and result["target_missing"]
    assert result["admission_counts"]["started"] == 1
    assert result["admission_counts"]["accepted"] == 0
    assert len(result["groups"]) == 6 and all(
        g["completed"] == 0 for g in result["groups"]
    )
    if outcome == "interrupted":
        assert result["unknown_work"] and result["training_work"] == {}
    else:
        assert not result["unknown_work"] and result["training_work"] == {
            "edge_visits": 123
        }
        assert result["admission_counts"]["refused"] == 1
    assert experiment.custody.read(folder / "last-completed.json") == before
    assert experiment.Brain.from_snapshot(before).snapshot() == before


def test_source_and_data_freeze_rejects_changed_inputs(tmp_path):
    root = tmp_path / "frozen"
    experiment.freeze(root)
    experiment.validate(root)
    data = experiment.custody.read(root / "data.json")
    altered = copy.deepcopy(data)
    altered["mixed"][0]["actual_y"] = [0.99]
    experiment.custody.atomic(root / "data.json", altered)
    with pytest.raises(AssertionError):
        experiment.validate(root)
