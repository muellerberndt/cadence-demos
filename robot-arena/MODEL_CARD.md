# Model card: the Showcase League roster

| | |
| --- | --- |
| Demo | Robot Arena, the Cadence Showcase League (`robot-arena/`) |
| Files | six brains in `showcase-app/public/pack/brains/` (the page's pack), the same files and the two robots not packed in `league-live/brains/`; SHA-256 per brain in `showcase-app/public/pack/manifest.json` |
| Library | `cadence-net` 0.95.2 (`Brain.load` on the CPU, float64; in the page the same wheel in Pyodide) |
| Composition | per robot `Brain.compose(inputs, motor neurons, modules=(48, 24), slots=<one slot per motor>, recall=False, episodic=True, consolidation=0.05, working_memory_amplitude=0.3, working_memory_decay=0.1, efference_amplitude=0, lateral=-0.5, scales={"sensory": 4, "trace": 12}, temperature=0.3, actor_eta=0.03, actor_eta_bias=0.003, actor_lam=0.6, actor_gamma=0.95, actor_eta_critic=5, arousal=<founder>)` (`arena/brain.py:compose`) |
| Size | 132 to 154 neurons, 4,632 to 5,708 synapses per brain |
| Date | 2026-11-09 |

## The roster

| Robot | Body | Motor neurons | Inputs | Neurons | Synapses | File (SHA-256) | Moments lived | Driving test | Marks | Elo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dozer | heavy: wheel@70, wheel@-70, wheel@110, wheel@-110, arm/spike@15, arm/spike@-15, arm/hammer@0 | 21 | 26 | 143 | 5,178 | `Dozer.npz` (115 KB, `08fb2c823ff01742…`) | 114,615 | +0.28 (4/8) | `+-++---+` | 1143 |
| Crab | medium: leg@60, leg@-60, leg@120, leg@-120, arm/hammer@20, arm/spike@-20 | 18 | 32 | 146 | 5,316 | `Crab.npz` (127 KB, `2814f8d419c34d74…`) | 109,888 | +0.25 (3/8) | `-+-+---+` | 1050 |
| Hexapod | heavy: leg@40, leg@-40, leg@90, leg@-90, leg@140, leg@-140, arm/spinner@0 | 23 | 35 | 154 | 5,708 | `Hexapod.npz` (138 KB, `00a5a8727cc36396…`) | 109,356 | +0.38 (4/8) | `++----++` | 997 |
| Mantis | medium: leg@50, leg@-50, leg@130, leg@-130, arm/hammer@0 | 15 | 30 | 141 | 5,070 | `Mantis.npz` (121 KB, `9f436ab56de8147b…`) | 108,705 | +0.23 (3/8) | `----+-++` | 991 |
| Cart | medium: wheel@100, wheel@-100, arm/spike@25, arm/spike@-25 | 12 | 24 | 132 | 4,632 | `Cart.npz` (107 KB, `b32f2276eaba1556…`) | 108,191 | +0.54 (6/8) | `+-+-++++` | 983 |
| Scorpion | medium: leg@45, leg@-45, leg@135, leg@-135, arm/spinner@180 | 17 | 31 | 144 | 5,216 | `Scorpion.npz` (123 KB, `9b6a60d79a956fa4…`) | 107,202 | -0.39 (1/8) | `------+-` | 941 |

Marks, in order: approach, escape, the closing ring, engagement, chase, facing, no spinning,
no stalling. The driving test and the Elo are those the pack records: the test was run by
`pack.py` on the packed files, after the league's royales. Elo is over the league's 20 royales
(start 1000).

## What it sees and does

Inputs: four cosine-tuned direction cells for the nearest robot and four for the ring's edge,
closing and receding speed of the nearest robot, a weapon within half a metre of the hull,
speed forward and backward, turning left and right, hit points, pain, damage dealt, outside the
ring, each leg's stride and whether it is planted, each arm's angle and whether a rival is in its reach, and a constant drive (`arena/senses.py`).
Outputs: one motor slot per motor of the body, read from one settlement of the whole brain: a
wheel or leg is three motor neurons (reverse, brake, forward), an arm three, a spinner's switch
two. A moment is one `Brain.live` call: calm, the brain answers from one settled state and
learns nothing; aroused (a contradicted forecast, pain, a want), it samples, learns from the
outcome of its last command and remembers. Every moment continues from the last; nothing is
reset between fights.

## How it was trained

From the world's pay alone; no teacher, no labels. Recipe in `README.md` ("Train your own
league"), run on an Apple M4 (10 cores, shared with other jobs) with `cadence-net[fast]`:

1. **Nursery** (`python -m arena nursery --moments 100000`): every stock body alone with a
   dummy and a sparring partner, immortal, inside a standing ring that burns at its edge. Pay:
   metres closed on the target, damage dealt, a destroyed target; cost: damage taken, the burn.
   Three founder seeds per body, 100,000 moments each (36 and 43 minutes for the two batches).
2. **Driving test** (`python -m arena licence --all`) of every seed; the best-licensed seed of
   each body stays (one per body: Cart seed 1, Crab seed 2, Dozer seed 1, Mantis seed 2, Roller
   seed 1; Hexapod, Scorpion, Tumbler the stock seed).
3. **Royales** (`python -m arena royale --fights 20 --size 6 --duration 2400 --zone-moments 2000
   --zone-end 3.5 --stage <PAGE_STAGE>`): the eight chosen robots and two uniform-random twins,
   on the ring stage the page uses (need 0, heat 0, temperature 0.2, actor rate 0.001). 7 minutes.
4. **Pack** (`showcase-app/pack.py`): the six highest-rated brains, their driving test, the wheel.

The recall memory that `Brain.compose` holds by default is off: with and without it the
nursery gave the same readings to the last decimal on three bodies over 9,000 moments. MLX is
slower at this size (100.5 ms against 40.6 ms per moment on one CPU core for Mantis), and
`backend="auto"` keeps these brains on the CPU.

## How it was measured

| Reading | Number | Where |
| --- | --- | --- |
| Nursery progress, 100,000 moments, the packed seeds | Dozer 1,674 m, Cart 1,858, Crab 1,201, Mantis 861, Hexapod 433, Scorpion 602 | `python -m arena nursery` output |
| The eight bodies at their stock seed, uniform random | -22 to -80 m | `--controls` |
| The eight bodies at their stock seed, frozen newborn (greedy, never learning) | -5 to -1,618 m | `--controls` |
| Driving test, random policy, every body | -0.02 to -0.05 (1 to 2 of 8 marks) | `licence --random` |
| Driving test, packed brains | +0.54 to -0.39, mean +0.22 | manifest |
| Royales, 20 of six | Dozer 11 wins of 12 fights; Random-Mantis 3; Hexapod and Cart 2; Crab and Mantis 1 | league ladder |
| Damage dealt per fight in the royales | Dozer 217, Crab 159, Mantis 144, Cart 132, Hexapod 73, Scorpion 7; random twins 15 and 26 | royale output |
| Page check (`check_page.mjs`) | the league wakes, a fight runs and ends, a brain is inspected, the brains are saved and restored | headless Chrome |

## In the page

The brains keep learning while the visitor watches: every robot runs its `Brain.live` life on
the ring stage, and in the first fight of the page check the brains were aroused and learning
on 72 to 82 percent of moments (3,200 to 4,900 learning sweeps each). Their brains are saved
in the browser (IndexedDB) after each fight and restored on the next visit; "Reset the brains
to how they arrived" restores the packed files. Six brains took 55 to 98 ms per moment in
Pyodide on the M4 while other jobs ran.

## Limits

- The ranking is narrow: Dozer won 11 of its 12 fights, and the uniform-random Mantis twin
  rated above five brains (it places by staying alive, dealing 26 damage per fight).
- The driving test moved during the royales: the brains learn in fights, and Scorpion fell
  from +0.14 to -0.39 and Dozer from +0.49 to +0.28. Tumbler, the best driving test after the
  nursery (+0.56, 7 of 8 marks), rated last in the royales and is not packed.
- Three seeds per body is a small selection; no lineage evolution was run for this roster.
- Nursery progress and kills are counts in this world with these pay rules; they do not
  certify skill outside it.

## Licence

GPL-3.0, as Cadence.
