import numpy as np

from patchworld.world import BERRY, N_INPUTS, Body, Rules, World, input_names


def test_observation_shape_and_names():
    w = World(1)
    c = w.add_creature(Body())
    obs = w.observe([c.id])
    assert obs.shape == (1, N_INPUTS) == (1, len(input_names()))
    assert np.isfinite(obs).all()


def test_same_seed_same_world():
    a, b = World(5), World(5)
    assert (a.terrain == b.terrain).all() and (a.food == b.food).all()
    ca, cb = a.add_creature(Body()), b.add_creature(Body())
    for t in range(50):
        a.step({ca.id: t % 6})
        b.step({cb.id: t % 6})
    assert (a.food == b.food).all() and (ca.x, ca.y, ca.energy) == (cb.x, cb.y, cb.energy)


def eat_berry(world):
    c = world.add_creature(Body(), energy=10)
    world.food[c.y, c.x] = BERRY
    out = world.step({c.id: 4})[c.id]
    return c, out


def test_berry_nourishes_in_summer_and_poisons_in_winter():
    w = World(2)
    assert w.summer
    c, out = eat_berry(w)
    assert out["reward"] == w.rules.berry_summer and "berry" in out["events"]
    w.flip_season()
    assert not w.summer
    c, out = eat_berry(w)
    assert out["reward"] == w.rules.berry_winter and "poisoned" in out["events"]
    assert c.sick > 0
    nausea = input_names().index("nausea")
    assert w.observe([c.id])[0, nausea] > 0


def test_season_is_not_sensed_but_the_air_turns_slowly():
    w = World(3, Rules(predators=0))
    c = w.add_creature(Body())
    cold = input_names().index("cold")
    w.flip_season()
    w.step({c.id: 5})
    just_after = w.observe([c.id])[0, cold]
    for _ in range(600):
        w.step({c.id: 5})
    later = w.observe([c.id])[0, cold]
    assert just_after < 0.3 and later > 0.7  # a flip is not announced; the cold comes later


def test_immortal_nursery_and_mortal_world():
    w = World(4, Rules(immortal=True, predators=0))
    c = w.add_creature(Body(), energy=0.5)
    for _ in range(100):
        w.step({c.id: 4})
    assert c.alive and c.energy >= 1.0
    m = World(4, Rules(predators=0))
    d = m.add_creature(Body(), energy=0.5)
    for _ in range(100):
        m.step({d.id: 4})
    assert not d.alive and d.cause == "starved"


def test_predator_bites():
    w = World(6, Rules(predators=0))
    c = w.add_creature(Body(), energy=15)
    w.add_predator(at=(c.x, c.y))
    w.predators[0]["rest"] = 0
    out = w.step({c.id: 5})
    assert "bitten" in out[c.id]["events"] and c.energy < 15
