# Doom Lab components and contracts

The active player lives in [`v1/`](../v1/). It is the renamed current Doom-baby
implementation, historically called `v3`; immutable evidence and remote paths
retain that historical name. This document describes the scientific/runtime
boundaries. [Experiment history](EXPERIMENTS.md) records measured results;
[model inventory](MODELS.md) records checkpoint identities. Neither topology
nor a numerical qualification flag establishes competent play.

Cadence implements an observer-like self-reading system: bounded local patch
states, declared sensory/motor ports, state and prediction-error readback,
joint settlement, feedback-driven repair, durable records and public evidence.
All deployed motor scores are actual settled policy-patch coordinates. Within
a life only the public common patch repair changes relations; there is no
separately optimized neural motor head or privileged fallback controller.

## Component map

| Component | Main source | Responsibility and boundary |
| --- | --- | --- |
| Native tasks/engine | [`tasks.py`](../v1/tasks.py) | Pins task, WAD/scenario, rendering, seed, native reward and termination; keeps privileged facts out of actor inputs |
| Observation/actions/history | [`interface.py`](../v1/interface.py) | Exact 2,020-coordinate pixel/history encoding, normalization, 20 legal motor macros and execution acknowledgments |
| Cadence graph and actor | [`brain.py`](../v1/brain.py) | Candidate genomes, one coupled equilibrium, qualification, argmax, immutable queries and portable bundles |
| Finite starter collection | [`teacher.py`](../v1/teacher.py), [`collection.py`](../v1/collection.py) | Privileged finite demonstrations with teacher proposals and actual actions separately recorded; never a fallback for student gameplay |
| Preparation/bootstrap | [`training.py`](../v1/training.py), [historical capacity evidence](../evidence/run3/baby_screen_02/README.md) | Whole-episode splits, train-only normalizer, immutable sampling order, public admissions and checkpoints; frozen campaign launchers remain archived |
| Native action feedback | [`native_feedback.py`](../v1/native_feedback.py), [`native_feedback_long.py`](../v1/native_feedback_long.py), [`native_feedback_navigation_long.py`](../v1/native_feedback_navigation_long.py) | Exact fresh-engine replay, one intervention, frozen qualified Cadence continuation, complete native witnesses |
| Candidate life/retention | [`practice.py`](../v1/practice.py), [`practice_protocol.py`](../v1/practice_protocol.py) | Single mutable learner, durable experience queue/replay, frozen continuation/founder, candidate gates, promotion and rollback |
| Experience sampling | [`experience_sampling.py`](../v1/experience_sampling.py) | Declared collection stride, complete executed history, persistent selected/pending counters and backpressure |
| Browser bridge/package | [`runtime.py`](../v1/runtime.py), [`lab_deployment.py`](../v1/lab_deployment.py), [`server.py`](../server.py) | Actor/game ownership, model import/export, task/platform validation, practice opt-in and champion handoff |
| Local deployment preparation | [`deployment.py`](../v1/deployment.py) | Separate 16-case Basic operational validation, then derive a source-bound local package from immutable originals; no training or automatic learner enablement |
| Native evaluation | [`evaluate.py`](../v1/evaluate.py), [first confirmation](../evidence/run3/final64_confirmation_02/README.md), [second confirmation](../evidence/run3/second_confirmation_01/README.md), [browser confirmation](../evidence/run3/browser_confirmation_01/README.md) | Frozen paired schedules, complete qualified gameplay, success/return/tic accounting and reserved confirmation; historical confirmation launchers remain archived |
| Independent verification | [`evidence/`](../evidence/run3/) and its archived `verify_*.py` producers | Source/model/trace hashes, native sums and terminal predicates, replay reconstruction, separately computed comparisons |
| Monitoring | [`watch_training.py`](../v1/watch_training.py), [historical operational receipts](../evidence/run3/ops/) | Read-only admission, queue, qualification and gameplay statistics; retired cloud monitors remain archived, and counters never imply success |

The browser is the user interface to a native engine and Cadence runtime.
The measured AWS-backed demos did not run all inference and ViZDoom inside a
JavaScript/WASM browser tab. API/native checks and visual browser QA are distinct:
the September campaign recorded API/native checks, while connected visual
browser automation was unavailable. The repository refactor has its own
validation record; it must not retrospectively rename those checks as visual QA.

The single-version entry point is `v1.runtime.Adapter`; `brainlab.Student`
owns the model registry and adapter. Durable journal behavior moves from the
historical `v2.journal` dependency into `v1.journal`. Active imported bundles
live at `data/models/<safe_id>/bundle.json`; immutable original models retain
their own inventory and hashes. Historical `cadence-doom-player-v3/1`, interface
and protocol identifiers remain accepted compatibility identifiers. Derived
deployment copies explicitly bind the migrated runtime/new practice wave and
their original checkpoint/file identities. Historical practice packages are
not silently relabeled as new source-validated deployments.

## Exact sensory and motor boundary

The raw observation is **320×240 GRAY8 uint8 pixels**, including the rendered
HUD. The actor sees neither coordinates, map geometry, object/depth labels,
teacher choices nor evaluator-only native variables.

| Input port | Coordinates | Construction |
| --- | ---: | --- |
| `periphery` | 640 | Exact 20×32 rectangular area means over the whole current image |
| `fovea` | 384 | Exact 12×32 means over rows 48:192 and columns 32:288 |
| `visual_history` | 644 | Four past 10×16 coarse images, each with one validity coordinate |
| `executed_action_history` | 352 | Last 16 executed actions × (20 one-hot choices + actual duration + validity) |
| **Total** | **2,020** | Four complete named ports; missing, malformed or nonfinite inputs are refused |

Pixel features divide by 255, then use training-only mean/scale with a 0.05
scale floor and `0.2 * clip(z, -3, 3)`. A fixed unfitted normalizer is an explicit
control. The exact normalizer belongs to the bundle; restoring only the weights
is insufficient. History values are bounded consistently with the sensory
contract; action identity/validity scale is 0.2 and duration is `0.2*tics/4`.

Default visual lags are **1, 4, 16, 64 executed decisions**; the short-history
control is 1, 2, 4, 8. These are not raw engine-tic indices. A full four-tic
decision makes the longest default lag 256 tics. History resets at episode
boundaries and advances only after the proposed action actually executes.
It is explicit bounded external memory, not learned long-term recurrent memory.
An unanswered or refused query cannot advance history or silently reuse pixels.

Nine physical buttons define 20 fixed legal macros: noop; forward/backward;
left/right turn; left/right strafe; forward with either turn or strafe; USE;
fire; fire with either turn or strafe; backward-fire; forward-fire; weapon-next.
One macro is selected by argmax of 20 **unclamped, qualified settled scores**.
Each action requests four native tics, shortened only by actual terminal state.
There is no independent per-button threshold or hidden contradiction arbiter.
The score is a declared preference, not a calibrated probability or Q-value.

## Network, settlement and public repair

`scene` receives periphery plus visual history; `aim` receives fovea plus
executed-action history. Observer populations can read both current states and
exact prediction errors from preceding populations within **one coupled solve**.
Ordinary-state-reading controls use the same population arrangement without
error-readback edges. Depth 1 connects the policy to scene/aim; depths 2/3 add
one/two reflection populations before policy. The policy always has 20 patches.

| Width gene | Depth 1 scene/aim | Depth 2 scene/aim + reflection | Depth 3 scene/aim + two reflections | Total patches |
| --- | --- | --- | --- | ---: |
| Small | 16 + 16 | 10 + 10 + 12 | 8 + 8 + 8 + 8 | 52 |
| Medium | 32 + 32 | 20 + 20 + 24 | 16 + 16 + 16 + 16 | 84 |
| Large | 64 + 64 | 40 + 40 + 48 | 32 + 32 + 32 + 32 | 148 |

The total includes the 20 policy patches. Equal patch count does **not** mean
equal parameter count: depth, error reads and bypass genes change edges. The
initial depth-one sensory-skip designs had 61,120/94,720/161,920 edges; use each
bundle's inspected layout for another topology. The preserved ad9 and 9b97
actors each have 52 patches and 44,384 edges at depth three. `sensor_skip` controls direct
current-pixel policy inputs; `policy_history_skip` separately controls the
direct executed-action-history policy input. Both disabled forces policy input
through the latent pathway but still permits a constant bias solution.

The measured default numerical genes were float64, state bound 1, parameter
bound 4, parameter prior 0.4, initial scale 0.3, state prior 0.01 and tolerance
1e−6. Training usually budgeted 2,048 sweeps, queries 512. Larger budgets and
other priors/scales were explicit candidates; a refused query counted as a
failure. The 1,024-query-budget comparison preserved weights/tolerance and
showed that some apparently poor deep models had a numerical budget problem.

`Actor.choose` calls the module-level `query` helper, which calls
`Brain.settle` for the free action query. `Brain.observe_batch` receives
immutable ordered input/target pairs with `source="estimate"`; qualified,
accepted, nonduplicate admissions alone advance the training cursor. Its
common repair uses the batch mean objective and the pre-admission parameter
anchor. Batch size therefore changes the optimization transaction and anchor
schedule, even at matched presented examples. Qualification certifies the
declared numerical solve, not lower free loss, skill, retention or improvement.
Queries must leave the parameter snapshot unchanged. Detached weight lesions
exist only as diagnostics and are never deployed learning steps.

Topological recursion and useful recursion remain separate claims. Deeper
candidates can depend on their latent path without changing chosen actions
when visual inputs are permuted. The existing narrow probes do not establish
a gameplay benefit of residual readback; see [measured comparisons](EXPERIMENTS.md).

## Three kinds of targets, kept separate

**Finite bootstrap.** Teacher actions are privileged estimates, never native
returns. Whole episodes are split before row sampling; normalization uses
training frames only, and history is reconstructed from actual executed
actions. The centered target gives the selected action 0.76 and all others
−0.04. The offset control uses 0.6/−0.2 with the same 0.8 margin. Sampling is
uniform over available task/action groups, then rows within each group; this
is not uniform over episodes or necessarily over tasks. Frozen row identities
and actual presentation order are retained.

**Autonomous native feedback.** The record binds seed/task, episode and step,
actual action/outcome prefixes, pre-action raw hash, all four input ports,
executed action/transition, checkpoint and qualified/no-fallback provenance.
For every legal first action a fresh engine replays the exact prefix, checks
current pixels/history, executes that intervention for four tics, then uses
one frozen qualified Cadence actor until the horizon or native terminal. Any
refused or partial branch rejects the complete 20-coordinate context. Raw
native events/returns are retained separately from the target transformation.
This is simulator-derived counterfactual policy improvement; there is no new
scripted teacher label, discounted bootstrapped Q target, or multiplayer opponent.

| Contract | Horizon/units | Important boundary |
| --- | --- | --- |
| Original `native_action4_frozen_actor_continuation_v1` | Default Basic/navigation H36; Basic divisor 300; navigation divisor 1; supported horizon bound 4–560 | Historical bytes unchanged; old units cannot be silently relabeled |
| Audited long Basic contract | Tested H36/144/300; conservative native return range `[-6H,106]`, divisor `max(6H,106)` | Pins installed cfg/WAD; +106 kill, −5 shot and −1 living tic audited from assets |
| Long navigation contract | Tested H144/H600; native range `[-0.0001H,1]`, divisor 1 | Separately versioned to allow H600; scenario goal success is distinct from full-map native exit |
| Visible novelty diagnostic | Native and bounded visual novelty recorded separately | Explicit utility gene, not native reward; only native gameplay could promote |

For native-ranked preferences, winners within tolerance 1e−12 share unit
probability and the target is `0.8*(p_best - 0.05)`. All 20 actions tied means
no lesson. This hard rank discards advantage magnitude: shrinking a novelty
bonus need not shrink the update at all. The feedback values mean “this first
action, then this frozen continuation”; changing the learner can invalidate
that continuation assumption. Cached witnesses may be reused only with their
source, complete native vector, order and contract intact.

**Own-score rehearsal/blend.** The experimental
[`retained_targets.py`](../v1/retained_targets.py) freezes qualified current
scores on actual experience. Basic own-score anchors are estimates, not teacher
truth or native witnesses. New target genes use
`y = (1-eta)*frozen_scores + eta*native_rank`, with η=0/0.1/0.25/1 explicitly
compared. Endpoints are exact, dimensions/bounds finite, inputs immutable.
All arms use the same frozen actor scores, never a moving candidate target.
This is an isolated experiment, not a claim that ongoing Lab practice already
uses the blend. Own-score targets do not guarantee zero parameter movement.

## Practice, promotion and tasks

The gameplay actor and mutable candidate have separate ownership. A learner
worker labels durable executed records, makes public repairs and evaluates
candidates; it cannot race an actor query or edit the active champion in place.
The deployed practice wave binds original retention founder, starting champion,
frozen continuation, bootstrap replay, native contract, collection gene and
source identities. Imports must preserve that package; importing a later
checkpoint cannot silently redefine the retention founder or revert H144 to H36.

The original practice defaults were eight new plus eight old examples per
repair, replay capacity 512, queue capacity 64, and a four-repair candidate
lifetime. One- and 16-repair lives, more old replay, and collection strides
1/32/64 were declared comparisons. The old mixture alternates frozen bootstrap
rows and acquired replay once available; individual updates are not inherently
task-stratified. Backpressure preserves selected evidence rather than dropping
it. An accepted update means numerical admission; a promotion additionally
requires native behavior gates. Partial candidates/pending rows and rejected
models remain durable. Promotion transfers a verified bundle at a safe actor
boundary; rollback restores a retained champion with matching observation and
practice identity.

The migrated local deployment protocol requires 16 scheduled Basic episodes,
at least 12 native successes, complete qualified execution without fallback,
and unchanged bundle/source/platform identities. This is an operational
compatibility check on the local native engine, separate from the historical
64-seed scientific confirmations. Preparation uses its verified receipt to
derive a new package; it does not modify the original winner or automatically
start gameplay/learning.

Repeated development checks compare candidate with both original founder and
current champion: complete native episodes, every query qualified, no fallback,
no lost retained success and no task-mean return decrease. The navigation
comparisons additionally require strict native navigation gain and a complete
four-update life. Reserved Basic confirmations used their separately frozen
compound criterion: at least 58/64 wins, at most five percentage points success
loss, and a positive paired 95% native-return interval, with complete qualified
execution. Development gates select; reserved tests confirm. Repeatedly tuning
on a reserved set would spend it as development data.

| Task | Native success boundary | Status of evidence |
| --- | --- | --- |
| Basic | Kill the one-hit target before the native 300-tic timeout | Confirmed restricted skill/improvement |
| Navigation (`my_way_home`) | Native goal/armor scenario completion, 2,100-tic timeout | Latest matched collection 0/32; no competent policy |
| Doors | No-monster E1M1 native exit | Finite teaching/task implementation; no confirmed student skill |
| Survival/health survival | Survive declared 1,050-tic native horizon | Implemented curriculum; no confirmed competence here |
| Combined | E1M1 native exit with declared minimum kill | Implemented curriculum; no confirmed student completion |
| Full maps | Native alive exit before timeout on unmodified IWAD | Train E1M1–3, development E1M4, held-out E1M5–6, reserved extension E1M7–9; no general-player result |

Native simulated tics, wall time, deaths, timeouts, exits and scenario goals
remain separate fields. A process cap, query refusal or externally cut-short
episode cannot be treated as native success. A fresh random seed may reproduce
an earlier visible start; initial-frame overlap is measured independently.

## Dependencies, evidence and checks

The active [`core_runtime.py`](../v1/core_runtime.py) loads a hash-pinned
Cadence source copy from [`runtime/`](../runtime/), preserving the implementation
that owns these checkpoints. It verifies the complete module set and refuses
an already imported different Cadence package. A `CADENCE_SRC` override must
match that same manifest; it cannot silently follow newer sibling-repository
code. Native ViZDoom uses Python/Torch/NumPy, with Pillow/aiohttp supporting
the Lab. The historical matched CPU hosts pinned Python 3.11.16, Torch
2.14.0+cpu, NumPy 2.4.6, ViZDoom 1.3.1 and Pillow 12.3.0. The active
[`requirements.txt`](../requirements.txt) pins the local application packages
separately, using Python 3.12.6 and NumPy 2.5.3; it deliberately does not install a newer
`cadence-net` over the preserved core. Different package/platform combinations
need their own operational validation. Float64 GPU repair used an A10G and separately
recorded CPU/CUDA discrepancies. WADs, scenario cfg/WAD bytes, executable,
`vizdoom.pk3` and Python extension hashes matter in addition to package version.

A model bundle binds snapshot, observation/action contract, normalizer,
genome, target contract, query budget, implementation and SHA256 identities.
Deployment adds native task and platform evaluation metadata. Each experiment
freezes its source/core hashes, actor files, task/engine assets, seeds/order,
genes, resource caps, failure policy and comparison rule before execution.
Native reconstruction checks prefix outcomes, raw pixels, encoded history,
executed actions and reward/tic sums. Source hashes are especially necessary
because the active checkout changed during the campaign. Namespace migration
must preserve historical bundle/schema compatibility and frozen receipt bytes;
new source paths alone cannot claim historical binary identity.

Multiprocessing uses `spawn`, persistent bounded actor pools and one BLAS/OpenMP
thread per native worker. Each branch still gets a fresh engine and reset
history. Equivalent scheduling must reproduce action/native witnesses after
removing timing fields. Cloud jobs have per-episode/life limits plus external
process-group caps; stopped-instance disks and AWS-to-AWS verified archives
preserve all outcomes. Bulk artifacts over about 100 MB stay on AWS; local
evidence contains compact sources, fixtures, hashes and summaries, catalogued
in [DATA_CATALOGUE.md](../../../DATA_CATALOGUE.md).

The active and historically archived test families exercise distinct failure
boundaries. Campaign-specific tests remain with their archived producers when
the corresponding launcher is not part of the active package:

- `test_interface`, `test_brain`, `test_training`: dimensions/bounds, causal
  acknowledgments, distinct settled outputs, topology/normalizer restoration,
  whole-episode leakage, immutable source arrays and deterministic sampling.
- `test_native_feedback*`, `test_tasks_evaluate`: exact prefix/selected-action
  custody, native time/reset/terminal rules, engine initialization cleanup,
  asset drift, changed contracts, unqualified continuations and whole-context
  refusal. Historical original-H36 contracts remain controls.
- `test_practice*`, `test_experience_sampling`, `test_lab_deployment`,
  `test_runtime`: replay units/identity, single mutable ownership, restart and
  pending-record custody, rejection/rollback/promotion gates and portable
  practice-wave imports. These cannot prove future learning success.
- `test_retained_targets`, `test_native_blend_campaign`,
  `test_retention_margin_campaign`, `test_navigation_collection`: exact
  controls, target endpoints/bounds, immutable plans, complete anchor coverage,
  explicit repeats and unique actual-context selection without fabricated rows.
- Confirmation and `verify_*` tests: paired schedules, all-attempt denominators,
  trace/source/checkpoint hashing, native success predicates and independently
  recomputed statistical comparisons. Passing integrity is distinct from
  passing a skill or retention gate.

After the namespace migration, use the active repository's test entry points
from `doom-lab` (for example `python -m unittest discover -s v1 -t .`). The
migration's actual pass/fail record belongs to its own closeout; older test
counts describe their frozen source versions only.
