"""False-green mutations and fresh-query checks; no accepted learning updates."""

import copy

import acquisition_controls as collector
import pytest
import verify_acquisition_controls as verifier


@pytest.fixture
def refused_gate(tmp_path, monkeypatch):
    # A single intentionally refused admission followed by genuine pure gate
    # queries gives a small portable receipt without training another model.
    monkeypatch.setattr(collector, "CHECKPOINTS", (1,))
    monkeypatch.setattr(verifier, "MILESTONES", (1,))
    original = collector.Brain.observe_batch

    def refuse(brain, examples, **options):
        return original(brain, examples, budget=0, **options)

    monkeypatch.setattr(collector.Brain, "observe_batch", refuse)
    protocol = collector.freeze(tmp_path)
    spec = protocol["cases"][0]
    report = collector.run_arm(tmp_path, spec, "ordinary", protocol, 1)
    assert report["admissions"] == 0 and report["refusals"] == 1
    assert report["status"] == "complete" and not report["gates"][0]["passed"]
    return tmp_path, spec


def verify_fixture(fixture, replay=False):
    root, spec = fixture
    data = collector.base.read(root / f"tape-{spec['condition']}.json")
    schedule = collector.base.read(root / f"replay-{spec['condition']}.json")
    founder = (root / f"founder-{spec['id']}-ordinary.json").read_text()
    return verifier.verify_arm(
        root, spec, "ordinary", data["development"], schedule, founder, 1, replay
    )


def test_refusal_is_not_learning_and_all_fresh_queries_are_reproduced(refused_gate):
    result = verify_fixture(refused_gate, replay=True)
    assert result["status"] == "complete" and result["refusals"] == 1
    assert result["admissions"] == result["admitted_presentations"] == 0
    assert result["attempted_presentations"] == 16
    assert result["replayed_queries"] == 164
    assert result["checkpoints_reloaded"] == 3
    assert not result["gates"][0]["passed"]


def test_gate_promotion_rejected_even_if_both_report_copies_change(refused_gate):
    root, spec = refused_gate
    folder = root / "results" / spec["id"] / "ordinary"
    payload = collector.base.read(folder / "gate-1.json")
    payload["score"]["passed"] = True
    collector.base.atomic(folder / "gate-1.json", payload)
    report = collector.base.read(folder / "report.json")
    report["gates"][0]["passed"] = True
    collector.base.atomic(folder / "report.json", report)
    with pytest.raises(ValueError, match="gate promotion"):
        verify_fixture(refused_gate)


@pytest.mark.parametrize(
    "field", ["attempted_presentations", "admitted_presentations", "presentations"]
)
def test_exposure_promotion_rejected(refused_gate, field):
    root, spec = refused_gate
    path = root / "results" / spec["id"] / "ordinary/report.json"
    report = collector.base.read(path)
    report[field] += 16
    collector.base.atomic(path, report)
    with pytest.raises(ValueError, match=field):
        verify_fixture(refused_gate)


def test_replay_rejects_fabricated_settled_forecast(refused_gate):
    root, spec = refused_gate
    folder = root / "results" / spec["id"] / "ordinary"
    checkpoint = collector.base.read(folder / "checkpoint-1.json")
    brain = collector.Brain.from_snapshot(checkpoint["brain"])
    rows = collector.base.read(root / "tape-fixed_positive.json")["development"]
    query = collector.base.read(folder / "gate-1.json")["queries"][0]
    query["state"][-2] += 0.1
    query["future"][0] += 0.1
    with pytest.raises(ValueError, match="fresh query state"):
        verifier.replay_queries(brain, rows, [query])
    assert brain.snapshot() == checkpoint["brain"]


def test_timeout_receipt_retains_attempted_but_unadmitted_rows(tmp_path, monkeypatch):
    protocol = collector.freeze(tmp_path)
    spec = protocol["cases"][0]

    def timeout(operation, remaining):
        raise collector.base.ArmTimeout("fixture timer")

    monkeypatch.setattr(collector.base, "limited_call", timeout)
    collector.run_arm(tmp_path, spec, "ordinary", protocol, 512)
    data = collector.base.read(tmp_path / "tape-fixed_positive.json")
    result = verifier.verify_arm(
        tmp_path,
        spec,
        "ordinary",
        data["development"],
        collector.base.read(tmp_path / "replay-fixed_positive.json"),
        (tmp_path / f"founder-{spec['id']}-ordinary.json").read_text(),
        512,
        False,
    )
    assert result["status"] == "censored" and result["unknown_work_calls"] == 1
    assert result["admissions"] == 0 and result["attempted_presentations"] == 16
    assert len(result["gates"]) == 3 and all(
        g["status"] == "missing" for g in result["gates"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["arm_censor", "case_incomplete", "outer_censor", "refusal", "gate_fail"],
)
def test_selection_never_uses_incomplete_or_failed_pair(mutation):
    case = {
        "spec": {
            "role": "development",
            "condition": "balanced_mixed",
            "layout": "small",
            "parameter_prior": 0.1,
            "parameters": 34,
        },
        "verification": "verified",
        "case_status": "complete",
        "execution": {"returncode": 0},
        "arms": [
            {
                "status": "complete",
                "refusals": 0,
                "gates": [
                    {"status": "complete", "update_attempts": 32, "passed": True}
                ],
            }
            for _ in range(2)
        ],
    }
    assert verifier.choose([case])["updates"] == 32
    changed = copy.deepcopy(case)
    if mutation == "arm_censor":
        changed["arms"][0]["status"] = "censored"
    elif mutation == "case_incomplete":
        changed["case_status"] = "incomplete"
    elif mutation == "outer_censor":
        changed["execution"]["returncode"] = 124
    elif mutation == "refusal":
        changed["arms"][0]["refusals"] = 1
    else:
        changed["arms"][0]["gates"][0]["passed"] = False
    assert verifier.choose([changed]) is None
