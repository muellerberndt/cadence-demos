# Amen startup curriculum

This development experiment compares uniform training with extra exposure to real
starts of the Amen recordings. Both arms use the same flat 71-patch Cadence
candidate brain, 585 supplied history/clock/wake inputs, 41,606 parameters and the
public `observe_batch(..., source="witness")` learning rule. Every output comes
from qualified patch settlement. There are no state/error contacts or learned
recurrent memory; temporal context is the supplied eight-event history.

The candidate core is commit `ab3cad2207e4c8b50b269829a4b44c2d18543ed5`.
This experiment does not release Cadence, replace the public demo, or establish
musical quality or recursive advantage.

## Frozen comparison

Three paired seeds, 1103/1109/1117, receive 128 batches of 32 witnessed rows.
Uniform uses the original shuffled row order. The curriculum keeps the first
16 rows of every uniform batch and replaces the last 16 with cyclic shuffled
visits to **all** 568 actual first-eight rows from the 71 training regions.
There is no target filtering, fabricated start, changed history, or decoder
repair. Startup fraction 0.5 and prefix length 8 are declared curriculum genes;
uniform is their control. Repeats and overlap remain in the ledger.

All six cases use the original 128 held-out rows selected with seed 1103,
float64 CPU settlement, four threads per worker, the original priors and solver
budgets, and a 900-second case cap. All cases, refusals and interrupted work are
retained. Seed 1103 and this corpus were already used during development; the
other seeds are additional development seeds, not independent task confirmation.
Five held-out regions share source recordings with training.

The original gates remain: all 128 admissions accepted; all free queries
qualified; held-out decoded MAE improves by at least 0.01; a 128-half-beat argmax
rollout has drum presence at least 0.5 and bass presence at least 0.25; and all
four fixed sampled rollouts complete. Campaign success requires all six cases
to complete numerically and all three curriculum cases to pass those gates.
A failed uniform comparator is retained as an outcome. No seed is selected.

The owner listened to the original uniform pilot and rejected its musical
quality, reporting that it fades to noise. Passing the above numerical and
presence gates would not reverse that assessment or establish musical success.

## Verified outcome

The campaign failed its frozen gate. All six cases completed, with 768 accepted
admissions and no refused or interrupted calls. The verifier checked 121,896
prepared rows, 42 snapshots, and exactly replayed 5,376 free queries. The uniform
seed-1103 brain exactly reproduced the original pilot's parameters and cursor.

| Seed | Uniform final MAE | Curriculum final MAE | Uniform presence gate | Curriculum presence gate |
| --- | ---: | ---: | --- | --- |
| 1103 | 0.150151 | 0.165093 | Fail | Fail |
| 1109 | 0.157261 | 0.164418 | Pass | Pass |
| 1117 | 0.147457 | 0.171850 | Pass | Fail |

Extra startup exposure worsened held-out MAE in all three pairs. It sustained
symbolic drum presence, but did not make bass generation reliable. Actual audio
also exposes a weakness in the presence gate: curriculum seed 1109 has drum
flags throughout, yet zero rendered drum energy in its last three bars because
the predicted gain reaches zero. These gates do not certify usable music.

See the [verification receipt](evidence/20261001/amen-startup-curriculum/verification.json),
[frozen protocol](evidence/20261001/amen-startup-curriculum/protocol.json), and
[all-output audio diagnostics](evidence/20261001/amen-startup-curriculum/audio.json).

## Sources and reproduction

- [Collector](amen_startup_curriculum.py), with `freeze`, `launch`, and `arm` modes.
- [Verifier](verify_amen_startup_curriculum.py), with source-bound free-query replay.
- [Audio renderer](render_amen_startup.py), reading verified events without learning.
- Focused tests: `test_amen_startup_curriculum.py` and
  `test_verify_amen_startup_curriculum.py`.

On a host containing the exact frozen app, core, corpus and original pilot:

```sh
PYTHONPATH=core/src python collector/amen_startup_curriculum.py freeze run \
  --app "$PWD/app" --reference-helper "$PWD/reference.py" \
  --baseline-run /home/ec2-user/cadence-060-flat-amen-20261001/runs/flat-1103
PYTHONPATH=core/src python collector/amen_startup_curriculum.py launch run
PYTHONPATH=core/src python collector/verify_amen_startup_curriculum.py run \
  --out verification.json
PYTHONPATH=core/src python collector/render_amen_startup.py run \
  --verification verification.json \
  --texture-source "$PWD/dependency-copies/texture_synth.py" --out audio
```

The retained verifier pins this campaign's protocol and collector hashes. A new
campaign needs its own reviewed protocol binding; do not overwrite the retained
run or silently change the expected hash. The exact replay also depends on the
recorded Python/NumPy/Torch runtime and original absolute source paths. The
archive keeps small copies of the original pilot and renderer dependencies;
large shared fixtures remain at their catalogued AWS paths.

Verification checks the complete prepared row cache, deterministic schedules,
founders, source pins, witness clamps, admission cursors, work, snapshot custody
and roundtrips. It exactly replays every returned free query and checks qualified
flat outputs against an independent analytical optimum. Uniform seed 1103 must
match the original 128-batch pilot's weights, biases, live state and admission
cursor exactly. Training solves are not numerically replayed. Rare interrupted
bookkeeping gaps are conservatively rejected, not counted as successful cases.

Every final brain is rendered in argmax mode and with fixed sample seeds 1–4,
using the unchanged instrument and gains. Per-bar actual drum gain, separate
stem RMS, exact zero-stem bars and last active events are descriptive diagnostics
requested after the listening failure; they do not alter any gate. No output
normalization, best-example selection, or public demo replacement occurs.

Large row caches, logs, checkpoints and all 30 WAVs stay on AWS, as required by
the workspace data policy. Only compact evidence and the six argmax listening
files are copied locally.
