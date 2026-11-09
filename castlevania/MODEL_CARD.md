# Model card: Simon (D2 at 425,280 decisions)

| | |
| --- | --- |
| Demo | Castlevania (`castlevania/`) |
| File | `brain/brain.npz` · 36.7 MB · SHA-256 `b868dc955e544df9…` |
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
5. 100,160 decisions of DAgger (run D2): the brain's own greedy action is executed and the
   teacher labels every state it reaches, same lesson and draw; eight streams on one c7i core.
   After 74,880 of them the teacher gained one recovery rule (jump left off the low ledge past the
   underground's exit stairs, onto the floor, x 470-500 at y 144), and the run resumed from its
   checkpoint at 400,000 with it. Checkpoints were read every 25,000 decisions; the one at 425,280
   is packed.

The commands are in the README's "Train your own" (`training/train.py`, `training/pack.py`).

## How it was measured

Brain alone, frozen and greedy, from power-on, 1,500 decisions per start
(`training/evaluate.py`; [`evidence/receipt.json`](evidence/receipt.json)). The runs' checkpoints
were compared on nine selection starts and this one was picked there; nine fresh starts were
read once after the pick.

| Reading | Fresh starts (1, 5, 11, 17, 25, 31, 38, 45, 49) | Selection starts (0, 3, 7, 10, 14, 21, 28, 35, 42) |
| --- | --- | --- |
| Past the hall's stairs (stage 2 reached) | 9 of 9 | 9 of 9 |
| Down the stage-2 staircase and across the underground | 8 of 9 | 9 of 9 |
| Stage 3 reached (the giant bat's stage) | 2 of 9 | 3 of 9 |
| Bat health taken (of 64), best start | 0 | 36 (start 42) |
| Deaths (all four lives on every start) | 20 in stage 2, 5 in stage 1, 2 in stage 3 | 17 in stage 2, 2 in stage 1, 4 in stage 3 |
| Starts where the brain stands still | 0 | 0 |

The previous packed brain (C2sd at 450,016): fresh 9 of 9 past the stairs, 8 of 9 across the
underground, 0 of 9 in stage 3; selection 9, 6 and 0. Gate for replacing the packed brain: no worse
on both sets, no start standing still. All readings with `backend="cpu"` on a c7i (Linux).

## The video

[`docs/castlevania-run.mp4`](docs/castlevania-run.mp4): one whole game from the first frame Simon
can move, start after 42 idle decisions (a selection start), frozen, greedy, no search, no cuts,
every frame drawn by the page's own brain view (`web/render.html`, [`record.py`](record.py));
per-decision log in [`evidence/castlevania-run.json`](evidence/castlevania-run.json). Life 1 clears
the courtyard and the hall and climbs into stage 2 (0:56). Lives 1 and 2 are lost in stage 2. Life 3
goes down into the underground, across it, up its exit stairs and into stage 3 (2:14), and is lost
there. Life 4 fights the giant bat, which loses 36 of its 64 health, until the game over (4:32).
[`docs/castlevania-highlights.mp4`](docs/castlevania-highlights.mp4) cuts two stretches of that game
together (life 1 to stage 2; life 3 through the underground into stage 3), each captioned with its
start and life and preceded by a card marking the cut. The game's first block ends with the giant
bat at stage 3; this brain has not beaten it.

## In the page

Frozen: nothing is learned while the visitor watches. The visitor can start a new game after 0
to 42 idle decisions, pause, and run at 1x, 2x, 4x or as fast as the brain answers. The working
trace and recall memory are cleared at each new game. Nothing is saved. One decision took 35 to
47 ms on an Apple M4 CPU under load (the page shows each decision's time and sweep count).

## Limits

- It has not beaten the giant bat that ends the game's first block (stage 3): it reaches the bat
  on 2 of 9 fresh starts. On the other starts it loses its lives in stage 2, at the bottom-left
  staircase or on the low ledge past the underground's exit.
- It learned from a teacher's labels; reward played no part.
- Simon's position, facing, stage, block and body state come from RAM, not from pixels.
- Checked on the PRG1 printing and stable-retro's FCEUmm core only.
- The readings are nine starts of one brain; they certify nothing beyond them.

## Licence

GPL-3.0, as Cadence. The game and its ROM are Konami's and are not distributed here.
