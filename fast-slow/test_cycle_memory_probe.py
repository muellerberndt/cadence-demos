"""Pure derivative, control and freeze tests; no learning."""

import cycle_memory_probe as probe
import pytest


def test_scalar_equation_has_correct_state_cycle_and_parameter_derivatives():
    for gain in probe.GAINS:
        for state in (-0.91, -0.15, 0.0, 0.15, 0.91):
            for cue in probe.CUES:
                result = probe.scalar_audit(cue, state, 2.0, gain, 0.0)
                assert result["finite_difference_max_abs_error"] < 5e-8
                assert result["energy"] >= 0
    assert probe.scalar_audit(0.0, 0.0, 2.0, 2.0, 0.0)["energy"] == 0


def test_teacher_clamp_changes_posterior_without_derivative_error():
    result = probe.teacher_audit()
    prior, observed, teacher = result["cases"]
    assert all(r["qualified"] for r in result["cases"])
    assert all(r["finite_difference_max_abs_error"] < 5e-8 for r in result["cases"])
    assert observed["errors"][1] == pytest.approx(0.02013849339176, abs=1e-11)
    assert teacher["errors"][1] == pytest.approx(0.1863863326387, abs=1e-11)
    assert prior["errors"] == (0.0, 0.0, 0.0)


def test_protocol_predeclares_every_gene_and_control_without_running(tmp_path):
    root = tmp_path / "frozen"
    probe.freeze(root)
    p = probe.read(root / "protocol.json")
    assert p["gains"] == list(probe.GAINS)
    assert p["blank_delays"] == [1, 8, 128]
    assert len(p["cases"]) == 14
    assert p["sources"] == probe.sources()
    assert not (root / "calls.jsonl").exists()
    with pytest.raises(FileExistsError):
        probe.freeze(root)


def test_changed_frozen_gene_inventory_cannot_run(tmp_path):
    root = tmp_path / "frozen"
    probe.freeze(root)
    protocol = probe.read(root / "protocol.json")
    protocol["gains"] = [2.0]
    probe.write(root / "protocol.json", protocol)
    with pytest.raises(ValueError, match="frozen design"):
        probe.run(root)
    assert not (root / "calls.jsonl").exists()
