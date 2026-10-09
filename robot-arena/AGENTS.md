# Working on the Cadence robot arena

**One continuing brain per robot.** A robot is one `Brain.compose` life on the Cadence
revision pinned in `requirements.txt`, System 1 by default, with the working trace as short-term
memory, the efference copy of its own commands, one reward channel that carries relief
(damage dealt, progress, a win) and suffering (damage taken, the burn, elimination), and TD
eligibility over its own recent commands. It lives through `Brain.live`: calm, it answers
from one settled state and learns nothing; surprised or in want, it samples, learns and
remembers. The brain that walks in the nursery is the brain that fights, and it keeps the
same life through every fight. Never reset a robot's brain between fights; declared
boundaries (`done`) are the only episode marks.

**Every motor is a slot of the one motor cortex.** `Blueprint.slots` is the brain's motor
layout: a three-state motor is three motor neurons, the spinner's switch two. Commands are
read from one settlement of the whole graph. Do not add a head, a controller or a gait
generator between the brain and the motors: a gait is something the brain finds.

**Not an MLP, not a classifier.** The equilibrium of the whole graph is the robot's world
model. Do not set a brain up as senses pressed into one module and read out; do not teach
with labels; do not run a feed-forward pass. The library is used at that pinned revision; bodies,
worlds, rewards and measurements live here.

**The world supplies problems, never answers.** The nursery pays progress and damage; the
ring pays placement and burns the shy. Nothing tells a robot how to walk, where its
weapon is or which motor to move. Every constant of the brain is a gene of the blueprint,
with the founder (`arena/brain.py:FOUNDER`, the arena's measured nursery point)
as the control. The earlier library reward-chamber point (`preset: chamber`) and the
library's composed defaults (`preset: compose`) remain additional controls.

**Measure behaviour, not intelligence.** Counts a robot cannot fake: metres of progress
toward the dummy, dummies destroyed, damage dealt and taken, placements, Elo, the share of
calm moments, learning sweeps per fight. The uniform-random policy with the same body is the
baseline for every claim; a frozen newborn (greedy, never learning) is the control for
"kept learning". A brain that does not beat random has learned nothing worth reporting,
and `python -m arena` prints the numbers it got, not the numbers it hoped for.

**Where things are.** `arena/` holds the parts catalogue, physics, senses, brain wrapper,
nursery, royale, league and probe; `viewer/arena.html` the isometric replay page; `tests/`
the checks; `league/` the committed stock league; `runs/` is local only.
