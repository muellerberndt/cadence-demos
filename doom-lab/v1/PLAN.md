# Doom Lab V1: the Doom baby and its path to full gameplay

**Final goal.** A patch-net equilibrium brain that is more scalable, more capable and more efficient than a transformer. Every Cadence result is measured against that goal at matched information, matched task and a declared resource model. The Amen jungle composer is the first test platform.

**Principles.** The main hypothesis stays: a brain that settles in global equilibria. The building block stays as simple as possible, like in nature, and every part of the brain answers with a settled state of that same patch rule; a feed-forward readout or a copied input is a baseline, never a result. Natural evolution is preferred to design: any parameter that looks designed is a gene, picked by selection against the hand-set value, which stays as the control. Within a life only the patch rule learns; across lives the genome evolves.

The implementation is `v1`; schema strings and AWS paths inside bundles and
receipts retain `v3` as exact identifiers. The immediate objective is a
bootstrapped Cadence brain that acquires skills from its own experience.

The measured starting point is two confirmed Basic-combat descendants (ad9 and
9b97), intact training/evidence and 512 verified new navigation contexts.
Navigation collection scored 0/32; reliable continued improvement and useful
recursive depth remain open. The latest browser wave accepted 98 updates but
promoted no candidate. See [experiments](../docs/EXPERIMENTS.md)
and [models](../docs/MODELS.md).

Next execution steps, retaining the original priorities:

1. Retain the validated V1 demo as the frozen baseline: Mac operational checks
   passed (ad9 16/16; 9b97 15/16), and original winner files remain immutable
   and locally available. Revalidate after future source/platform changes.
2. Label the recovered matched navigation experience using H600 native feedback
   under each actor's own frozen continuation. Keep all ties and failed branches.
3. Compare bounded common-rule learning lives with actual Basic retention replay;
   assess complete navigation episodes and all retained skills before promotion.
4. Confirm any new skill on untouched seeds, then add doors, survival and memory
   comparisons, followed by connected levels and reserved-map transfer.
5. Measure whether deeper state/error readback contributes to decisions and new
   skill acquisition. Topology, parameter count and qualification are insufficient.

The immediate deliverable is a **Doom baby**: a Cadence deep recursive
settlement brain bootstrapped with basic playing competence, then acquiring
more competence through autonomous gameplay. Broader full-game mastery remains
the long-term task; it is not a prerequisite for testing whether this baby can
learn for itself.

The official application is `cadence-demos/doom-lab`. The V1 Lab is the default
app on8666, with model import, current champion and controls. Stage candidates
with isolated runtime data on8667, then promote only the verified result.
A schedule is not evidence that learning worked; record actual outcomes.

## What the brain is

Every decision comes from a qualified, unclamped Cadence equilibrium. Add
**two and three observer levels**, each reading the preceding population's
current states and exact prediction errors within the same coupled solve.
Do not simulate depth with a chain of completed predictions. Do not add a
feed-forward motor network, a geometry controller, a hidden teacher fallback,
or a separate optimizer. Only the public common repair rule changes relations.

The initial design had one observer level. The implemented candidate family
now supports depth1/2/3 at matched52 and84 total processing patches, with148-patch
GPU candidates also tested. Topology depth does not by itself establish useful
recursive computation. Report edge counts as well: matched patch
count is not matched parameter count. Compare direct sensory skips with a
no-skip control on the leading topology. An ablation must measure whether the
deep path contributes to behavior. A deep diagram alone is not a result.

The first causal probe found weak recursive drive and near-linear tanh operating
ranges. A second frozen six-arm GPU comparison therefore holds small depth3,
no direct current-pixel policy skip and the original bootstrap data fixed,
while comparing initial scales0.3/1/2 and parameter priors0.4/0.04. These are
explicit candidate genes; the original0.3/0.4 remains the control. All use64
public repair admissions and the same example order. Native behavior and causal
ablations decide usefulness, not greater nonlinearity by itself.

The next exposure comparison freezes four candidates: small/medium × depth1/3,
initial scale0.3, repair prior0.4, both direct policy bypasses disabled, and
256 public admissions per candidate. Four concurrent CUDA learners use the
same finite dataset and example order; no further expert collection is involved.
Checkpoint every32 admissions so native development can separate insufficient
exposure from saturation or forgetting. Keep the original64-admission results
as historical controls, and use each new life's own64-admission checkpoint for
the matched exposure comparison. The existing balanced sampler advances its
row-choice RNG according to total draw count, so an8-epoch run does not share
the exact row prefix of an earlier2-epoch run. Each job is bounded at2,400seconds, with external process-group
termination. Compare native Basic/navigation outcomes and qualified queries;
teacher agreement alone does not select a deployment.

The next batching comparison holds the complete4,096-row presentation order
fixed across small/large depth3 lives with both policy bypasses disabled,
scale0.3 and prior0.4. Batch64 uses64 admissions; batch128 uses32 admissions.
All use four checkpoint intervals and the same finite dataset, with1,800s per
life and four concurrent CUDA learners. The preceding small-depth3 batch16 life
uses the same4,096 draws and256 admissions and remains the finer-batch control.
This isolates information and exposure; grouping changes the public batch
repair objective and compute cost, so neither admissions nor FLOPs are matched.
Native competence/retention and actual work decide whether larger batches help
the observed forgetting and weak deeper-path acquisition.

The shared sensory boundary is visible320×240 grayscale pixels with HUD,
current visual crops, four declared past-frame lags and16 actual executed
actions. History is bounded external memory, not learned recurrent memory.
All20 motor macros, including USE and weapon cycling, are available through
settled action scores. No actor receives positions, map geometry, labels or
teacher decisions. The observer-like structure has bounded local patch states,
ports, state/error readback, repair feedback and reproducible public evidence.

## Stage1: bounded bootstrap

Use a **finite seed experience set**, initially16 Basic episodes,8 navigation
episodes and at most8 varied door episodes plus the existing bounded door
sample. Scripted data generators may supply these initial examples. They are
not separate learned brains and are not the thing being demonstrated. Do not
spend the campaign optimizing full-level teachers or collecting expert routes
through all maps. Stop expert collection after the fixed bootstrap budget
unless a diagnosed missing primitive justifies a recorded amendment.

The existing Basic Cadence champion and all earlier experience remain useful
controls. Initial new-brain training may use explicitly named action-preference
estimates, with centered targets versus an offset control at matched action
margin. Those scores are not returns or Q-values. Hold out whole episodes,
fit normalization on training data only, and report exact visual duplicates.
No teacher-agreement score establishes autonomous competence.

Initial native competency gates, fixed before evaluating a selected founder:
Basic at least58/64 wins; navigation at least24/32 native completions; doors at
least12/16 native exits on the declared no-monster curriculum. Track each skill
separately. A candidate that passes only Basic is a Basic founder, not a complete
baby with all three skills. Broader combined/full-map exits remain measured
extensions. No unseen-map mastery claim is made from these starter tasks.

## Stage2: learning from its own gameplay

1. A frozen Cadence actor executes qualified actions in the real simulator.
   Record pre-action pixels, actual actions/tics, rewards, native outcomes,
   checkpoint identity and the complete replay prefix. Refused queries end
   attempts visibly; there is no scripted continuation substituted for them.
2. Parallel fresh-engine workers reconstruct sampled executed states exactly.
   They evaluate a proposed action for the **same4tics used by deployment**,
   then continue with the frozen Cadence actor for the declared horizon.
   Initial informative horizons are36tics for Basic and144tics for survival;
   longer navigation credit requires a separately declared comparison.
   Record native rewards/events separately from target transformations.
3. Derive explicitly versioned centered **policy-preference** targets from
   these outcomes. For the best-action tie setK, use probability1/|K| on its
   members and0 elsewhere, then target0.8×(probability−0.05). A unique best
   action receives0.76 and the others−0.04, exactly the centered bootstrap
   convention. Skip states where all20 actions tie. Preserve the entire native
   outcome vector, its utility definition and derivation with each label.
   This is **model-based autonomous practice using simulator
   branches**, not an external expert choosing gameplay actions. Do not call
   it model-free learning. Keep the finite bootstrap preferences as explicitly
   identified seed replay; all new preferences come from autonomous outcomes.
   The head remains an action-preference head throughout and is never renamed
   Q or expected return. Freeze continuation policy and target version per wave.
4. Independent candidate brains admit new and retained experience through
   `Brain.observe_batch(..., source="estimate")`. Start with half new and half
   earlier-skill replay. Compare bounded candidate lifetimes of1/4/16 updates;
   a single declined update need not erase all accumulated learning. Preserve
   the champion separately so development can take several steps safely.
5. Compare candidates with the unchanged champion on the same development
   seeds, including every acquired skill. Native progress and retention decide
   promotion; target MSE, admission count and qualification alone cannot.
   Promote immutable bytes at episode boundaries, with rollback available.

The original Basic feedback diagnostic completed all four arms without a
promotion. It showed lower utility-fitting error alongside worse action ranking.
Therefore neither the corrected horizon nor a longer candidate lifetime is
assumed sufficient. The campaign must produce a measured behavioral gain.

## Evidence that the baby learns

A before/after checkpoint pair is frozen before confirmation. Use independent
seeds not used for training or model selection; compare both policies on the
same scheduled seeds, keep deaths/timeouts/refusals/missing attempts in the
outcomes, and report confidence intervals and wall work. For an already-solved
Basic task, success retention plus improved native return/time is meaningful.
For a new survival/navigation skill, require improved native success or censored
survival/completion time, with no more than5percentage points loss on earlier
skill success and no query/fallback regression. Initial confirmation schedule:
64 paired episodes per measured skill; freeze exact seeds before the wave.
A positive gain requires a95% paired interval above zero for the declared
primary metric. Preserve the unmodified founder and unsuccessful candidates.

Demonstrate at least one successful independent repeat of autonomous
improvement before presenting self-improvement as reliable. Record the fraction
of attempted lives that improve, not only a selected success. Compare deep
state/error-path ablation at frozen weights and a matched shallow training
control; these address different questions. Report whether the evidence actually
supports the user's requested deep recursive architecture.

## Parallel execution and monitoring

For the next authorized learning wave, reuse the preserved64-vCPU/128GiB AWS
c7i.16xlarge while useful work is active. Cap numerical
threads per process. Benchmark8/16/32/48 independent fresh-engine rollout
workers and choose measured throughput; reserve cores/RAM for6–12 independent
learners/evaluators. Never average separately repaired brains as a shortcut.
Pipeline collection, feedback, repair and evaluation with bounded queues.
Add a second AWS instance only when measured queue pressure shows the first is
saturated. Benchmark GPU execution only through Cadence's existing mathematically
identical accelerated engine; use it when the measured end-to-end gain exceeds
transfer and reference-qualification overhead.

Exact native-engine, core-source and cross-host episode parity checks precede
any second worker's use. Keep live practice and independent
evaluation/collection on separate hosts, and stop hosts between useful jobs.
A private batched-query benchmark is a diagnostic only: compare it with
parallel CPU throughput before adding a service or changing the production
query path.

The matched navigation collection is complete: confirmedad9 and the native-goal-
trained eta1 candidate each played the same16 starts with qualified Cadence
actions only. The32episodes yielded512evenly spaced actual contexts and0goals;
all native trajectories were independently replayed after recovery. Actor,
experience and continuation identities are frozen separately. The next step is
new H600 labeling, not repeating collection or treating fitted targets as skill.
This addresses distribution change: fitting one-step choices under the old
continuation did not establish navigation under the changed actor. Each arm has
its own source/experience/feedback identity; do not reuse labels under a changed
continuation. Basic rehearsal comes from recorded actual experience and frozen
own-score estimates; these are not ground-truth targets or a new expert policy.

The AWS workspace is `/home/ec2-user/doom-v3-20260929`.
Freeze source, engine, task, normalization, target and checkpoint identities for
each wave. Mac and Linux frames have already failed exact replay despite matching
ViZDoom version strings; generate/replay training experience on the same engine,
and separately validate browser-platform deployment. Do not weaken pixel checks.

Bulk corpora and logs remain on AWS and are registered in workspace
`DATA_CATALOGUE.md`. Winning models stay local, alongside sources, compact
receipts and the exact model manifest. Each job and host has a bounded
watchdog; renew the host safety stop explicitly while authorized work
continues. Preserve durable evidence before stopping or terminating resources.
Keep the Mac above 20GB free.

The Lab panel polls full-game/baby development every15seconds and distinguishes
teacher bootstrap evidence, candidate training and actual student outcomes.
Expose competency, new-skill acquisition, retention, depth/width, qualification,
repair admissions, action latency, simulation speed, rollback, queue pressure,
cloud utilization and storage. Continue concise user updates while actively
working. No working browser connection is currently available to the control
plugin; HTTP/WS/engine checks continue, with visual browser verification pending.

## Relationship to full gameplay

Full-level measurements remain in their execution receipts.
Training E1M1–E1M3, developing on E1M4 and withholding E1M5/E1M6 remains the
map-transfer direction once the baby learns. Reserved maps stay unopened for
policy development. General competent full gameplay is the intended growth
path; the first deliverable is a bootstrapped, deep Cadence learner with
measured autonomous improvement and an honest browser demonstration.
