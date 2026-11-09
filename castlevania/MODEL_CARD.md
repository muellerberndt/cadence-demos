# Model card: Simon (C2sd at 450,016 decisions)

| | |
| --- | --- |
| Demo | Castlevania (`castlevania/`) |
| File | `brain/brain.npz` · 38.3 MB · SHA-256 `b5305d061227e7c1…` |
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
4. 125,120 decisions of practice on 0.95.2 (run C2s): eight streams side by side in one
   emulator, `Brain.lesson(x, labels, weights=w)` on all eight rows (rows at critical places
   weigh 3), then `Brain.act`; the draw weighted to stage 2. 57 minutes on one c7i core.
5. 124,896 decisions of DAgger (run C2sd): the brain's own greedy action is executed and the
   teacher labels every state it reaches, same lesson and draw; 32 streams on `backend="mlx"`
   (float32) on an Apple M4, 62 minutes. Checkpoints were read every 25,000 decisions; the one at
   450,016 is packed.

The commands are in the README's "Train your own" (`training/train.py`, `training/pack.py`).

## How it was measured

Brain alone, frozen and greedy, from power-on, 1,500 decisions per start
(`training/evaluate.py`; [`evidence/receipt.json`](evidence/receipt.json)). The runs' checkpoints
were compared on nine selection starts and this one was picked there; nine fresh starts were
read once after the pick.

| Reading | Fresh starts (1, 5, 11, 17, 25, 31, 38, 45, 49) | Selection starts (0, 3, 7, 10, 14, 21, 28, 35, 42) |
| --- | --- | --- |
| Past the hall's stairs (stage 2 reached) | 9 of 9 | 9 of 9 |
| Down the stage-2 staircase and across the underground (block 0, world x 495) | 8 of 9 | 6 of 9 |
| Stage 3 reached | 0 of 9 | 0 of 9 |
| Deaths (all four lives on every start) | 33 in stage 2, 2 in stage 1 | 29 in stage 2, 5 in stage 1 |
| Starts where the brain stands still | 0 | 0 |

The brain before step 5 (C2s at 325,120): fresh 9 of 9 past the stairs and 7 of 9 across the
underground; selection 9 of 9 and 4 of 9. Gate for replacing the packed brain: no worse on both
sets, no start standing still. All readings with `backend="cpu"`: the selection starts on an Apple
M4, the fresh starts on a c7i (Linux).

## The video

[`docs/castlevania-run.mp4`](docs/castlevania-run.mp4): one whole game from the first frame Simon
can move (start after 49 idle decisions, one of the fresh starts: no life lost before stage 2, the
earliest crossing of the underground among them), frozen, greedy, no search, no cuts, drawn
frame by frame by the page's own brain view (`web/render.html`, [`record.py`](record.py)); per-decision log in [`evidence/castlevania-run.json`](evidence/castlevania-run.json).
It shows the courtyard and hall passed with no life lost (0:58), the first life lost at the
stage-2 staircase, then on each of the three other lives the brain going down the staircase and
across the underground to world x 495 (1:18, 2:28, 3:53) and standing there below the staircase
up and out until the life is lost; game over at 4:23. The game's first block ends with the giant
bat at stage 3; this brain does not reach stage 3.

## In the page

Frozen: nothing is learned while the visitor watches. The visitor can start a new game after 0
to 42 idle decisions, pause, and run at 1x, 2x, 4x or as fast as the brain answers. The working
trace and recall memory are cleared at each new game. Nothing is saved. One decision took 35 to
47 ms on an Apple M4 CPU under load (the page shows each decision's time and sweep count).

## Limits

- It does not get past stage 2. On some starts it stops a few pixels short of the bottom-left
  staircase's foot and holds down, which crouches, until enemies take its lives; where it goes
  down, it crosses the underground but walks past the staircase up and out.
- It learned from a teacher's labels; reward played no part.
- Simon's position, facing, stage, block and body state come from RAM, not from pixels.
- Checked on the PRG1 printing and stable-retro's FCEUmm core only.
- The readings are nine starts of one brain; they certify nothing beyond them.

## Licence

GPL-3.0, as Cadence. The game and its ROM are Konami's and are not distributed here.
