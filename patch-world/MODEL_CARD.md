# Model card: the Patch World founders

| | |
| --- | --- |
| Demo | Patch World (`patch-world/`) |
| Files | eight brains in `web/pack/founders/` (0.90 MB together), named with their genes in `web/pack/founders/founders.json`; SHA-256 per brain in `web/pack/manifest.json` and in the table below |
| Library | `cadence-net` 0.95.2 (`Brain.load(path, backend="cpu")`, float64; in the page the same wheel in Pyodide) |
| Composition | per founder `Brain.compose(38, 6, modules=(width,) or (width, width // 2), recall=<gene>, episodic=True, consolidation, memory_rate, working_memory_amplitude, working_memory_decay=0.1, efference_amplitude, lateral=-0.5, scales={"sensory": <gene>, "trace": 12}, temperature, actor_eta, actor_eta_bias=actor_eta / 10, actor_lam, actor_gamma, actor_eta_critic, arousal={threshold, decay 0.9, tolerance, floor 0.1, fast 0.05, slow 0.005, heat, youth 300, value_surprise 1, need}, backend="cpu")`, the genes per founder in `web/pack/founders/founders.json`; a brain with the recall gene also takes `teaching="founder", learning_surprise=False, learning_fast_settle=False`, so the gene changes only the memory (`patchworld/brain.py: compose`) |
| Size | 92 to 168 neurons, 1,806 to 3,630 synapses per brain (one association region of 24 neurons; five carry a recall memory of 128 slots) |
| Date | 2026-11-09 |

## The founders

| Founder | Association | Generations in round 2 | Round-1 founder | Island | Neurons | Synapses | File (SHA-256) | Actor step | Temperature | Heat | Need | Store rate | Sense | Size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| round2-1 | 24 | 46 | evolved-6 | 26 | 92 | 1,806 | `round2-1.npz` (59 KB, `8206909d586224c2…`) | 0.012 | 0.10 | 0.55 | 0.279 | 0.19 | 5 | 1.50 |
| round2-2 | 24 | 35 | evolved-6 | 23 | 92 | 1,806 | `round2-2.npz` (52 KB, `3a80003dc8da2a02…`) | 0.017 | 0.10 | 1.62 | 0.127 | 0.47 | 3 | 1.50 |
| round2-3 | 24, recall | 55 | evolved-6 | 40 | 168 | 3,630 | `round2-3.npz` (138 KB, `0890a7898f3919b9…`) | 0.008 | 0.10 | 1.12 | 0.004 | 0.34 | 4 | 1.31 |
| round2-4 | 24, recall | 44 | evolved-7 | 12 | 168 | 3,630 | `round2-4.npz` (140 KB, `6ab79a08a1e95558…`) | 0.024 | 0.15 | 0.38 | 0.207 | 0.13 | 3 | 1.50 |
| round2-5 | 24 | 36 | evolved-6 | 18 | 92 | 1,806 | `round2-5.npz` (59 KB, `b1f58c5f8e739e50…`) | 0.002 | 0.11 | 0.76 | 0.098 | 0.14 | 3 | 1.49 |
| round2-6 | 24, recall | 47 | evolved-8 | 38 | 168 | 3,630 | `round2-6.npz` (148 KB, `d6b3e46b21682e7f…`) | 0.020 | 0.10 | 1.22 | 0.029 | 0.05 | 5 | 1.50 |
| round2-7 | 24, recall | 45 | evolved-6 | 9 | 168 | 3,630 | `round2-7.npz` (142 KB, `0749ba3adf8220cc…`) | 0.009 | 0.12 | 1.46 | 0.108 | 0.33 | 4 | 1.50 |
| round2-8 | 24, recall | 67 | evolved-7 | 8 | 168 | 3,630 | `round2-8.npz` (140 KB, `5c29ad0a935a25b8…`) | 0.008 | 0.10 | 1.36 | 0.215 | 0.07 | 3 | 1.50 |

Every founder has one association region (depth 1) and speed 1; the full genes are in
`founders.json`. The round-1 founders they descend from (evolved-6, -7, -8 of round 1) were
33, 36 and 27 generations past the nursery.

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
3. **Selection** (`training/breed.py select`): the eight round-1 survivors older than 1,500
   moments with the best intake per moment, one per island.
4. **Round 2** (`training/breed.py evolve --nursery runs/founders/after`): those eight founded
   48 islands for 118,500 moments, with the genes they had evolved; survivors were 55
   generations from them on average (at most 136). 65 minutes, beside other runs on the same machine.
5. **Selection** again, as in step 3: the page's founders, saved at the end of a summer. They
   replaced the round-1 founders because they beat them on the same fresh-seed readings: learner
   against twin lifespan, the season flip, the second winter, and a shared world with births.

## How it was measured

All on world seeds from 100,000 on, which neither the nursery nor the evolution used; the
receipts bind each reading to the SHA-256 of the sources and of every brain it read.

| Reading | Number | Sample | Receipt |
| --- | --- | --- | --- |
| Mean age at death: learner, frozen twin, random walker | 3,933 / 284 / 300 moments | 32 mortal worlds x 8 founders, up to 12,000 moments | `evidence/controls.json` |
| Learner outlived its own twin | 253 of 256; paired difference 3,648 (95% CI 3,277 to 4,005) | same | `evidence/controls.json` |
| Intake per moment: learner, twin, random | 0.209 / 0.069 / 0.037 | same | `evidence/controls.json` |
| Share of berries eaten when standing on one, last 100 moments of summer, then winter 0-100, 200-300, last 100 | learners 99%, 45%, 23%, 5%; twins 97%, 98%, 100%, 96% | 32 worlds x 8 founders, nobody dies | `evidence/flip.json` |
| Berries per 100 moments, first 300 moments of winter 1 and winter 2 | learners 0.60, 0.32; twins 0.15, 0.15 | 32 worlds x 8 founders | `evidence/seasons.json` |
| Intake per moment and lifespan without births, page founders against generation 0 | 0.212 against 0.162; 3,249 against 2,968 moments | 32 worlds per group | `evidence/evolution.json` |
| Page founders' share of the learners after 12,000 moments of a world with births shared with generation 0 | 89% (95% CI 76% to 99%); all learners in 25 worlds, none in 3 | 32 worlds, 8 founders a side | `evidence/competition.json` |
| The same against the round-1 founders | 82% (95% CI 68% to 96%) | 32 worlds | `evidence/round2-vs-round1-competition.json` |
| Learner minus twin age, generation-0 brains, heat on / heat and need at zero | -451 (CI -728 to -172) / +925 (CI 629 to 1,217) | 32 worlds x 8 brains | `evidence/heat-on.json`, `evidence/heat-off.json` |
| Nuts from hidden caches per 1,000 moments, recall on / off | 0.98 / 1.05 (paired -0.07, 95% CI -0.22 to 0.07) | 16 nursery pairs x 16 worlds | `evidence/caches.json` |

## In the page

Learning, always: every learner in the page lives through `brain.live` as above, from the
packed founder or its parent's brain at birth. Frozen twins (a founder's brain, sampling its
policy, never learning) and random walkers are controls. The visitor can flip the season, drop
berries or roots, add up to four predators and remove them; nothing is saved in the browser.
Measured in headless Chromium (`check_page.py`, `evidence/page-check.json`): The page booted in 2.6 s with Pyodide cached; it ran 43.7 moments a second at full speed (36 ms a moment) with 12 learners, 2 frozen twins and 2 random walkers in four brain workers, the inspected learner's brain recorded sweep by sweep; the brain view drew a frame in 2.5 ms; through a flip the learners kept living and the inspected learner's aroused moments grew; no console errors.

## Limits

- Reward-trained from scratch with no teacher: the founders still eat on bare ground about 131
  moments in 1,000 and pass food they sense; they are measured against frozen twins and random
  walkers, not against an optimal forager.
- The twins lose mostly through a habit their brain held when it was frozen (eating where there
  is nothing), not through winter berries; the winter readings come from worlds where nobody
  dies.
- After a winter, learners return to the berries slowly (27% acceptance in the second summer).
- The recall memory showed no advantage on the caches; selection spread it in round 1 (0.25 to
  0.55 of the survivors) and held it near half in round 2, for reasons not identified here.
- A child starts from a copy of its parent's brain: what is selected is genes over inherited,
  experienced brains.
- Energy is a declared simulation economy; a settle's residual says the brain agrees with
  itself, not that its action was good.

## Licence

GPL-3.0, as Cadence.
