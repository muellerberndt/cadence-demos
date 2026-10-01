"""Adversarial checks for the independent exposure verifier."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parents[1] / "temp/worktrees/cadence-060/examples"
sys.path.insert(0, str(EXAMPLES))
import credit_diagnostic as diagnostic  # noqa: E402
import credit_exposure as exposure  # noqa: E402
from cadence import Brain, Cortex  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "verify_exposure", HERE / "verify_exposure.py"
)
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def fixture():
    owner = diagnostic.make(2, 1)
    records, outcomes, work, status = diagnostic.collect(owner, 1, 0)
    assert status == "complete"
    return owner, dict(records=records, outcomes=outcomes), work


def test_collection_rng_action_reward_and_founder_are_independently_reproduced():
    owner, collection, work = fixture()
    records = verify.validate_collection(collection, 2, 0, 1)
    rebuilt, replay_work = verify.founder(Cortex, 2, 1, records)
    assert rebuilt.snapshot() == owner.brain.snapshot()
    assert replay_work == work
    bad = copy.deepcopy(collection)
    bad["outcomes"][0]["actions"][1] = 1 - bad["outcomes"][0]["actions"][1]
    with pytest.raises(ValueError, match="identity differs"):
        verify.validate_collection(bad, 2, 0, 1)


def test_schedule_verifier_rejects_equal_count_wrong_order_and_exposure_tampering():
    _, collection, _ = fixture()
    records = collection["records"]
    rows = diagnostic.schedule(records, 1000005, updates=512)
    schedules = dict(
        stratified=rows, reverse_stage=exposure.reverse_blocks(rows, records)
    )
    verify.validate_schedules(schedules, records, 2)
    bad = copy.deepcopy(schedules)
    bad["reverse_stage"][0][0], bad["reverse_stage"][31][-1] = (
        bad["reverse_stage"][31][-1],
        bad["reverse_stage"][0][0],
    )
    with pytest.raises(ValueError, match="order"):
        verify.validate_schedules(bad, records, 2)
    bad = copy.deepcopy(schedules)
    bad["reverse_stage"][0][0] = bad["reverse_stage"][31][-1]
    with pytest.raises(ValueError, match="exposure differs"):
        verify.validate_schedules(bad, records, 2)


def test_checkpoint_and_td_spot_check_reject_forged_values():
    owner, collection, _ = fixture()
    records = collection["records"]
    saved = json.loads(owner.snapshot())
    saved["config"]["credit_horizon"] = 1
    owner = diagnostic.Reinforcement.from_snapshot(json.dumps(saved))
    initial = owner.brain.snapshot()
    rows = diagnostic.schedule(records, 1000005, updates=1)[0]
    update = diagnostic.fit(owner, records, rows, "one_step")
    verify.validate_targets(Brain.from_snapshot(initial), update, records, 1)
    bad = copy.deepcopy(update)
    bad["targets"][0] += 0.01
    with pytest.raises(ValueError, match="Numerical mismatch"):
        verify.validate_targets(Brain.from_snapshot(initial), bad, records, 1)
    check = exposure.checkpoint(owner, records, dict(delay=1, preferred=0), 1)
    result = verify.validate_checkpoint(
        Brain.from_snapshot(owner.brain.snapshot()), check, records, 1, 0
    )
    assert result["free_decisions"] == 2
    bad = copy.deepcopy(check)
    bad["calibration"]["rows"][0]["observed_return"] += 0.01
    with pytest.raises(ValueError, match="Numerical mismatch"):
        verify.validate_checkpoint(
            Brain.from_snapshot(owner.brain.snapshot()), bad, records, 1, 0
        )
