# Model card: Mako and Mako Deep

Two Tron brains on one page. Both see the same field, answer with the same three motor neurons and
play the same way; they differ in depth and in how they were raised.

| | Mako (flat) | Mako Deep |
| --- | --- | --- |
| Demo | Tron (`tron/`), `?brain=flat` | Tron (`tron/`), `?brain=deep` (the default) |
| File | `web/pack/flat/brain/brain.npz` · 14.2 MB · SHA-256 `a235900228b601f9…` | `web/pack/deep/brain/brain.npz` · 21.7 MB · SHA-256 `77050758caa684f0…` |
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
and the skip held at rate 0 through `learner.synapse_rate`, until the deep pathway decided 75% of
the moves (the deep lessons on the L4, `backend="torch"`). Then two kept generations of
distillation on cadence-net 0.95.2 (`scripts/distil.py`, one c7i.48xlarge, about 35 minutes for the
two): the brain rides alone against bots and its own earlier generations; at each position it
reaches, its own brain + tree search (200 simulations, territory leaves) chooses a move; the
children learn those choices as `lesson` labels, every act and lesson from rest, at rate
0.0009/20, positions where the search is sharp weighted 2.5; a child is kept only if the brain alone
beats its parent through a sequential test of paired differences against `voronoi` (+0.086 over
128 pairs, then +0.069 over 288) and holds head to head against its parent (0.52, 0.55) and the
previous deep brain (0.54, 0.58).

Mako was raised on the 0.95 series before 0.95.2 and loads unchanged on 0.95.2; Mako Deep's last
two generations and all its readings below are on 0.95.2.

## How it was measured

Mirror pairs against `voronoi` (each arena seed twice, the brain in either seat, draws count half),
every move settled from rest, greedy.

| Reading | Mako | Mako Deep | Receipt |
| --- | --- | --- | --- |
| `voronoi`, 128 pairs, seeds 2,200,000+ | 186-68-2, 0.73 ± 0.05 | 182-74, 0.71 ± 0.06 | `brains/flat.json`, `evidence/deep-g3-readings.json` |
| `voronoi`, 128 pairs, seeds 7,000,000+ (never used by selection) | 182-74, 0.71 ± 0.06 | 188-68, 0.73 ± 0.05 | the same |
| Mako 1.0, 128 pairs, seeds 8,000,000+ | 128-106-22, 0.54 | 122-120-14, 0.50 | the same |
| Mako 1.5, 128 pairs, seeds 8,000,500+ | 130-78-48, 0.60 | 102-114-40, 0.48 | the same |
| `voronoi2`, `voronoi3`, `ab5`, 64 pairs each | 0.20, 0.25, 0.14 | `voronoi3` 0.12 | [TRAINING.md](TRAINING.md#5-self-play), `evidence/deep-g3-readings.json` |
| On cadence-net 0.95.2: `voronoi`, 32 pairs, seeds 2,200,000+ | 48-16, 0.75 | (all its readings are on 0.95.2) | `evidence/reading-0952.json` |
| The deep pathway cut (its 73,920 synapses at zero) | | changes 81% of moves, 0.00 against `voronoi` | `evidence/deep-g3-ablation.json` |
| Page: the same moves as the native brain, 2 games each | identical | identical | `evidence/page_check.json` |
| Brain + search, 8 / 16 simulations (not on the page): `voronoi`, 32 pairs; deep: the previous deep brain | 0.63 / 0.66 | 0.63 / 0.63 | `evidence/search-0952.json` |
| Brain + search, 8 / 16 simulations: `voronoi3`, 32 pairs (brain alone 0.27 / 0.09) | 0.25 / 0.09 | 0.22 / 0.09 | the same |

`voronoi` moves to the cell that leaves it the most cells it reaches first, one move ahead for both
riders; `voronoi2` and `voronoi3` look two and three rounds ahead; `ab5` is a 10-ply alpha-beta.
The ± are 95% intervals over games; games from one seed are correlated, so two seed sets can
differ by more than either interval.

## In the page

Frozen: nothing is learned while you play, and a round is fully determined by the seed and your
moves. The visitor picks the brain (`?brain=flat|deep`); the record against each brain is kept in
the browser's local storage, apart per brain. The worker checks every file against its SHA-256
before running. Measured in headless Chromium on an Apple M4 with the anatomy view on
(`evidence/page_check.json`): start 6.1 s (flat) and 10.2 s (deep: Pyodide, NumPy, the wheel and
the brain), a settle in Python 20 ms (flat) and 32 ms (deep) at the median, the whole move in the
worker 26 and 40 ms, the brain view at 60 frames per second; the page ticks every 120 ms. The
panel draws the brain from the side by default (`?view=layers` for the layers): every neuron
replays its recorded sweeps, and every tract is as bright as its live |weight x activation|.

## Limits

- The brain alone loses most games to bots that look further ahead (`voronoi2`, `voronoi3`,
  `ab5`). A tree search the brain guides is stronger at 200 simulations a move and does not fit the
  page: at 8 and 16 simulations a move takes 0.4 to 0.8 s in Pyodide against the 120 ms tick, and
  is no stronger than the brain alone (`evidence/search-0952.json`).
- Readings are against bots, not people; a person who walls the brain in early can beat it.
- It does not learn from your games, and it has no memory between moves.
- A settled state certifies the settle's equations at the tolerance, not the quality of the move.
- The deep brain matches the flat one against `voronoi` and is weaker against `voronoi3` and the
  earlier flat brains; its point is that its deep layers play.

## Licence

GPL-3.0, as Cadence.
