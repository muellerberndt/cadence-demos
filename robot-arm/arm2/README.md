# arm2: the job under contact physics (stage 2)

A Franka Panda with gripper from MuJoCo Menagerie in plain MuJoCo on the CPU (`scene.py`),
the stage-1 observation, actions, teacher, loop and inspection carried over (`arm1`), grasp,
lift and place read from contacts and the block's height.

    pip install cadence-net==0.91.1 mujoco==3.17.0 pytest   # from robot-arm/
    export PYTHONPATH=.
    export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1
    PY=python
    sh arm2/menagerie/fetch.sh                             # the Panda model, pinned
    $PY -m pytest tests/test_arm2.py -q
    $PY -m arm2.teacher --trials 20                      # the teacher: the ceiling, nominal physics
    $PY -m arm2.teacher --trials 20 --physics heldout
    $PY -m arm2.train --arm D1 --cells 4 --episodes 5 --out runs/arm2-smoke --inspect-trials 10 --fresh-trials 10
    $PY -m arm2.inspect --checkpoint runs/arm2-smoke/brain.npz --trials 10 --heldout
    $PY -m arm2.render --checkpoint runs/arm2-smoke/brain.npz --out runs/arm2-smoke/frames/final

## Simulator (`scene.py`)

Menagerie's `franka_emika_panda/panda.xml` (fetched unchanged into `menagerie/` by `menagerie/fetch.sh`,
Apache 2.0, commit in `menagerie/SOURCE.md`), loaded through `mujoco.MjSpec` with a table (top z = 0), a free
block, two open bins (inner side 13 cm, walls 4 cm) at (0.62, -0.22) and (0.62, 0.22), two lamps,
and a `tcp` site 0.1034 m down the hand between the fingertip pads. Physics at the model's 500 Hz;
a decision is 100 steps (0.2 s). The seven joint servos (`kp` 4500/3500/2000, no gravity
compensation) take `ctrl[:7]` as the equilibrium posture; `ctrl[7]` drives the finger tendon
(255 open, 0 closed). One change to the Menagerie model, applied at load time and not in its
files: the finger tendon servo at 1000 N/m in place of 100 N/m (`GRIP_STIFFNESS`), so a block is
squeezed with 10-25 N (the real gripper holds 70 N); at 100 N/m the teacher placed 0.65 of 20
and the carry slipped. Per job the block draws half side 1.5-3 cm, mass, friction and contact
time constant from the physics set: nominal mass 0.03-0.12 kg, friction 0.7-1.2, solref 0.02 s;
held-out mass 0.13-0.18 kg, friction 0.45-0.60, solref 0.008-0.012 or 0.03-0.04 s (the teacher
places 0.98 of 100 nominal, 0.70 of 20 held-out). Block yaw is not randomized. Holding = both fingers in contact with the block while closed; a slip is holding
lost with the gripper closed; a release is judged once the block rests (bin right/wrong, or
dropped).

## Observation (`senses.py`, 262 inputs on Cartesian pools)

tcp x,y,z (3x15); block minus tcp (3x15, warped); release point minus tcp (3x15, warped); seven
joints (7x7 spindles over each range); gripper opening (7); closed and holding (2); seven joint
velocities (7x7 over +-2 rad/s; zero under `--no-velocity`, the arm D1nv); the efference copy of
the last command (17, one-hot per slot); the lamp (3). Blind twin zeroes 45..135.

## Actions (`actions.py`)

Cartesian (5,5,5,2): dx,dy,dz at -2..+2 cm, gripper. Reflex: target = tcp + shift (floored 1 cm),
three damped-least-squares iterations on the tcp site's position and orientation (hand kept
pointing down) with `mj_jacSite`, lambda 0.05, rotation weight 0.5, null-space bias 0.05 toward
home, the change clipped to 0.15 rad per joint. Joint pools (5x7, 2): 0.03 rad per level.

## Teacher (`teacher.py`)

Continuous targets as in stage 1: over the block at a height falling with the planar distance
(8 cm hover to the block centre), close within 1.2 cm in the plane and height, hold still while
the fingers close (reopen after three decisions without a hold), lift to 15 cm, move to the bin
as the hand rises, release within 2 cm above the bin. Labels: per-axis centimetres clipped to two;
joint labels from the reflex's own IK solution.

## Cells across processes (`pool.py`)

The physics dominates a decision (5.3 ms per cell on one laptop core: 0.68 s of a 0.75 s decision at
128 cells), so `train.py --workers N` (default 6) forks N processes that own the cells' worlds,
teacher labels, senses and warm starts, forked before the brain is built; `--workers 0` keeps one
process. The brain, the lessons and the recall patch stay in the parent; the readings are
unchanged.

## Gates (`job.py`)

Sampled at 100 Hz against the block centre (hand empty) and the release point (holding):
oscillation (1 cm and 3 cm bands), overshoot, settling, `effort_nms` (sum |actuator_force| dt),
`effort_cmd` (sum |ctrl - q| dt), jerk (mean |d^3 tcp/dt^3|), commanded movement, path.
`inspect --heldout` reads the brain and the teacher again at held-out physics, reported apart.

