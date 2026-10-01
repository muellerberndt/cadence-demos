"""Fresh confirmation ownership and boundaries; no learning or launch."""

import copy
import platform

import innovation_confirmation as confirmation
import pytest
import shared_innovation as development


@pytest.mark.parametrize("condition", development.CONDITIONS)
def test_new_tape_is_independent_and_boundary_equations_are_unchanged(condition):
    old, new = development.tape(condition), confirmation.tape(condition)
    old_inputs = {
        (r["inputs"]["u"][0], r["inputs"]["v"][0])
        for rows in old.values()
        for r in rows
    }
    new_inputs = {
        (r["inputs"]["u"][0], r["inputs"]["v"][0])
        for rows in new.values()
        for r in rows
    }
    assert not old_inputs & new_inputs
    assert new == confirmation.tape(condition)
    train = {
        (r["inputs"]["u"][0], r["inputs"]["v"][0])
        for phase in ("clean", "mixed")
        for r in new[phase]
    }
    for phase in ("clean_test", "mixed_test"):
        assert not train & {
            (r["inputs"]["u"][0], r["inputs"]["v"][0]) for r in new[phase]
        }
    for rows in new.values():
        for row in rows:
            assert row == development.body(
                row["inputs"]["u"][0], row["inputs"]["v"][0], row["delta"], row["id"]
            )
            forged = copy.deepcopy(row)
            forged["actual_y"], forged["delta"] = [-0.9], 100
            assert development.query(forged) == development.query(row)


def test_confirmation_seeds_and_founders_are_separate_but_exactly_paired():
    assert confirmation.SEEDS == (61, 67, 71, 73, 79)
    assert not set(confirmation.SEEDS) & set(development.SEEDS)
    for seed in confirmation.SEEDS:
        pair = development.founders(seed)
        models = [development.Brain.from_snapshot(pair[a]) for a in development.ARMS]
        assert models[0].weights == models[1].weights
        assert all(
            m.config["seed"] == seed and len(m.weights) + len(m.biases) == 9
            for m in models
        )


def test_fresh_freeze_records_primary_protocol_source_ownership_and_no_launch(tmp_path):
    old, new = tmp_path / "old", tmp_path / "confirmation"
    development.freeze(old)
    # Freeze-only fixture: the file supplies a completed source-run marker;
    # no comparison, query or learning call is executed by this test.
    development.custody.atomic(old / "execution.json", [])
    confirmation.freeze(new, old)
    protocol = confirmation.validate(new)
    assert protocol["schema"] == "shared-innovation-confirmation/1"
    assert (
        protocol["primary_condition"] == "narrow"
        and protocol["primary_checkpoint"] == 32
    )
    assert protocol["required_clean_checks"] == [0, 32, 128]
    assert (
        protocol["seeds"] == list(confirmation.SEEDS)
        and protocol["data_seed"] == 20261006
    )
    assert protocol["platform"] == platform.platform()
    assert protocol["development_protocol_sha256"] == development.custody.sha(
        old / "protocol.json"
    )
    assert not (new / "launch.json").exists() and not (new / "execution.json").exists()
    changed = copy.deepcopy(protocol)
    changed["confirmation_source_sha256"] = "0" * 64
    development.custody.atomic(new / "protocol.json", changed)
    with pytest.raises(ValueError, match="confirmation source changed"):
        confirmation.validate(new)
    with pytest.raises(FileExistsError):
        confirmation.freeze(new, old)
