# arm1: control on true state (stage 1)

The cell is `arm/world.py` unchanged (spring-damper joints, equilibrium-point control, magnetic
grasp within 3 cm, two bins named by a lit lamp); the teacher is `arm091.job.smooth_plan`. This
package supplies the true state, commands the hand in Cartesian terms through a disclosed reflex,
teaches by surprise without ever crediting an unexecuted action, and reads every checkpoint
frozen, in a separate process, against the teacher and the controls.

Run from `robot-arm/` with the library installed:

    pip install cadence-net==0.91.1 mujoco==3.17.0 pytest   # from robot-arm/
    export PYTHONPATH=.
    export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1
    PY=python
    $PY -m pytest tests/test_arm1.py -q
    $PY -m arm1.teacher --trials 100                      # the teacher through the reflex: the ceiling
    $PY -m arm1.train --arm D1 --cells 4 --episodes 10 --out runs/arm1-smoke --inspect-trials 10 --fresh-trials 10
    $PY -m arm1.inspect --checkpoint runs/arm1-smoke/brain.npz --trials 10
    $PY -m arm1.render --checkpoint runs/arm1-smoke/brain.npz --out runs/arm1-smoke/frames/final

## Observation (`senses.py`, 168 inputs)

Population codes of Gaussian bumps in the style of the joint senses (`World.body`: 15 centres,
sigma 0.75 of the spacing).

| slice | size | what |
| --- | --- | --- |
| 0..45 | 3 x 15 | fingertip x, y, z over (-0.40, 0.40), (0.00, 0.60), (0.00, 0.45) m, centres uniform |
| 45..90 | 3 x 15 | block centre minus fingertip per axis, centres uniform in `u = sign(d) sqrt(min(abs(d), R)/R)`, R = 0.60, 0.60, 0.45 m: the first bump off zero sits at 1.2 cm, then 4.9, 11, 20, 31, 44, 60 cm |
| 90..135 | 3 x 15 | release point (the ordered bin at the carrying height 0.12 m) minus fingertip, same warp; zero without an order |
| 135..165 | 30 | the body: 4 x 7 spindles, gripper closed, holding |
| 165..168 | 3 | the lamp, one-hot over (none, A, B) |

The blind twin zeroes 45..135.

## Actions (`actions.py`)

Cartesian pools (5, 5, 5, 2): dx, dy, dz at -2, -1, 0, +1, +2 cm per decision and the gripper.
The IK reflex: target = fingertip + shift (height floored 2 mm above the table); from the rest
angles, three damped-least-squares iterations with the analytic Jacobian of `forward`,
`dq = J^T (J J^T + 0.05^2 I)^-1 err + (I - J^+ J) 0.05 (home - q)`, clipped to the joint limits;
the rest change clipped to two fine steps (0.09 rad) per joint and passed to `World.decide` as
fractional steps. `--pools joint` keeps the per-joint pools (5, 5, 5, 5, 2) for D2.

## Teacher (`teacher.py`)

Per axis the smooth plan's waypoint minus the fingertip, rounded to whole centimetres and clipped
to two (under 5 mm: hold); the gripper from the plan's phase. Joint labels: `arm091.teacher.job_steps`.

## Protocol (`train.py`)

Per decision: labels, `Brain.lesson` (surprise: only disagreeing rows), `Brain.act`, execute the
brain's or the teacher's command (share 0.5 fading to 0 over the run). `Brain.step` is never
called. Cells restart on placement or after 80 decisions; 0.7 of fresh jobs begin with the
teacher driving 0 to 40 decisions. Step 0.03 (D3: its normalized point), a third at the first
plateau of six selection readings, halved at later ones. Readings every 20 episodes (40 selection
trials, seed 30000+s) and every 100 (200 fresh trials on seeds 80000+1000s+10k with the controls
and four rendered trials), one JSON line each in `readings.jsonl`.

## Arms (`brains.py`)

D1 flat (256,); D2 D1 on joint pools; D3 (256, 128) apical 0.25, normalized teaching,
`learning_normalize_relative=0.1`, `learning_nudged_steps=32`, `learning_nudged_fixed=True`,
`learning_qualified=False`; D4 D1 + `recall=True, recall_action=True, recall_heads=1`. Controls:
uniform random, the teacher, the blind twin, the frozen newborn, the torch MLP (`mlp.py`,
`--arm mlp`). 0.91.1 keys a recall memory on the whole observation (`recall_heard` is one
number), so D4 keys on every input plus the command, not on the body senses alone.

## Gates (`job.py`)

`reached` counts the hover point within 2.5 cm or a grasp; `reached_hover` is the old criterion.
Per trial from every physics frame: oscillation (velocity sign changes per second within 1 cm of
the waypoint), overshoot (cm moved away in the half second after first coming within 1 cm),
settling time (3 cm to a 0.2 s stay within 1 cm), actuator effort (integrated |stiffness (rest-q)
- damping dq|), commanded rest movement and path length; `inspect` reports each as a ratio to and
a difference from the teacher's value on the same trials (`gates_vs_teacher.ratio`, `.minus`).

