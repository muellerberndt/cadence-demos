# Frozen current-policy rehearsal preparation

Prepared **32 actual ad9 Basic contexts across six episodes**, selected evenly
from the 226 stopped-Lab records whose native feedback had already verified
their executed experience. Selection follows immutable queue chronology,
without selecting by reward. There were 290 queued records in total; the
remaining64 without joined successful feedback were not silently treated as
verified experience.

For each selected record, a fresh native engine replayed its complete actual
action prefix, reproduced every recorded transition, reproduced the exact raw
pixel hash and all four encoded input ports, and reproduced its qualified ad9
action and executed transition. These32 reconstructions used2,580 native tics.
The32 Basic queries and32 additional queries on the existing navigation
fixture all qualified; the actor snapshot stayed byte-identical throughout.
Preparation took17.30 seconds and performed **zero parameter admissions**.

The rehearsal targets are the exact frozen actor's own unclamped score vectors,
marked `source="estimate"` and
`target_origin="frozen_qualified_own_policy_scores"`. They are neither native
reward targets nor teacher truth. They preserve the behavior of a particular
Cadence model, with its bounded states, sensory/history ports, coupled residual
readback and publicly qualified settlement. They are a candidate retention
mechanism, not a guarantee against forgetting under later shared repairs.

The actor checkpoint is
`ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc`.
Its detached artifact SHA is
`844503dcdce34a253dcb3ba2689b7cd042a338b5bfd381684dfcf5ffc3237dd9`,
identical to the navigation fixture's original actor artifact. Source manifests,
wave/package hashes, engine executable, common-core identity and all immutable
journal file hashes were checked. A later native-blend preflight additionally
binds the original navigation actor artifact/preprocessing, asserts every
navigation task identity, and rechecks all64 stored score vectors through
independent public queries before training.

AWS artifacts remain under
`/home/ec2-user/doom-v3-20260929/datasets/own_rehearsal_02/`:
`rehearsal_pool.json`, `navigation_scores.json`, `frozen_actor.json`,
`freeze.json`, and `receipt.json`. Only compact receipts are local.
The stopped source is Lab `baby_02`, source-manifest SHA
`a45f3769684ac2e16f798403d1c7e0a420c4ebdc379d4298f0f1e2991c18bdda`.
No live Lab files or controls were changed.

The first attempt refused before querying because the browser record stores a
complete task specification, while its selection predicate expected the name
string. The successful attempt compares the normalized complete Basic task
object. Failed source and the pre-query refusal remain in
`code/own_rehearsal_01` and `datasets/own_rehearsal_01`; the corrected source is
`code/own_rehearsal_02`.

`../../retained_targets.py` provides the separately declared convex target gene
`y=(1-eta)*frozen_ad9_scores + eta*native_rank_preferences` for
eta0/.1/.25/1. Both endpoints preserve their source vectors exactly; finite
shape/state bounds are enforced, all-native ties skip, and no clipping or
private weight update occurs. The helper labels the blend as an estimate,
preserves the original native vector and full-rank preferences, and never
normalizes current scores to zero mean. Three focused tests cover endpoints,
convex displacement/bounds, unchanged inputs, ties and invalid evidence. The
authorized follow-up experiment is recorded separately under
`runs/native_blend_02`; this preparation itself admitted no parameters.
