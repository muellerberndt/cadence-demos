"""Mutation checks of independent Freeway promotion and exact replay equality."""

import copy

import pytest
import verify_atari_flat_bootstrap as v


def fixture():
    report = {"status": "complete", "sources_unchanged": True}
    episodes = [
        {
            "seed": s,
            "terminated": True,
            "truncated": False,
            "refused": False,
            "return": 8.0,
        }
        for s in v.a.PLAY_SEEDS
    ]
    baseline = [
        {
            "seed": s,
            "baseline": "teacher",
            "return": 10.0,
            "terminated": True,
            "truncated": False,
        }
        for s in v.a.PLAY_SEEDS
    ]
    held = [{"correct": True} for _ in range(512)]
    returned = [
        {"kind": "admission", "result": {"qualified": True, "accepted": True}}
        for _ in range(64)
    ]
    return report, episodes, baseline, held, returned, 0


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_seed",
        "truncation",
        "return",
        "unknown",
        "unqualified",
        "refused_admission",
        "missing_admission",
        "heldout",
        "source",
        "status",
        "teacher_censor",
    ],
)
def test_independent_gate_rejects_each_invalid_case(mutation):
    values = list(copy.deepcopy(fixture()))
    assert v.gate(*values)
    if mutation == "missing_seed":
        values[1].pop()
    elif mutation == "truncation":
        values[1][0]["truncated"] = True
    elif mutation == "return":
        values[1][0]["return"] = 7.99
    elif mutation == "unknown":
        values[-1] = 1
    elif mutation == "unqualified":
        values[4][0]["result"]["qualified"] = False
    elif mutation == "refused_admission":
        values[4][0]["result"]["accepted"] = False
    elif mutation == "missing_admission":
        values[4].pop()
    elif mutation == "heldout":
        values[3][0:27] = [{"correct": False}] * 27
    elif mutation == "source":
        values[0]["sources_unchanged"] = False
    elif mutation == "teacher_censor":
        values[2][0]["terminated"] = False
    else:
        values[0]["status"] = "time_limit"
    assert not v.gate(*values)


def test_exact_comparison_checks_numeric_outputs_and_parameter_hash():
    actual = {
        "outputs": {"motor": [0.2, 0.3, -0.1]},
        "parameters_sha256": "abc",
        "qualified": True,
    }
    v.same(actual, copy.deepcopy(actual), "same")
    changed = copy.deepcopy(actual)
    changed["outputs"]["motor"][0] += 1e-12
    with pytest.raises(ValueError, match="output"):
        v.same(actual, changed, "output")
    changed = {**actual, "parameters_sha256": "different"}
    with pytest.raises(ValueError, match="parameters"):
        v.same(actual, changed, "parameters")


def test_episode_flags_cannot_promote_censored_trace_by_forging_report():
    trace = [{"terminated": False, "truncated": False}]
    forged = {
        "terminated": True,
        "truncated": False,
        "censored": False,
        "refused": False,
    }
    with pytest.raises(ValueError, match="native end flags"):
        v.episode_flags(forged, trace, False)
    correct = {
        "terminated": False,
        "truncated": False,
        "censored": True,
        "refused": False,
    }
    v.episode_flags(correct, trace, False)
    with pytest.raises(ValueError, match="native refusal"):
        v.episode_flags(correct, trace, True)
