# Model card: the Patch World founders

| | |
| --- | --- |
| Demo | Patch World (`patch-world/`) |
| Files | eight brains in `web/pack/founders/` (0.97 MB together), named with their genes in `web/pack/founders/founders.json`; SHA-256 per brain in `web/pack/manifest.json` and in the table below |
| Library | `cadence-net` 0.95.2 (`Brain.load(path, backend="cpu")`, float64; in the page the same wheel in Pyodide) |
| Composition | per founder `Brain.compose(38, 6, modules=(width,) or (width, width // 2), recall=<gene>, episodic=True, consolidation, memory_rate, working_memory_amplitude, working_memory_decay=0.1, efference_amplitude, lateral=-0.5, scales={"sensory": <gene>, "trace": 12}, temperature, actor_eta, actor_eta_bias=actor_eta / 10, actor_lam, actor_gamma, actor_eta_critic, arousal={threshold, decay 0.9, tolerance, floor 0.1, fast 0.05, slow 0.005, heat, youth 300, value_surprise 1, need}, backend="cpu")`, the genes per founder in `web/pack/founders/founders.json`; a brain with the recall gene also takes `teaching="founder", learning_surprise=False, learning_fast_settle=False`, so the gene changes only the memory (`patchworld/brain.py: compose`) |
| Size | 92 to 184 neurons, 1,806 to 5,086 synapses per brain (an association region of 24 or 32 neurons; five carry a recall memory of 128 slots) |
| Date | 2026-11-09 |

## The founders

| Founder | Association | Generation | Island | Neurons | Synapses | File (SHA-256) | Actor step | Temperature | Heat | Need | Store rate | Sense | Size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| evolved-1 | 24 | 20 | 14 | 92 | 1,806 | `evolved-1.npz` (58 KB, `35fbd1fc31adb6eb…`) | 0.065 | 0.13 | 1.67 | 0.000 | 0.50 | 2 | 1.37 |
| evolved-2 | 24 | 3 | 4 | 92 | 1,806 | `evolved-2.npz` (58 KB, `72fa8d1fc0b993d1…`) | 0.039 | 0.22 | 0.54 | 0.000 | 0.20 | 2 | 0.86 |
| evolved-3 | 32, recall | 36 | 21 | 184 | 5,086 | `evolved-3.npz` (175 KB, `40c635f1938b0c76…`) | 0.010 | 0.10 | 0.22 | 0.165 | 0.35 | 2 | 1.33 |
| evolved-4 | 32, recall | 55 | 11 | 184 | 5,086 | `evolved-4.npz` (171 KB, `c4e97dda2132cbc8…`) | 0.017 | 0.21 | 0.00 | 0.146 | 0.26 | 2 | 1.08 |
| evolved-5 | 24, recall | 70 | 13 | 168 | 3,630 | `evolved-5.npz` (140 KB, `5a9cfe8fca6d2744…`) | 0.038 | 0.16 | 0.00 | 0.000 | 0.58 | 3 | 1.50 |
| evolved-6 | 24 | 33 | 6 | 92 | 1,806 | `evolved-6.npz` (58 KB, `28237d7e01f207bb…`) | 0.018 | 0.10 | 0.62 | 0.000 | 0.38 | 2 | 1.34 |
| evolved-7 | 24, recall | 36 | 3 | 168 | 3,630 | `evolved-7.npz` (143 KB, `65f447bad980f90e…`) | 0.020 | 0.10 | 0.84 | 0.114 | 0.19 | 2 | 1.39 |
| evolved-8 | 24, recall | 27 | 20 | 168 | 3,630 | `evolved-8.npz` (141 KB, `693b0b757b9a20cc…`) | 0.024 | 0.13 | 0.27 | 0.069 | 0.40 | 2 | 1.19 |

Every founder has one association region (depth 1), speed 1, and the genes of
`patchworld/genes.py: RANGES` otherwise; the full genes are in `founders.json`.

## What it sees and does

Inputs (38, `patchworld/world.py: observe`): for each of north, east, south and west, the
closeness of the nearest berry, root, leaf, water, predator and other creature within the sense
range (a quadrant each; closeness 1 adjacent, falling to 1/range at the edge; at night the range
halves); underfoot: berry, root, leaf, cache, water beside it; energy as a share of capacity,
thirst, daylight, nausea (the share of a poisoning's 20 moments still to run), cold (one minus
the air temperature, which follows the season with a lag of 250 moments, plus noise of 0.05);
the place as the sine and cosine of each coordinate. The season itself is not an input.

Outputs: six motor neurons in one slot: north, east, south, west, eat, drink. A moment is one
`brain.live(observation, reward=[outcome of the previous action])`: calm, the greedy choice of one
qualified settle, nothing learned; aroused (surprise at the critic's forecast, a want, or its youth),
a sampled choice, the actor and critic learn from the outcome through eligibility
traces, the associative store records it. A refused settle (it never qualified) is retried
without the outcome and otherwise answered with a random action; the count is reported.

## How it was trained

From the world's pay alone; no teacher, no labels. Commands and settings in
[TRAINING.md](TRAINING.md); one c7i.16xlarge (64 vCPU), `cadence-net[fast]`, one thread per
process.

1. **Nursery** (`training/breed.py nursery`): 256 newborn brains, 32 worlds of eight, 30,000
   moments each in a world where energy never falls below one; four gene sets per world, each
   with and without a recall memory on one brain seed. A creature ate 4.9 winter berries per
   1,000 moments in its first winter and 2.8 in its tenth (`evidence/nursery.json`). 11 minutes.
2. **Evolution** (`training/breed.py evolve`): the eight best nursery brains (intake over the
   last 5,000 moments, net of brain cost), arousal heat and need set to zero, founded 32 mortal
   islands of up to 12 learners for 58,500 moments, with births (a child: half the energy, a copy
   of the parent's brain, mutated genes) and deaths. Survivors were 39 generations from their
   founder on average (at most 114); `evidence/islands.json` gives the genes before and after.
   29 minutes.
3. **Selection** (`training/breed.py select`): the eight survivors older than 1,500 moments with
   the best intake per moment, one per island. They were saved at the end of a summer.

## How it was measured

All on world seeds from 100,000 on, which neither the nursery nor the evolution used; the
receipts bind each reading to the SHA-256 of the sources and of every brain it read.

| Reading | Number | Sample | Receipt |
| --- | --- | --- | --- |
| Mean age at death: learner, frozen twin, random walker | 3,117 / 365 / 303 moments | 32 mortal worlds x 8 founders, up to 12,000 moments | `evidence/controls.json` |
| Learner outlived its own twin | 250 of 256; paired difference 2,752 (95% CI 2,443 to 3,067) | same | `evidence/controls.json` |
| Intake per moment: learner, twin, random | 0.220 / 0.100 / 0.037 | same | `evidence/controls.json` |
| Share of berries eaten when standing on one, last 100 moments of summer, then winter 0-100, 200-300, last 100 | learners 98%, 48%, 25%, 4%; twins 96%, 98%, 99%, 92% | 32 worlds x 8 founders, nobody dies | `evidence/flip.json` |
| Berries per 100 moments, first 300 moments of winter 1 and winter 2 | learners 0.72, 0.38; twins 0.50, 0.47 | 32 worlds x 8 founders | `evidence/seasons.json` |
| Intake per moment, evolved against generation 0 (no births) | 0.231 against 0.162 | 32 worlds per group | `evidence/evolution.json` |
| Evolved founders' share of the learners after 12,000 moments of a shared world with births | 56% (95% CI 39% to 72%); all learners in 16 worlds, none in 13 | 32 worlds, 8 founders a side | `evidence/competition.json` |
| Learner minus twin age, generation-0 brains, heat on / heat and need at zero | -451 (CI -728 to -172) / +925 (CI 629 to 1,217) | 32 worlds x 8 brains | `evidence/heat-on.json`, `evidence/heat-off.json` |
| Nuts from hidden caches per 1,000 moments, recall on / off | 0.98 / 1.05 (paired -0.07, 95% CI -0.22 to 0.07) | 16 nursery pairs x 16 worlds | `evidence/caches.json` |

## In the page

Learning, always: every learner in the page lives through `brain.live` as above, from the
packed founder or its parent's brain at birth. Frozen twins (a founder's brain, sampling its
policy, never learning) and random walkers are controls. The visitor can flip the season, drop
berries or roots, add up to four predators and remove them; nothing is saved in the browser.
Measured in headless Chromium (`check_page.py`, `evidence/page-check.json`): The page booted in 8.2 s with Pyodide cached; it ran 13.3 moments a second at full speed (77 ms a moment) with 12 learners, 2 frozen twins and 2 random walkers in four brain workers, the inspected learner's brain recorded sweep by sweep; the brain view drew a frame in 4.0 ms; through a flip the learners kept living and the inspected learner's aroused moments grew; no console errors.

## Limits

- Reward-trained from scratch with no teacher: the founders still eat on bare ground about 94
  moments in 1,000 and pass food they sense; they are measured against frozen twins and random
  walkers, not against an optimal forager.
- The twins lose mostly through a habit their brain held when it was frozen (eating where there
  is nothing), not through winter berries; the winter readings come from worlds where nobody
  dies.
- After a winter, learners return to the berries slowly (24% acceptance in the second summer).
- The recall memory showed no advantage on the caches; selection spread it (0.25 to 0.55 of the
  survivors), for reasons not identified here.
- A child starts from a copy of its parent's brain: what is selected is genes over inherited,
  experienced brains.
- Energy is a declared simulation economy; a settle's residual says the brain agrees with
  itself, not that its action was good.

## Licence

GPL-3.0, as Cadence.
