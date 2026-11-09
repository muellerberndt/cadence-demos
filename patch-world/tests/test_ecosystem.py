import copy

import numpy as np

from patchworld.ecosystem import Ecosystem, LocalMinds, run
from patchworld.genes import FOUNDER
from patchworld.world import Rules


def founders(n=3):
    return [{"genes": dict(FOUNDER, width=16), "lineage": i} for i in range(n)]


def test_population_runs_with_controls():
    eco = Ecosystem(1, Rules(predators=0), founders=founders(), cap=4, frozen=1, random=1)
    minds = LocalMinds(seed=1)
    minds.born(eco.populate())
    kinds = sorted(lf.kind for lf in eco.lives.values())
    assert kinds == ["frozen", "live", "live", "live", "random"]
    run(eco, minds, 30)
    assert eco.world.t == 30
    assert set(minds.minds) == {cid for cid, lf in eco.lives.items() if lf.died is None}


def test_a_child_inherits_its_parents_brain_and_mutated_genes():
    eco = Ecosystem(2, Rules(predators=0), founders=founders(1), cap=3, frozen=0, random=0)
    minds = LocalMinds(seed=2)
    minds.born(eco.populate())
    parent = next(iter(eco.lives))
    eco.world.creatures[parent].energy = eco.world.creatures[parent].body.capacity()
    replies = minds.answer(eco.requests())
    changes = eco.advance(replies)
    births = [b for b in changes["births"] if b["parent"] == parent]
    assert births, "a full creature bears a child"
    minds.born(births)
    child = births[0]["id"]
    a = minds.minds[parent].brain.learner.brain.efficacy
    b = minds.minds[child].brain.learner.brain.efficacy
    assert np.array_equal(a, b) and a is not b
    assert eco.lives[child].generation == 1 and eco.lives[child].parent == parent


def test_tally_by_kind():
    eco = Ecosystem(3, Rules(), founders=founders(2), cap=2, frozen=1, random=1)
    minds = LocalMinds(seed=3)
    minds.born(eco.populate())
    run(eco, minds, 40)
    t = eco.tally()
    assert {"live", "frozen", "random"} <= set(t)
