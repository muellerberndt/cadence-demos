from arena.brain import RobotBrain
from arena.licence import licence
from arena.nursery import SPAR, run_nursery, spar_commands
from arena.parts import stock_designs
from arena.senses import input_count, input_names
from arena.world import Arena, Robot

DESIGNS = {b.name: b for b in stock_designs()}


def test_senses_include_closing_and_threat():
    bp = DESIGNS["Tumbler"]
    names = input_names(bp)
    assert names[8:11] == ["robot closing", "robot receding", "weapon threat"]
    assert input_count(bp) == len(names)


def test_the_sparring_partner_hunts_the_pupil():
    pupil, spar = Robot.build(0, DESIGNS["Tumbler"]), Robot.build(1, SPAR)
    arena = Arena([pupil, spar], spawn=False)
    pupil.place_at(0.0, 0.0, 0.0)
    spar.place_at(4.0, 3.0, 0.0)
    start = (spar.x - pupil.x) ** 2 + (spar.y - pupil.y) ** 2
    taken = 0.0
    for _ in range(200):
        out = arena.step({0: [1, 1, 1], 1: spar_commands(spar, pupil)})
        taken += out[0]["taken"]
    assert (spar.x - pupil.x) ** 2 + (spar.y - pupil.y) ** 2 < start
    assert taken > 0.0  # it reaches the pupil and its spinner hurts


def test_a_short_nursery_with_sparring_reports_its_counts():
    r = run_nursery(DESIGNS["Cart"], moments=120, seed=2, block=60)
    assert {"spar_kills", "spar_taken", "burn", "outside_share"} <= set(r["total"])


def test_licence_scores_a_newborn_and_random(tmp_path):
    bp = DESIGNS["Tumbler"]
    path = RobotBrain.newborn(bp).save(tmp_path / "newborn.npz")
    r = licence(bp, path, "brain", scale=0.1)
    assert set(("licence", "approach", "escape", "engage_dealt", "spin")) <= set(r)
    assert -1.5 <= r["licence"] <= 1.5 and 0.0 <= r["spin"] <= 1.0
    q = licence(bp, None, "random", scale=0.1)
    assert q["policy"] == "random"
