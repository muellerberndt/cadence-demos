# Model card: Simon (W6, eye v2)

| | |
| --- | --- |
| Demo | Castlevania (`castlevania/`) |
| File | `brain/brain.npz` · 26.3 MB · SHA-256 `58225f8f15911ae4…` |
| Library | `cadence-net` 0.95.2 (`Brain.load(path, backend="cpu")`, float64, as `server.py` loads it) |
| Composition | 827 inputs, 10 motor neurons in slots (3, 3, 2, 2), modules (256, 128), apical 0.25, recall memory (128 slots, 2 heads, the executed command and the boundary in its keys, position 32, no recency), `memory_choice=True`, arousal; learner set by `LearnerConfig` (raw step 0.2, bias step 0.02, 32 nudged sweeps run whole, unqualified, every row taught) |
| Size | 4,697 neurons (the recall memory's regions included), 724,736 synapses |
| Date | 2026-11-09 |

## What it sees and does

- **Inputs (827, [`simon/eye.py`](simon/eye.py)).** The gray screen pooled to 12 x 16 cells and
  its change since the last decision; two 64 x 48 px foveas on Simon, one ahead and one behind,
  pooled to 12 x 16; 12 body readings (position, scroll, health, lives, stage, facing, the last
  command); one-hot stage, block, body state and floor. Positions and those readings come from
  RAM, the rest is pixels.
- **Outputs.** Four slots: horizontal (left, none, right), vertical (up, none, down), whip
  (B), jump (A). The strongest neuron of each slot is pressed for 12 frames.
- **One decision.** `Brain.act(x, greedy=True)`: the whole brain settles warm from the previous
  decision's state (32 sweeps at tolerance 3e-3 in the page's readings); no search at play.

## How it was trained

Imitation of a scripted RAM-reading teacher ([`training/teacher.py`](training/teacher.py)):
routes per stage, the whip for enemies in reach, and a savestate lookahead at the giant bat.
The teacher alone reaches stage 4 on ten of ten starts.

1. Practice pools of teacher games from power-on: emulator savestates with the observation, the
   teacher's memory and its next labels ([`training/harvest.py`](training/harvest.py)).
2. 200,000 decisions of practice segments (40 decisions from drawn practice states, weighted to
   the hall stairs, stage 2 and the bat), one `Brain.lesson` with the teacher's label and then
   one `Brain.act` per decision, the teacher's action executed. This ran on an earlier release
   of the library with the first 588 inputs of the eye (about 5.3 hours on one core of a c7i).
3. The checkpoint was carried to 0.95.2 (its two recall heads moved to the competing read
   0.95 runs), then [`training/widen.py`](training/widen.py) copied every learned array onto the
   827-input eye with the new inputs' synapses at zero. On 400 held-out positions the widened
   brain's memory-free answers equal the original's on every one.

The commands are in the README's "Train your own" (`training/train.py`, `training/pack.py`).

## How it was measured

Brain alone, frozen and greedy, from power-on after 0, 3, 7, 10, 14, 21, 28, 35 and 42 idle
decisions, 1,500 decisions each (`training/evaluate.py`; [`evidence/receipt.json`](evidence/receipt.json)):

| Reading | Value |
| --- | --- |
| Past the hall's stairs (stage 2 reached) | 9 of 9 starts |
| Stage 3 reached | 0 of 9 |
| Lives lost | 4 of 4 on every start |
| Where the lives went | 17 in stage 2 (the bottom-left staircase), 3 in stage 1 |

The teacher it imitated, on ten power-on starts: stage 4 on 10 of 10.

## In the page

Frozen: nothing is learned while the visitor watches. The visitor can start a new game after 0
to 42 idle decisions, pause, and run at 1x, 2x, 4x or as fast as the brain answers. The working
trace and recall memory are cleared at each new game. Nothing is saved. One decision took 35 to
47 ms on an Apple M4 CPU under load (the page shows each decision's time and sweep count).

## Limits

- It does not get past stage 2: at the bottom-left staircase down into the underground it stops
  a few pixels short of the staircase's foot and holds down, which crouches, until enemies take
  its lives.
- It learned from a teacher's labels; reward played no part.
- Simon's position, facing, stage, block and body state come from RAM, not from pixels.
- Checked on the PRG1 printing and stable-retro's FCEUmm core only.
- The readings are nine starts of one brain; they certify nothing beyond them.

## Licence

GPL-3.0, as Cadence. The game and its ROM are Konami's and are not distributed here.
