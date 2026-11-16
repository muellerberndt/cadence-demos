# Model card: the Showcase League roster

| | |
| --- | --- |
| Demo | Robot Arena, the Cadence Showcase League (`robot-arena/`) |
| Files | six brains in `showcase-app/public/pack/brains/` (the page's pack) and `league-live/brains/`; SHA-256 per brain in `showcase-app/public/pack/manifest.json` |
| Library | `cadence-net` 0.95.2 (`Brain.load` on the CPU, float64; in the page the same wheel in Pyodide) |
| Composition | per robot `arena/brain.py:compose`: `Brain.compose(inputs, motor neurons, modules=<gene>, slots=<one slot per motor>, recall=<gene>, teaching=<gene>, episodic=True, working_memory_amplitude=<gene>, efference_amplitude=<gene>, scales={"sensory": <gene>, "trace": 12}, lateral=-0.5, temperature=<gene>, actor_eta=<gene>, ...)`; the genes per robot are below |
| Date | 2026-11-09 |

## The roster

| Robot | Body | Layout | Recall | Teaching | Other genes off the founder | Moments lived | Driving test | Marks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dozer-31.27 | heavy: 3 wheels, 3 hammer arms | (256, 128) | on | composed | eta 0.027, temperature 0.16, lam 0.70, trace 0.17, efference 0.12 | 173,997 | +0.77 | `++++++++` |
| Mantis-25.44 | medium: 4 legs, 2 hammer arms | (128,) | off | composed | eta 0.033, sensory scale 6.2, lam 0.62, trace 0.26 | 131,751 | +0.56 | `++++--++` |
| Roller-32.4 | heavy: 4 wheels, 1 leg, 2 hammer arms, 1 spinner | (128,) | on | deep | temperature 0.30, lam 0.61, trace 0.18, efference 0.14, bias rate 0.0041 | 153,189 | +0.44 | `+--++-++` |
| Cart-28.4 | medium: 2 wheels, 3 legs, 1 hammer arm | (64,) | on | deep | sensory scale 2.8, trace 0.43, efference 0.23 | 257,796 | +0.37 | `+--+--++` |
| Tumbler-44.41 | medium: 1 wheel, 1 leg, 3 hammer arms, 1 spike arm | (128, 64) | off | normalized | lam 0.36, critic rate 7.2, trace 0.40, efference 0.20, bias rate 0.0025 | 115,308 | +0.16 | `---+--++` |
| Crab-25.33 | medium: 4 legs, 1 hammer arm, 1 spike arm | (64, 32) | off | deep | eta 0.038, sensory scale 4.7, lam 0.90, bias rate 0.0014 | 136,120 | +0.04 | `---+---+` |

Names are lineage and generation: a lineage keeps its founder's name, its body mutates. Marks,
in order: approach, escape, the closing ring, engagement, chase, facing, no spinning, no
stalling. The driving test is deterministic for a brain file and was read on the packed files.

## What it sees and does

Inputs: four cosine-tuned direction cells for the nearest robot and four for the ring's edge,
closing and receding speed of the nearest robot, a weapon within half a metre of the hull,
speed forward and backward, turning left and right, hit points, pain, damage dealt, outside the
ring, each leg's stride and whether it is planted, each arm's angle and whether a rival is in
its reach, and a constant drive (`arena/senses.py`). Outputs: one motor slot per motor, read
from one settlement of the whole brain. A moment is one `Brain.live` call: calm, the brain
answers from one settled state and learns nothing; aroused, it samples, learns from the
outcome of its last command and remembers. Nothing is reset between fights.

## How it was bred and trained

From the world's pay alone; no teacher, no labels. `python -m arena.breed` on one c7i.24xlarge
(96 vCPU, `cadence-net[fast]`), 9.7 hours, three populations: 64 to 80 robots with the best two
of every lineage kept (47 generations, 80,000-moment nurseries), an independent population of
64 (35 generations, 120,000-moment nurseries), and a population of 72 whose lineages keep their
founder's chassis, locomotion and weapon kinds (28 generations, 100,000-moment nurseries).
Every generation: newborns go through the nursery and survivors through a 20,000-moment
refresher; every robot fights six royales of six against anchors (the previous roster's brains,
reloaded fresh every fight, and two uniform-random twins); every brain takes the driving test.
Fitness: placement against the anchors, plus the driving test, plus a share for damage dealt,
plus a share for the fights in which it placed above every random twin, minus a cost for slower
layouts (every layout, with or without recall, runs within twice the founder's cost per moment
in plain NumPy, the page's path; Dozer's (256, 128) with recall is the costliest, about 1.9). The
elite keep their brains; offspring are mutants of body and genes with newborn brains.

The roster: for each body, the living robot with the best driving test plus share of fights
above the twins among those placing at least +0.3 against the anchors; the six best bodies.

## How it was measured (`python -m arena.gate`, as run)

| Test | Reading | Bar |
| --- | --- | --- |
| Head to head: 48 royales, three new and three previous robots each, both sides learning through the series | new minus previous placement score +0.261, 95% bootstrap interval [+0.128, +0.400]; Elo 1027 against 973 | interval above zero: met |
| Driving test, mean of the six | +0.391; previous roster +0.22 | clearly above the previous: met |
| Random twins (3b): for each brain and twin, the brain's placement minus the twin's over the fights they shared (36 to 41 each) | no interval entirely below zero | met |
| Random twins (3a): the roster's mean placement minus the twins' mean in the same fight, 70 of 72 royales | +0.117, 95% bootstrap interval [-0.024, +0.253] | interval above zero: missed narrowly |

Per pair (3b), mean placement difference against the Mantis twin / the Tumbler twin: Tumbler
+0.54 / +0.39 (both intervals above zero), Cart +0.33 / +0.18, Mantis +0.17 / +0.25,
Crab -0.25 / +0.09, Roller -0.04 / -0.16, Dozer +0.03 / +0.02. Wins in the head to head: Tumbler
15, Mantis 8, Cart 5, Roller 2, Crab 2, Dozer 1; the previous roster's Dozer 9, Crab 3, Cart 2,
Hexapod 1, Mantis 0, Scorpion 0.

The owner chose to ship this roster because it beats the previous one on every measured
reading, including against the twins: in the previous roster's 20 royales the random Mantis
twin rated above five of its six brains. The breeding continues toward a roster that also
clears (3a) and a driving-test mean of +0.54.

## In the page

Every robot runs its `Brain.live` life on the ring stage (need 0, heat 0, temperature 0.2,
actor rate 0.001) and keeps learning in every fight; brains are saved in the browser
(IndexedDB) after each fight and restored on the next visit. The brain inspector draws the
selected brain from its own state every moment (`showcase-app/src/arena/brainview.ts`); for
Dozer, Roller and Cart it includes the recall memory's reads.

## Limits

- Placement rewards survival: the random twins survive by not engaging, and two brains (Roller,
  Dozer) place about level with them. The 95% interval of the roster against the twins
  includes zero.
- Crab and Tumbler pass few marks of the driving test: they fight well in the ring (Tumbler won
  15 of the head-to-head royales) but approach, escape and chase poorly in the test's open
  space.
- Placement, damage and the driving test are counts in this world with these pay rules; they do
  not certify skill outside it.

## Licence

GPL-3.0, as Cadence.
