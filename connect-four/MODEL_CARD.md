# Model card: the Connect Four brain

| | |
| --- | --- |
| Demo | Connect Four (`connect-four/`) |
| File | `web/pack/brain.npz` · 25.0 MB · SHA-256 `29bac892de8fd1cd…` (the full hash is in `web/pack/manifest.json`) |
| Library | `cadence-net` 0.95.2, loaded with `Brain.load(path, backend="cpu", precision="float64")` |
| Composition | `Brain.compose(126, 10, modules=(1024, 1024), slots=(7, 3), apical=0.25, working_memory_amplitude=0.0, episodic=False)`; no recall memory; the normalized teaching point with a projection-relative floor of 0.1 and nudged phases of a fixed 32 sweeps |
| Size | 3,208 neurons, 3,295,232 synapses (1,058,816 on the apical compartment) |
| Date | 2026-11-09 |

## What it sees and does

- **Inputs:** 126 neurons in {0, 1}, each a 6 × 7 board read row-major from the bottom left: the
  stones of the side to move (on its turn, the brain), the opponent's stones, and the cells where
  a stone dropped in each column would land.
- **Outputs:** two motor slots. Seven column neurons, one per column; three verdict neurons, its
  judgement of the position for the side to move (loss, draw, win).
- **A decision:** one memory-free settle from rest,
  `brain.learner.free(brain.stimulus(x, memory=False))`, until no activation moves by 0.003 in a
  sweep (budget 1,024 sweeps). The move is the strongest column neuron among the columns with
  room (greedy). The verdict is read beside it; the move does not read it. No search.

## How it was trained

From a perfect Connect Four solver ([Pascal Pons' solver](https://github.com/PascalPons/connect4))
as the teacher, on one NVIDIA A10G (torch backend), in three stages, each continuing the brain
of the one before:

| Stage | Lessons | Rows a lesson | Precision | Wall time | What was taught |
| --- | --- | --- | --- | --- | --- |
| 1 | 2,000 | 256 | float64 | 1.2 h | from a fresh brain: the solver's centre-most optimal column, or the brain's own column where it keeps the theoretical result; the solver's result as the verdict |
| 2 | 58,000 | 256 | float32 | 12.0 h | the same |
| 3 | 20,000 | 512 | float32 | 6.3 h | the same at a third of the rate, annealed once more (by 0.33) at a plateau |

Every row of a batch was taught. Batches drew from three million solver-labelled positions of
games of the solver against itself (deliberate mistakes, short random openings, each position
also mirrored); a quarter of each batch had a win to take or a win to block, an eighth were
finished boards seen by the loser (verdict: loss). Every 1,000 lessons the brain played 64 games
against the solver and 16 from the empty board, whose positions joined the pool, with each move
that slipped shown four more times.

The trainer is `training/c4train/train.py`; the README gives the commands to continue this brain
on a CUDA GPU or on Apple silicon with MLX, with the lesson options of 0.95.x (`targets=` and
`weights=`). The page's file is `training/c4train/page_copy.py` of the trained checkpoint: the
optimizer's running moments zeroed and the synapses stored in float32, the precision the brain
was trained in. On 256 test positions its motor activations differ from the checkpoint's by at
most 2e-6, with the same moves.

## How it was measured

`python -m c4train.reading web/pack/brain.npz 200 20991` (record: `evidence/reading.json`), the
brain alone:

| Reading | Result |
| --- | --- |
| The solver's optimal move, 3,000 held-out positions from solver games never taught | 77.3% |
| A move that keeps the theoretical result, where the mover is not already lost | 92.3% |
| An immediate win taken (positions that have one) | 68.0% |
| A forced block made (positions that need one) | 85.3% |
| The verdict agrees with the solver's result | 89.2% |
| Moving first against the perfect solver, 200 games from the empty board | 119 won, 50 drawn, 31 lost |
| Moving second against the solver at 90% (a random column one move in ten), 200 games | 46 won, 36 drawn, 118 lost |

The perfect solver wins every game it starts, so the second-seat games are against a solver that
makes random moves. The page plays the brain alone.

## In the page

Frozen while you play: its moves never change during a game. A visitor can teach it (*Teach
it*): one `brain.lesson` on the brain's last board, labelled with the visitor's column and the
verdict the brain holds now, only when the brain does not already play that column, at a step of
0.0033 (the bias a tenth of it). Lessons live in the tab; a reload or *Reset brain* restores the
file. The visitor's record and lessons are not saved.

Measured by `check_page.py` in headless Chromium on an Apple M4 (`evidence/page_check.json`):
startup (Pyodide, NumPy, Cadence, the brain) 32 s; a settle 43–85 sweeps and 0.9–2.9 s in the
worker; a click to the brain's stone on the board 2.8–4.9 s with the animations; the seven
imagined replies, when ticked, 8.6 s more. The machine was running other jobs at the time.

## Limits

- It misses about a third of the immediate wins it could take and about one forced block in
  seven.
- It plays from one settle: no search, no opening book, no memory of the game so far.
- The verdict is a judgement read beside the move, not a proof; it agrees with the solver's
  result on 89% of held-out positions.
- The readings certify these sets and seeds, not every game; a settled state certifies the
  settle's equations at the tolerance, not the move's quality.

## Licence

GPL-3.0, as Cadence. The solver used to train and measure it (not included) is AGPL-3.0.
