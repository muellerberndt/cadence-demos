# Doom experiment record

This is an evidence guide, current through 2026-09-30. The active
implementation is called `v1`; September 29 receipts, schema identifiers,
source freezes and remote directories retain their original `v3` names. A
directory rename does not rerun an experiment or change its measured result.
See [components](COMPONENTS.md) and [the model guide](MODELS.md).

The strongest result is **confirmed improvement on ViZDoom Basic through native
self-practice**. Two selected descendants passed separate 64-seed confirmations
against their original founder. Navigation, connected full-level play, reliable
continuing browser improvement, and a gameplay advantage from recursive
readback remain unestablished. More patches, admissions, teacher agreement or
qualified queries have repeatedly failed to imply better native play.

## Full-game preparation, then finite Doom-baby bootstrap

The early full-level geometry teacher eventually completed an E1M1 exit at
skill 2 in 2,838 tics, with four kills and 96 health. It used privileged map
information; this was teacher feasibility, not student competence. Following
the owner's clarification, full-level teacher expansion stopped. Existing
finite demonstrations seeded the Doom-baby comparison; later practice acquired
new labels from native simulator interventions on the student's own states.

The [initialization audit](../evidence/run3/initialization_repair_20260929/README.md)
restored scenario-configured warm-up and private per-engine configuration.
The earlier suspicion that short demonstrations contained identical,
uninitialized Basic monsters was not supported: both tested initialization
variants produced 16 distinct Basic initial images. The corrected finite
collection contained 16 successful Basic teacher episodes/57 transitions and
eight successful navigation episodes/520 transitions, plus bounded existing
door evidence. These success counts describe teaching, not autonomous play.
Old initialization artifacts were retained and excluded from the corrected
bootstrap. A separate native `_vizdoom` first-start directory race was fixed
before the successful parallel screen; earlier failures remain recorded.

Twelve CPU bootstrap lives compared small/medium widths, depths 1/2/3 and two
initialization seeds on the same finite, task/action-balanced stream. Each
accepted 64 public repairs: 768 total in 1,268.9 s. The
[first native screen](../evidence/run3/baby_screen_02/README.md) completed 104
episodes and 28,003 qualified queries across those lives and an untrained
control. Five candidates won 4/4 Basic games; navigation's best result was 1/4.
The selected small depth-three founder `307604…` later won 13/16 on expanded
Basic development seeds versus its untrained counterpart's 6/16. These were
selection results. Navigation traces included 502 repeated forward actions
against a wall and a 525-decision left/right oscillation with eight raw images.

## Feedback alignment and the confirmed Basic improvements

An earlier restricted-player correction compared held-action feedback against
an initial action followed by frozen-champion continuation, crossed with one
versus four updates before gating. It made 64 repairs, 768 counterfactual
branches and 1,312 evaluation episodes, with zero promotions. Linux correctly
refused archived Mac contexts whose raw frames did not reproduce. Replacing
that fixture with exact Linux experience repaired custody, not competence.
The [retained result](../evidence/run3/receipts/feedback_02/RESULT.md) records both failures
and the aligned experiment.

The 20-action bootstrap founder then ran three Basic practice lives with
candidate lifetimes 1/4/16 repairs. They accepted 15/16/16 repairs and promoted
none. A selected rejected checkpoint improved return on development cases but
exchanged one retained win for one new win. Exact reconstruction reproduced
its checkpoint and all 316 repair sweeps; it remained selection evidence.

Delayed kills often occurred after 146–291 tics. A matched incoming-experience
comparison therefore reused 128 actual contexts across ten founder episodes,
varying native horizons 36/144/300 while holding continuation, order and replay
fixed. H144 processed 128 informative contexts, accepted 16 repairs and selected
its first four-update candidate, `ad9…`. H300 produced byte-identical first-four
update weights at higher feedback cost; H36 did not promote. Later H144
candidates scored 6/8, 7/8 and 2/8 and were rejected. Continued training was
not monotonically beneficial.

| Frozen Basic comparison | Founder wins | Candidate wins | Mean native-return gain | Paired 95% interval | Interpretation |
| --- | ---: | ---: | ---: | --- | --- |
| [First confirmation: ad9](../evidence/run3/final64_confirmation_02/README.md), seeds 1400000000–63 | 61/64 | 63/64 | +90.390625 | [43.515625, 136.78125] | Prespecified primary and competency/retention gates passed |
| [Second confirmation: 9b97](../evidence/run3/second_confirmation_01/README.md), seeds 1400100000–63 | 53/64 | 64/64 | +93.421875 | [44.296875, 145.6875] | New actual experience plus selected replay ratio; gates passed |
| [Browser candidate 7613 versus starting ad9](../evidence/run3/browser_confirmation_01/README.md), seeds 1400300000–63 | 64/64 | 59/64 | +50.390625 | [9.09375, 89.0] | Failed retention: five lost wins, no gains |

All episodes and queries in these confirmations completed without fallback.
The first result establishes improved return, not a statistically established
increase in win rate. The second used a changed replay recipe after two
unchanged-recipe repeats failed to promote within 64 contexts; it is not an
exact replication. On the second set ad9 also won 63/64, and the 9b97-minus-ad9
return interval crossed zero. There is no demonstrated efficiency superiority
of 9b97 over ad9. Each 64-seed confirmation had 60 distinct initial images;
unused seed integers do not imply 64 independent hidden-state configurations.
The first confirmation's open-journal preflight refusal remains in its own
receipt; no gameplay occurred in that failed attempt.

Browser candidate 7613 illustrates why native return alone cannot select the
champion: it was faster and scored better on average, but lost reliability.
An integrity verifier passing means the experiment is reproducible; it does
not mean its gameplay gate passed. The latest recovered browser wave,
`baby_04`, completed 98 accepted updates/1,568 presentations from 801 processed
selected records. All 24 gates rejected loss of a retained founder success;
there were zero promotions. Its two-hour guard paused normally. The ad9
champion, partial candidate, 512 replay rows, three unused new rows, source
manifest, complete journals and referenced candidate traces survived recovery.

## Depth, capacity, exposure and batch size

The architecture comparisons kept one common Cadence patch rule. Depth meant
coupled state/error readback, not a separately trained motor network. Direct
pixel and direct action-history policy connections were independent genes.
Removing only the pixel connection still left a 352-coordinate action-history
bypass. Later forced-depth candidates removed both.

| Comparison | Measured outcome | Limit |
| --- | --- | --- |
| First six CUDA width/skip lives | 384 qualified updates; small direct-pixel model 13/16 Basic, no-pixel counterpart 3/16 | Removing a useful direct path did not teach the deeper path |
| Small depth-three scale/prior genes | All prior 0.04 arms refused the first batch at the original 2,048-sweep budget | Refused lives were failures, not missing data; no tolerance relaxation |
| Both policy bypasses removed | Stable scale 0.3/prior 0.4 scored 9/16; scale 1 scored 5/16 | Earlier weak-prior models had many refused episodes |
| Fixed 256-admission exposure, small/medium × depth 1/3 | Intermediate depth-one 10/16→4/16 and depth-three 7/16→4/16 from 64→128 admissions | More exposure can erase native competence |
| Same final snapshots, query budget 512→1024 | Small depth-three reached 16/16; medium 10/16, all queries qualified | First refused contexts needed 521/542 sweeps; convergence was a separate limitation |
| [Batch64/128, same 4,096 presentations](../evidence/run3/gpu_batch_development_16_08/README.md) | Small batch64 15/16; large batch64 5/16; both batch128 0/16, turning left throughout | Batch64 made 64 admissions, batch128 32; grouping changes repair objective and anchor schedule |

Causal probes qualify the apparent deep results. In the
[early paired probe](../evidence/run3/recovered_causal_12_01/README.md), deleting
latent or residual reads changed 0/12 actions while deleting direct pixel
reads changed 12/12. In the
[forced-depth probe](../evidence/run3/forced_deep_causal_01/README.md), deleting
latent readback changed 12/12 actions for the stable forced model, but rotating
visual inputs with motor history held fixed and deleting residual reads each
changed 0/12. The later 16/16 development model showed the same important
distinction in [its recorded probe](../evidence/run3/forced_deep_causal_02/):
dependence on a latent pathway is not evidence that it performs useful visual
recursive inference. These detached lesions are narrow sensitivity tests, not
trained controls or native gameplay ablations. No altered weights were deployed.
The proposed on-policy causal probe of the small batch64 model was staged but
never launched before the interruption; it has no result.

## Navigation credit, retention and changed-policy experience

The [trace audit](../evidence/run3/navigation_credit_audit_01/README.md) found only
45 goal-containing 36-tic future windows among 25,057 actual contexts from 52
development episodes. Forty-seven episodes failed. Longer credit and useful
exploration are separate requirements: a longer fixed failed continuation can
still supply tied values.

The [visible-novelty comparison](../evidence/run3/navigation_novelty_01/README.md)
used 32 frozen actual contexts from four complete ad9 episodes. Native H36
returns tied everywhere; bounded visible novelty made 21 contexts informative,
producing two repairs and five pending examples. The candidate lost Basic wins
(4/8 versus ad9's 8/8) without navigation gain. Novelty can reward turning;
neither an intrinsic score nor a lower training loss could promote a model.

The [learning diagnosis](../evidence/run3/learning_diagnosis_01/README.md) found
only **one Basic bootstrap anchor across those two updates**. Approximately
96.1% of squared parameter displacement was in direct input-to-policy weights.
Hard ranking also erased novelty's magnitude: dividing its bonus by 100 left
all 21 preference targets unchanged. Thus reward weight was not update-size
regularization in that fixture. No target-normalization cancellation defect
was established. Old teacher labels also need not preserve an improved
actor's current predictions.

The [cached 2×2 control](../evidence/run3/retention_margin_01/README.md) exactly
reproduced the adverse original admissions and native traces before testing
task-stratified old replay and a smaller new preference margin:

| Old eight rows | New margin | Basic wins/8 | Navigation wins/4 |
| --- | ---: | ---: | ---: |
| Original uniform | 0.8 | 4 | 0 |
| Original uniform | 0.08 | 6 | 1 |
| Six Basic, one doors, one navigation | 0.8 | 5 | 0 |
| Six Basic, one doors, one navigation | 0.08 | 5 | 1 |

All four lost retained Basic successes and were rejected. They were two-update
partials, never promotion-eligible complete lives. The 48 native episodes and
8,887 qualified queries all verified.

The [native horizon diagnosis](../evidence/run3/navigation_horizon_01/README.md)
reused exactly those 32 contexts and frozen ad9 continuation. H36/H144/H600
produced 0/2/14 informative mixed goal/no-goal contexts. All 1,280 new branches
and 90,254 continuation queries completed; 1,920 shorter-prefix comparisons
matched exactly. H600 exposed goal-reaching alternatives in an originally
failed episode, but informative lessons came from only two starts. This is
evidence of delayed credit, not a trained navigation policy.

[Own-score rehearsal](../evidence/run3/own_rehearsal_02/README.md) froze 32 actual
Basic contexts from 226 verified stopped-Lab records across six episodes.
Each was reconstructed in a fresh native engine and queried with unchanged ad9.
The targets are that actor's own scores, explicitly estimates. The
[four-arm native blend](../evidence/run3/native_blend_02/receipt.json) then used
the 14 informative H600 lessons twice and all 32 Basic anchors once, in four
public repairs of seven new plus eight old rows. Every arm started at ad9:

| Native preference blend η | Basic wins/8 | Basic mean return | Navigation wins/4 | Squared parameter drift |
| --- | ---: | ---: | ---: | ---: |
| 0, own-score-only control | 8 | −32.125 | 0 | 0.00011648 |
| 0.1 | 8 | −29.125 | 0 | 0.00332801 |
| 0.25 | 8 | −33.25 | 0 | 0.01836173 |
| 1, full native rank | 8 | −42.625 | 0 | 0.27583761 |

All 16 repairs and 48 native episodes completed; all 9,252 action queries
qualified. No arm passed strict native improvement/retention. η=0 was a real
control, not assumed to be a no-op: the common repair objective still moved
parameters slightly. The
[acquisition probe](../evidence/run3/native_blend_02/acquisition.json) found that
η=1 selected the H600-best action on 13/14 taught contexts versus ad9's 0/14;
η=0.1 and 0.25 each selected 1/14. Fitting those lessons did not transfer to
the full navigation tests. Cached branch values assume subsequent **ad9**
actions, whereas changing global parameters changes future actions too.
This experiment changed both data/target source and rehearsal relative to
novelty; it cannot isolate rehearsal as the cause of preserved Basic wins.
An earlier engine-hash-dictionary preflight refusal is retained separately as
`runs/native_blend_01`; it performed no training.

Finally, the prospectively frozen matched collection ran ad9 and η=1 on 16 new
starts each. [Recovery verification](../evidence/run3/recovery_20260930/navigation_pair_01/independent_verification.json)
reconstructed all **32 complete episodes, 16,800 qualified decisions and 67,200
native tics**, including every saved pixel, action and reward. Both actors
scored **0/16**. The 512 selected actual contexts are retained, with each
actor's own frozen continuation identity. No feedback or training has consumed
this collection. It supplies changed-policy experience, not a successful
navigation checkpoint.

## Parallelism

Float64 A10G benchmarking measured same-host repair speedups of
4.50×/6.73×/10.20× for 52/84/148-patch brains; maximum post-repair CPU/CUDA
output difference was 1.24e−6. This does not claim bitwise identity, faster
queries, or those speedups over the newer C7 CPU. Independent CUDA lives and
CPU-native workers were run concurrently with bounded threads and process
groups. [Feedback scheduling](../evidence/run3/feedback_parallel_20260929/README.md)
measured 5.700 s for a cold 32-worker, four-context batch versus 53.641 s for
the serial reference; 48 workers were slower. The later
[context-pipeline comparison](../evidence/run3/pipeline_benchmark_01/README.md)
yielded only 1.094× under concurrent load. Scaling claims remain workload-specific.

Bulk corpora, rejected candidates and complete run directories stay on AWS; the
authoritative artifact locations are in [DATA_CATALOGUE.md](../../../DATA_CATALOGUE.md).
Historical source hashes remain evidence identities.
