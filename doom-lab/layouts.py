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


HIST_STEPS = 4
HIST_SIZE = 96  # half-resolution fovea (3 x 32) per retained step
PHIST_STEPS = 3
PHIST_SIZE = 160  # quarter-resolution periphery (10 x 16) per retained step


def history_shape():
    from cadence.memory import History
    return History(HIST_SIZE, steps=HIST_STEPS).shape


def build_flagship(seed, parameter_prior=0.1, device="cpu", sizes=None):
    """The full-feature lineage brain: retinas + efference + fovea history in,
    motor + foresight out. History is explicit external context (a bounded
    caller-fed window), not learned recurrent memory."""
    sizes = sizes or SIZES["grand"]
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET,
                    parameter_prior=parameter_prior)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    efference = cortex.input("efference", shape=(len(BUTTONS),))
    fovea_history = cortex.input("fovea_history", shape=history_shape())
    scene = cortex.column("scene", patches=sizes["scene"], inputs=periphery)
    aim = cortex.column("aim", patches=sizes["aim"],
                        inputs=(fovea, fovea_history))
    integration = cortex.observer(
        "integration", patches=sizes["integration"],
        inputs=(periphery, fovea, efference, fovea_history),
        observes=(scene, aim),
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


SIZES["ultimate"] = {"scene": 128, "aim": 96, "integration": 64,
                     "reflection": 32}


def periphery_history_shape():
    from cadence.memory import History
    return History(PHIST_SIZE, steps=PHIST_STEPS).shape


def build_ultimate2(seed, parameter_prior=0.1, device="cpu"):
    """Ultimate with a wide policy read: motor decisions draw on every
    processing stage instead of the reflection bottleneck alone."""
    sizes = SIZES["ultimate"]
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET,
                    parameter_prior=parameter_prior)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    efference = cortex.input("efference", shape=(len(BUTTONS),))
    fovea_history = cortex.input("fovea_history", shape=history_shape())
    periphery_history = cortex.input("periphery_history",
                                     shape=periphery_history_shape())
    scene = cortex.column("scene", patches=sizes["scene"], inputs=periphery)
    aim = cortex.column("aim", patches=sizes["aim"],
                        inputs=(fovea, fovea_history))
    integration = cortex.observer(
        "integration", patches=sizes["integration"],
        inputs=(periphery, fovea, efference, fovea_history,
                periphery_history),
        observes=(scene, aim),
    )
    reflection = cortex.observer(
        "reflection", patches=sizes["reflection"],
        observes=(scene, aim, integration),
    )
    policy = cortex.observer(
        "policy", patches=48, inputs=(efference,),
        observes=(scene, aim, integration, reflection),
    )
    foresight = cortex.observer(
        "foresight", patches=max(8, FORESIGHT * 4), inputs=(efference,),
        observes=(integration,),
    )
    cortex.output("motor", shape=(len(BUTTONS),), reads=policy)
    cortex.output("outcome", shape=(FORESIGHT,), reads=foresight)
    return cortex.build()


def build_ultimate(seed, parameter_prior=0.1, device="cpu"):
    """The lineage brain: five sensory streams, motor + foresight heads.

    Both history inputs are explicit external context windows (bounded,
    caller-fed), not learned recurrent memory.
    """
    sizes = SIZES["ultimate"]
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET,
                    parameter_prior=parameter_prior)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    efference = cortex.input("efference", shape=(len(BUTTONS),))
    fovea_history = cortex.input("fovea_history", shape=history_shape())
    periphery_history = cortex.input("periphery_history",
                                     shape=periphery_history_shape())
    scene = cortex.column("scene", patches=sizes["scene"], inputs=periphery)
    aim = cortex.column("aim", patches=sizes["aim"],
                        inputs=(fovea, fovea_history))
    integration = cortex.observer(
        "integration", patches=sizes["integration"],
        inputs=(periphery, fovea, efference, fovea_history,
                periphery_history),
        observes=(scene, aim),
    )
    reflection = cortex.observer(
        "reflection", patches=sizes["reflection"],
        observes=(scene, aim, integration),
    )
    foresight = cortex.observer(
        "foresight", patches=max(8, FORESIGHT * 4), inputs=(efference,),
        observes=(integration,),
    )
    cortex.output("motor", shape=(len(BUTTONS),), reads=reflection)
    cortex.output("outcome", shape=(FORESIGHT,), reads=foresight)
    return cortex.build()
