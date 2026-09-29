# Training the Doom player

This is the pipeline that produced the shipped brains, end to end. Every
stage writes receipts (JSON) so results stay auditable. Times below are from
an Apple M4; a many-core cloud box shortens the sweep linearly.

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
  pressed-recall (the honest number for rare actions), live kills vs
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

Exports land in `runs/ultimate/exports/`; copy any of them into
`data/models/` to play that age of the brain. The run is resumable: a
`progress.json` sidecar plus the latest export restart it with `--resume`.
History windows are explicit external context (`cadence.memory.History`),
built per-row for exactly the frames the run needs — never claim learned
recurrent memory from them.

## 6. Install a trained brain into the lab

A model is two files in `data/models/`:

```sh
cp runs/dagger1/dagger_r2.json.gz       data/models/my-player.json.gz
cp runs/dagger1/dagger_r2.norms.json    data/models/my-player.norms.json
echo '{"label": "My player"}'         > data/models/my-player.meta.json
```

It appears in the lab's dropdown immediately (no restart), or share it with
someone by pressing EXPORT and letting them IMPORT the file.

## Honest boundaries

Settlement qualification is a numerical property, not task success; a
qualified brain can still play badly. Teaching and DAgger are supervised
witness admission — replayed demonstrations, not reinforcement learning.
Whether recursive observation *helps* is an empirical question your
recursive-vs-control receipts answer per task; do not claim a depth
advantage without that pair.
