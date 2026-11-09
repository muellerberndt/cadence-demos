# Model card: W1b (run F2, checkpoint 35)

| | |
| --- | --- |
| Demo | Super Mario Bros. (`mario/`) |
| File | `brain/brain.npz` · 15.7 MB · SHA-256 `c2309a13b99638470fbe399225d864aa292e47363149d762cd52b0fa27802472` (the bytes saved in training, unchanged) |
| Library | `cadence-net` 0.95.2 (`Brain.load(path, backend="cpu")`, float64, as `play.py` and `evaluate.py` load it); trained on 0.91.1 to 0.91.3 |
| Composition | `Brain.compose`: 2,000 inputs, modules (256,), 7 motor neurons in one slot, no observers, seed 0 |
| Size | 2,519 neurons, 581,120 synapses |
| Author | Sean Hall ([cadence-arcade](https://github.com/sean-mcclane832/cadence-arcade)) |
| Date | trained 2026-11-01; packed 2026-11-09 |

## What it sees and does

- **Inputs (2,000, [`smb/eye.py`](smb/eye.py)).** The playfield below the score bar in grey,
  8 x 8 px blocks (26 x 32), as distance from the frame's most common grey, for this decision
  and the previous one (1,664). Then 42 body readings, 8 copies (336): Mario's x and y speed as
  population codes, float state, still rising, facing, power state, hurt and star timers and the
  level timer, all from RAM, and the 4 buttons held during the last decision. No enemy, tile or
  pit position is read from RAM.
- **Outputs.** One slot of 7: none, right, right+jump, run, run+jump, jump, left. The chosen
  combination is held for 4 frames.
- **One decision.** `Brain.predict(x)` on that decision's observation.

## Memory

| Memory | Writes | Reads | Capacity | Reset |
| --- | --- | --- | --- | --- |
| Two-frame screen (in the input) | each decision | each decision | 1 previous decision | new attempt |
| Held buttons (in the input) | each decision | each decision | the last decision | new attempt |
| Working memory (composed: association to prefrontal, 256) | none in play | not by `predict` | - | - |
| Hippocampus (composed, consolidating) | 0 (none in training or play) | - | - | - |
| Recall memory | not composed | - | - | - |

`predict` carries nothing from one call to the next: on the 32 recorded observations in
`tests/answers.npz` the answers in forward and in reversed order are identical
(`tests/test_brain.py`). By this repository's AGENTS.md the layout is close to a control (a window
of input, one processing region, a readout taught on every presentation). It is packed because it
is the brain that got furthest in this game.

## How it was trained

Imitation of a coach, then DAgger. The coach is not a learner: at every decision it saves the
emulator, plays out a fixed menu of short button plans 16 decisions ahead (run, run-jumps of
several lengths, wait, back off, short hops), and labels the first button of the plan that ends
furthest right without dying, scoring plans by Mario's x and the death flag read from RAM.

Training steps are batches of 32 labelled observations through the brain's learner with memory
off (`brain.learner.step(brain.stimulus(x, memory=False), labels)`), 250 steps a chunk, from piles
of coach labels per level. DAgger rounds: the brain plays greedily, from the level's start and
from points along the coach's own path, and the coach labels every screen the brain reaches;
those rows join the pile.

Lineage, all on screen input plus the body readings above:
1. `1-2_12n59`: a 1-1 and 1-2 brain (steady training on 1-1 and 1-2 piles with DAgger on 1-2).
2. Three hours of 1-2 DAgger (run N), checkpoint 35.
3. Run F, all four World 1 levels (lesson shares 1-1 0.20, 1-2 0.30, 1-3 0.25, 1-4 0.25, DAgger on
   1-3 and 1-4 every 10 chunks), checkpoint 30.
4. Run F2 from there (shares 1-1 0.15, 1-2 0.25, 1-3 0.40, 1-4 0.20; a DAgger round on 1-3 every
   8 chunks, 16 attempts, half from the start, half from points on the coach's 1-3 paths),
   checkpoint 35, 77 minutes in, 4 worker processes.

The training code is in
[cadence-arcade](https://github.com/sean-mcclane832/cadence-arcade/tree/main/mario)
(`concepts/csteady.py`, `concepts/cplay.py`, `dagger.py`, `game.py`); it runs on
gym-super-mario-bros, whose licence is not an open one, so it is not part of this folder.

## How it was picked

Start sets are idle frames before the first decision (the emulator is deterministic). Training and
DAgger drew from starts 0 to 79 except 32 to 41. Each chunk's checkpoint was compared on selection
starts from that pool (every third start), and the run's log also read the held-out starts for
each new best. Several F2 checkpoints were scored on the 50 held-out starts (32 to 41, 80 to 99,
even 100 to 138), and at that point (02:20, 77 minutes in) this one was the most balanced of those
scored (every level at least 7 of 50; checkpoint 87, scored later, also reached 7 on every level,
with 22 / 7 / 15 / 27). Six F2 checkpoints played the five-life gauntlet; this is the one that got
past 1-1 (one cleared nothing, four cleared only 1-1). So the held-out column is the set it was
picked on; the fresh column (starts 140 to 189) was read once, after the pick, for this card.

## How it was measured

Brain alone, frozen and greedy, one attempt per start, small Mario, stuck limit 40 decisions
without a new furthest x, cap 900 decisions ([`evaluate.py`](evaluate.py);
[`evidence/receipt.json`](evidence/receipt.json)).

| Level | Held-out (picked on) | Fresh 140 to 189 (read once) |
| --- | --- | --- |
| 1-1 | 7 of 50 | 11 of 50 |
| 1-2 | 8 of 50 | 1 of 50 |
| 1-3 | 9 of 50 | 15 of 50 |
| 1-4 | 27 of 50 | 34 of 50 |
| Attempts ended standing still (40 decisions, no new furthest x) | 40, all on 1-1 | 27, all on 1-1 |

The five-life gauntlet ([`evidence/gauntlet.json`](evidence/gauntlet.json), the video): 1-1, 1-2
and 1-4 on the first try, 1-3 on the fourth (deaths at x 747, 1,200, 1,202), then game over in
2-1 (x 343, 346), never trained on. The first tries start at 0 idle frames, which is in the
training pool.

## Console parity

The brain was raised on gym-super-mario-bros 7.4.0 (Christian Kauten).
[`smb/console.py`](smb/console.py) re-implements its single-level start and frame handling step by
step on nes-py; none of its code is copied. With the training dump, the 9 gauntlet attempts and
the 200 held-out attempts give identical screens, RAM, observations and buttons at every decision
(32,402 decisions), on 0.91.1 with that package and on 0.95.2 with this console; cadence-net
0.95.2 answers the same as 0.91.1 on every one of those observations (0.91.1 and 0.91.3 had
answered identically on 18,000 observations when the line moved to 0.91.3). `tests/test_brain.py`
keeps 32 of them.

## Limits

- World 1 only. It has never been trained on any other world: in 2-1 it got no further than x 722
  on 50 starts (0 flags) and died at x 343 and 346 in the gauntlet.
- None of the four levels is consistent. 1-4 is the strongest (27 and 34 of 50); 1-2 drops from
  8 held-out clears to 1 fresh one, so its held-out number was partly the pick.
- On 1-1 most failures are standing still, not deaths.
- The dump: measured on one dump of the cartridge; other dumps are unchecked.
