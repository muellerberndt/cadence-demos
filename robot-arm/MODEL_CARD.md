# Model card: B_D3b, seed 3 (the Robot Arm page's brain)

| | |
| --- | --- |
| Demo | Robot Arm (`robot-arm/`) |
| File | `site/pack/brain.npz` · 6,711,302 bytes · SHA-256 `fb2337350fa66246…` |
| Library | `cadence-net` 0.95.2 (`Brain.load`, CPU, float64, as the page's worker loads it in Pyodide) |
| Composition | `Brain.compose(262, 17, slots=[5, 5, 5, 2], seed=3, modules=(256, 128, 64), apical=0.25, teaching="deep", learning_surprise=True, learning_qualified=False, recall=False, arousal=True)`; a prefrontal region of 64 carries the working trace |
| Size | 791 neurons, 155,264 synapses |
| Date | 2026-11-09 (packed on 0.95.2) |

## What it sees and does

- **Inputs (262 values, fixed population codes of true state):** the hand's position (45), the
  block minus the hand (45), the target bin's release point minus the hand (45), the seven joint
  angles (49) and speeds (49), the gripper's opening (7), closed and holding (2), the brain's own
  last command (17, the efference copy), and which lamp is lit (3). Not pixels. Layout in
  `site/pack/run.json`.
- **Outputs (17 motor neurons in four slots):** a move of the hand of −2 to +2 cm along x, y and z
  (5 neurons each) and open or close (2). An inverse-kinematics reflex, an application controller,
  turns the move into joint targets; MuJoCo then runs 100 steps of 2 ms.
- **One decision:** `Brain.act(x, greedy=True)` on the 262 values, the strongest neuron per slot.
  The working trace carries from decision to decision within a trial; `Brain.reset` clears it at
  the start of each trial. No search.

## How it was trained

Imitation of a scripted teacher (hover, close, lift, carry, release; `--teacher recover`
re-approaches a block that slipped) in MuJoCo with a Franka Panda, on the `wide` physics set
(block size, mass, friction and contact stiffness randomized per job). 128 cells on one brain,
400 episodes, decision cap 80. At each decision `Brain.lesson` teaches by surprise (only rows
where the brain disagrees), then `Brain.act` answers; `Brain.step` is never called. Each cell
executes the brain's or the teacher's command; the teacher's share fades from 0.5 to 0 over the
run. Learner step 0.003, bias step 0.0003. The page's brain is the best fresh-reading checkpoint
(`brain_best`) of seed 3. The run (`site/pack/run.json`) was on cadence-net 0.91.1, MuJoCo
3.17.0, 3 workers on a 4-thread x86_64 machine; `run.json` does not record the wall time. The
composition above is the same recipe in 0.95.2's names, with the same learner configuration.

```sh
PYTHONPATH=. python -m arm2.train --arm D3b --physics wide --teacher recover --arousal \
    --episodes 400 --cells 128 --workers 3 --seed 3 --out runs/B_D3b_s3
```

## How it was measured

Frozen brain, fresh trials, brain alone (`evidence/stage2b_final.json`, `evidence/moved_bins.jsonl`):

| Reading | Trials | Brain | Teacher on the same trials |
| --- | --- | --- | --- |
| `wide` physics: placed in the right bin | 200 | 0.955 | 0.955 |
| `wide` physics: dropped | 200 | 0.110 | – |
| `wide` physics: grasped; median decisions | 200 | 1.000; 39 | – |
| `heldout2` (light, slippery, bouncy blocks beyond `wide`): placed right | 200 | 0.465 | 0.295 |
| Controls (uniform random, blind, newborn): placed right | 200 | 0.0 each | – |
| Target bin at (0.62, −0.10), (0.62, −0.33), (0.70, −0.06), (0.62, +0.08), (0.72, −0.22), nominal physics | 20 each | 20, 19, 19, 20, 19 | – |
| Target bin at the trained places (0.62, ±0.22) | 20 each | 19, 19 | – |
| Target bin in the far corner (0.72, +0.32) | 20 | 10 (10 dropped) | – |

The other seeds of the same recipe at episode 400 (`stage2b_final.json`): seed 1 0.950 /
`heldout2` 0.370, seed 2 0.915 / 0.375.

On cadence-net 0.95.2 (2026-11-09): the brain host gives the recorded command at all 104
decisions of the two recorded trials (`site/tests/fixtures/`), and the physics port matches
Python on both (`evidence/parity.txt`: grasped at decision 24 and 25, placed right at 51).

## In the page

Frozen: the synapses do not change while the visitor plays. The visitor places the block and
the bins (bins only inside the band where the brain placed 19 or 20 of 20), picks the target
bin, runs, and may move the target bin while the arm carries the block. Run and Reset clear the
working trace; nothing is saved in the browser. The page check (`evidence/page_check.json`,
headless Chrome on a Mac running other jobs): the brain loads in 6.2 s; bin A placed in 52
decisions; bin B, moved to (0.66, −0.12) mid-carry, placed in the moved bin in 60 decisions;
median 16.3 ms per brain decision; no console errors. Every second decision the worker also
replays the decision's settle sweep by sweep for the brain panel (exact, checked against the
answer's state): 42.2 ms of worker time on those decisions against 18.9 ms on the others.

## Limits

- It imitates a scripted teacher; the teacher and the inverse-kinematics reflex are application
  controllers, not learned.
- Senses are true state, not vision. The block's yaw is not randomized; the bins never moved in
  training.
- On `heldout2` it places fewer than half of the blocks; in the far corners of the bin band half.
- No reward learning: `arm2/live.py` (refinement through `Brain.live`) is not usable yet.
- The readings certify these trials only, not general manipulation.

## Licence

GPL-3.0, as Cadence. The Panda model is MuJoCo Menagerie's `franka_emika_panda` (Apache-2.0).
