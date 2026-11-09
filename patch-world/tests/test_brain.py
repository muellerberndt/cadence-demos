import copy

import numpy as np

from patchworld.brain import FrozenMind, LiveMind, RandomMind, compose, retune
from patchworld.genes import FOUNDER, mutate, structure
from patchworld.world import N_ACTIONS, N_INPUTS


def test_founder_brain_lives():
    brain = compose(FOUNDER, seed=0)
    assert len(brain.sensory_index) == N_INPUTS
    mind = LiveMind(brain)
    rng = np.random.default_rng(0)
    reward = None
    for _ in range(20):
        out = mind.moment(rng.random(N_INPUTS), reward)
        assert 0 <= out["action"] < N_ACTIONS
        reward = float(rng.normal())
    assert brain.learner.updates > 0  # young: it learns


def test_frozen_twin_never_learns():
    brain = compose(FOUNDER, seed=1)
    before = brain.learner.brain.efficacy.copy()
    mind = FrozenMind(brain)
    rng = np.random.default_rng(1)
    for _ in range(20):
        out = mind.moment(rng.random(N_INPUTS), 1.0)
        assert 0 <= out["action"] < N_ACTIONS
    assert np.array_equal(before, brain.learner.brain.efficacy)


def test_random_walker():
    mind = RandomMind(3)
    acts = {mind.moment(np.zeros(N_INPUTS), None)["action"] for _ in range(100)}
    assert acts == set(range(N_ACTIONS))


def test_genes_mutate_within_ranges_and_retune():
    rng = np.random.default_rng(2)
    g = copy.deepcopy(FOUNDER)
    for _ in range(50):
        g = mutate(g, rng, rate=0.8, structural=0.5)
    assert 2 <= g["sense"] <= 6 and g["speed"] in (1, 2) and 0.7 <= g["size"] <= 1.5
    brain = compose(g, seed=2)
    retune(brain, mutate(g, rng, rate=1.0, structural=0.0))
    assert structure(g).startswith("w")


def test_recall_grows_onto_a_brain():
    brain = compose(FOUNDER, seed=4)
    assert brain.recall is None
    grown = brain.grow(recall=True)
    assert grown.recall is not None
    out = LiveMind(grown).moment(np.zeros(N_INPUTS), None)
    assert 0 <= out["action"] < N_ACTIONS
