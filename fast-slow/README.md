# Fast action with slower recursive feedback

An experiment on **Cadence 0.50.0** using Amen, C64 Maestro and native Atari.
Fast patches answer while a recursive observer works on captured readback.
Both use the existing patch and repair rule. Every emitted action requires a
qualified fast settlement; an observer's correction becomes an input to a
later settlement.

This is an observer-like self-reading system: bounded patch states, sensory
and action ports, state/error records, recursive feedback, public repair calls,
and source-bound evidence. It is an experimental application, not a new library
release or a certificate that the asynchronous whole has globally settled.

## One interface for applications

```python
from agent import Agent

with Agent("trained-agent.json") as brain:
    decision = brain.step(observation)
    if decision["qualified"]:
        execute(decision["output"])
```

`observation` is the demo's ordinary sensory vector. The exported bundle owns
its normalization, trained fast and recursive parameters, attention calibration,
feedback timing and worker lifecycle. Create a new agent per episode. An
application does not connect separate brain parts or implement evaluators.
The fixed sensor encoding and output decoding are the body's interface.

This facade runs trained candidates; it does **not** yet perform online outcome
learning or choose strategic goals. Putting the experimental scheduler behind
one interface does not resolve the deeper core question of asynchronous global
equilibrium. No core learning or settlement law was changed.

## What was measured

Two training seeds per dataset, the same 96 fast updates of 16 examples, and a
separate 24-update recursive learner. All updates use public `observe_batch`
with derived targets labeled `source="estimate"`. Fast-only and conditioned
descendants start from the same founder and receive identical final row IDs.
Half the conditioned examples replay neutral feedback. These are small screens,
not converged models or a comparison against legacy Amen's different mechanism.

| Dataset | Fast training time, excluding evaluation | Median fast query | Development result |
| --- | --- | --- | --- |
| Amen | 45–46 s | 18.2 ms | Event MAE falls from about .438 to .18; free continuations remain limited |
| C64 Maestro | 1.6 s | .51–.52 ms | Pitch error falls from about 15 to 5–5.5 semitones |
| Atari Freeway | 5.5 s | 2.4 ms | Constant-UP habit learned; native bounded returns 7 and 5 |
| Atari Space Invaders | 11.2 s | 4.6 ms | 93.75% development teacher agreement; native gains inconsistent across model seeds |

Times are from CPU training on a c7i.16xlarge host with one Torch/BLAS thread
per learner. The reference Python backend made the query measurements. Different
widths and sensor encodings make these domain timings non-comparable as tasks.
All sampled fast queries qualified in two sweeps.

Forty-eight native Atari episodes compare untrained, fast-only, conditioned,
feedback-disabled, surprise-scheduled and teacher arms on two predeclared play
seeds, for each trained seed. Episodes are bounded at 512 decisions and usually
censored. Every action and reward, sampled image, and termination flag was
independently replayed in ALE. Slow feedback did not change the native returns
in these comparisons. Space Invaders seed 2 did worse than its untrained
control; seed 7 did better. These results establish neither robust control
improvement nor a useful strategic observer.

Surprise scheduling reduced observer submissions by **25% in Freeway** and
**19% in Space Invaders**, preserving the returns in this small screen. It uses
the error of a persistence prediction of sensory features, with its threshold
calibrated on training transitions only. It is not learned semantic surprise.
No learned-agent observation-to-action interval missed the tested 1/15-second
deadline; this is measured behavior, not a real-time guarantee.

Both music seeds produced 128-event continuations in three arms, using executed
history and the actual Amen/SID instruments. All events qualified and each
enabled arm used 120 delayed corrections. Amen seed 2 lost crop/bass diversity
with feedback; C64 sustained all voices. Rendering and diversity do not establish
musical quality, and no listening assessment was recorded. A failed Amen render
in an environment missing SciPy is retained alongside the successful retries.

Compact evidence is in [evidence/20261001](evidence/20261001/). Complete models,
private data windows, frozen sources, event traces and audio have separate AWS
custody recorded in the workspace `DATA_CATALOGUE.md`. No original demo champion
was replaced.

## Internal mechanisms and the next architectural question

`actor.py` owns the two execution rates. The observer sees captured fast
state/error and longer sensory context. Feedback is eligible one block after
capture, expires after the next block or the sensory-age bound, and cannot
cross episodes. Refused feedback becomes neutral conditioning. The fast action
still comes from settlement. This supplies independent execution without a
hard deadline guarantee from Python threads.

`attention.py` increases observer duty after a sensory prediction miss, then
returns to occasional checks. Timing, widths, priors and thresholds are declared
experimental controls; they have not been selected by evolution. Scheduled
checks are internal, not a required application callback.

The intended continuation is **shared valence, local responsibility, and retained
experience across timescales**, inside one brain interface. Good/bad outcomes
should inform fast and recursive activity. Their consequences should be learned
according to participating decisions and context, so a poor route does not
automatically erase successful aiming. Surprise and desirability have different
roles: an expected bad outcome still matters, and an unexpected observation need
not be bad. Low settlement residual is neither outcome success nor world-model
accuracy.

Cadence 0.50.0 already supplies reward-based replay in `Reinforcement`; the older
library had an explicit `Valence`/eligibility implementation. The earlier valence
experiments identified a downstream actor-learning problem despite improving
value prediction. These mechanisms are evidence to build on, not proof that
long-horizon credit or whole-brain modulation is already solved. This screen
used supervised bootstrap targets, not that reward-learning path.

`outcomes.py` is an internal bookkeeping interface for future outcome-predicting
patches. It retains the original goal/context/model identity until the measured
horizon arrives and marks unobserved horizons as censored. It is not itself a
planner, value learner, or causal-credit estimator. Doom navigation and StarCraft
strategy still require learned predictive memory, credit over longer intervals,
and retained-skill validation. No Doom promotion or StarCraft capability follows
from this screen.

The 0.60 design must preserve **brain-wide equilibrium**. This two-owner
experiment is a control, not an acceptable replacement for one qualified brain.
The requirements and exact results are tracked in
[Cadence #72](https://github.com/muellerberndt/cadence/issues/72).

`equilibrium_probe.py` tests retained state on the unchanged joint solver.
Across five seeds, repeated inputs need zero repair sweeps while retaining
whole-graph checks. Freezing unresolved observers after a disturbance gives
five conditionally settled answers that all fail the complete graph criterion.
The receipt is `evidence/20261001/equilibrium-probe.json`; no learning or
semantic attention is claimed from this numerical control.

The separate experimental 0.60 delayed-credit comparison is recorded under
`evidence/20261001/credit-horizon/`, including frozen sources. Five seeds at
delays 1/8/32/128 show no advantage over matched one-step replay, with one
additional regression at delay 32. It is not a selected release implementation.

## Reproduce

The `query_cache.py`, `query_small.py`, `verify_060.py`, `verify_exposure.py` and
`c64_joint.py` collectors also support the isolated **0.60 development branch**.
Their compact evidence is under `evidence/20261001/wave2/`. These comparisons
use one jointly qualified brain or compare numerical kernels on identical
mathematical states; they do not promote the two-owner facade above as the
finished architecture. Historical credit receipts require their frozen
reinforcement reader: later development changes acknowledgment and checkpoint
schemas. The complete source archives and large ledgers stay on AWS at the
catalogued paths. Do not rewrite checkpoint hashes to load them with newer code.

`c64_joint.py build-data` excludes cross-split musical families before selecting
training and validation windows. `c64_joint.py train` compares common next-event
and future-context targets in flat, ordinary and recursively observing brains.
Its bounded pilot measures feasible learning work; twelve admissions and one
seed cannot establish a recursive capability advantage. Use each collector's
`--help` and source-frozen protocol for its full invocation and limits.

`self_correction.py` freezes a five-seed, six-patch prediction/recovery test
before running it. `verify_self_correction.py` checks causal ledger order,
shared observations, matched coefficients and source-bound checkpoints. The
stable-task acquisition gate must pass before interpreting a correction
comparison. For the development branch, set `PYTHONPATH` to that branch's
`src` directory rather than the sibling 0.50 checkout.

`occlusion_protocol.json` specifies the proposed visual-completion comparison
using Tang et al.'s original whole/partial feature data. Compact import receipts
are under `evidence/20261001/occlusion-data/`; large arrays remain on AWS. This
is a verified data import and a candidate experiment design, with no occlusion
training result yet. Exact original folds and Hopfield construction remain
reproduction gates; native Cadence uses its own patch law. Whole-object
acquisition precedes any partial-view capability comparison.

`acquisition_controls.py` separates fixed-rule learning, balanced mixed-rule
experience, capacity and replay duration. Its development seed is excluded from
independent confirmation. `verify_acquisition_controls.py` replays saved query
checks without learning. The complete small synthetic run, frozen sources,
interrupted attempts and checkpoints are preserved in the verified archive
under `evidence/20261001/acquisition-controls-pilot/`.

`readback_signal_probe.py` measures the errors available to an observer in an
untrained graph, with all states free or an observed boundary clamped.
`verify_readback_signal.py` recomputes its four-patch predictions and free-state
energy derivatives directly. This is a signal diagnostic, not a learned
advantage. Shared-innovation experiments use independent synthetic body targets
to test whether those signals can support useful correction.

`shared_innovation.py freeze ROOT` and `launch ROOT` compare three-patch,
nine-parameter ordinary and error-reading brains on the same observed
disturbance. Both clean prediction heads must pass free-query acquisition and
retention gates before interpreting correction. `verify_shared_innovation.py`
replays saved queries independently and retains every scheduled outcome.
`innovation_confirmation.py` uses fresh seeds and data to test the early
exposure hypothesis suggested by development, while retaining the later
accuracy and counted-work comparisons. Equal exposure is not equal compute.

`work_matched_innovation.py` freezes the observer's 32-admission endpoint and
continues the ordinary model until it reaches the same cumulative training
edge visits. Whole admissions may overshoot that work target. Its verifier
also keeps the ordinary 32-admission and both final checkpoints, preventing
extra training from hiding a late reversal. Complete small archives include
the exact core sources, ledgers and query-replay verification.

`residual_reuse.py` separates input-only prediction-error reuse from a
predictor whose latent state can change during correction. Each within-layout
pair has identical parameter counts and observations; comparisons between
the two- and three-patch layouts are mechanism controls, not capacity matches.
`residual_representation_witness.py` supplies a six-case analytic obstruction
for the specific ordinary two-patch head and an engineered error-reading
solution. It uses fixed private-kernel coefficients, not a learned checkpoint;
the public builder verifies both topology inventories. This narrow result
cannot establish a general recursive, learning or efficiency advantage.

`cycle_memory_probe.py` and `learned_cycle_memory.py` investigate explicit
state cycles through the private kernel. The public builder does not currently
expose those topologies. Both use the common patch law and freely settled
chronological queries, checking write, blank retention, opposite-cue overwrite
and reset separately. The former uses engineered coefficients; the latter
learns from paired small random initializations. A history-input arm explicitly
has one extra external memory scalar. Persistent nonzero activity is a local
metastable equilibrium; it is not the globally lowest-energy state, learned
planning, or proof that residual-observer columns help. Every failed arm and
numerical refusal remains in the frozen comparison.
`cycle_write_confirmation.py` separately freezes stronger cue targets and
64/256/1,024 admissions using fresh seeds. It retains the failed original
regime as a control and evaluates every checkpoint through the same free
chronological memory task. The original flat/history controls remain historical;
this follow-up tests acquired cyclic memory, not matched performance superiority.
`cycle_write_continuation.py` continues every source-bound final checkpoint
to a separately declared endpoint while preserving the earlier failed result.
Its self-contained parent bundle allows replay after raw parent cleanup.
`flat_blank_obstruction.py` proves the specific one-patch flat control cannot
retain opposed histories under identical blank input; this is not a theorem
about all ordinary graphs.

`delayed_bandit.py` tests one outstanding executed decision with immediate or
delayed actual outcomes. It retains the original forecasts and teaches only
the executed action's witnessed outcome through the common patch law. Its
four-patch, 14-parameter comparison uses explicit collector memory; it does
not demonstrate learned temporal memory or planning. Run the full campaign
on AWS because its complete outcome journals exceed the local data limit.
`verify_delayed_bandit.py` checks every outcome's action ownership, original
forecast, witness order and complete-graph qualification, then replays the
held-out checkpoint queries and verifies that neutral delays preserve the
learning trajectory. Compact receipts are under
`evidence/20261001/delayed-bandit/`; full journals stay at the catalogued AWS path.

Use the sibling Cadence checkout through `PYTHONPATH=../../cadence/src` from this
directory. Training needs NumPy and CPU Torch. Native play/replay additionally
needs Gymnasium/ALE and available ROMs. Music rendering uses the existing Amen
fixtures/SciPy or C64 Maestro native SID environment.

```sh
python data.py amen --workspace ../.. --out /path/on/aws/amen.npz
python data.py c64 --workspace ../.. --out /path/on/aws/c64.npz
python data.py atari --game Freeway --out /path/on/aws/freeway.npz
python train.py --data /path/on/aws/amen.npz --out /path/on/aws/run --seed 2
python agent.py --run /path/on/aws/run --data /path/on/aws/amen.npz --out /path/on/aws/trained-agent.json
python verify.py --run /path/on/aws/run --data /path/on/aws/amen.npz --sources /path/on/aws/frozen-sources
```

Keep the source directory frozen while training or evaluating. The batch scripts
record every exit and enforce process time limits. Verification checks artifact
hashes, matched exposure and snapshot reloading. Run focused tests with:

```sh
PYTHONPATH=../../cadence/src python -m pytest -q .
```

## Website demo baselines before candidate migration

[`demo-baselines/smoke.json`](evidence/20261001/demo-baselines/smoke.json)
records the original Amen source/model verifier, Atari browser fixture parity
and a 20-tick Patch World mass-conservation probe. All three pass. These checks
exercise the existing engines: Amen's archived record patch, Atari's 0.50
JavaScript port and Patch World's separate JavaScript implementation. They do
not establish candidate compatibility, musical quality or recursive advantage.
The website comparison covers local synchronized runtime files and their
recorded manifest; no live browser or audio check was performed in that initial audit.
A subsequent [Browser Use check](evidence/20261001/demo-baselines/live-browser.json)
loaded all three published demos, generated one Amen dub, observed Atari
activity and advancing Patch World counters, and paused Patch World. It records
visible UI behavior only, with no audio-quality or candidate-migration claim.

The receipt also reproduces the Python Atari loop's lost pending-action flag
using a fake action owner, and checks that its old feedback call does not bind
to the candidate's executed-outcome signature. Migration must preserve actual
execution, rewards and episode identity together; merely adding keywords is
insufficient. Existing native behavior must be remeasured after that repair.

The owner selects a newly trained **flat Amen brain** as the first application
test. Atari and Patch World should start with flat or shallow controls; deeper
observation needs a measured task benefit. Baseline reproduction and a passing
page smoke remain distinct from a tested replacement under the new architecture.


## Parallel routine bootstrap on the public candidate

The application checks use independent brains and serialized admissions within
each brain. They retain the common patch rule, require qualified free actions,
and preserve failed attempts. Full cloud journals and checkpoints remain at the
paths in the workspace data catalogue; compact receipts are beside the code.

- [Atari Freeway](atari_flat_README.md): a flat brain acquires a supplied
  constant-UP routine, then controls complete native games without teacher
  fallback. This tests routine acquisition and execution, not visual strategy
  or reward-driven discovery.
- [Patch World](patchworld_README.md): flat, composed and observer layouts learn
  a supplied local-foraging routine, then act in the unchanged JavaScript body.
  The bounded single-organism experiment checks actual metabolism, actions and
  conserved mass. It does not replace the website's separate brain engine.
- Amen's flat composer is trained by the workspace's
  `cadence-amen/drsn_amen/train.py --wiring flat`. Its next-event acquisition and
  free generation from silence are separate gates. A successful prediction fit
  alone cannot qualify a replacement musical demo.

The public candidate's [brain-design guide](https://github.com/muellerberndt/cadence/blob/codex/cadence-0.60/docs/BRAIN_DESIGN.md)
explains how to choose observations, context, connected capacity and exposure,
and how to test whether deeper observation justifies its cost. These routine
checks do not demonstrate integrated System 1/System 2 attention or a causal
advantage from recursive correction.
