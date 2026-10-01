"""Read-only topology/cap checks; no learning or quality selection."""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

P = Path(__file__).with_name("amen_architecture_calibrate.py")
spec = importlib.util.spec_from_file_location("ordinary_probe", P)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


@pytest.mark.parametrize("width,total", [(64, 47870), (256, 174014)])
def test_native_ordinary_graph_has_hidden_interaction_and_same_inputs(width, total):
    app = Path(
        os.environ.get(
            "AMEN_APP", str(Path(__file__).resolve().parents[2] / "cadence-amen")
        )
    )
    M, _T = A.modules(app)
    brain = A.build(M, width)
    assert len(brain.weights) + len(brain.biases) == total
    assert brain.inspect()["patches"] == width + 71
    assert brain.inspect()["input_samples"] == 585
    A.require_ordinary(brain)
    assert sum(kind == "state" for kind, _, _ in brain.graph.edges) == width * 71
    assert brain.inspect()["admissions"] == 0
    assert brain.inspect()["last_event_id"] == -1
    assert len(brain.inspect()["populations"]) == 2
    assert brain.config["parameter_prior"] == 0.4
    assert brain.config["state_prior"] == 0.01


def test_rejects_residual_readback_contacts():
    brain = SimpleNamespace(graph=SimpleNamespace(edges=[("residual", 0, 1)]))
    with pytest.raises(ValueError, match="observer"):
        A.require_ordinary(brain)
