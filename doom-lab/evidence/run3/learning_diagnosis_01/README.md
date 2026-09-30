# Learning diagnosis from frozen Doom experiments

The navigation experiment gives concrete evidence of underprotected Basic
retention and overconfident novelty labels. It does **not** establish a Cadence
derivative bug or show that either issue explains every unsuccessful Basic
practice life. This audit admitted no parameters, created no native engines,
changed no application or core source, and used no new teacher data.

`analyze.py` reads immutable AWS artifacts and prints `receipt.json`. It joins
native example identities back to their actual fixture records, counts the
presentations in every recorded admission, compares existing snapshots, and
runs 72 public unclamped queries. The full artifacts remain on AWS under
`/home/ec2-user/doom-v3-20260929`; only this small receipt is local. The query
phase took 8.43 seconds, every query qualified, and both snapshots remained
byte-identical before and after querying.

## What actually went wrong in navigation

The replay pool is 36 Basic, 66 navigation and 90 doors examples. Uniform
sampling from that pool is not uniform task retention. During the two novelty
repairs, only **one of 32 presentations was Basic**: the first batch contained
10 navigation and 6 doors rows; the second contained 14 navigation, 1 Basic
and 1 doors row. After the first batch, half of the eight old slots came from
earlier native navigation examples, further reducing bootstrap retention.

The resulting `f7b691` candidate lost four of the eight Basic development
wins held by its `ad9` starting model. On the 36 existing Basic bootstrap
training inputs, 21 actions changed and teacher agreement fell from 27/36 to
17/36. This latter measurement is a forgetting diagnostic on training inputs,
not a native competence estimate. The existing native experiment is the
behavioral evidence. Navigation remained 0/4 in its development gate.

The two repairs changed shared parameters throughout the network. Direct
input-to-policy weights account for about 96% of total squared parameter
displacement, including biases in the denominator. Their squared displacement
was 0.250206, compared with 0.001960 for latent-state-to-policy and 0.001864 for
residual-to-policy weights. The visible observer-like Cadence system still
uses bounded patch state, input boundaries, exact residual readback, public
settlement witnesses and feedback repairs, but these updates predominantly
altered its shared direct sensory/action-history policy path. No task-specific
parameter isolation or guaranteed preservation is supplied by `observe_batch`.

All 32 native navigation vectors were exact ties. The novelty term broke ties
in 21 contexts, despite no measured native goal advantage. Converting these
utilities to hard maximum-action preferences removes utility-gap magnitude:
for `k` tied winners the winning margin is `0.8/k`, regardless of how small the
nonzero novelty advantage was. **All 21 target vectors stayed exactly equal
when the recorded novelty bonus was divided by 100.** Reducing beta from .05
to .0005 would therefore produce the same lessons on this fixture. A bounded
novelty reward is not a bounded or confidence-weighted policy update.

## What does not explain the other failures

Basic-only practice always had eight new Basic rows, followed by four old
native Basic rows once replay was warm. Its old bootstrap Basic counts were:

| Experiment | Bootstrap Basic counts in repairs 1–4 | Native Basic counts in repairs 1–4 | First gate wins |
| --- | --- | --- | --- |
| Original H144, later confirmed `ad9` | 1, 1, 0, 1 | 8, 12, 12, 12 | 8/8 |
| Fresh life 0, old8 | 2, 0, 0, 0 | 8, 12, 12, 12 | 4/8 |
| Fresh life 1, old8 | 0, 1, 2, 0 | 8, 12, 12, 12 | 6/8 |
| Fresh life 0, old24 | 3, 2, 4, 1 | 8, 20, 20, 20 | 2/8 |
| Fresh life 1, old24 | 5, 1, 1, 3 | 8, 20, 20, 20 | 8/8 |

The old8 controls exactly reproduce the corresponding original life counts.
The old24 winner and loser each received ten bootstrap Basic presentations in
their first four repairs. Coverage alone consequently cannot explain that
outcome difference. Context distribution, label choice and shared-parameter
projection remain material; more replay is not a universal fix.

Bootstrap and native targets use compatible centered coordinates: a unique
winner is .76 and every loser is -.04. Native ties intentionally divide the
positive probability among winners; every target sums to zero. Native reward
normalization is used before ranking, not erroneously mixed as raw action
scores with bootstrap labels. The current snapshot normalizer and observation
contracts remain shared. This audit found no new/old numerical target-scale
implementation mismatch. The weakness is what the ranked labels assert, and
how little old behavior they protect, rather than an accidental units mix.

The common core uses mean per-example energy plus one parameter anchor at the
start of each batch. More examples change the average objective; they do not
multiply its force. Each later batch resets its parameter anchor. Consequently
more admissions, more presentations and a larger batch are distinct resource
and learning trajectories. The worsening forced-depth exposure results cannot
be repaired by assuming extra accepted admissions imply acquired competence.
Earlier causal receipts already show weak input-dependent deep computation;
structural depth or latent-path dependence does not establish a useful
recursive contribution. This audit does not identify an exact solver defect.

The frozen continuation correctly defines values for one alternative action
followed by a particular fixed Cadence policy. Those are not optimal Q values.
They cannot expose a navigation improvement requiring several coordinated
deviations when the continuation itself does not perform them. A short horizon
also misses delayed goals. Retention repair and native navigation credit are
separate problems; the parallel H144/H600 credit diagnosis addresses the latter.

## Selected follow-up: cached retention and margin comparison

Root review selected a bounded 2×2 comparison that replays the **same two**
navigation repairs from `ad9`, using the existing 32 contexts and their
native/novelty vectors. The unchanged uniform/.8 control must reproduce both
original admitted checkpoint hashes, ending in `f7b691`, before variants run.
The two independently declared genes are:

- Original uniform old replay versus six Basic, one doors and one navigation
  bootstrap rows in every eight-row old half. The latter deliberately changes
  retained capacity and replaces the control's later native replay mixture;
  it is not merely a different random seed or a perfectly source-matched arm.
- Intrinsic preference margin .8 versus .08, applied when intrinsic examples
  are created and preserved if those examples later replay. Bootstrap target
  coordinates remain .76/−.04. Original native/novelty vectors and the original
  full-margin target stay in each example's witness.

All four arms retain eight new/eight old rows, the same new contexts, initial
checkpoint, public repair rule, two admissions, normalization and frozen
continuation. Every row identity is frozen before training. Each arm ends with
five unadmitted pending examples; no extra rows are manufactured to finish a
life. Basic bootstrap exposure is one in the uniform arms and twelve in the
stratified arms. No teacher expansion or feedback engines are required.

Use the same complete native Basic8/navigation4 development episodes and
unchanged retention requirements. Count both partial lifetimes honestly;
neither two-repair candidate is automatically eligible for deployment under
the four-repair promotion rule. A useful result preserves every `ad9` Basic
success and improves navigation native success/return. Merely restoring Basic
while navigation stays 0/4 supports the retention mechanism but is not the
requested skill acquisition. Keep beta and the original native/novelty
utility calculation unchanged, so the margin factor changes the estimated
teaching target rather than silently redefining native reward. The 2×2 design
separates retention from target strength and records their interaction. The
executable source is `../../retention_margin_campaign.py`; frozen AWS run
`runs/retention_margin_01` has a 900-second process-group cap and at most sixteen
native evaluation workers. Three small fixture tests check task coverage,
target scaling, unchanged feedback, refusal and adverse-promotion guards.
The completed [comparison](../retention_margin_01/README.md) reached a goal in
one of four navigation episodes with the smaller margin, but none of the arms
preserved all Basic successes. Thus retention sampling and target strength
matter, while neither tested change solved the requested combined capability.

The first two analyzer attempts stopped on journal-schema assumptions before
any query: native examples use an `example` payload rather than a fixed event
kind, and their task must be joined from fixture hashes. The corrected audit
does those joins explicitly. No model, target admission or gameplay was
consumed by either failed attempt.
