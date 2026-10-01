"""Independent crossing/metric/purity mutations; no learning."""

import copy

import pytest
import verify_work_matched_innovation as verifier


def updates():
    return [
        {
            "phase": "clean" if i < 64 else "mixed",
            "update": i + 1 if i < 64 else i - 63,
            "accepted": True,
            "work": {"edge_visits": 10},
        }
        for i in range(192)
    ]


def test_first_crossing_is_whole_admission_not_favorite_checkpoint():
    rows = updates()
    target = {"training_edge_visits": 1005}
    assert verifier.first_crossing(rows, 1005) == 37
    record = {
        "mixed_update": 37,
        "training_work": {"edge_visits": 1010},
        "target_edge_visits": 1005,
        "overshoot_edge_visits": 5,
        "checkpoint_sha256": "bound-snapshot",
    }
    verifier.check_crossing(record, rows, target, "bound-snapshot")
    for field, value in [
        ("mixed_update", 38),
        ("overshoot_edge_visits", 0),
        ("target_edge_visits", 990),
        ("checkpoint_sha256", "later"),
    ]:
        with pytest.raises(ValueError, match="first-crossing"):
            verifier.check_crossing(
                {**record, field: value}, rows, target, "bound-snapshot"
            )


def test_crossing_range_and_missing_or_refused_work_cannot_be_promoted():
    rows = updates()
    assert verifier.first_crossing(rows, 1) == 32
    assert verifier.first_crossing(rows, 1120) == 48
    assert verifier.first_crossing(rows, 1121) is None
    assert verifier.first_crossing(rows, None) is None
    rows[95]["accepted"] = False
    assert verifier.first_crossing(rows, 1) is None


def query_rows():
    return [
        {
            "check": "mixed0",
            "group": "clean-free",
            "qualified": True,
            "past_absolute_error": 0.01,
            "future_absolute_error": 0.01,
        }
        for _ in range(32)
    ]


def test_clean_gate_requires_all_rows_and_both_free_heads():
    rows = query_rows()
    assert verifier.groups(rows, None)[0]["clean_gate"]
    assert not verifier.groups(rows[:-1], None)[0]["clean_gate"]
    rows[0]["qualified"] = False
    assert not verifier.groups(rows, None)[0]["clean_gate"]
    rows = query_rows()
    for row in rows:
        row["past_absolute_error"] = 0.031
    assert not verifier.groups(rows, None)[0]["clean_gate"]


def cases():
    result = []
    for seed in verifier.SEEDS:
        for arm in verifier.ARMS:
            result.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "eligible": True,
                    "ordinary_crossing": 35 if arm == "ordinary" else None,
                    "groups": [
                        {
                            "check": f"mixed{n}",
                            "group": "correction",
                            "qualified_only_mae": {
                                "future": 0.02 if arm == "ordinary" else 0.01
                            },
                        }
                        for n in (32, 35, 128)
                    ],
                }
            )
    return result


def test_both_comparisons_all_five_seeds_and_effect_size_are_required():
    rows = cases()
    assert verifier.comparison(rows)["primary_pass"]
    rows[0]["eligible"] = False
    failed = verifier.comparison(rows)
    assert not failed["primary_pass"] and len(failed["rows"]) == 5
    rows = cases()
    ordinary = next(c for c in rows if c["arm"] == "ordinary")
    ordinary["groups"][1]["qualified_only_mae"]["future"] = 0.009
    assert not verifier.comparison(rows)["primary_pass"]
    rows = cases()
    for row in rows:
        if row["arm"] == "ordinary":
            row["groups"][0]["qualified_only_mae"]["future"] = 0.0149
    assert not verifier.comparison(rows)["primary_pass"]


def test_actual_replay_rejects_altered_head_or_qualification_and_keeps_snapshot():
    model = verifier.frozen.base.brain(83, "observer")
    row = verifier.frozen.tape()["mixed_test"][0]
    snapshot = model.snapshot()
    query = {
        "group": "correction",
        **model.settle(row["inputs"], targets={"past": row["actual_x"]}),
    }
    assert query["qualified"]
    verifier.replay_query(model, query, row)
    for field in ("state", "errors", "work", "qualified"):
        changed = copy.deepcopy(query)
        if field == "qualified":
            changed[field] = False
        elif field == "work":
            changed[field]["edge_visits"] += 1
        else:
            changed[field] = list(changed[field])
            changed[field][-1] += 0.01
        with pytest.raises(ValueError, match="fresh"):
            verifier.replay_query(model, changed, row)
    assert model.snapshot() == snapshot


def test_stationarity_tolerance_is_not_silently_relaxed():
    row = {
        "qualified": True,
        "stationarity": 1e-6,
        "work": {"edge_visits": 1},
        "wall_seconds": 0.1,
        "cpu_seconds": 0.1,
    }
    verifier.qualify(row)
    with pytest.raises(ValueError, match="qualification"):
        verifier.qualify({**row, "stationarity": 1.0000001e-6})
