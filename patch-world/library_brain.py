"""A Patch World founder brain, built with the Cadence library.

    python3 -m pip install cadence-net==0.70.0
    python3 library_brain.py

The page runs core.js, a JavaScript version of the same equations. This file
shows the same brain in the library's own words: three populations settling
together, one action value per policy patch, learning from the reward that
followed the creature's own action. `--observer` makes the policy an observer
that also reads the prediction errors of the stages below.
"""

from __future__ import annotations

import random
import sys

from cadence.experimental.equilibrium import Cortex, Reinforcement

ACTIONS = ("north", "east", "south", "west", "eat", "wait")
SENSES = 106  # a 3x3 window of food and neighbours, energy, last outcome, light, hearing


def build(observer=False, seed=7):
    cortex = Cortex(seed=seed, fan_in=9, parameter_prior=0.3, tolerance=1e-3, settle_budget=64)
    senses = cortex.input("senses", shape=SENSES)
    perception = cortex.column("perception", patches=10, inputs=senses)
    stage = cortex.column("stage", patches=8, inputs=(senses, perception))
    if observer:
        policy = cortex.observer("policy", patches=6, inputs=senses, observes=(perception, stage))
    else:
        policy = cortex.column("policy", patches=6, inputs=(senses, perception, stage))
    for index, name in enumerate(ACTIONS):
        cortex.output(name, shape=1, reads=policy, indices=(index,))
    brain = cortex.build()
    # One settle answers every action; the value of an action is one policy patch.
    return Reinforcement(brain, actions=len(ACTIONS), action_input=None, value_output=ACTIONS,
                         discount=0.6, exploration=0.1, reward_scale=4.0,
                         capacity=256, batch_size=4, seed=seed)


def reading(food_here, rng):
    """A toy reading: unit 0 says whether food lies under the creature."""
    values = [float(rng.random() < 0.1) for _ in range(SENSES)]
    values[0] = float(food_here)
    return {"senses": values}


def main():
    rng = random.Random(1)
    creature = build(observer="--observer" in sys.argv)
    eat = ACTIONS.index("eat")
    food, eaten, refused, rows = True, [], 0, 300
    senses = reading(food, rng)
    for _ in range(rows):
        decision = creature.act(senses)
        if decision["action"] is None:  # a refused settle waits; nothing is learned from it
            refused += 1
            creature.reset()
            continue
        action = decision["action"]
        reward = 1.0 if food and action == eat else -0.1 if action == eat else 0.0
        if food:
            eaten.append(action == eat)
        food = rng.random() < 0.5
        senses = reading(food, rng)
        # the same call teaches during the whole life: there is no separate training mode
        creature.feedback(reward, senses, decision_id=decision["decision_id"], executed_action=action)
    early, late = eaten[:40], eaten[-40:]
    print(f"ate when food was present: {sum(early)}/{len(early)} early, {sum(late)}/{len(late)} late; "
          f"{refused} refused settles in {rows} ticks")


if __name__ == "__main__":
    main()
