"""Learning cases from the library for the browser engine's learning parity test
(tests/learning_parity.mjs): the library's default free/nudged rule (docs/learning.md) on the
whole oculomotor net, every synapse and every bias plastic, reciprocal pairs sharing one
efficacy, a centred quadratic nudge on the integrator neurons toward the state they held when
a saccade's burst ended. Three saccades, a lesson after each, from a gain below the selected
one (the leaky start of the learning page).

    CONNECTOME_DATA=../connectome-research/data PYTHONPATH=../cadence-connectome-compiler/src \\
        ../cadence/.venv/bin/python tools/learning_cases.py
"""
from __future__ import annotations

import base64, json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cadence-examples"))
from engine.export import dense_drive  # noqa: E402
from connectome_compiler import compile, brain  # noqa: E402
from connectome_compiler.sources import zebrafish_brainstem as zb  # noqa: E402
from connectome_compiler.verify.burst import GRADED_UNIT  # noqa: E402
from cadence.learning import Learner, LearnerConfig  # noqa: E402

START = 0.8            # the learning page starts at this fraction of the selected gain: a leaky integrator
BURST_STEPS, BURST_LEVEL, DRIFT_STEPS = 5, 0.1, 25   # the demo's saccade, and one second of drift before the lesson
CFG = dict(nudge="quadratic", centered=True, beta=0.1, eta=0.2, nudged_steps=50, tolerance=1e-4)  # library defaults except the nudge

b64 = lambda a: base64.b64encode(np.ascontiguousarray(np.asarray(a, dtype=np.float64)).tobytes()).decode("ascii")
payload = json.loads(Path("web/data/brain_oculomotor.json").read_text())
gain = START * payload["gain"]
t = zb.load(scope="oculomotor"); c = compile(t)
b = brain(c, gain, backend="cpu", **GRADED_UNIT)
C = b.connectome
Int = [int(i) for i in C.populations["_Int_"]]
cfg = LearnerConfig(**CFG)
learner = Learner(b, outputs=Int, config=cfg)   # defaults: every synapse and bias plastic, reciprocal pairs
assert learner.plastic_synapses.all() and learner.plastic_neurons.all() and learner.reciprocal
burst = dense_drive(b, {"_Int_": BURST_LEVEL}); zero = np.zeros(C.n)
mean_int = lambda s: float(np.asarray(s)[Int].mean())
lessons, state = [], None
for k in range(3):
    s1 = learner.brain.settle_batch(burst[None, :], steps=BURST_STEPS, state=state)
    target = s1.activation[0].copy()
    free = learner.brain.settle_batch(zero[None, :], steps=DRIFT_STEPS, state=s1)
    nudged = learner.nudged(zero[None, :], free, target[None, :], sign=1.0)
    opposite = learner.nudged(zero[None, :], free, target[None, :], sign=-1.0)
    report = learner.update(free, nudged, opposite)
    lessons.append({
        "burst_end_int": mean_int(s1.activation[0]), "free_int": mean_int(free.activation[0]),
        "nudged_int": mean_int(nudged.activation[0]), "opposite_int": mean_int(opposite.activation[0]),
        "nudged_steps": int(nudged.steps), "opposite_steps": int(opposite.steps),
        "scale_step": report["scale_step"], "bias_step": report["bias_step"],
        "efficacy": b64(learner.brain.efficacy), "bias": b64(learner.brain.bias),
        "efficacy_abs_mean": float(np.abs(learner.brain.efficacy).mean()), "efficacy_max": float(np.abs(learner.brain.efficacy).max()),
        "paired_synapses": int(len(learner._paired)),
    })
    state = free
    print(f"lesson {k + 1}: burst end {lessons[-1]['burst_end_int']:.6f} free {lessons[-1]['free_int']:.6f} nudged {lessons[-1]['nudged_int']:.6f} ({nudged.steps} steps) opposite {lessons[-1]['opposite_int']:.6f} ({opposite.steps} steps) | scale step {report['scale_step']:.3e} bias step {report['bias_step']:.3e} | efficacy mean {lessons[-1]['efficacy_abs_mean']:.6f} max {lessons[-1]['efficacy_max']:.4f}")
out = {"format": "cadence.learning-cases/1", "payload": "web/data/brain_oculomotor.json", "start_gain_factor": START, "gain": gain,
       "burst": {"population": "_Int_", "level": BURST_LEVEL, "steps": BURST_STEPS}, "drift_steps": DRIFT_STEPS, "outputs": "_Int_",
       "config": {**CFG, "eta_bias": cfg.eta_bias, "scale_cap": cfg.scale_cap, "reciprocal": True, "plastic": "every synapse and every bias"},
       "connectome_digest": payload["connectome_digest"], "lessons": lessons}
Path("tests/learning_cases.json").write_text(json.dumps(out))
print("wrote tests/learning_cases.json:", len(lessons), "lessons, paired synapses", lessons[0]["paired_synapses"], "of", C.synapses)
