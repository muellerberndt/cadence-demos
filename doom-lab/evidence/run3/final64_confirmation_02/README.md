# First reserved Basic confirmation, 2026-09-29

The prospectively frozen first H144 update4 checkpoint passed every declared gate against its bootstrap founder on 64 reserved paired Basic seeds. No model was replaced during testing and this runner did not deploy a model.

| Outcome | Founder 307604135121 | Candidate ad9b330cd1c1 |
| --- | ---: | ---: |
| Native kills / scheduled episodes | 61 / 64 | 63 / 64 |
| Mean native return | -124.562500 | -34.171875 |
| Mean native tics | 165.906250 | 104.062500 |
| Qualified queries / attempted | 2677 / 2677 | 1684 / 1684 |
| Native timeouts | 3 | 1 |

The primary paired return improvement was **90.390625**, with the prespecified 10,000-resample 95% paired bootstrap interval **[43.515625, 136.781250]**. The duration difference was -61.843750 tics, interval [-96.093750, -27.531250]. Both won 60 cases; only the candidate won 3; only the founder won 1; neither won 0. The success-rate difference was +3.125 percentage points, interval [-3.125, +9.375]; this does **not** establish a success-rate improvement. The candidate Wilson success interval is [0.916659, 0.997236].

All 128 episodes completed with no fallback, missing outcomes, source drift, or unqualified queries. Independent verification recomputed every recorded transition sum, action/button/tic identity, native success predicate, checkpoint/normalizer/source hash, and paired bootstrap using a separate NumPy implementation. It passed. Native evaluation took 35.2366 seconds with at most 16 one-thread workers, executing 17,278 tics and 4,361 queries.

Before play, the prior-use audit read 1,815 existing V3 record files (390,552,591 decompressed bytes), finding no reserved seed integers. The first preflight attempt refused an unfinished gzip writer before any gameplay; it is preserved separately. After the writer closed, the identical candidate, criteria and seeds were used. The 64 initial frames contain 60 distinct hashes, identical between paired models. Different seeds are not a guarantee of independent hidden layouts; this is a reserved-seed Basic result, not general Doom competence or proof that recursive paths caused the gain.

Full evidence remains on AWS at `/home/ec2-user/doom-v3-20260929/runs/final64_confirmation_02`. Small local receipts are `freeze.json`, `summary.json`, and `independent_verification.json`. Freeze SHA-256: `85ca79572dbc39f3bae9ca52a769af32ef388ff57870e7863d137977cbc64327`; summary: `1fa597a393721ce7451d0ba11ef9862310c14cecc565abb3dd1cba4d3727885d`.

A separate post-hoc image-hash description found one initial image shared with the finite bootstrap training corpus (final seed1400000014, bootstrap1100100003), none with its development starts, and four duplicate initial-image pairs within the final64. It checks visible initial images only, not hidden-state or complete-trajectory equality, and not all later practice exposures. The original reserved-seed criteria and result are unchanged; do not describe this as64distinct unseen visual states. See `bootstrap_initial_frame_overlap.json`.
