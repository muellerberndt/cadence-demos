"""Verifier mutations target false eligibility and causal/custody corruption."""

import copy
import json

import pytest
import self_correction as collector
import verify_self_correction as verifier


@pytest.fixture
def censored_case(tmp_path, monkeypatch):
    out = tmp_path / "seed2"
    protocol = collector.freeze(out, 2)
    calls = 0

    def two_calls(operation, remaining):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise collector.ArmTimeout("fixture interruption")
        return operation()

    monkeypatch.setattr(collector, "limited_call", two_calls)
    report = collector.run_arm(
        out, "ordinary", protocol, collector.make_tape(), collector.schedule()
    )
    assert report["status"] == "censored"
    return out


def rewrite_calls(out, mutate):
    path = out / "ordinary/calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(calls)
    path.write_text("".join(collector.encoded(c) + "\n" for c in calls))
    report_path = out / "ordinary/report.json"
    report = collector.read(report_path)
    report["ledger_sha256"] = collector.sha(path)
    collector.atomic(report_path, report)


def test_real_censored_checkpoint_verifies_and_all_seeds_survive(censored_case):
    result = verifier.verify_campaign(censored_case.parent)
    assert result["valid"] and result["verdict"] == "inconclusive"
    assert [c["seed"] for c in result["cases"]] == list(verifier.SEEDS)
    case = result["cases"][0]
    assert case["verification"] == "verified"
    ordinary, observer = case["arms"]
    assert ordinary["status"] == "censored" and ordinary["checkpoints_reloaded"] == 2
    assert ordinary["work"]["unknown_work_calls"] == 1
    assert observer["status"] == "missing"
    assert all(c["verification"] == "missing" for c in result["cases"][1:])


@pytest.mark.parametrize(
    "mutation", ["order", "qualification", "error", "custody", "clamp"]
)
def test_rehashed_ledger_tampering_is_rejected(censored_case, mutation):
    def mutate(calls):
        c = calls[0]
        if mutation == "order":
            c["phase"] = "probe"
        elif mutation == "qualification":
            c["result"]["qualified"] = not c["result"]["qualified"]
        elif mutation == "error":
            c["position_error"] += 0.01
        elif mutation == "custody":
            c["after_brain_sha256"] = "0" * 64
        else:
            c["result"]["state"][2] += 0.01

    rewrite_calls(censored_case, mutate)
    with pytest.raises(ValueError):
        verifier.verify_case(censored_case)


def test_gate_promotion_and_fake_complete_are_rejected(censored_case):
    path = censored_case / "ordinary/report.json"
    original = collector.read(path)
    for field in ("gate", "status"):
        changed = copy.deepcopy(original)
        if field == "gate":
            changed["gate"]["passed"] = True
        else:
            changed["status"] = "complete"
        collector.atomic(path, changed)
        with pytest.raises(ValueError):
            verifier.verify_case(censored_case)


def test_initial_founder_and_future_tape_mutations_rejected(censored_case):
    protocol_path = censored_case / "protocol.json"
    original = collector.read(protocol_path)
    path = censored_case / "tape.json"
    tape = collector.read(path)
    tape["test"][24]["future"][0] += 0.1
    collector.atomic(path, tape)
    changed = copy.deepcopy(original)
    changed["tape_sha256"] = collector.sha(path)
    collector.atomic(protocol_path, changed)
    with pytest.raises(ValueError, match="tape differs"):
        verifier.verify_case(censored_case)
    collector.atomic(path, collector.make_tape())
    founder = censored_case / "founder-observer.json"
    data = collector.read(founder)
    data["weights"][0] += 0.01
    founder.write_text(collector.encoded(data))
    original["founders"]["observer"] = collector.sha(founder)
    collector.atomic(protocol_path, original)
    with pytest.raises(
        ValueError, match="initialization differs|without an admitted event"
    ):
        verifier.verify_case(censored_case)


def test_source_bytes_cannot_be_bypassed_by_recorded_hash(censored_case):
    protocol = collector.read(censored_case / "protocol.json")
    key = next(k for k in protocol["sources"] if k.endswith("brain.py"))
    protocol["sources"][key] = "0" * 64
    with pytest.raises(ValueError, match="source inventory"):
        verifier.source_check(protocol)


def test_recovery_recomputed_without_producer_metrics():
    calls = []
    for i in range(128):
        calls.append(
            {
                "ordinal": len(calls),
                "kind": "forecast",
                "phase": "test",
                "index": i,
                "status": "returned",
                "seconds": 0.1,
                "position_error": 0.2 if i in verifier.SWITCHES else 0.01,
                "causal_oracle_error": 0.2 if i in verifier.SWITCHES else 0.0,
                "result": {"qualified": True, "work": {"evaluations": 3}},
            }
        )
        calls.append(
            {
                "ordinal": len(calls),
                "kind": "admission",
                "phase": "test",
                "index": i,
                "status": "returned",
                "seconds": 0.2,
                "result": {
                    "qualified": True,
                    "accepted": True,
                    "work": {"evaluations": 4},
                },
            }
        )
    record = verifier.recovery(calls)[0]
    assert record["first_informed_forecast"] == 24
    assert record["unavoidable_first_error"]["position_error"] == 0.2
    assert record["windows"]["8"]["position_mae"] == 0.01
    recovered = record["recovered"]
    assert recovered["confirmed_at"] == 26 and recovered["admissions"] == 3
    assert recovered["work"]["evaluations"] == 21
    assert recovered["including_first_forecast"]["work"]["evaluations"] == 24
    calls[48]["position_error"] = None
    calls[48]["result"]["qualified"] = False
    record = verifier.recovery(calls)[0]
    assert not record["windows"]["1"]["complete"]
    assert record["recovered"]["confirmed_at"] == 27


def test_empty_campaign_cannot_produce_eligible_comparison(tmp_path):
    result = verifier.verify_campaign(tmp_path)
    assert result["valid"] and result["verdict"] == "inconclusive"
    assert len(result["cases"]) == 5


@pytest.mark.parametrize("budget", [0, None])
def test_actual_witness_admission_or_refusal_and_forged_targets(budget):
    tape = collector.make_tape()
    brain = collector.make_brain(2, "ordinary")
    before = collector.digest(brain.snapshot())
    result = brain.observe(
        *collector.witness(tape["test"][0]), source="witness", budget=budget
    )
    assert result["accepted"] is (budget is None)
    call = {
        "kind": "admission",
        "phase": "test",
        "index": 0,
        "indices": [0],
        "row_ids": ["test:0"],
        "before_brain_sha256": before,
        "after_brain_sha256": collector.digest(brain.snapshot()),
        "seconds": 0.01,
        "status": "returned",
        "result": result,
    }
    expected = ("admission", "test", 0, [0])
    _, admissions = verifier.verify_call(call, expected, tape, before, 0)
    assert admissions == int(result["accepted"])
    forged = copy.deepcopy(call)
    forged["result"]["state"] = list(forged["result"]["state"])
    forged["result"]["state"][4] += 0.1
    with pytest.raises(ValueError, match="witness state clamps"):
        verifier.verify_call(forged, expected, tape, before, 0)


def test_probe_after_forecast_before_changed_transition_admission():
    sequence = verifier.expected_calls()
    for switch in verifier.SWITCHES:
        i = sequence.index(("forecast", "test", switch, [switch]))
        assert sequence[i + 1] == ("forecast", "probe", switch + 1, [switch + 1])
        assert sequence[i + 2] == ("admission", "test", switch, [switch])
        assert sequence[i + 3] == ("forecast", "test", switch + 1, [switch + 1])


def test_outer_censor_keeps_partial_tail_and_unknown_inflight_work(censored_case):
    folder = censored_case / "ordinary"
    ledger = folder / "calls.jsonl"
    calls = [json.loads(line) for line in ledger.read_text().splitlines()]
    ledger.write_text(collector.encoded(calls[0]) + '\n{"ordinal":1')
    inflight = {
        key: calls[1][key]
        for key in (
            "ordinal",
            "kind",
            "phase",
            "index",
            "indices",
            "row_ids",
            "before_brain_sha256",
        )
    }
    collector.atomic(folder / "inflight.json", inflight)
    (folder / "report.json").unlink()
    collector.atomic(
        censored_case / "process-timeout.json",
        {
            "status": "censored",
            "seconds": 360,
            "reason": "outer process cap",
            "protocol_sha256": collector.sha(censored_case / "protocol.json"),
        },
    )
    result = verifier.verify_case(censored_case)
    assert result["verification"] == "verified" and result["verdict"] == "inconclusive"
    assert result["process_censor"]["status"] == "censored"
    assert result["arms"][0]["partial_ledger_tail"]
    assert result["arms"][0]["unlogged_call_work_unknown"]
    assert result["arms"][0]["status"] == "incomplete"
