# Model card: Mako and Mako Deep

Two Tron brains on one page. Both see the same field, answer with the same three motor neurons and
play the same way; they differ in depth and in how they were raised.

| | Mako (flat) | Mako Deep |
| --- | --- | --- |
| Demo | Tron (`tron/`), `?brain=flat` | Tron (`tron/`), `?brain=deep` (the default) |
| File | `web/pack/flat/brain/brain.npz` · 14.2 MB · SHA-256 `a235900228b601f9…` | `web/pack/deep/brain/brain.npz` · 15.1 MB · SHA-256 `bfac8fa5fa938a09…` |
| Library | `cadence-net` 0.95.2, `Brain.load(..., backend="cpu")`, float64 (NumPy in Pyodide on the page) | the same |
| Composition | `Brain.compose(2470, 3, modules=(256,), lateral=-0.5, recall=False, arousal=True, seed=23)`, teaching at the normalized point (rate 3.75e-5, normalize 0.99), temperature 0.1, working-trace amplitude 0 | `Brain.compose(connectome=...)`: the (256, 128, 32) layout plus a skip between `module_0` and the motor neurons both ways; the same learner settings at rate 9e-4; recall off; working-trace amplitude 0 |
| Size | 2,985 neurons, 699,398 synapses | 2,921 neurons, 708,806 synapses |
| Date | 2026-11-09 | 2026-11-09 |

## What it sees and does

**Inputs (2,470, `tron/field.py`).** The whole 24 x 24 arena turned so the rider's heading points
up: blocked cells (walls and every trail, 576), the opponent's trail (576), its own head (576), the
opponent's head (576); a 9 x 9 fovea around its head, blocked cells (81) and the opponent's head
(81); the opponent's heading relative to its own, one of four (4).

**Outputs.** Three motor neurons: turn left, ride straight, turn right.

**One decision.** `brain.reset()`, then `brain.act(field(arena, seat)[None, :], greedy=True)`: the
whole brain settles from rest on the field and the strongest motor neuron is the move. No search
and no memory between moves. A settle that does not qualify is refused and the cycle rides
straight on; the page counts refusals.

## How it was trained

The full route, with commands, hardware and times, is [TRAINING.md](TRAINING.md);
`scripts/smoke.sh` runs every stage at a size that takes half an hour on a laptop.

**Mako (flat).** A genetic search over `Brain.compose` settings (1,536 raisings on a 64-core box,
about 4 h) picked a one-region brain at the normalized teaching point. Then, on one box with an
NVIDIA L4 and 64 cores: corpus lessons from a `voronoi3` teacher and DAgger with `voronoi3`
labels on the brain's own positions (100,000 moments); expert iteration, where a 6-ply alpha-beta
search with the brain's own move as a prior labels each position the brain reaches, kept
generation by generation through a gate (40,000 moments: Mako 1.0); selection between short
branches of expert iteration (Mako 1.5, 1.6); self-play against its own past generations, an
exploiter and a pool of bots and earlier brains, with search labels taught by `lesson`, critical
positions weighted 2.5 through `lesson(..., weights=)` and a sequential gate (two lines, 20
generations, 28,500 moments in the second). About 43 hours of wall time from the search to the shipped brain.

**Mako Deep.** Mako 1.6 grafted into the first layer of a (256, 128, 32) brain with a skip from
that layer to the motor neurons, the new pathway at 0.2 of its construction, so the deep brain
starts with Mako 1.6's play; one kept generation of self-play; then five stages, each halving the
skip and teaching the deep pathway alone the moves of that self-play brain, with the first layer
and the skip held at rate 0 through `learner.synapse_rate`, until the deep pathway decides 75% of
the moves. The deep lessons ran on the L4 (`backend="torch"`).

Both were raised on the 0.95 series before 0.95.2 and load unchanged on 0.95.2; their 0.95.2
re-reading is below.

## How it was measured

Mirror pairs against `voronoi` (each arena seed twice, the brain in either seat, draws count half),
every move settled from rest, greedy.

| Reading | Mako | Mako Deep | Receipt |
| --- | --- | --- | --- |
| `voronoi`, 128 pairs, seeds 2,200,000+ | 186-68-2, 0.73 ± 0.05 | 160-96, 0.63 ± 0.06 | `brains/flat.json`, `brains/deep.json` |
| `voronoi`, 128 pairs, seeds 7,000,000+ (never used by selection) | 182-74, 0.71 ± 0.06 | 170-86, 0.66 ± 0.06 | the same |
| Mako 1.0, 128 pairs, seeds 8,000,000+ | 128-106-22, 0.54 | 108-122-26, 0.47 | the same |
| Mako 1.5, 128 pairs, seeds 8,000,500+ | 130-78-48, 0.60 | 104-104-48, 0.50 | the same |
| `voronoi2`, `voronoi3`, `ab5`, 64 pairs each | 0.20, 0.25, 0.14 | not read | [TRAINING.md](TRAINING.md#5-self-play) |
| On cadence-net 0.95.2: `voronoi`, 32 pairs, seeds 2,200,000+ | 48-16, 0.75 | 40-24, 0.63 | `evidence/reading-0952.json` |
| The deep pathway cut (its 73,920 synapses at zero) | | changes 75% of moves, 0.00 against `voronoi` | `brains/deep.json` |
| Page: the same moves as the native brain, 2 games each | identical | identical | `evidence/page_check.json` |

`voronoi` moves to the cell that leaves it the most cells it reaches first, one move ahead for both
riders; `voronoi2` and `voronoi3` look two and three rounds ahead; `ab5` is a 10-ply alpha-beta.
The ± are 95% intervals over games; games from one seed are correlated, so two seed sets can
differ by more than either interval.

## In the page

Frozen: nothing is learned while you play, and a round is fully determined by the seed and your
moves. The visitor picks the brain (`?brain=flat|deep`); the record against each brain is kept in
the browser's local storage, apart per brain. The worker checks every file against its SHA-256
before running. Measured in headless Chromium on an Apple M4 (`evidence/page_check.json`): start
8.1 to 8.4 s (Pyodide, NumPy, the wheel and the brain), a settle in Python 30 ms (flat) and 40 ms
(deep) at the median, the whole move in the worker 38 and 47 ms; the page ticks every 120 ms.

## Limits

- The brain alone loses most games to bots that look further ahead (`voronoi2`, `voronoi3`,
  `ab5`). A tree search the brain guides is stronger and is not on the page yet
  ([TRAINING.md](TRAINING.md#a-brain-guided-search)).
- Readings are against bots, not people; a person who walls the brain in early can beat it.
- It does not learn from your games, and it has no memory between moves.
- A settled state certifies the settle's equations at the tolerance, not the quality of the move.
- The deep brain is weaker than the flat one against `voronoi`; its point is that its deep layers
  play.

## Licence

GPL-3.0, as Cadence.
