# Training the Doom player

This is the pipeline that produced the shipped brains, end to end. Every
stage writes receipts (JSON) so results stay auditable. Times below are from
an Apple M4; a many-core cloud box shortens the sweep linearly.

> **Warning.** The large, deep layouts (`flagship`, `ultimate`) are expensive
> and sensitive to train. One batch-96 admission of the 327k-edge `ultimate`
> brain takes 3.5 to 6.5 minutes on a 64-thread cloud machine, one pass over
> a 20k-witness corpus takes half a day there, and the same run on a laptop
> takes days. The outcome depends on many coupled hyperparameters: parameter
> prior, batch size, sweep budgets, target encoding, `forward_keep`, input
> standardization and decode calibration each moved measured recall by large
> factors in our runs, and a mis-set one produces a brain that ranks well on
> its receipts and stands frozen in the game. Start with the small layouts,
> change one setting at a time, and read every receipt before scaling up.
> Section 7 lists what our large runs measured.

## 0. One-time setup

```sh
./get_wad.sh
```

## 1. Collect a witness corpus from the scripted teacher

The teacher is a privileged scripted player: it reads object labels, the
depth buffer and map coordinates (the student never sees any of that), fights
with serpentine strafing, dodges incoming fireballs, and patrols
automatically-routed waypoints derived from the WAD's own geometry
(`wadmap.py`: sector rasterization, climb-aware A*, damage-floor pricing).

```sh
# Single map, ~50k witnesses in about a minute (8 workers):
python collect.py --episodes 40 --checks 8 --workers 8 --out data/corpus1

# Multi-map generalization corpus with shuffled routes per episode,
# plus efference and outcome tracks for the foresight variant:
python collect.py --episodes 100 --checks 10 --workers 8 \
  --maps E1M1,E1M2,E1M3,E1M4,E1M5 --out data/corpus3
```

The receipt records per-episode kills, deaths and the action distribution.
A corpus is only as good as its teacher — check those numbers first.

## 2. Understand the two things that make training fast

- **Input conditioning.** Raw Doom frames are heavily correlated, which
  ill-conditions settling: cold admission needed >16k sweeps raw vs ~3k
  standardized in our measurements. `norms.py` fits per-coordinate
  standardization **on training rows only** and is saved beside every
  checkpoint; the same transform must be applied at play time (the lab does
  this automatically).
- **Cold-start ramp.** A fresh brain's first batches settle hardest. The
  trainers admit a few small batches (8 → 64) before full-size ones;
  without the ramp, the first full batch can exhaust its sweep budget and
  refuse.

## 3. Bootstrap one candidate

```sh
python train_sweep.py --spec '{
  "name": "base-recursive_s0", "layout": "base-recursive",
  "seed": 0, "parameter_prior": 0.1, "epochs": 2,
  "forward_keep": 0.35, "max_examples": 6000, "max_checks": 1200,
  "max_error": 0.55, "batch_size": 64, "eval_episodes": 6
}' --corpus data/corpus1/witnesses.npz --out runs/sweep1
```

Notes that matter:

- `forward_keep` subsamples pure-forward frames so rare actions (fire, use,
  strafe) stay visible. Batched admission optimizes the mean example energy,
  and oversized batches measurably soften rare-action learning — keep
  batches moderate and balance the data instead.
- Every candidate is evaluated on live episodes against a
  **marginal-action control** (same action statistics, no perception), and
  the layout grid pairs every recursive layout with a **matched
  ordinary-composition control** (same patch counts, `observes` replaced by
  plain inputs). Claims about recursion require that pair.
- The receipt contains the bootstrap history, per-button agreement,
  pressed-recall (the number that matters for rare actions), live kills vs
  control, and the checkpoint hash.

## 4. DAgger: correct the student's own mistakes

Behavior cloning compounds drift: one wrong turn and the student visits
states the teacher never labeled. `dagger.py` runs student-driven episodes,
has the privileged teacher label every visited frame, and admits those
corrections mixed with replayed corpus rows (against forgetting),
re-evaluating after each round:

```sh
python dagger.py runs/sweep1/base-recursive_s0.json.gz \
  --corpus data/corpus1/witnesses.npz --out runs/dagger1 --rounds 2
```

## 5. The foresight variant (world model + efference)

`train_self.py` trains the `build_self` layout: retinas **plus an efference
copy of the previous action** in, motor **plus a foresight head** out. The
foresight targets are measured next-decision outcomes — Δhealth, Δammo,
kill events, view change — encoded into the state range. Reality supplies
these targets; no teacher is involved in them.

```sh
python train_self.py --corpus data/corpus3/witnesses.npz \
  --out runs/self1 --name self-grand_s0 --seed 0
```

The receipt's `outcome_mae` tracks world-model quality; its prediction error
is the surprise signal a curiosity-driven experience selector can use.

## 5b. The lineage trainer: one brain, its whole life on record

`train_flagship.py` trains the full-feature layouts — `--layout flagship`
(retinas + efference + fovea history + foresight) or `--layout ultimate`
(adds a periphery-history stream and larger populations) — and exports a
registry-ready checkpoint+norms pair **on a time cadence**, each with a
readiness probe, so the model dropdown becomes the brain's biography:

```sh
python train_flagship.py --layout ultimate \
  --corpus data/corpus3/witnesses.npz --out runs/ultimate \
  --name doom-hero --max-examples 20000 --batch 96 \
  --export-minutes 60 --threads 16
```

Do not raise `--threads` past 64: batched admission saturates at or below
64 threads, and 128 threads measured 13 to 26 % slower than 64 on identical
re-admissions of a real batch.

Exports land in `runs/ultimate/exports/`; copy any of them into
`data/models/` to play that age of the brain. The run is resumable: a
`progress.json` sidecar plus the latest export restart it with `--resume`.
History windows are explicit external context (`cadence.memory.History`),
built per-row for exactly the frames the run needs — never claim learned
recurrent memory from them.

`deep_probe.py` enriches every export with comparable diagnostics: it
watches the exports directory and writes a `deep` block into each meta
file, holding a fixed-row settle probe (the same rows for every
checkpoint, so the trend is free of sample noise), per-button pressed
recall and predicted press rates, and two short closed-loop episodes
measuring path, kills and button usage. The lab's TRAINING panel charts
these values once they appear. `evaluate.py` and `dagger.py` read the
brain's declared input streams and feed efference and both history
windows exactly as the lab does, for flagship and ultimate layouts alike.

```sh
python deep_probe.py --exports runs/ultimate/exports \
  --corpus data/corpus3/witnesses.npz
```

## 6. Install a trained brain into the lab

A model is two files in `data/models/`:

```sh
cp runs/dagger1/dagger_r2.json.gz       data/models/my-player.json.gz
cp runs/dagger1/dagger_r2.norms.json    data/models/my-player.norms.json
echo '{"label": "My player"}'         > data/models/my-player.meta.json
```

It appears in the lab's dropdown immediately (no restart), or share it with
someone by pressing EXPORT and letting them IMPORT the file.

## 7. Measured results at ultimate scale

One `ultimate` lineage (336 patches, 327,104 edges, five input streams,
batch 96, a 20k-witness multi-map corpus) trained on a 64-vCPU cloud box
with hourly checkpoint exports and fixed-row deep probes. The run was
stopped at batch 65 of a planned 208 after the probes went flat. Numbers
below come from those receipts; the same probes run on any brain you train
with this pipeline.

- **Settling economics.** The warmup ramp cut the first admission from
  9,236 to 640 sweeps. A batch-96 admission then ran 438 to 771 sweeps,
  3.5 to 6.5 minutes at 64 threads.
- **Ranking is learned early.** Mean AUC over the eight buttons reached
  0.90 at the first export and held between 0.90 and 0.92 through batch
  63. Forward AUC opened at 0.85 and sat between 0.78 and 0.83 afterwards.
- **The decode operating point decides whether the brain moves.** The
  ±0.6 motor targets are heavily imbalanced, so each button's settled
  score mean sits near the base-rate mean of its targets (forward:
  measured −0.284); zero-threshold decode then freezes the policy, with
  closed-loop path 0.0 while the ranking stays sound. Per-button
  thresholds calibrated on teacher score quantiles raised forward pressed
  recall from 0.34 to 0.64 at the same checkpoint and unfroze the closed
  loop (path 0 → 73.6 and 201.0 on the two probe seeds). The lab's
  RAW / CAL / TOP-1 decode modes and `dagger.py`'s per-round calibration
  come from this measurement.
- **Late batches were net-negative for deployability.** From batch 14 to
  63, calibrated forward recall held between 0.59 and 0.66 while raw
  forward recall fell from 0.48 to 0.13, forward score p90 went negative,
  and settle refusals at the probe budget of 384 rose from 0 to 16 to 52
  per 150 rows. Longer training bought nothing after the first day.
- **A linear baseline outranks the big brain at this scale.** Ridge
  regression on the same standardized rows reaches forward AUC 0.856 on
  the consumed rows and 0.871 on the full corpus, above the brain's 0.78
  to 0.83. At small scale the order flips: on 2k-row button prediction
  the brain beats ridge (0.763 to 0.781 against 0.735, prior-dependent),
  with the largest margins on sub-1 % actions. The parameter prior drives
  that margin; see the bootstrap study in the cadence repository
  ([docs/BOOTSTRAP.md](https://github.com/muellerberndt/cadence/blob/main/docs/BOOTSTRAP.md)).
- **No large checkpoint clears the live control.** Kills were 0 in every
  short probe episode, and the best calibrated closed-loop path at batch
  63 was 52.5 on all three probe seeds. Teacher-mixed DAgger rollouts are
  implemented; DAgger rounds at this scale are work in progress.

## Boundaries

Settlement qualification is a numerical property, not task success; a
qualified brain can still play badly. Teaching and DAgger are supervised
witness admission — replayed demonstrations, not reinforcement learning.
Whether recursive observation *helps* is an empirical question your
recursive-vs-control receipts answer per task; do not claim a depth
advantage without that pair.
