# Navigation: delayed credit and exploration are separate problems

This is a read-only recommendation from existing traces. No new navigation
gameplay, teacher data, training, model promotion or reward modification was
performed. The producer is `../../navigation_trace_audit.py`; the full input
is the immutable AWS `runs/baby_screen_02` screen.

The52 navigation episodes include repeated models on the same four development
seeds, so they are not52 independent tests. Five episodes reached the native
goal;47 timed out. Across25,057 recorded action contexts:

| Additional native horizon | Actual future windows containing the goal reward | Fraction |
| --- | ---: | ---: |
| 36 tics | 45 | 0.180% |
| 144 tics | 163 | 0.650% |
| 300 tics | 260 | 1.038% |
| Whole remaining episode, at most2100 tics | 381 | 1.521% |

These are windows along the already executed policy, not twenty-action
counterfactual comparisons. They do not prove that every alternative would
tie. They show that a longer horizon can expose delayed successes, but cannot
manufacture successes on the47 failed continuations.

The reward is not literally zero: `my_way_home.cfg` charges0.0001 per tic and
the ACS goal script supplies+1. Equal-duration unsuccessful branches therefore
receive the same return, for example−0.0036 over36 tics. Extending a fixed
failed continuation usually increases cost without creating an action-ranking
signal. Exhaustive long branching still cannot replace a policy that visits
useful states.

The qualified student traces include502 consecutive forward actions into a
wall and a525-decision left/right oscillation with eight distinct raw frames.
Neither a settling refusal nor an engine error caused these failures. Longer
credit is appropriate near a reachable goal; an exploration mechanism is
needed to generate experience outside these loops.

## Candidate comparison to consider later

Keep a native-only control with the longer frozen continuation horizon. Compare
it against the same learner, actor information, bootstrap, actual-context
budget, native-tic budget and wall-time accounting, adding one explicitly
versioned **visual novelty utility gene**. Set novelty weight zero in the
control. Do not claim that a utility selected for exploration is the native
task reward, and do not silently mix its old replay labels into another
contract.

The novelty candidate should use only visible scene/history and executed
actions, with an episodic memory of already encountered perceptual states.
It should reward encountering a new state more than repeatedly traversing the
same visual cycle. A bounded episode-level novelty budget is easier to audit
than an uncapped reward every frame. Its budget/weight, representation, memory
size, similarity scale and horizon are declared genes; the hand-set settings
remain controls. Native goal completion remains the selection and confirmation
criterion. A small novelty budget can be kept below the native goal reward,
but that alone does not guarantee useful exploration.

For a Cadence implementation, prefer a self-reading observer population that
learns action-conditioned sensory predictions through the same public patch
repair rule and exposes bounded records of prediction or visitation novelty.
Keep this auxiliary population's cost, admissions, readback and changes in the
representation visible. Do not add a hidden route planner or a policy that
chooses a hardcoded escape action. A coarse scene-count utility can be a
simple declared control, but its usefulness would not demonstrate learned
observer-based exploration.

Freeze the novelty representation, its episodic history at the branch point,
and its lifetime state for each counterfactual cohort. Each fresh branch gets
its own copy of that state and may update only its branch-local record. Record
native reward and novelty separately. Otherwise branch order, asynchronous
updates or one branch consuming another's novelty can change the labels.
Past/current/future replay ownership must be as strict as the existing native
feedback contract.

## Failure cases the experiment must expose

- **Spinning:** new camera orientations can earn novelty without navigation.
  A finite episode memory should exhaust a repeated turn cycle; distinguish
  novelty in the first rotation from continuing bonuses after revisiting it.
- **Weapon, HUD and particle changes:** firing, bobbing, changing numbers or
  random effects can create visually new frames while the player remains
  stationary. Exact image hashes are unsuitable as the reward representation.
  Cropping or learned invariance is a declared candidate, not a guarantee.
- **Controllable distractions:** inverse dynamics alone does not remove the
  weapon problem, because firing is an action the agent controls.
- **Forgetting and memory resets:** representation drift or a tiny memory can
  make an old corridor continually appear new. Declare resets and retention;
  compare cumulative novelty against native goal progress.
- **Reward domination:** intrinsic reward can favor exploration over finishing
  a visible goal. Keep both components in the receipt and select on native
  outcomes, retaining failures and the zero-novelty control.
- **More compute mistaken for better learning:** a2100-tic continuation can
  cost roughly58 times the native work of36 tics before early stopping. Report
  actual engines, tics and qualified queries, not only repaired contexts.

The literature makes the proposal plausible, not proven for this Cadence
genome. [Pathak et al.](https://arxiv.org/abs/1705.05363) studied prediction-based
curiosity using action-relevant features, including ViZDoom, and explain the
unpredictable-pixel distraction problem.
[Never Give Up](https://arxiv.org/abs/2002.06038) combines episodic novelty memory
with action-relevant embeddings. Both motivate an explicit controlled
experiment; neither establishes that the current actor will learn navigation
from the proposed utility.
