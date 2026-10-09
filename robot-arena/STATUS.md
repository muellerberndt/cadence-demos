# Status

Measured on cadence-net 0.77.0, macOS, Apple M4 (10 cores), one BLAS thread per brain.
Every number below is what the run printed. Uniform random with the same body is the
baseline; the frozen newborn and the linear policy-gradient learner are the controls.

## The nursery: can a robot learn to steer toward a target?

The task: a Tumbler (light chassis, two wheels, a spike) alone in the ring with a training
dummy 4 to 7 m away that reappears elsewhere when destroyed or after 400 moments. Reward per
moment: 10 x metres of approach (capped at 0.5), damage dealt minus taken over 20, +1 for a
kill. Readings per 1/8 of the life: metres of progress toward the dummy (random: about 0).

### Grids 1 to 3: the library's reward-chamber operating point is observation-blind here

The founder genes were the key-door / reward-rhythm point (trace 0.3, efference copy 3.0,
actor eta 0.1, lam 0.95, gamma 0.95, critic 5.0, arousal need 0.05, heat 2.0). In 8,000
and 20,000 moments no arm learned: progress within noise of random, and the fingerprint
(the greedy command in eight declared situations, read from a saved copy) gave one answer
in all eight for every brain, with identical probabilities to two decimals. Arms tried:
lam 0.6 and 0, need 0.02 / 0.1 / 0.2, eta 0.3, episodic memory, the composed defaults,
heat 0.5 / 1.0, learner temperature 0.1, efference 0 / 0.3 / 1.0, sensory scale 4 / 8.

Measured cause, at birth: the senses move the motor state by 0.003 (standard deviation
across the eight situations) with the efference copy at 3.0 through its scale-12
projection, 0.010 without it, 0.030 without it and with the sensory projection at scale 4.
A newborn with the copy answers identically in all eight situations; without it and at
scale 4 it gives four distinct answers. During life, eta 0.1 saturated the motor cortex
(probabilities 0.99) long before the senses' small, consistent drift could accumulate: the
saturation latch of the key-door chamber.

### Grid 4: a small actor step learns (40,000 moments, 2 seeds, efference 0, scale 4)

| arm | seed | progress by eighth (m) | total | kills | damage | calm share, 2nd half | distinct / 8 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eta 0.01 | 1 | -0.4 44.1 56.0 42.0 0.0 0.0 0.0 0.0 | 141.7 | 3 | 932 | 0.00 | 2 |
| eta 0.01 | 2 | -2.6 15.3 41.3 24.8 0.0 0.0 0.0 0.0 | 78.8 | 1 | 492 | 0.00 | 3 |
| eta 0.03 | 1 | 6.8 35.7 16.8 42.0 25.2 1.6 0.9 0.0 | 129.0 | 2 | 822 | 0.06 | 1 |
| eta 0.03 | 2 | 7.3 23.6 31.4 30.9 0.0 0.0 0.0 0.0 | 93.2 | 0 | 510 | 0.00 | 3 |
| eta 0.01, heat 0.5 | 1 | 0.3 6.3 18.7 18.9 53.1 45.0 4.7 0.0 | 146.9 | 0 | 688 | 0.09 | 2 |
| eta 0.01, heat 0.5 | 2 | 0.0 31.4 52.4 9.7 0.0 0.0 0.0 0.0 | 93.5 | 0 | 430 | 0.00 | 1 |
| eta 0.01, scale 8 | 1 | 14.3 44.0 49.4 0.0 0.0 0.0 0.0 0.0 | 107.7 | 0 | 723 | 0.00 | 2 |
| eta 0.01, scale 8 | 2 | 13.6 36.8 55.0 4.7 0.0 0.0 0.0 0.0 | 110.1 | 0 | 472 | 0.00 | 1 |
| eta 0.01, lam 0.6 | 1 | 10.6 40.4 54.1 53.4 43.5 38.2 54.7 53.7 | 348.8 | 0 | 2692 | 0.28 | 2 |
| eta 0.01, lam 0.6 | 2 | 32.9 47.8 0.0 0.0 0.0 0.0 0.0 0.0 | 80.7 | 4 | 599 | 0.00 | 3 |
| eta 0.003 | 1 | -0.5 11.6 27.7 47.1 52.1 48.3 39.7 0.0 | 226.0 | 1 | 1211 | 0.13 | 5 |
| eta 0.003 | 2 | -8.6 -1.5 17.4 35.8 40.0 48.9 61.7 57.6 | 251.3 | 4 | 1634 | 0.17 | 1 |
| uniform random | 1 | 2.8 4.0 -2.8 -1.6 -2.0 -6.9 -2.0 -2.6 | -11.2 | 0 | 0 | | |
| uniform random | 2 | -3.0 -4.5 0.4 0.4 2.1 2.9 -2.7 5.5 | 0.9 | 0 | 2 | | |

Every arm learns to approach (40 to 60 m per 5,000 moments against random's noise), and
the fingerprints show steering: the greedy command turns when the target is on one side
and drives straight when it is ahead. The residual failure is a collapse: a run that has
learned "drive straight" presses against the wall, earns exactly nothing for the rest of
its life, and its aroused sampling (temperature 0.2 x 3 under full want) cannot leave a
motor cortex saturated at 0.98. The nursery had no burn then; it has a standing ring now.

### The linear control (same inputs, same reward, 20,000 moments)

A softmax policy per motor on the 19 inputs with eligibility traces and a linear TD critic
(alpha 0.05, lam 0.6, temperature 0.5) learns the approach too: seed 1 earns 152 m of
progress, 1,626 damage and two kills; seed 2 collapses after 5,000 moments into a still
policy, as do most of its variants (alpha 0.2 / 0.01, lam 0.95, temperature 0.2). The
problem is learnable with this information and these moments; the collapse into a
deterministic, unrewarded policy is the hazard for every softmax learner here, and for a
Cadence brain the motor activations are bounded, so the learner temperature bounds it.

### Grid 5: the learner temperature bounds the saturation (20,000 moments, 2 seeds, eta 0.03)

| arm | seed | progress by eighth (m) | total | kills | damage | distinct / 8 |
| --- | --- | --- | --- | --- | --- | --- |
| T 0.5 | 1 | 4.7 9.7 0.2 14.3 3.2 0.6 1.9 19.4 | 54.0 | 0 | 203 | 3 |
| T 0.5 | 2 | 6.7 22.7 16.5 24.2 5.8 2.8 0.0 0.0 | 78.8 | 0 | 518 | 2 |
| T 1.0 | 1 | -0.8 5.8 23.0 8.9 5.2 4.6 19.0 21.3 | 87.0 | 0 | 272 | 3 |
| T 1.0 | 2 | 6.3 10.8 20.3 17.1 15.1 19.6 17.9 16.5 | 123.7 | 1 | 431 | 3 |
| T 0.5, eta 0.1 | 1 | -1.3 -2.2 -3.1 -5.3 -4.0 -5.8 -2.0 -0.5 | -24.1 | 0 | 10 | 2 |
| T 0.5, eta 0.1 | 2 | 4.2 1.0 3.0 2.4 9.0 -9.5 17.2 2.2 | 29.4 | 0 | 35 | 2 |
| T 0.5, heat 0.5 | 1 | 3.2 5.2 17.4 18.3 30.2 -0.1 0.0 0.0 | 74.3 | 1 | 417 | 1 |
| T 0.5, heat 0.5 | 2 | 19.6 22.7 14.9 -8.2 2.2 25.7 5.5 0.0 | 82.3 | 0 | 372 | 1 |
| T 1.0, eta 0.1, heat 0.5 | 1 | 3.5 3.7 9.7 1.6 23.4 10.2 9.4 23.9 | 85.4 | 0 | 324 | 3 |
| T 1.0, eta 0.1, heat 0.5 | 2 | 2.2 3.6 3.3 10.2 13.2 1.1 8.0 1.1 | 42.6 | 0 | 113 | 1 |
| T 0.5, lam 0.6 | 1 | 5.7 25.8 25.2 31.8 9.0 0.0 0.0 0.0 | 97.5 | 2 | 555 | 2 |
| T 0.5, lam 0.6 | 2 | 5.5 30.6 23.4 25.4 27.4 0.0 0.0 0.0 | 112.3 | 5 | 882 | 2 |

At temperature 1.0 the motor probabilities stay near 0.58 and no run stops; at 0.5 the
early learning is faster (25 to 32 m per eighth with lam 0.6, five kills) and some runs stop.

### Grid 6 found the stops: the pupils were dead

With the standing ring (6 hp/s outside 8.5 m) every arm, and uniform random, read exactly
0.0 progress after one to three eighths, with burn totals equal to the body's hit points
(70 for the Tumbler, 110 for the Mantis) or with hundreds of damage dealt by ramming, which
costs the lighter rammer more than its victim. A dead robot earns nothing forever. Several of
the earlier "collapses" were deaths by ramming as well. The nursery now restores the pupil's
hit points every moment: pain is paid, the life goes on. Grid 7 repeats the three leading
arms on the Tumbler and the Mantis with an immortal pupil.

### Grid 7: the founder, confirmed on the Tumbler (immortal pupil, 40,000 moments, 2 seeds)

| arm | seed | progress by eighth (m) | total | kills | damage | calm share, 2nd half |
| --- | --- | --- | --- | --- | --- | --- |
| T 0.5, eta 0.03, lam 0.6 (founder) | 1 | 37.2 49.3 50.8 52.2 52.5 53.6 54.7 52.1 | 402.4 | 9 | 2524 | 0.15 |
| founder | 2 | 22.7 51.3 57.9 57.4 51.9 45.6 52.1 29.6 | 368.5 | 21 | 3235 | 0.14 |
| T 1.0, eta 0.03, lam 0.6 | 1 | 36.8 42.7 41.9 34.5 32.6 34.6 55.0 41.9 | 320.1 | 0 | 1268 | 0.12 |
| T 1.0, eta 0.03, lam 0.6 | 2 | 16.1 41.0 42.6 37.1 49.0 31.8 34.1 40.7 | 292.3 | 2 | 956 | 0.09 |
| T 1.0, eta 0.01, lam 0.6 | 1 | 5.1 16.3 37.2 29.7 37.1 32.3 48.3 36.1 | 242.2 | 2 | 799 | 0.11 |
| T 1.0, eta 0.01, lam 0.6 | 2 | 18.3 15.4 25.0 41.8 49.5 44.5 50.3 41.7 | 286.5 | 0 | 949 | 0.12 |
| uniform random | 1 | 0.6 -1.7 1.9 -0.3 0.7 -1.0 2.7 3.0 | 5.9 | 0 | 0 | |

Every arm learns for the whole life and none stops. The founder (`arena/brain.py:FOUNDER`)
is the first row: about 50 m of progress per 5,000 moments from the second eighth on, nine
and twenty-one dummies destroyed against random's none. Its greedy fingerprint reads one
answer in all eight situations while its sampled policy steers: the probability of a wheel
command moves by up to 0.2 with the target's side, and the robot is aroused for 85 % of
its moments, so the sampled policy is the one that acts. The probe now reports that graded
sensitivity beside the count of distinct greedy answers.

The same grid on the Mantis (four legs) was a negative: progress -78 to -163 m, 99 % of the
moments in the burn, for the brains and for uniform random alike. The cause was the body:
a leg could only push forward, so a legged robot pressed against the wall could not back
away, and the flat, painful reward there taught it to hold still. Legs now push both ways
and recover by a stepping reflex (`arena/world.py`); a random Mantis stays inside the ring.
Grid 8 reruns the founder on the Mantis, the Hexapod and the Tumbler.

### Grid 8: the founder on legs (40,000 moments, 2 seeds)

| robot | seed | progress by eighth (m) | total | kills | damage | sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| Mantis (4 legs, hammer) | 1 | 3.9 8.9 15.1 18.4 25.6 17.3 26.2 35.9 | 151.3 | 6 | 802 | 0.176 |
| Mantis | 2 | 4.0 1.4 5.4 10.6 13.8 19.9 20.4 14.5 | 90.0 | 0 | 96 | 0.067 |
| Hexapod (6 legs, spinner) | 1 | 1.0 5.7 6.5 -6.6 13.9 -6.9 4.2 17.3 | 35.1 | 0 | 70 | 0.008 |
| Hexapod | 2 | 2.3 7.1 7.6 0.1 9.6 -4.0 0.2 10.4 | 33.3 | 0 | 54 | 0.009 |
| Tumbler (2 wheels, spike) | 1 | 37.2 49.3 50.8 52.2 52.5 53.6 54.7 52.1 | 402.4 | 9 | 2524 | 0.013 |
| Tumbler | 2 | 22.7 51.3 57.9 57.4 51.9 45.6 52.1 29.6 | 368.5 | 21 | 3235 | 0.072 |
| Mantis, uniform random | 1 | -2.0 4.6 -0.5 -1.2 -1.3 0.5 1.3 0.1 | 1.3 | 0 | 0 | |
| Hexapod, uniform random | 1 | -1.1 1.2 0.5 -2.2 -2.0 -1.3 0.5 -0.7 | -5.1 | 0 | 0 | |

With the reflex legs the Mantis learns to walk to the dummy and hit it (its progress rises
through the life, 36 m in the last eighth of seed 1); the Hexapod, with eight motor slots and
a heavy body, is the slow learner of the catalogue at this length of life. Sensitivity is the
probe's graded reading: the mean range, across the eight situations, of a command's
probability. The showcase league raises every robot for 80,000 moments.

## The Cadence Showcase League (`scripts/showcase.sh league 80000 40`)

### Raised in the nursery: 80,000 moments each, eight brains in parallel

| robot | body | progress (m) | 2nd half | kills | damage | aroused share | random (m / kills) | frozen newborn (m / kills) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tumbler | light, 2 wheels, spike | 726.4 | 393.9 | 8 | 4803 | 0.86 | 1.0 / 0 | -147.4 / 0 |
| Cart | medium, 2 wheels, 2 spikes | 652.6 | 339.1 | 12 | 2555 | 0.91 | -3.6 / 0 | -236.2 / 0 |
| Roller | heavy, 4 wheels, spinner | 544.1 | 281.2 | 8 | 1219 | 0.96 | 2.4 / 0 | 0.0 / 0 |
| Dozer | heavy, 4 wheels, 2 spikes, hammer | 421.6 | 257.0 | 22 | 2608 | 0.97 | -4.1 / 0 | 94.4 / 0 |
| Mantis | medium, 4 legs, hammer | 282.5 | 164.1 | 9 | 1721 | 0.97 | -2.9 / 0 | -7.4 / 0 |
| Crab | medium, 4 legs, hammer, spike | 281.5 | 178.8 | 8 | 1232 | 0.97 | -6.1 / 0 | 234.6 / 0 |
| Scorpion | medium, 4 legs, spinner | 225.0 | 146.4 | 0 | 118 | 0.98 | 3.2 / 0 | -5.7 / 0 |
| Hexapod | heavy, 6 legs, spinner | 110.8 | 71.5 | 0 | 128 | 1.00 | -2.1 / 0 | -16.3 / 0 |

Each brain ran at 117 to 166 moments per second with eight nurseries sharing the ten
cores, six to eight times the body's real time; uniform random with the same bodies at 150
to 300 times. No control destroyed a dummy. Two frozen newborns drift forward by their
initial wiring (Crab 235 m, Dozer 94 m) without ever hitting anything; the trained Crab and
Dozer destroy eight and twenty-two. Wheels learn faster than legs; the Hexapod, with eight
motor slots on a heavy body, is the slowest and still makes 111 m against -2 for random.

### Forty royales, six robots each, the ring closing from 10 m to 2.5 m

The ten robots (eight brains, two uniform-random twins) fought 40 royales, 24 each, picked
by fewest fights first. 2,015 s of ring time took 500 s of wall time with six brains settling
in parallel: four times real time, learning included (a fight averaged 1,008 moments and
12.5 s). Brains were aroused in 88 to 100 % of their fight moments and spent 9,000 to 13,000
learning sweeps per fight: at these incomes the arousal law keeps them learning nearly all
the time, and routine moments are rare in the ring.

**The winner changes.** Eight different robots won a fight; the winner changed 34 times in
40 fights; no random twin ever won. The Elo leader changed hands seven times between the
Dozer, the Mantis and the Roller, and the Mantis took the lead in the last two fights.

| # | robot | elo | wins / 24 | mean place | dealt per fight | taken per fight |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Mantis (4 legs, hammer) | 1107 | 7 | 2.46 | 107 | 91 |
| 2 | Dozer (4 wheels, 2 spikes, hammer) | 1079 | 8 | 2.46 | 71 | 142 |
| 3 | Crab (4 legs, hammer, spike) | 1074 | 8 | 2.83 | 93 | 88 |
| 4 | Roller (4 wheels, spinner) | 1056 | 7 | 2.79 | 18 | 139 |
| 5 | Hexapod (6 legs, spinner) | 985 | 2 | 3.54 | 10 | 154 |
| 6 | Scorpion (4 legs, spinner) | 982 | 4 | 4.04 | 9 | 96 |
| 7 | Cart (2 wheels, 2 spikes) | 967 | 2 | 3.83 | 81 | 108 |
| 8 | Random-Mantis | 952 | 0 | 3.96 | 19 | 110 |
| 9 | Random-Tumbler | 906 | 0 | 4.62 | 13 | 71 |
| 10 | Tumbler (2 wheels, spike) | 892 | 2 | 4.46 | 64 | 72 |

**Tactics change over the fights** (each robot's first eight fights against its last eight):

| robot | place | damage dealt | weapon hits | burn taken | moments outside the ring |
| --- | --- | --- | --- | --- | --- |
| Dozer | 2.25 → 2.88 | 52 → 106 | 52 → 136 | 102 → 79 | 37 % → 30 % |
| Mantis | 3.00 → 2.38 | 102 → 131 | 11 → 13 | 52 → 42 | 19 % → 15 % |
| Scorpion | 4.62 → 2.25 | 9 → 7 | 32 → 22 | 27 → 40 | 14 % → 14 % |
| Roller | 2.38 → 2.62 | 16 → 16 | 65 → 53 | 93 → 49 | 32 % → 18 % |
| Crab | 3.25 → 2.50 | 113 → 100 | 83 → 76 | 31 → 63 | 13 % → 24 % |
| Hexapod | 3.50 → 4.38 | 10 → 11 | 34 → 56 | 90 → 73 | 32 % → 30 % |
| Cart | 3.50 → 4.00 | 90 → 85 | 249 → 239 | 24 → 36 | 9 % → 16 % |
| Tumbler | 3.88 → 5.50 | 67 → 49 | 150 → 100 | 25 → 11 | 11 % → 8 % |
| Random-Mantis | 3.75 → 3.88 | 20 → 19 | 2 → 4 | 93 → 99 | 41 % → 45 % |
| Random-Tumbler | 4.88 → 4.38 | 6 → 9 | 12 → 20 | 51 → 53 | 26 % → 26 % |

The Dozer doubled its damage and its hits; the Roller halved its burn and the time it spent
outside the ring; the Mantis and the Scorpion climbed from mid-table to the podium; the
Tumbler, the nursery's best pupil, is the ring's loser: a light chassis of 70 hit points that
dies in 23 of 24 fights, early to rams and the closing burn. The random twins did not change.
These are counts over eight fights each on one league run; they show that the brains keep
changing inside the ring and that the order of the table is not fixed, not that any one of
these trends would repeat with another seed.

### What this does not show yet

Routine is rare: in the ring the brains are aroused nearly every moment, so "a calm brain
answers cheaply" is seen in the nursery (15 % calm at the founder's income there) and not
in fights. The founder was selected on the Tumbler and confirmed on the Mantis and the
Hexapod with two seeds each; a fresh-seed confirmation with the usual gate has not been run.
The policy fingerprint reads one greedy answer for most trained brains while the sampled
policy steers; a probe of the sampled policy's expected command would read the tactic
directly. No evolution run has been reported (the `evolve` command exists and is tested
only as code).

## One hour of lineage evolution on 192 vCPUs (`docs/aws.md`, league in `league-evolved/`)

c7i.48xlarge, us-east-1, 2026-10-08. The league's three best (Mantis, Dozer, Crab, with their
trained brains) kept their lives and founded three lineages; 189 mutants of their bodies and
genes were born with newborn brains and raised for 80,000 moments each (all at once); then
every generation: 30 rounds of 32 simultaneous royales of six (600 moments, the ring closed by
moment 500, the `evolve` defaults), ranking by mean placement score, the best third kept with
their brains, 128 retired, 128 born from the survivors and raised. Budget `--hours 1.0`,
final cut to twelve.

| generation | minutes | Dozer line | Mantis line | Crab line | best three of the generation (score over 30 fights) |
| --- | --- | --- | --- | --- | --- |
| 1 | 14.0 | 153 | 23 | 16 | Dozer-039 +0.69, Crab-06 +0.55, Dozer-043 +0.55 |
| 2 | 12.0 | 134 | 35 | 23 | Crab-044 +0.41, Dozer-1.48 +0.37, Mantis-1.63 +0.37 |
| 3 | 12.2 | 127 | 31 | 34 | Dozer-2.37 +0.51, Dozer-2.89 +0.48, Crab-2.68 +0.47 |
| 4 | 12.6 | 116 | 35 | 41 | Mantis-3.42 +0.53, Crab-3.110 +0.45, Mantis-3.75 +0.37 |

3,840 royales, 32.5 hours of ring time in 51 minutes of wall time (38x), 512 robots born.

- **The founders lost to their descendants.** After generation 1 the Mantis ranked 92nd and
  the Crab 99th of 192 and retired; the Dozer ranked 64th, survived once, and retired 89th
  in generation 2 (Elo 1077 after 84 fights, 22 wins).
- **The dominant lineage changed.** The Dozer line took 153 of 192 places after the first
  cut and lost ground every generation after; the Crab line grew from 16 to 41 and the
  Mantis line from 23 to 35, and the last generation's podium was Mantis, Crab, Mantis.
- **Bodies converged on the heavy chassis.** All twelve survivors are heavy, including every
  Mantis and Crab descendant (their founders were medium): in a short fight with a fast
  ring, 160 hit points are worth more than speed.
- **Two tactics.** Dozer descendants win by damage (Dozer-2.37 dealt 3,631 over its 30
  fights); the Mantis descendants on top of generation 4 dealt 112 and 368 and won by
  staying inside the ring and outliving the rest. The gene mutations kept by the survivors
  are small (eta 0.037, temperature 0.39, lam 0.45 to 0.63, youth 259 to 328, arousal
  threshold 0.16, an efference copy at 0.1 to 0.3); the body mutations are large (legs
  removed or added, arms re-armed, a spinner on a Mantis).

The twelve then fought six full-length showcase royales on the laptop (1,200 moments, ring
closing over 1,000) for the replays in `league-evolved/fights/`; the league page
`league-evolved/index.html` carries the evolution section.

Caveats: one run, one seed; the fights of the evolution were half the showcase's length, which
favours heavy bodies; placement score over 30 fights is noisy at the margin (the cut between
rank 64 and 65); the founders' brains had 24 fights of experience against newborns with 30
each, so "founders lost" is a statement about these conditions.

## The page (`showcase-app/`)

The six best evolved robots run live in the browser: Pyodide 314.0.7 loads the cadence-net
0.77.0 wheel and the `arena` sources into a worker; the host (`showcase-app/py/host.py`)
runs the royale loop moment by moment with the royale's own reward and frame functions.
Measured in headless Chrome on the M4: a six-robot moment costs about 10 ms in Pyodide
(all six brains, physics and the frame), so a 1,200-moment fight runs in about 70 s at full
speed and at real time otherwise; a full fight in the page learned 8,000 to 14,000 sweeps
per brain, and the brains and the record were saved to IndexedDB and restored on reload
(`check_page.mjs`).

## The ring, measured (2026-10-08, evening)

Three readings on the evolved six and on the original nursery champions, four full-length
royales per arm, from the fight statistics (`closing_share` = the share of a robot's moments
in which the gap to its nearest rival shrank; chance is about 0.5):

| ring stage | aroused share | closing share | dealt per robot | ms per moment |
| --- | --- | --- | --- | --- |
| the gene (need 0.05) | 0.99 | 0.50 | 93 | 3.9 |
| need 0 | 0.91 | 0.45 | 87 | 3.4 |
| need 0, reset, heat 0, temperature 0.2 | 0.00 to 0.77 by robot | 0.25 to 0.53 | 5 to 392 | |

- **Why they are aroused.** Instrumented per moment: surprise is zero in the ring (TD errors
  0.04 to 0.08 against a usual of 0.06 to 0.12 and a tolerance of 2). The arousal is want: the
  long-run reward (0.02 to 0.075, the nursery's income and the placements) against a recent
  income near zero, over a scale of 0.05 to 0.19. The long-run reading only learns from the
  brain's own best-guess outcomes, and a sampling brain rarely acts on its best guess, so a
  brain raised on a richer income wants forever in a ring that pays less. `Arousal.reset` on
  entering the ring (the ring stage) ends it: several robots then fight whole royales calm.
- **Why they still look random when calm.** Their greedy policies do not steer. On the
  nursery's own task, greedy and without learning, Crab-3.110 makes 5 m in 3,000 moments
  (random: -2), Dozer-2.114 makes -27 m, with policy sensitivities of 0.006 and 0.004; only
  Mantis-3.75 reads its senses (0.34) and it does not approach either. Four more fights
  change none of this. The hour of evolution selected survivors of 600-moment fights, heavy
  bodies that outlive the rest, not steerers. The nursery champions of the first league
  (Tumbler 726 m with sampling) have greedy sensitivities of 0.01 to 0.07: the nursery's
  progress came from a weak bias of the sampled policy toward a lone, stationary dummy, and
  in the ring, among five moving rivals and the burn, that bias does not express.

What follows for the library and the lane:

1. The arousal law's "used to" memory should also learn from sampled outcomes, or want
   should decay under sustained sampling; otherwise poor-and-aroused is an absorbing state
   (cadence issue 158).
2. Arousal flattens the policy (temperature times 1 + heat x want over activations bounded in
   [-1, 1]) instead of sharpening it: an aroused brain behaves at random whatever it knows.
   Heat 0 at the ring stage is the gene-level workaround; the law may want a different shape
   (cadence issue 159).
3. The actor leaves greedy margins too small to make the greedy policy read its senses after
   80,000 moments, while the sampled policy carries the learned bias. That is the capability
   limit behind every "looks random" in this lane and the sibling of cadence issue 143; it
   needs library work on how credit reaches the sensory synapses (cadence issue 160).
4. A routine moment still settles twice (the forecast and the answer): cheaper routine needs
   cadence's settled-state reuse (issue 122). Routine saves the learning phases, measured as
   3.9 to 3.4 ms per six-robot moment here.
5. For the arena: select on tactics, not on placement in short fights (closing share, hits),
   and raise a second nursery stage against a moving dummy that strikes back under the ring's
   own rules, so the policy that is learned is the ring's.

The page now runs the ring stage (need 0, heat 0, temperature 0.2, the reset on arrival) so
that routine, cheap moments and learning bursts on surprise are what it shows; its robots'
tactics are as weak as measured here, and the page says so.

## Cadence 0.79.0 (2026-10-09): the same bodies from scratch

The release carries the repairs of issues 158, 159 and 160 (income counted during
exploration, extra heat on one motor slot, credit to the behaviour that sampled). A moment
costs the same as on 0.77 (2.0 to 2.4 ms aroused). The eight stock robots raised from
scratch, 80,000 moments each, same nursery, same controls:

| robot | progress 0.77 → 0.79 (m) | kills 0.77 → 0.79 | damage 0.79 | calm share late, 0.79 |
| --- | --- | --- | --- | --- |
| Dozer | 422 → 804 | 22 → 132 | 9,694 | 0.44 |
| Cart | 653 → 812 | 12 → 26 | 4,416 | 0.28 |
| Roller | 544 → 756 | 8 → 27 | 4,268 | 0.26 |
| Crab | 282 → 706 | 8 → 84 | 7,852 | 0.42 |
| Tumbler | 726 → 687 | 8 → 38 | 5,137 | 0.24 |
| Scorpion | 225 → 573 | 0 → 1 | 849 | 0.37 |
| Mantis | 283 → 559 | 9 → 16 | 3,070 | 0.40 |
| Hexapod | 111 → 488 | 0 → 0 | 292 | 0.38 |

Uniform random with the same bodies: -6 to +3 m, no kills; frozen newborns no kills except
the Crab's three. Twenty-four royales against the two random twins in a slower ring (2,400
moments, closing over 2,000 to 3.5 m): eight different winners, the twins 7th and 9th with
one artefact win (the brains eliminated each other and the untouched twin survived), the
brains dealing 1,200 to 2,500 damage over their fights where on 0.77 most dealt under 500,
calm for 10 to 33 % of their fight moments. Fights end by elimination before the clock.

### The second hour on 192 vCPUs (`league-evolved-079/`)

All eight nursery champions founded lineages (184 mutants), full-length fights in the slower
ring, 24 rounds of 32 royales per generation, the best third kept, final cut to twelve.

| generation | minutes | Dozer | Crab | Roller | Cart | Mantis | Hexapod | Tumbler | Scorpion | best three |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 15.7 | 66 | 34 | 23 | 22 | 28 | 15 | 3 | 1 | Dozer-013 +0.78, Dozer-017 +0.75, Dozer (founder) +0.72 |
| 2 | 13.3 | 122 | 27 | 15 | 12 | 13 | 0 | 3 | 0 | Dozer-017 +0.83, Dozer-1.1 +0.58, Dozer-1.73 +0.57 |
| 3 | 12.5 | 140 | 14 | 14 | 20 | 0 | 0 | 4 | 0 | Dozer-2.8 +0.80, Dozer-1.110 +0.65, Dozer-1.75 +0.63 |
| 4 | 13.1 | 144 | 26 | 10 | 8 | 0 | 0 | 4 | 0 | Dozer-3.128 +0.72, Dozer-2.8 +0.52, Crab-3.40 +0.52 |

3,078 royales, 55 hours of ring time in 55 minutes (60x). The Dozer founder ranked 3rd of
192 in generation 1 and retired in generation 4 after 111 fights and 37 wins; the Crab
founder retired in generation 3 after 86 fights and 22 wins; the other six founders retired
in generation 1 or 2. Over the hour the league's damage dealt per robot per fight rose from
93 (first ten rounds) to 116 (last ten), closing share from 0.33 to 0.42, aroused share
fell from 0.81 to 0.75. The twelve kept are ten Dozer-line robots (heavy, three or four
wheels, a spike or two and up to three hammers) and two Crab-line robots (medium, three
legs, three hammers); their kept gene mutations are small (temperature 0.29 to 0.34,
sensory scale 4.6 to 5.3, lam 0.47 and 0.99, an efference copy at 0.07 to 0.19, arousal
decay 0.99).

In the ring the command flips per motor per moment measure what exploration costs the
eye: 0.03 to 0.07 in calm moments, 0.5 to 0.6 aroused. The ring stage (temperature 0.2,
heat 0, need 0, the income memory reset on arrival) cuts the flips to a third with the
same damage dealt (125 against 127 per robot over three fights) and two thirds of the
moments calm. The page runs that stage with the six best of the twelve, in continuous
rounds, and shows damage per fight and the ladder over the fights lived in the browser.
