import numpy as np

from patchworld.brain import FrozenMind, LiveMind, compose
from patchworld.genes import FOUNDER
from patchworld.world import Body, World


def live_for(mind, moments, detail_from):
    w = World(3)
    c = w.add_creature(Body())
    reward, out = None, None
    for t in range(moments):
        out = mind.moment(w.observe([c.id])[0], reward, detail=t >= detail_from)
        reward = w.step({c.id: out["action"]})[c.id]["reward"]
    return out


def test_the_brain_view_reads_the_settle_the_action_came_from():
    mind = LiveMind(compose(dict(FOUNDER, width=16, recall=True), seed=1))
    out = live_for(mind, 12, 10)
    b = out["brain"]
    assert b["frames"] and b["sweeps"] >= 1 and len(b["frames"]) == len(b["frame_sweeps"])
    final = b["frames"][-1]["motor"]
    assert int(np.argmax(final)) == out["action"] or out["mode"] == "aroused"  # sampled when aroused
    assert any(k.startswith("sensory:vision>") for k in b["tracts"])
    assert b["recall"]["slots"] == mind.brain.recall.capacity
    young = out["mode"] == "aroused"
    assert (b["changed"] > 0) == young or not young  # a young brain learns: synapses change


def test_reading_the_brain_changes_nothing():
    brain = compose(dict(FOUNDER, width=16), seed=2)
    twin = FrozenMind(brain)
    before = brain.learner.brain.efficacy.copy()
    out = live_for(twin, 6, 0)
    assert "frames" in out["brain"] and np.array_equal(before, brain.learner.brain.efficacy)
