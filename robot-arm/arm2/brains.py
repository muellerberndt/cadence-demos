"""The stage-2 arms: ``arm1.brains``'s recipes on the contact cell's observation and pools.

D1 flat Cartesian; D1nv D1 without the joint velocities in its senses (the control that must
recover momentum from its history); D2 flat joint pools; D3 deep apical; D4 D1 with the recall
phase memory; mlp the torch control.
"""

from __future__ import annotations

from arm1 import brains as base

from .actions import slots_of
from .senses import inputs

ARMS = ("D1", "D1nv", "D2", "D3", "D3b", "D4", "D5")
RECIPES = {**base.RECIPES, "D1nv": base.RECIPES["D1"]}
DEFAULT_POOLS = {**base.DEFAULT_POOLS, "D1nv": "cartesian"}
DEFAULT_ETA = {**base.DEFAULT_ETA, "D1nv": 0.03}
VELOCITY = {"D1": True, "D1nv": False, "D2": True, "D3": True, "D3b": True, "D4": True, "D5": True, "mlp": True}
set_steps = base.set_steps
describe = base.describe


def compose(arm: str, pools: str, seed: int, *, surprise: bool = True, inputs_count: int | None = None, **options):
    """``inputs_count`` overrides the observation width (the slip senses widen it)."""
    return base.compose("D1" if arm == "D1nv" else arm, pools, seed, surprise=surprise,
                        inputs=inputs(pools) if inputs_count is None else int(inputs_count), slots=slots_of(pools), **options)
