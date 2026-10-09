import pytest

from arena.parts import Blueprint, Part, blueprint_from_dict, stock_designs
from arena.senses import input_count, input_names


def test_stock_designs_are_valid_and_slot_layouts_cover_every_motor():
    for bp in stock_designs():
        assert bp.motors == len(bp.slots)
        assert bp.motor_neurons == sum(bp.slots)
        spinners = sum(1 for p in bp.parts if p.weapon == "spinner")
        assert bp.motors == len(bp.parts) + spinners
        assert input_count(bp) == len(input_names(bp))
        assert blueprint_from_dict(bp.to_dict()) == bp


def test_blueprint_rejects_impossible_robots():
    with pytest.raises(ValueError):
        Blueprint("x", "light", (Part("arm", 0, "spike"),))  # no drive
    with pytest.raises(ValueError):
        Blueprint("x", "light", (Part("wheel", 0),) * 5)  # too many parts for a light chassis
    with pytest.raises(ValueError):
        Blueprint("x", "light", (Part("arm", 0),))  # an arm without a weapon
    with pytest.raises(ValueError):
        Blueprint("x", "light", (Part("wheel", 0, "spike"),))  # a wheel with a weapon
    with pytest.raises(ValueError):
        Blueprint("x", "tank", (Part("wheel", 0),))


def test_mass_adds_up():
    bp = Blueprint("x", "medium", (Part("wheel", 90), Part("wheel", -90), Part("arm", 0, "hammer")))
    assert bp.mass == 30.0 + 3.0 + 3.0 + 4.0 + 6.0
