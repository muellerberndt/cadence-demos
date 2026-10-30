import numpy as np

from arm.anatomy import Anatomy, Stage, build, raising_config
from arm.eyes import Eyes, HeadSpec
from arm.life import Life, summarize
from arm.world import ArmSpec, World


def tiny_brain():
    head = HeadSpec(size=16, eyes=2)
    anatomy = Anatomy(size=16, channels=head.channels, hidden=32, stages=(Stage(4, 5, 2),), sheet=6)
    brain = build(anatomy, seed=0, memory_choice=True, memory_context=0.5, memory_rate=0.5, memory_replay=8,
                  memory_demonstrations=1.0, memory_expansion=256, memory_winners=8, arousal=True)
    raising_config(brain)
    return brain, head


def test_life_runs_every_mode_and_waits():
    brain, head = tiny_brain()
    world, eyes = World(ArmSpec(), seed=1), Eyes(head)
    life = Life(brain, world, eyes, waits=2)
    rows = life.run(3, "shown") + life.run(3, "corrected") + life.run(3, "alone")
    assert len(rows) == 9
    assert all((r["own"] is None) == r["refused"] for r in rows)  # a refusal is counted, never hidden
    assert sum(r["own"] is not None for r in rows) >= 6
    assert rows[0]["taught"] and all(r["mode"] == "alone" and not r["taught"] for r in rows[6:])
    s = summarize(rows)
    assert s["decisions"] == 9 and 0.0 <= (s["agreement"] or 0.0) <= 1.0


def test_shown_moments_execute_the_caregiver():
    brain, head = tiny_brain()
    world, eyes = World(ArmSpec(), seed=2), Eyes(head)
    life = Life(brain, world, eyes)
    before = world.tip().copy()
    rows = life.run(12, "shown")
    assert np.linalg.norm(world.tip() - before) > 0.01  # the caregiver moved the arm
    assert all(r["want"] is not None and len(r["want"]) == 5 for r in rows)


def test_live_continuation_after_teaching():
    brain, head = tiny_brain()
    world, eyes = World(ArmSpec(), seed=3), Eyes(head)
    life = Life(brain, world, eyes, continuation="live")
    life.run(2, "shown")
    rows = life.run(3, "alone")
    assert len(rows) == 3
