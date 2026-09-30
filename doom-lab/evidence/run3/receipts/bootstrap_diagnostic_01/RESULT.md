# Frozen bootstrap diagnostic, 2026-09-29

The similar early accuracies were not a constant-action collapse. The more
consequential finding is weak use of the deep observer path at the current
operating scale. No original parameters changed. These are prepared-data
development diagnostics, not fresh gameplay, a depth advantage, or a proof
that the architecture is linear.

Five seed-zero epoch-two checkpoints used the same 96 selected development
rows, 32 training rows and 12 causal-probe rows. All query variants qualified.
The five-worker diagnostic completed in 30 seconds. The separate operating
range follow-up completed in 19 seconds. Its first attempt failed after two
seconds because NumPy interpreted a tuple of population indices as dimensions;
the corrected attempt used a new source/run directory and preserved the
failure. Neither attempt admitted parameters or deployed a model.

| Model | Training agreement /32 | Development agreement /96 | Original development subset /32 | Basic /21 | Doors /42 | Navigation /33 |
|---|---:|---:|---:|---:|---:|---:|
| 52 patches, depth1 |18|62|20|13|31|18|
| 52 patches, depth2 |20|61|21|14|30|17|
| 52 patches, depth3 |19|57|20|13|27|17|
| 84 patches, depth2 |20|60|20|13|30|17|
| 84 patches, depth3 |20|60|21|13|30|17|

Each model predicted seven action types. The depth-two/three models agreed on
89–94 of the 96 actions despite measurable score differences; the depth-one
control agreed with them on 74–75. All models correctly selected USE on the
eight sampled USE rows. That does not demonstrate autonomous door completion.

## What the network is using

On the same twelve development contexts, zeroing all residual-read weights
changed **zero actions in all five models**. Zeroing all latent state/residual
inputs to the policy also changed zero actions. Zeroing direct current-pixel
weights into the policy changed 8–9 actions. These interventions affect cloned
models only, and their qualified score deltas remain recorded in the receipts.
Zeroing explicit action history changed 2–3 actions; zeroing visual history
changed none in the depth-two/three models and one in the depth-one model.

The deeper brains are therefore not structurally disconnected, but their
latent contribution is small relative to direct pixel/history contributions on
this sample. The full coupled equilibrium and common nonlinear patch rule
still execute. A structural depth count alone does not show acquired hierarchical
skill or useful recursive readback.

Across 96 actual contexts, the 52-patch depth-three checkpoint's signed policy
drive components had RMS magnitudes:

| Component | RMS |
|---|---:|
| Current pixels |0.13521|
| Executed-action history |0.07211|
| Bias |0.06757|
| Latent patch states |0.00459|
| Residual readback |0.000706|

Its scene/aim state RMS was 0.0144/0.0134; reflection1 was 0.00202 and
reflection2 was 0.01080. The reflection tanh derivative medians were
0.999998/0.999983. No state was within 1e-6 of a box boundary in any model.
The policy itself was not uniformly near-linear: the smallest measured tanh
derivative was about 0.24–0.31, depending on model.

The core prediction is `tanh(b + sum(w * signal))`; inactive box constraints
alone do not imply linearity. Nine selected pairs of actual development
endpoints had exactly identical visual/action histories. Across the four
depth-two/three models, midpoint-query RMS departure from the affine midpoint
was at most about 0.554% of endpoint RMS score separation, with no midpoint
argmax disagreement. Four pairs were Basic, four doors, and one navigation.
This is a narrow operating-range observation; the midpoint itself is synthetic,
and the result cannot establish global linearity or global absence of depth
benefit.

## Data coverage and ambiguity

The 4,597 prepared rows contain only 36 Basic training rows from twelve
episodes, with 21 development rows from four episodes. Their only labels are
fire-left, fire-right and fire-strafe-right. Navigation has 403 training rows
from six episodes and 117 development rows from two. Doors contributes 3,216
training and 804 development rows, with repeated scripted trajectories.

No exact complete-input collision has conflicting teacher labels. No exact
current-pixel collision has conflicting labels either. Thus these checks do
not support claiming that contradictory labels are the immediate failure.
Action-history-only collisions do conflict: 18 groups covering 352 rows.

There are 47 complete-input and 564 current-pixel groups shared across training
and development. On the same 96 development rows, nearest-neighbor lookups into
training data obtain 80/96 using current pixels, 76/96 using all ports, and
70/96 using action history alone. These are diagnostic baselines, not Cadence
results or deployable shortcuts. They show that repeated trajectories make
offline agreement optimistic and that this representation already contains
information the current learned mapping does not fully use.

## Consequences for the next bounded comparison

1. Keep the successful Basic checkpoint as a retained-skill anchor while
   measuring autonomous practice on its own visited states. Do not equate
   roughly 60% teacher agreement with native failure or native competence;
   separate gameplay receipts determine that.
2. Compare sensor-skip and no-sensor-skip candidates at matched examples and
   public repair budget. The existing no-sensor-skip gene still keeps a direct
   executed-action-history path into the policy. A further explicit control
   removing that direct path would test whether decisions actually require
   the hierarchy; it must remain a declared architectural candidate, not a
   hidden change to the current actor.
3. Test initial-scale/conditioning and repair-prior genes with these same
   causal and operating-range measurements. The present evidence supports
   weak deep-path signal, not a derivative or qualification bug and not an
   argument for modifying the common patch equation. More patches alone have
   not solved this bottleneck in the matched first wave.
4. If a finite bootstrap extension is needed, add diverse starting views and
   bounded deviations/recovery contexts using the already frozen generator,
   rather than repeating the same expert trajectory. Keep the budget fixed
   and episode-split; later improvement labels must still come from the
   learner's own native experience. Navigation has not been shown acquired by
   this offline probe.
5. Do not use these repeated development data to make a fresh-confirmation
   claim. Preserve prospective native seed/map evaluation after selection.

Full receipts are in this directory and `../bootstrap_nonlinearity_02/`.
The original model/data artifacts stay in AWS workspace
`/home/ec2-user/doom-v3-20260929`. The two executable diagnostic modules and
the core causal helper preserve exact model, dataset, row-selection and source
hashes. `verification.json` checks the local small receipt set.
