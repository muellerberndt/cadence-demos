# Raising the Tron brains

The two brains on the page came out of one campaign: a genetic search, a school, expert iteration,
selection and self-play for the flat brain, then a deep brain grown from the flat line. This file
gives each stage's command, where it ran, how long it took and what it read. Every command runs
from this folder (`tron/`) with `cadence-net==0.95.2` installed; the scripts write under `runs/`.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
```

Set the thread counts: the scripts run one brain per process, and NumPy's BLAS otherwise starts a
thread per core in every process.

**Hardware.** The genetic search ran on one AWS c7i.16xlarge (64 vCPU), one brain per core. Every
later stage ran on one g6.16xlarge (an NVIDIA L4 and 64 vCPU): the deep brains' lessons on the L4
(`--backend torch`), the flat brains and the selection children on the CPU, the labelling bots
(pure Python and Numba) on the CPU beside them. Times below are wall-clock on those boxes, with
other runs sharing them.

**Readings.** A reading plays mirror pairs: each arena seed twice, the brain in either seat; a
draw counts half. `voronoi` (one move of look-ahead for both riders, maximizing the cells it reaches
first), `voronoi2` and `voronoi3` (two and three rounds), and `ab5` (a 10-ply alpha-beta with the
Voronoi leaf, `tron/absearch.py`) are the bots. Seeds 2,200,000+ are the checkpoint set, 7,000,000+
the confirmation set that no selection step reads, 8,000,000+ the head-to-head set.
`scripts/r3eval.py` runs readings in a process pool.

**Settling.** The final readings and every move on the page settle from rest: `brain.reset()`
before each `brain.act`. A deep reciprocal brain can hold two stable states for one observation,
one reached warm from the last move and one from rest, and the lesson must correct the state the
act is taken from. The policy in `tron/r3.py` resets before every move. In the original campaign
the flat stages up to early self-play rode warm, which for a flat brain makes no difference: its
warm and rest moves differed on at most 1 of about 1,700 positions. On cadence-net 0.95.2 a
lesson's free phase starts from the state the act just settled to.

## 0. Data

```sh
python scripts/prepare.py
```

Writes `runs/r3/corpus3.jsonl` (3,000 games of `voronoi3` against the school pool, the corpus
lessons replay them through the sense), `runs/r3/scenarios.json` (strategy positions: walled in,
cutting off, space filling, from bot games on seeds 2,000,000+, never trained on) and
`runs/r3/turnset.npz` (positions a brain reaches against the labelling opponents with the `ab5`
label, whether it turns and whether some move loses there; the selection gate and the deep scripts
score agreement on it). The scenario search and the turn set's 10-ply labels run in one process
each; expect about an hour on a laptop.

## The flat brain

| Stage | Script | Where, how long | Result |
| --- | --- | --- | --- |
| 1. Genetic search | `ga3.py` | c7i.16xlarge, about 4 h, 1,536 raisings | flat256, normalized teaching: validation strength 0.117, no win against `voronoi` |
| 2. School | `phaseb.py --arm instruct` | L4 box, about 14 h for 100,000 moments (18 runs at once) | 0.18 against `voronoi` (confirmation set) |
| 3. Expert iteration | `phasec.py --arm exit` | L4 box CPU, about 5 h for 40,000 moments | **Mako 1.0**: 0.51 / 0.48 |
| 4. Selection | `select_exit.py` | L4 box CPU, 12 minutes per generation | **Mako 1.5** 0.62 / 0.59 (generation 0), **Mako 1.6** 0.67 / 0.66 (generation 2) |
| 5. Self-play | `select_exit.py --selfplay --sprt` | L4 box, about 13 h for two lines, 20 generations | **Mako**: 0.73 / 0.71 |

Results are scores against `voronoi` on the checkpoint / confirmation seeds, 128 pairs each.

### 1. Genetic search

```sh
python scripts/ga3.py --out runs/r3/ga --pop 64 --gens 24 --workers 64 --games 8
```

A genome names the brain (layout from (256,) to (512, 256, 128, 64), the sense, the apical share,
the teaching point and its rate, temperature, lateral weight, working-trace amplitude and decay,
sensory scale) and its short school (corpus lessons, rows per lesson, DAgger games); the founder
is a (256, 128, 64) brain with the compose defaults. One evaluation raises one brain on one core
(`tron/r3.py`): corpus lessons, DAgger games with `voronoi2` labelling every position the brain
reaches, then a frozen tournament against the bot pool, 8 games per bot. Fitness is the weighted
score less a penalty for moves slower than 40 ms. Population 64, steady state after generation 0:
each new genome is an elite raised again, an immigrant, or a child of two tournament-picked
parents (crossover, one to three mutations). The eight best genomes with at least two raisings are
raised three more times and played 16 games per bot on seeds 900,000+; they are ranked by that
validation alone (`runs/r3/ga/summary.json`).

All eight finalists were flat or two-layer brains on the full-field sense with 32 rows per lesson;
within a short school the deeper layouts learned less. The winner: (256,), normalized teaching,
rate x 0.3, lateral -0.5, working trace 0, 1,200 corpus lessons. It won no game against `voronoi`
or `voronoi2`, 71% against `safe` (a bot that only avoids crashing). `TRON_DEEP=1` restricts the
search to deep layouts; `TRON_PRIOR` names a folder of earlier brains to add to the tournament
pool (optional).

### 2. School

```sh
python scripts/phaseb.py --arm instruct --genome runs/r3/ga/summary.json --rank 0 --seed 23 \
    --out runs/r3/b/instruct-s23 --rows 16 --watch 15000 --stage2 40000 --stage3 60000 --workers 4
```

15,000 corpus lessons of 16 rows, then DAgger on the brain's own positions with `voronoi3` labels
(the long school), checkpoints every 10,000 moments with the strategy tests and a tournament.
Arms `control` (`voronoi2` labels), `selfplay` and `combined` were the comparisons; self-play from
outcomes alone (`step` with rewards) fell to 0.00 to 0.02 against `voronoi`. The best brain,
seed 23 at 100,000 moments, read 18-46 against `voronoi` on 32 validation pairs.

### 3. Expert iteration

```sh
python scripts/phasec.py --arm exit --start runs/r3/b/instruct-s23/brain-m100000.npz --sense field \
    --seed 32 --rows 32 --workers 3 --backend cpu --gate-voronoi --out runs/r3/c/exit-s32
```

The brain rides against the labelling opponents; at every position it reaches, a 3-round
alpha-beta (6 ply, Voronoi leaf) with +8 leaf units on the brain's own greedy move labels the
position, and that label is the lesson. A generation (10,000 moments) is kept only if it scores
above 0.5 against the previous generation over 64 pairs, or at least 0.45 and better against
`voronoi`; otherwise the previous generation is restored. At 40,000 moments seed 32 read 130-126
(0.51) and 122-134 (0.48) against `voronoi`, from a start at 0.18: **Mako 1.0**. Deeper search in
the labels (10 ply) and larger steps lowered the brain; DAgger on `ab5` labels reached 0.20 to
0.38; replaying earlier labelled positions lowered every arm that used it.

### 4. Selection between short branches

```sh
python scripts/select_exit.py --start runs/r3/c/exit-s32/brain-m40000.npz --out runs/r3/c/sel-mako \
    --children 12 --depth 3 --moments 2500 --gate-pairs 64 --gens 60 --workers 24
```

Each generation raises 12 children from the current best for 2,500 moments of expert iteration;
child k divides the learner's rates by 2, 3, 4 or 6 and gives its own move a prior of 8, 4 or 16
leaf units. The children and the best play 64 pairs against `voronoi` on fresh gate seeds, the
three best play 64 more on a second set and play the best head to head; the pick replaces the best
only if it is not lower on both gate sets and scores at least 0.45 against the best. Generation 0
gave **Mako 1.5** (158-96-2 and 152-104 against `voronoi`), generation 2 **Mako 1.6** (172-84 and
170-86; 0.56 against Mako 1.0). Later picks within 0.06 of Mako 1.6; 64 gate pairs (± 0.09) do
not separate them. `--sprt` replaces the fixed gate with a sequential test (batches of 32 pairs,
H0 no gain against H1 +0.04, up to 512 pairs) and `--league a.npz,b.npz` adds past brains every
pick must hold against.

### 5. Self-play

```sh
# a first line from Mako 1.6; its first kept generation is the start of the second
python scripts/select_exit.py --start runs/r3/c/sel-mako/best-g3.npz --out runs/r3/c/sp-flat-b \
    --children 8 --eta-divs 25,40,60 --priors 8,4,16 --depth 3 --moments 1000 \
    --gens 400 --workers 8 --pipeline --sprt --league mako10.npz,mako15.npz \
    --selfplay --anchors bot:voronoi,bot:voronoi2,bot:voronoi3,bot:ab5,mako10.npz,mako15.npz,mako16.npz \
    --anchor-share 0.5 --softs "" --crit-w 2.5 --exploiter --train-half --selves 8
# the line that made the shipped brain
python scripts/select_exit.py --start runs/r3/c/sp-flat-b/best-g1.npz --out runs/r3/c/sp-flat-e \
    --children 8 --eta-divs 12,18,24 --priors 8,4,16 --depth 3 --moments 1500 --base-eta 0.0009 \
    --gens 400 --workers 8 --pipeline --sprt --league mako10.npz,mako15.npz \
    --selfplay --anchors bot:voronoi,bot:voronoi2,bot:voronoi3,bot:ab5,mako10.npz,mako15.npz,mako16.npz \
    --anchor-share 0.5 --softs "" --crit-w 2.5 --exploiter --train-half --selves 8
```

`mako10.npz`, `mako15.npz` and `mako16.npz` stand for the brains of stages 3 and 4. The children
play the line itself: the current best, its last 8 kept generations and an exploiter (a child that
plays only the best and joins the pool), and with probability 0.5 an anchor (the bots and the
earlier brains). Opponents are drawn by prioritized fictitious self-play, weight (1 - the child's
recent score against them)^2. The 6-ply search with the child's move as prior labels each
position (argmax: soft targets from the search's scores lowered every child that used them);
positions where some move loses weigh 2.5 (`lesson(..., weights=)`). The gate is the sequential
test against the best, a head-to-head and the league. The step size decided it: children 2 to 12
times under the start's rate fell against `voronoi` in every line; 12 to 60 times under kept
generations.

The first line's kept generation 0 read 176-80 and 170-86 against `voronoi`. The second line,
continued for 19 generations to 28,500 moments, gave the shipped flat brain: 186-68-2 and 182-74
against `voronoi`, 0.54 against Mako 1.0, 0.60 against Mako 1.5. Against the stronger bots it
scores 0.20 (`voronoi2`), 0.25 (`voronoi3`) and 0.14 (`ab5`).

## The deep brain

Raised from scratch, deep brains stayed near 0.1 against `voronoi`; distilled from a flat brain,
they agreed with it on 0.94 to 0.98 of positions and then drifted. What worked: start the deep
brain with the flat brain's function, then move the play into the deep layers in steps.

| Stage | Script | Where, how long | Result |
| --- | --- | --- | --- |
| 1. Function-preserving growth | `net2net.py` | minutes | (256, 128, 32) skip brain = Mako 1.6 within 0.001; 0.65 |
| 2. Self-play | `select_exit.py --selfplay` | L4, about 25 minutes per generation | 0.64 / 0.59; the deep pathway decides 0.1% of moves |
| 3. Distil the deep pathway | `skip_scale.py`, `deep_raise.py` | L4, 2,500 moments, under an hour | skip x 0.5: 0.64, the deep pathway decides 3.4% |
| 4. Anneal the skip | the same, five times | L4, overnight | skip x 0.016: 0.63 / 0.66, the deep pathway decides 75% |
| 5. Distil the brain + search | `distil.py` | one c7i.48xlarge, about 35 minutes for two kept generations | **Mako Deep**: 0.71 / 0.73, the deep pathway decides 81% |

### 1. Function-preserving growth

```sh
python scripts/net2net.py --donor mako16.npz --out runs/r3/c/n2n --layouts deep3n --eps 0.2
```

The (256, 128, 32) connectome plus synapses between `module_0` and `motor` both ways (a custom
anatomy through `Brain.compose(connectome=...)`); the flat donor grafted as sensory, its
association region into `module_0` and its motor neurons: its input weights and readout run
through the skip. Every synapse of the new pathway keeps this brain's construction scaled by 0.2,
so the brain plays the donor's moves (agreement 0.999 on the turn set) while the new layers
receive a learning signal. At 0 the brain is the donor exactly and the new layers never learn.

### 2. Self-play

As the flat line's stage 5, from the skip brain, rates divided by 20, 30 and 50. Generation 1 was
kept: 0.64 and 0.594 against `voronoi`, 0.55 against Mako 1.5. With its deep pathway cut it played
the same moves on 99.9% of positions: the skip played.

### 3. Distil the deep pathway

```sh
python scripts/skip_scale.py runs/r3/c/sp-deep3n/best-g2.npz 0.5 runs/r3/c/n2n/deepD-start.npz
python scripts/deep_raise.py --init load --start runs/r3/c/n2n/deepD-start.npz --mako runs/r3/c/sp-deep3n/best-g2.npz \
    --teacher mako --l1-rate 0 --skip-rate 0 --eta 0.0009 --moments 15000 --every 2500 --stop-at 0.6 \
    --out runs/r3/c/deepD --backend torch
```

The skip's efficacies are halved; then the deep pathway alone learns the teacher's moves (its
greedy move on every position the brain reaches), with the first layer and the skip held at rate
0 (`learner.synapse_rate`). The run stops when 128 checkpoint pairs reach 0.60. At 2,500 moments
it read 0.64 against `voronoi` and the deep pathway decided 3.4% of the moves.
`scripts/deep_ablation.py <brain>` reads that share: the brain with its deep pathway at zero,
agreement on the turn set and 64 pairs against `voronoi` with and without it.

### 4. Anneal the skip

Repeat stage 3 from each stage's `final.npz` with the skip halved again, until the skip is under
0.02 of its start (five halvings, 0.5 to 0.0156). The deep pathway's share of the moves grew
3.4% → 53% → 71% → 75%. The final brain decides 75% of its moves in the deep pathway; with the
pathway cut it scores 0.00 against `voronoi`. Read from rest over 128 pairs per set: 160-96 and
170-86 against `voronoi`, 0.47 against Mako 1.0, 0.50 against Mako 1.5.

### 5. Distil the brain + search into the brain alone

```sh
python scripts/distil.py --start deep-stage4.npz --out runs/distil/deep --league deep-stage4.npz \
    --sims 200 --positions 24000 --workers 90 --children 8 --eta-divs 20,30,50 --lessons 1200
```

Each generation the current best rides alone, half its games against bots (`voronoi`, `voronoi2`,
`voronoi3`, some `ab5`), the rest against itself, its kept generations and the league; a quarter
of the games follow the teacher's moves. At each position the brain reaches, the teacher (the
same brain guiding `tron/mcts.py` at 200 simulations, territory leaves) gives the root's visit
shares; about 30,000 positions a generation. Eight children learn from the last two generations'
positions at rates 0.0009 divided by 20, 30 or 50 (a fixed reference), even children the visit
shares (`lesson(x, targets=...)`), odd children their argmax, sharp positions weighted 2.5
(`weights=`), every act and lesson from rest. A child is kept only through the brain-alone gate:
the sequential test against its parent over mirror pairs against `voronoi` (cap 512, undecided:
128 fresh pairs), then head to head against its parent and each league brain. Kept: generation 0
(+0.086 over 128 pairs) and generation 2 (+0.069 over 288), both argmax children at rate
0.0009/20; generations 3 to 8 found no child ahead. The same route lowered every child of the flat
brain, at 200 and 800 simulations and rates down to 0.0009/800.

## A brain-guided search

`tron/mcts.py` is a PUCT search over rounds (my move, then the opponent's reply knowing it): the
brain's settled motor activations are the priors, the leaf value blends a value readout of the
settled state (`scripts/value_readout.py`) with the Voronoi territory. `scripts/az.py` is an
AlphaZero loop on it: self-play with the search, lessons on the root's visit shares
(`lesson(x, targets=...)`), a value readout per generation, and a gate by the player. Work in
progress: with territory leaves and 200 simulations (about 0.4 s a move on the CPU), the flat brain
with the search scores 0.92 against `voronoi`, 0.72 against `voronoi2`, 0.59 against `voronoi3` and
0.40 against `ab5` (128 games each), against 0.80, 0.20, 0.25 and 0.14 for the brain alone. The
page plays the brain alone.

## Smoke runs

Each route at a size that finishes in minutes, run on an Apple M4 on cadence-net 0.95.2. These
check that the stages run end to end, not that they raise a strong brain. `TRON_MAX_PAIRS` caps
every reading at that many pairs.

```sh
bash scripts/smoke.sh          # both routes; `flat` or `deep` for one
```

[`scripts/smoke.sh`](scripts/smoke.sh) builds small data files (64 corpus games, 30 scenario games,
a 3-game turn set), then runs every stage with tiny budgets: 4 genomes, 80 school moments, 60
moments of expert iteration in generations of 30, one selection generation of 2 children, one
self-play generation of 2 children from the shipped flat brain; and for the deep route the growth
of the shipped flat brain into (256, 128, 32), a halved skip, 40 moments of deep-pathway
distillation, the next halving and the ablation. `TRON_MAX_PAIRS=4` caps every reading at 4 mirror
pairs.

`bash scripts/smoke.sh all` ran end to end in 31 minutes with the data already built. The stages,
run one by one on an Apple M4 (cadence-net 0.95.2, Numba; the machine shared with other jobs):

| Stage | Wall time | What it printed |
| --- | --- | --- |
| data | 5 min | 64 games, 5,921 moments; 22 / 300 / 13 scenario positions; 473 turn-set positions |
| 1. genetic search | 2 min | 4 raisings and the validation, no errors |
| 2. school | 2 min | checkpoints at 40 and 80 moments |
| 3. expert iteration | 15 min | two generations through the gate (0.75 kept, 0.00 restored) |
| 4. selection | 2 min | one generation, the pick rejected by the gate |
| 5. self-play | 1.5 min | one generation through the sequential gate (no gain, not kept) |
| deep 1. growth | 1 min | agreement with the donor 1.000 on the turn set |
| deep 3. distillation | 6 min | checkpoints at 0, 20 and 40 moments, agreement with the teacher 0.98 |
| deep 4. next stage, ablation | 3 min | the deep pathway decides 3.0% of the moves after 40 moments |

Most of the expert-iteration minutes are its checkpoint readings: the strategy tests and the
hybrid player at every checkpoint.
