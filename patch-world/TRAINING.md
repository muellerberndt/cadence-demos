# Raising and breeding the founders

Everything below runs the same `patchworld` package the page runs in Pyodide, on
`cadence-net[fast]==0.95.2` (Numba) with one thread per process. The founders in
`web/pack/founders/` were bred on one 64-vCPU cloud machine (c7i.16xlarge, Amazon Linux 2023,
Python 3.12); the nursery took 11 minutes and the evolution 29 minutes of wall time there, and the measurements another half hour.

```sh
python -m pip install "cadence-net[fast]==0.95.2" pytest
export OMP_NUM_THREADS=1 NUMBA_NUM_THREADS=1
```

## 1. Nursery: raise brains where nobody dies

```sh
python training/breed.py nursery --worlds 32 --moments 30000 --seed 12 --procs 32 --out runs/nursery
```

Each of 32 worlds holds eight newborn brains: four gene sets (the founder genes of
`patchworld/genes.py` and mutations of them, widths 16 to 48, one or two regions), each twice,
once with a recall memory and once without, on the same brain seed. In the nursery a creature's
energy never falls below one, so a brain that has not yet learned to forage lives on and keeps
learning. Each brain lives 30,000 moments, twenty seasons, through `Brain.live`, learning from
what its actions bring: energy from food, water when thirsty, poison from winter berries, bites.
No teacher, no labels. Per 1,000 moments the run records each creature's intake, berries in
summer and in winter, nuts, drinks, bites and wasted acts (`runs/nursery/world*.json`).

`python training/seasons.py runs/nursery` prints the berries eaten in each winter of a life.
Measured on this run (`evidence/nursery.json`, which also holds two nurseries of the same size
whose creatures lacked the nausea sense, or the nausea and the cold): a creature ate 4.9 winter
berries per 1,000 moments in its first winter and 2.8 in its tenth; its intake rose from 102 to
111 units per 1,000 moments between its first and last 5,000 moments. The three nurseries read
within 0.4 berries of each other in every winter; the world keeps both senses.

## 2. Evolution in the mortal world

```sh
python training/breed.py evolve --nursery runs/nursery --islands 32 --moments 58500 --founders 8 \
    --cap 12 --seed 21 --procs 32 --genes '{"heat": 0.0, "need": 0.0}' --out runs/evolve
```

The eight nursery brains with the best intake over their last 5,000 moments (net of what their
brains cost) found 32 islands. On an island creatures die: of hunger, of thirst, of predators,
of age (8,000 moments). A creature that stores its `birth` share of its capacity bears a child
that takes half its energy, a copy of its brain as it is at that moment, and mutated genes
(`patchworld/genes.py: mutate`). Up to 12 learners live on an island; when fewer than three are
left, founders re-enter. 58,500 moments end each island at the close of a summer.

`--genes` sets the founders' arousal heat and need to zero. Heat widens the sampling of a
brain in want: a hungry creature with heat samples its policy hotter and wanders. With the
nursery's heat the learners lived shorter lives than their frozen twins in the mortal world;
with heat and need at zero they lived longer (`evidence/heat-on.json`, `evidence/heat-off.json`,
quoted in the README). Mutation can raise both again; selection decides. A second evolution
without `--genes` (16 islands, seed 22) is the control for that choice. What the two
evolutions changed, founders' mean against survivors' mean (`evidence/islands.json`):

| Gene | Founders | Survivors, heat set to 0 | Founders | Survivors, genes as raised |
| --- | --- | --- | --- | --- |
| arousal heat | 0 | 0.46 | 1.03 | 1.07 |
| arousal need | 0 | 0.061 | 0.056 | 0.070 |
| sampling temperature | 0.26 | 0.15 | 0.26 | 0.13 |
| associative store rate | 0.19 | 0.30 | 0.19 | 0.38 |
| recall memory share | 0.25 | 0.55 | 0.25 | 0.94 |
| sense range (cells) | 3.6 | 2.9 | 3.6 | 3.0 |
| body size | 1.02 | 1.26 | 1.02 | 1.22 |

Survivors of the main evolution are 39 generations from their founders on average (at most
114); on every island one founder's lineage held the whole population at the end. Births kept
each island at its cap of 12 learners, and founders re-entered 26 times in all (when fewer than
three learners were left).

## 3. Select the page's founders

```sh
python training/breed.py select --evolve runs/evolve --nursery runs/nursery --founders 8 --out runs/founders
python pack.py --founders runs/founders/after
```

The founders are the survivors with the highest intake per moment among those older than 1,500
moments, at most one per island. `runs/founders/before` keeps the generation-0 founders the
islands started from, for the evolution reading.

## 4. Measure

```sh
python training/evaluate.py controls  --founders web/pack/founders --seeds 32 --moments 12000
python training/evaluate.py flip      --founders web/pack/founders --seeds 32
python training/evaluate.py caches    --nursery runs/nursery --seeds 16 --pairs 16 --moments 3000
python training/evaluate.py seasons   --founders web/pack/founders --seeds 32
python training/evaluate.py evolution --founders web/pack/founders --before runs/founders/before --seeds 32 \
    --retune-before '{"arousal": {"heat": 0.0, "need": 0.0}}'
python training/evaluate.py competition --founders web/pack/founders --before runs/founders/before --seeds 32 \
    --moments 12000 --retune-before '{"arousal": {"heat": 0.0, "need": 0.0}}'
python training/evaluate.py controls  --founders runs/founders/before --seeds 32 --name heat-on
python training/evaluate.py controls  --founders runs/founders/before --seeds 32 --name heat-off \
    --retune '{"arousal": {"heat": 0.0, "need": 0.0}}'
python training/readings.py
python check_page.py
```

Every scenario runs on seeds from 100,000 on, none of which the nursery or the evolution used.
The receipts in `evidence/` hold the per-seed records, the SHA-256 of every source file and
brain they read, and the summaries the README quotes.

## Smoke scale

A run of every stage that takes a few minutes on a laptop:

```sh
python training/breed.py nursery --worlds 2 --moments 2000 --procs 2 --out runs/smoke/nursery
python training/breed.py evolve --nursery runs/smoke/nursery --islands 2 --moments 3000 --founders 4 --cap 8 --procs 2 --out runs/smoke/evolve
python training/breed.py select --evolve runs/smoke/evolve --nursery runs/smoke/nursery --founders 2 --min-age 0 --out runs/smoke/founders
python training/evaluate.py flip --founders runs/smoke/founders/after --seeds 2 --procs 2 --summer 300 --winter 300 --out runs/smoke
python -m pytest -q tests
```
