"""Settle cases from the library for the browser engine's parity test (tests/parity.mjs)."""
from __future__ import annotations

import json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cadence-examples"))
from engine.export import settle_cases  # noqa: E402
from connectome_compiler import compile, brain  # noqa: E402
from connectome_compiler.sources import zebrafish_brainstem as zb  # noqa: E402
from connectome_compiler.verify.burst import GRADED_UNIT  # noqa: E402

rec = json.loads(Path("receipts/brain_export.json").read_text())
t = zb.load(scope=rec["scope"]); c = compile(t)
P = {k: np.array(v) for k, v in c.populations.items()}
lg = np.zeros(c.n); lg[P["_Axl_"]] = -rec["axial_attenuation"]
b = brain(c, rec["gain"], backend="cpu", log_gain=lg, **GRADED_UNIT)
stimuli = {"integrator": {"_Int_": 0.03}, "vestibular": {"_DOs_": 0.3}, "motor_submodule": {"_Int_": 0.01, "_DOs_": 0.01}, "abducens": {"ABD_m": 0.2}, "periphery": {"periphery": 0.01}}
readouts = ["_Int_", "ABD_m", "ABD_i", "_DOs_", "_Axl_", "vSPNs", "periphery"]
out = settle_cases(b, stimuli, readouts, steps=120, out="tests/parity_cases.json")
print("cases", len(out["cases"]), "steps", out["steps"], "final active", [c_["final_active"] for c_ in out["cases"]])
