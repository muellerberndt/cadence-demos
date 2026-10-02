"""Record the library's answers for parity.mjs.

Brains are composed with the released ``cadence-net==0.70.0`` exactly as ``server.py``
composes them. Their newborn efficacies are digested (three and four actions), and two
tapes are driven through the calls the arcade makes: watched lessons (a greedy answer,
then ``learner.step`` with the teacher's label), decisions with rewards and an episode
end through ``brain.step``, a frozen stretch of ``brain.act`` and a reset. One tape is a
small brain whose every parameter is recorded; the other is the arcade's size, recorded
as sums and a sample. Screens come from an integer formula both sides can compute.

    python tools/make_parity_fixture.py        (from atari-arcade/web, in the demo's venv)
"""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path

import numpy as np

from cadence import ActorCriticConfig, Brain, LearnerConfig

ROOT = Path(__file__).resolve().parents[1]
LEARNING = dict(beta=0.1, temperature=0.2, tolerance=3e-3, free_steps=1024, nudged_steps=12,
                eta_bias=0.02, eta=0.003, momentum=0.9, normalize=0.99, normalize_floor=1e-4)
REWARD = dict(gamma=0.97, lam=0.9, eta=0.001, eta_critic=0.3, momentum=0.9, normalize=0.99)


def compose(inputs: int, actions: int, seed: int = 0) -> Brain:
    return Brain.compose(inputs, actions, seed=seed, learning=LearnerConfig(**LEARNING),
                         reward=ActorCriticConfig(**REWARD))


def screen(t: int, n: int) -> np.ndarray:
    """A sparse picture with a few bright and a few dim pixels that move with ``t``."""
    x = np.zeros(n)
    for i in range(n):
        h = (i * 73 + t * 151) % 997
        if h < 9:
            x[i] = 0.2 + 0.09 * h
        elif h > 990:
            x[i] = -0.04
    return x[None, :]


def blocks(brain: Brain) -> dict[str, list[float]]:
    """Efficacies by projection, in the order the browser engine keeps them."""
    graph, weights = brain.connectome, np.asarray(brain.brain.efficacy)
    pop = {k: np.asarray(v) for k, v in graph.populations.items()}
    dense = np.zeros((graph.n, graph.n))
    dense[graph.pre, graph.post] = weights
    s, h, p, m = pop["sensory"], pop["association"], pop["prefrontal"], pop["motor"]
    return {"sa": dense[np.ix_(s, h)].ravel().tolist(), "am": dense[np.ix_(h, m)].ravel().tolist(),
            "ma": dense[np.ix_(m, h)].ravel().tolist(), "pa": dense[np.ix_(p, h)].ravel().tolist(),
            "mm": dense[np.ix_(m, m)].ravel().tolist()}


def summary(brain: Brain, full: bool) -> dict:
    graph = brain.connectome
    pop = {k: np.asarray(v) for k, v in graph.populations.items()}
    bias = np.asarray(brain.brain.bias)
    efficacy = np.asarray(brain.brain.efficacy)
    out = {
        "bias_association": bias[pop["association"]].tolist(),
        "bias_motor": bias[pop["motor"]].tolist(),
        "critic": brain.basal_ganglia.w_critic.tolist() + [float(brain.basal_ganglia.b_critic)],
        "working_trace": brain.working_memory.trace.ravel().tolist(),
        "memory_sum": float(brain.hippocampus.consolidated.sum()),
        "memory_abs": float(np.abs(brain.hippocampus.consolidated).sum()),
        "efficacy_sum": float(efficacy.sum()),
        "efficacy_abs": float(np.abs(efficacy).sum()),
        "efficacy_sample": efficacy[::max(1, len(efficacy) // 1500)].tolist(),
    }
    if full:
        out["blocks"] = blocks(brain)
        out["memory"] = brain.hippocampus.consolidated.ravel().tolist()
    return out


def tape(inputs: int, actions: int, full: bool, watch: int, play: int, frozen: int) -> dict:
    brain = compose(inputs, actions)
    motor = np.asarray(brain.motor_index)
    events, t = [], 0
    for _ in range(watch):
        x, label = screen(t, inputs), (t * 2 + 1) % actions
        drive = brain.stimulus(x)
        own = int(brain.act(x, greedy=True)[0])
        state = brain.basal_ganglia.state
        _, report = brain.learner.step(drive, np.array([label]))
        events.append({"kind": "watch", "t": t, "label": label, "own": own,
                       "motor": state.activation[0, motor].tolist(),
                       "free_steps": int(report["free_steps"]), "nudged_steps": int(report["nudged_steps"])})
        t += 1
    pending = False
    for k in range(play):
        x = screen(t, inputs)
        reward, done = float([0, 1, 0, 0, -1, 0, 1, 0][k % 8]), k == play // 2
        if pending:
            action = int(brain.step(x, reward=np.array([reward]), done=np.array([done]))[0])
        else:
            action = int(brain.step(x)[0])
        state = brain.basal_ganglia.state
        events.append({"kind": "play", "t": t, "reward": reward if pending else None, "done": done if pending else None,
                       "action": action, "motor": state.activation[0, motor].tolist(),
                       "value": float(brain.basal_ganglia.value(state)[0]),
                       "dopamine": brain.last_learning.get("dopamine"),
                       "td_error": brain.last_learning.get("td_error"),
                       "free_steps": brain.last_learning.get("free_steps")})
        pending = True
        t += 1
    middle = summary(brain, full)
    brain.reset()
    for _ in range(frozen):
        x = screen(t, inputs)
        action = int(brain.act(x)[0])
        events.append({"kind": "frozen", "t": t, "action": action,
                       "motor": brain.basal_ganglia.state.activation[0, motor].tolist()})
        t += 1
    return {"inputs": inputs, "actions": actions, "watch": watch, "play": play, "frozen": frozen,
            "events": events, "after_play": middle, "after_frozen": summary(brain, False)}


def main() -> None:
    births = {}
    for actions in (3, 4):
        brain = compose(84 * 84, actions)
        efficacy = np.ascontiguousarray(brain.brain.efficacy, dtype="<f8")
        births[str(actions)] = {"neurons": int(brain.connectome.n), "synapses": int(brain.connectome.synapses),
                                "efficacy_sha256": hashlib.sha256(efficacy.tobytes()).hexdigest()}
    rng = np.random.default_rng(0)
    fixture = {
        "library": metadata.version("cadence-net"),
        "numpy": np.__version__,
        "learning": LEARNING, "reward": REWARD,
        "generator": {"seed": 0, "first": [rng.random() for _ in range(4)]},
        "births": births,
        "small": tape(48, 3, True, 10, 24, 4),
        "arcade": tape(84 * 84, 3, False, 6, 12, 2),
    }
    out = ROOT / "fixtures" / "parity_system1.json"
    out.write_text(json.dumps(fixture))
    print(out, out.stat().st_size, "bytes", births)


if __name__ == "__main__":
    main()
