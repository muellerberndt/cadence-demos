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
  sweep (budget 1,024 sweeps). *Brain alone:* the strongest column neuron among the columns with
  room (greedy). *Brain + search* (the page's default): the column neurons, as a softmax at the
  temperature 0.2, rank the columns for a negamax search with alpha-beta pruning over the game's
  rules (`connect4/search.py`, 120,000 positions a move, a threat count at its horizon); a proven
  win is played, columns proven lost are dropped, and among the rest the brain's column is played
  unless the search scores another higher by more than 0.25. The verdict is read beside the move
  and enters neither.

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
brain alone, on 3,000 held-out positions from solver games never taught:

| Reading | Result |
| --- | --- |
| The solver's optimal move | 77.3% |
| A move that keeps the theoretical result, where the mover is not already lost | 92.3% |
| An immediate win taken (positions that have one) | 68.0% |
| A forced block made (positions that need one) | 85.3% |
| The verdict agrees with the solver's result | 89.2% |

Games from the empty board, `python -m c4train.play_search` (record:
`evidence/search_reading.json`); won-drawn-lost for the brain's side, 40 games a row unless
stated; the solver at 0.9 and 0.7 plays a random column one move in ten and three in ten:

| Opponent | Brain alone | Brain + search |
| --- | --- | --- |
| The perfect solver, the brain first | 119-50-31 (200 games, `evidence/reading.json`) | 363-25-12 (400 games) |
| The perfect solver, the brain second | 0-0-40 | 0-0-40 |
| The solver at 0.9, the brain first | 29-10-1 | 38-1-1 |
| The solver at 0.9, the brain second | 12-7-21 | 62-13-45 (120 games) |
| The solver at 0.7, the brain first | 30-6-4 | 36-2-2 |
| The solver at 0.7, the brain second | 27-4-9 | 37-2-1 |
| Brain + search against the brain alone (search first, search second) | | 34-5-1, 24-3-13 |

The perfect solver wins every game it starts.

## In the page

Frozen while you play: its moves never change during a game. A visitor can teach it (*Teach
it*): one `brain.lesson` on the brain's last board, labelled with the visitor's column and the
verdict the brain holds now, only when the brain does not already play that column, at a step of
0.0033 (the bias a tenth of it). Lessons live in the tab; a reload or *Reset brain* restores the
file. The visitor's record and lessons are not saved.

Measured by `check_page.py` in headless Chromium on an Apple M4 at a load average near 200
(`evidence/page_check.json`), with brain + search: startup 42 s; a settle 54–116 sweeps and
0.9–3.0 s in the worker; the search, in JavaScript (`web/search.js`, identical to
`connect4/search.py` on 200 recorded positions), 0.28–0.97 s; a click to the brain's stone on the
board 3.7–7.6 s with the animations; the brain view at 29 frames per second.

## Limits

- Alone, it misses about a third of the immediate wins it could take and about one forced block
  in seven. With the search it takes every win the search proves and avoids every column
  the search proves lost while another remains; it still loses some games it starts against
  perfect play.
- The search is a hand-written look-ahead over the rules, not the brain; its horizon score is
  a threat count. Neither player has an opening book or a memory of the game so far.
- The verdict is a judgement read beside the move, not a proof; it agrees with the solver's
  result on 89% of held-out positions.
- The readings certify these sets and seeds, not every game; a settled state certifies the
  settle's equations at the tolerance, not the move's quality.

## Licence

GPL-3.0, as Cadence. The solver used to train and measure it (not included) is AGPL-3.0.
