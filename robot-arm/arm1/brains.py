"""The arms of stage 1, every one a ``Brain.compose`` on the true-state observation.

| arm | recipe |
| --- | --- |
| D1 | flat ``modules=(256,)``, Cartesian pools |
| D2 | D1's brain on the joint pools (yaw, shoulder, elbow, wrist, gripper) |
| D3 | ``modules=(256, 128)``, ``apical=0.25``, ``teaching="normalized"``, ``learning_normalize_relative=0.1``, ``learning_nudged_steps=32``, ``learning_nudged_fixed=True``, ``learning_qualified=False`` |
| D4 | D1 plus ``recall=True, recall_action=True, recall_heads=1``: an index of the stream's own moments with the executed command in key and value (the phase memory) |

Every arm teaches by surprise (``learning_surprise=True``): a lesson reaches only the rows whose
greedy answer disagrees with the label. The step: D1, D2 and D4 start at ``eta`` 0.03 with the
bias step a tenth of it (the founder ratio); D3 keeps the normalized teaching point (0.003 and
0.0003 under a running RMS) unless a step is given. 0.91.1 keys a recall memory on the whole
observation (``recall_heard`` is one number), so D4 keys on all 168 inputs plus the command, not
on the body senses alone; the deviation is recorded in ``run.json``.
"""

from __future__ import annotations

from dataclasses import asdict, replace

from cadence import Brain

from .actions import slots_of
from .senses import INPUTS

ARMS = ("D1", "D2", "D3", "D3b", "D4", "D5")
DEEP_FIRST = ("D5", "D3b", "D3", "D4", "D1", "D1nv", "D1all", "D2", "mlp")  # table order: deep arms first
APICAL = {"apical": 0.25, "teaching": "normalized", "learning_normalize_relative": 0.1, "learning_nudged_steps": 32,
          "learning_nudged_fixed": True, "learning_qualified": False}
RECIPES: dict[str, dict] = {
    "D1": {"modules": (256,)},
    "D2": {"modules": (256,)},
    "D3": {"modules": (256, 128), **APICAL},
    "D3b": {"modules": (256, 128, 64), **APICAL},  # the deeper brain, the same apical recipe
    "D4": {"modules": (256,), "recall": True, "recall_action": True, "recall_heads": 1},
    # the deeper apical brain with a two-head recall memory over the job's phases (lesson first)
    "D5": {"modules": (256, 128, 64), **APICAL, "recall": True, "recall_heads": 2, "recall_action": True,
           "recall_boundary": True, "recall_position": 32, "recall_recency": 0.0},
}
DEFAULT_POOLS = {"D1": "cartesian", "D2": "joint", "D3": "cartesian", "D3b": "cartesian", "D4": "cartesian", "D5": "cartesian",
                 "mlp": "cartesian"}
DEFAULT_ETA = {"D1": 0.03, "D2": 0.03, "D3": None, "D3b": None, "D4": 0.03, "D5": None}


def compose(arm: str, pools: str, seed: int, *, surprise: bool = True, inputs: int | None = None,
            slots: tuple[int, ...] | None = None, **options) -> Brain:
    """An arm's brain on this package's observation and pools by default; ``inputs`` and
    ``slots`` let another cell (stage 2) use the same recipes."""
    slots = list(slots_of(pools) if slots is None else slots)
    recipe = dict(RECIPES[arm])
    recipe.update(options)
    return Brain.compose(INPUTS if inputs is None else int(inputs), int(sum(slots)), slots=slots, seed=seed,
                         learning_surprise=surprise, **recipe)


def set_steps(brain: Brain, eta: float | None = None, scale: float = 1.0) -> dict:
    """The learner's steps through ``retune``: the step and the bias step together, the ratio kept."""
    c = brain.learner.config
    new_eta = (c.eta if eta is None else float(eta)) * scale
    bias = None if c.eta_bias is None else c.eta_bias * (new_eta / c.eta)
    brain.retune(learning=replace(c, eta=new_eta, eta_bias=bias))
    return {"eta": brain.learner.config.eta, "eta_bias": brain.learner.config.eta_bias}


def describe(brain: Brain) -> dict:
    c = brain.connectome
    return {"neurons": int(c.n), "synapses": int(c.synapses),
            "populations": {k: len(v) for k, v in c.populations.items()},
            "learning": {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v))
                         for k, v in asdict(brain.learner.config).items()}}
