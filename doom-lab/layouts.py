"""Candidate brain layouts for the Doom sweep.

Every candidate sees identical retinas and motor space. The ``control``
variants replace recursive observation with ordinary composition at the
same patch counts and data connections, as the matched-capacity baseline
required for any depth claim.
"""

from __future__ import annotations

from cadence import Cortex

from doomlab import BUTTONS

SETTLE_BUDGET = 16384

SIZES = {
    "base": {"scene": 32, "aim": 24, "integration": 16, "reflection": 8},
    "wide": {"scene": 48, "aim": 32, "integration": 24, "reflection": 12},
    "grand": {"scene": 96, "aim": 64, "integration": 48, "reflection": 24},
}


def build(layout, seed, parameter_prior=0.1, device="cpu"):
    """layout: '<size>-recursive' or '<size>-control'."""
    size_name, kind = layout.split("-")
    sizes = SIZES[size_name]
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET,
                    parameter_prior=parameter_prior)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    scene = cortex.column("scene", patches=sizes["scene"], inputs=periphery)
    aim = cortex.column("aim", patches=sizes["aim"], inputs=fovea)
    if kind == "recursive":
        integration = cortex.observer(
            "integration", patches=sizes["integration"],
            inputs=(periphery, fovea), observes=(scene, aim),
        )
        reflection = cortex.observer(
            "reflection", patches=sizes["reflection"],
            observes=(scene, aim, integration),
        )
    elif kind == "control":
        integration = cortex.column(
            "integration", patches=sizes["integration"],
            inputs=(periphery, fovea, scene, aim),
        )
        reflection = cortex.column(
            "reflection", patches=sizes["reflection"],
            inputs=(scene, aim, integration),
        )
    else:
        raise ValueError(f"unknown layout kind: {kind}")
    cortex.output("motor", shape=(len(BUTTONS),), reads=reflection)
    return cortex.build()


FORESIGHT = 4  # d_health, d_ammo, kill_event, d_view — measured next-decision


def build_self(seed, parameter_prior=0.1, device="cpu", sizes=None):
    """Generalist self-play layout: retinas + efference in, motor + foresight out.

    The foresight population observes integration and reads the efference
    copy of the previous action; its outputs are trained against measured
    outcomes, so the brain carries an action-conditioned world model inside
    the same settling equilibrium.
    """
    sizes = sizes or SIZES["grand"]
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET,
                    parameter_prior=parameter_prior)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    efference = cortex.input("efference", shape=(len(BUTTONS),))
    scene = cortex.column("scene", patches=sizes["scene"], inputs=periphery)
    aim = cortex.column("aim", patches=sizes["aim"], inputs=fovea)
    integration = cortex.observer(
        "integration", patches=sizes["integration"],
        inputs=(periphery, fovea, efference), observes=(scene, aim),
    )
    reflection = cortex.observer(
        "reflection", patches=sizes["reflection"],
        observes=(scene, aim, integration),
    )
    foresight = cortex.observer(
        "foresight", patches=max(8, FORESIGHT * 2), inputs=(efference,),
        observes=(integration,),
    )
    cortex.output("motor", shape=(len(BUTTONS),), reads=reflection)
    cortex.output("outcome", shape=(FORESIGHT,), reads=foresight)
    return cortex.build()
