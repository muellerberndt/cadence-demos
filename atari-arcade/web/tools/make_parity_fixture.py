"""Record the library's answers for parity.mjs.

A miniature of the arcade layout (two 4x4 tiles, two columns, three observers,
motor and value outputs) is built, queried, taught in batches and driven through
the Reinforcement helper with the reference engine. Every number the browser
engine must reproduce is written to fixtures/parity_small.json. The full arcade
brains (seed 0, three and four actions) are built too, and their edges and
newborn weights are digested into fixtures/parity_arcade.json.

    PYTHONPATH=<cadence>/src python3 tools/make_parity_fixture.py
"""

from __future__ import annotations

import hashlib
import json
import random
import struct
import sys
from pathlib import Path

from cadence import Cortex, Reinforcement

ROOT = Path(__file__).resolve().parents[1]
TILE, GRID = 28, 3


def digest(values):
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


def small_brain():
    c = Cortex(seed=0, settle_budget=4096, parameter_prior=0.4)
    t0 = c.input("tile0", shape=(4, 4))
    t1 = c.input("tile1", shape=(4, 4))
    act = c.input("action", shape=(3,))
    c0 = c.column("t0", patches=4, inputs=t0)
    c1 = c.column("t1", patches=4, inputs=t1)
    r = c.observer("r", patches=3, observes=(c0, c1))
    p = c.observer("p", patches=4, observes=(c0, c1, r))
    v = c.observer("v", patches=2, inputs=(act,), observes=(r, p))
    c.output("motor", shape=(3,), reads=p)
    c.output("value", shape=(1,), reads=v)
    return c.build()


def arcade_brain(n_actions, seed=0):
    c = Cortex(seed=seed, settle_budget=4096, parameter_prior=0.4)
    tiles = [c.input(f"tile{i}", shape=(TILE, TILE)) for i in range(GRID * GRID)]
    act = c.input("action", shape=(n_actions,))
    cols = [c.column(f"t{i}", patches=8, inputs=tiles[i]) for i in range(GRID * GRID)]
    r = c.observer("r", patches=12, observes=tuple(cols))
    p = c.observer("p", patches=16, observes=tuple(cols) + (r,))
    v = c.observer("v", patches=8, inputs=(act,), observes=(r, p))
    c.output("motor", shape=(n_actions,), reads=p)
    c.output("value", shape=(1,), reads=v)
    return c.build()


def solve_record(res):
    return {
        "sweeps": res["sweeps"], "qualified": res["qualified"], "reason": res["reason"],
        "energy": res["energy"], "stationarity": res["stationarity"],
        "evaluations": res["work"]["evaluations"],
    }


def main():
    rng = random.Random(123)
    tiles = lambda: {"tile0": [rng.uniform(-0.6, 0.6) for _ in range(16)],
                     "tile1": [rng.uniform(-0.6, 0.6) for _ in range(16)]}
    zero = [0.0, 0.0, 0.0]
    b = small_brain()
    out = {"layout": b.inspect()["populations"], "edges": [list(e) for e in b.graph.edges],
           "residual_order": list(b.graph.residual_order), "weights0": list(b.weights)}
    # 1. a query
    q0 = tiles()
    res = b.settle({**q0, "action": zero}, budget=64)
    out["query0"] = {"inputs": q0, **solve_record(res), "state": list(res["state"]), "outputs": res["outputs"]}
    # 2. two witness batches
    batches = []
    for size in (3, 8):
        examples = []
        for _ in range(size):
            tt = tiles(); a = rng.randrange(3)
            examples.append(({**tt, "action": zero}, {"motor": [0.6 if j == a else -0.6 for j in range(3)]}))
        res = b.observe_batch(examples)
        batches.append({"examples": [[ex[0], ex[1]] for ex in examples], **solve_record(res),
                        "accepted": res["accepted"], "weights": list(b.weights), "biases": list(b.biases),
                        "outputs": [dict(o) for o in res["outputs"]]})
    out["batches"] = batches
    # 3. a query after learning
    q1 = tiles()
    res = b.settle({**q1, "action": zero}, budget=64)
    out["query1"] = {"inputs": q1, **solve_record(res), "state": list(res["state"]), "outputs": res["outputs"]}
    # 4. reinforcement
    rf = Reinforcement(b, actions=3, action_input="action", value_output="value", discount=0.95,
                       exploration=0.05, reward_scale=1.0, capacity=2048, batch_size=16, seed=0)
    steps = []
    situation = tiles()
    for k in range(8):
        picked = rf.act(situation, budget=256)
        reward = round(rng.uniform(-1, 1), 3)
        terminal = k == 7
        following = None if terminal else tiles()
        fb = rf.feedback(reward, following, terminal=terminal, learn=False)
        steps.append({"inputs": situation, "action": picked["action"], "values": list(picked["values"]),
                      "exploratory": picked.get("exploratory"), "reward": reward, "terminal": terminal,
                      "next": following, "transitions": fb["transitions"]})
        situation = following if following is not None else tiles()
    rp = rf.replay(budget=2048)
    out["reinforcement"] = {"steps": steps, "replay": {"indices": list(rp["indices"]), "targets": list(rp["targets"]),
                                                       "accepted": rp["accepted"], "sweeps": rp["sweeps"],
                                                       "updates": rp["updates"], "weights": list(b.weights)}}
    (ROOT / "fixtures/parity_small.json").write_text(json.dumps(out) + "\n")
    arcade = {}
    for n in (3, 4):
        brain = arcade_brain(n)
        g = brain.graph
        arcade[str(n)] = {"n_inputs": g.n_inputs, "n_patches": g.n_patches, "edges": len(g.edges),
                          "edge_digest": hashlib.sha256(json.dumps(g.edges).encode()).hexdigest(),
                          "residual_order_digest": hashlib.sha256(json.dumps(g.residual_order).encode()).hexdigest(),
                          "weights_digest": digest(brain.weights), "weights_head": list(brain.weights[:8]),
                          "populations": [{"name": p["name"], "indices": list(p["indices"])} for p in brain.inspect()["populations"]]}
    (ROOT / "fixtures/parity_arcade.json").write_text(json.dumps(arcade, indent=1) + "\n")
    print("wrote", ROOT / "fixtures/parity_small.json", ROOT / "fixtures/parity_arcade.json")


if __name__ == "__main__":
    main()
