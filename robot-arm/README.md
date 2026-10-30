# Robot Arm

A Cadence brain drives a Franka Panda arm under contact physics (MuJoCo). It picks up a block
and places it in the bin that a lit lamp names. The brain learned the job during its life by
imitating a scripted teacher, and is then read frozen on trials it never trained on. The page in
[`site/`](site/) runs the trained brain and the physics in the browser. You place the block and
the bins and press Run; move the target bin while the arm carries the block and the arm follows
it.

Built with `cadence-net==0.91.1` and `mujoco==3.17.0`.

## The page

```sh
python3 -m http.server 8830 --directory site   # from robot-arm/; open http://127.0.0.1:8830/
```

MuJoCo 3.17 runs as WebAssembly with the same compiled cell the brain trained in. The brain runs in
a Web Worker in Pyodide with the released wheel, and the page draws every neuron of it after each
decision. [`site/README.md`](site/README.md) describes the files, the parity tests against the
Python cell and the checks; [`site/DEPLOY.md`](site/DEPLOY.md) describes hosting.

## The brain

```python
Brain.compose(262, 17, slots=[5, 5, 5, 2], seed=3, learning_surprise=True,
              modules=(256, 128, 64), apical=0.25, teaching="normalized",
              learning_normalize_relative=0.1, learning_nudged_steps=32,
              learning_nudged_fixed=True, learning_qualified=False)
```

This is the arm `D3b` in [`arm1/brains.py`](arm1/brains.py): three hidden regions with the apical
compartment, a prefrontal region carrying the working trace, and four motor slots. It has 791
neurons and 155,264 synapses.

- **Senses (262 values, [`arm2/senses.py`](arm2/senses.py)).** These are fixed population codes of
  true state, not pixels and not a learned code of meaning (the learned code is
  [cadence#211](https://github.com/muellerberndt/cadence/issues/211)). They are:
  - the hand's position;
  - the block minus the hand;
  - the target bin's release point minus the hand;
  - the seven joint angles and speeds;
  - the gripper's opening, and whether it is closed and holding;
  - the brain's own last command (the efference copy);
  - which lamp is lit.
- **Acts ([`arm2/actions.py`](arm2/actions.py)).** Each decision is a move of the hand of −2 to
  +2 cm along x, y and z, plus open or close. A disclosed reflex, damped-least-squares inverse
  kinematics on the hand, turns the move into the seven joints' equilibrium posture. MuJoCo then
  runs 100 steps (0.2 s).
- **Teacher ([`arm2/teacher.py`](arm2/teacher.py)).** A scripted plan labels every decision: hover,
  close, lift, carry, release. The brain imitates it. Training ([`arm2/train.py`](arm2/train.py))
  runs 128 cells on one brain. At each decision `Brain.lesson` teaches by surprise (only rows where
  the brain disagrees), `Brain.act` answers, and each cell executes the brain's or the teacher's
  command. The teacher's share fades from 0.5 to 0 over the run. There is no reward in this demo.
- **Physics sets ([`arm2/scene.py`](arm2/scene.py)).** Block size, mass, friction and contact
  stiffness vary per job:
  - `nominal`: the stage-2 training set;
  - `heldout`: outside `nominal`'s ranges;
  - `wide`: the stage-2b training set, spanning both;
  - `heldout2`: light, slippery, bouncy blocks beyond `wide`.

  The bins stay at (0.62, ±0.22) m in training.
- **Memories.**
  - *Synapses:* lessons write them during training. They are frozen in every reading and on the
    page.
  - *Working trace (prefrontal, 64 units):* written at every `Brain.act` and read by the top
    hidden region. `Brain.reset` clears it at the start of each trial, which is how every reading
    was taken; the page does the same at each Run.
  - *Episodic store:* composed by default, and not written by `Brain.act`.
  - *Recall memory:* only the arms `D4` and `D5` compose one.

## Train

```sh
pip install cadence-net==0.91.1 mujoco==3.17.0 pytest   # torch too, for the MLP control
sh arm2/menagerie/fetch.sh                               # the Panda from MuJoCo Menagerie, pinned and checked
PYTHONPATH=. python -m pytest tests -q
PYTHONPATH=. python -m arm2.train --arm D3b --physics wide --teacher recover --arousal \
    --episodes 400 --cells 128 --workers 3 --seed 3 --out runs/B_D3b_s3   # the page's brain
PYTHONPATH=. python -m arm2.inspect --checkpoint runs/B_D3b_s3/brain_best.npz --physics wide \
    --heldout --heldout-set heldout2 --trials 200 --controls
```

One 400-episode run takes about 8 hours on 3 CPU cores. `--teacher recover` re-approaches a block
that slipped. `--arousal` only composes the arousal system; no stage here gates by it. Stage 2
(`--physics nominal`) and the other arms (`--arm D1 | D1nv | D2 | D3 | D4 | D5 | mlp`) use the
same command. [`arm2/README.md`](arm2/README.md) documents the cell, the senses, the reflex, the
teacher and the gates.

## Results

All results are frozen brains on fresh trials, three seeds per arm, with the teacher read on the
same trials. The files are in [`evidence/`](evidence/).

**Stage 2, nominal physics, after 400 episodes** (200 trials; [`stage2_final.json`](evidence/stage2_final.json)):

| Arm | Placed right | Dropped | Held-out physics |
| --- | --- | --- | --- |
| D3, deep (256, 128), apical | 0.977 | 0.013 | 0.727 |
| D5, deep (256, 128, 64), apical, two recall heads | 0.973 | 0.010 | 0.728 |
| D3b, deep (256, 128, 64), apical | 0.973 | 0.010 | 0.698 |
| D1, flat (256) | 0.960 | 0.033 | 0.655 |
| D1nv, flat, no joint velocities | 0.962 | 0.020 | 0.683 |
| D4, flat, one recall head | 0.952 | 0.053 | 0.648 |
| D2, flat, joint-space pools | 0.047 | 0.027 | 0.032 |
| MLP trained by backpropagation (control) | 0.968 | 0.012 | 0.738 |
| Teacher | 0.970 | – | 0.762 |

Uniform-random, newborn and blind controls place none. The deep brains learn faster ([`stage2_curves.json`](evidence/stage2_curves.json)):
at episode 80 they place 0.94–0.97 of the selection trials, against 0.61 for the flat brain, which
reaches 0.95 at episode 240.

**Stage 2b, trained on `wide` physics** (200 trials; [`stage2b_final.json`](evidence/stage2b_final.json)):

| Arm | `wide`: brain / teacher | Dropped | `heldout2`: brain / teacher |
| --- | --- | --- | --- |
| D3b, episode 400 | 0.940 / 0.947 | 0.113 | 0.403 / 0.308 |
| D3b, seed 3, best checkpoint (the page's brain) | 0.955 / 0.955 | 0.110 | 0.465 / 0.295 |
| D5 with slip senses, episode 300 | 0.913 / 0.922 | 0.115 | 0.398 / 0.305 |
| D3b with slip senses, episode 300 | 0.910 / 0.922 | 0.130 | 0.330 / 0.305 |
| D1 flat with slip senses, episode 400 | 0.888 / 0.932 | 0.178 | 0.325 / 0.307 |

On the hardest physics the deep brains place more blocks than the teacher they imitate. The
stage-2 brains re-read on `heldout2` show the same order: deep D3 0.317 against the teacher's
0.280 ([`stage2_heldout2_reread.json`](evidence/stage2_heldout2_reread.json)).

**A moved target bin** (`nominal` physics, 20 trials per position, block placed at random;
[`moved_bins.jsonl`](evidence/moved_bins.jsonl)). The page's brain places the block in a target
bin moved to positions it never trained with:

| Target bin (x, y) m | (0.62, −0.10) | (0.62, −0.33) | (0.72, −0.22) | (0.70, −0.06) | (0.62, +0.08) | (0.72, +0.32) |
| --- | --- | --- | --- | --- | --- | --- |
| Placed right, of 20 | 20 | 19 | 19 | 19 | 20 | 10 |

At the two trained positions it places 19 of 20. The stage-2 brains D3 and D5 fail when the bin
moves back to x 0.72 (4 and 7 of 20). The page lets bins move only inside the band where the page's
brain placed 19 or 20 of 20.

## Limits

- The brain imitates a scripted teacher; the teacher and the inverse-kinematics reflex are
  application controllers.
- On nominal physics the flat brain catches up by episode 400. Depth shows in the speed of
  learning, in fewer drops and on held-out physics. The backpropagation MLP control matches the
  deep brains on this imitation task.
- [`arm2/live.py`](arm2/live.py), reward refinement through `Brain.live`, is not usable yet: its
  loop ends at the first refused settle.
- The block's yaw is not randomized. The bins never move in training.

## Folders

| Folder | What |
| --- | --- |
| `arm2/` | The Panda cell in MuJoCo, its senses, actions, teacher, training, inspection, rendering, and a Python live view (`arm2/demo/`) |
| `arm1/` | The recipes of every arm and stage 1: the same job on true state in a kinematic four-joint cell (`arm/world.py`) |
| `arm/`, `arm091/` | The four-joint cell, retinas, nursery and caregiver of the earlier arm that sees through its own eyes, which `arm1` builds on |
| `site/` | The page, its brain pack, its build tool and its parity tests |
| `evidence/` | The readings quoted above |
| `tests/`, `tools/` | Tests of the cells, senses, actions and hosts; diagnostics |

The Panda model is MuJoCo Menagerie's `franka_emika_panda` (Apache-2.0; `arm2/menagerie/SOURCE.md`).
`fetch.sh` downloads it at the pinned commit and checks it against the files the arm trained with.
