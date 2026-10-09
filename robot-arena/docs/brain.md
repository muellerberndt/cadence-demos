# The brain settings

The native adapter uses cadence-net 0.80.0. Every robot is one `Brain.compose` life: System 1, two reciprocally
coupled regions, the working trace as short-term memory, an associative memory, one reward
channel, and the actor-critic of the basal ganglia with TD eligibility over its own recent
commands. Every constant below is a gene of the robot's blueprint (`arena/brain.py:FOUNDER`),
so evolution can move it; the values are the founders. They are suggestions: one working
point, measured on these bodies in this ring, and the same goes for the bodies, the brain
layout, the nursery, the driving test and the stage. Start from them and change what you like.

The measurements below were recorded with 0.79.0. The 0.80.0 interface migration keeps their
settings: `compose` accepts the sensory scale and named actor rates, and `retune` applies a
stage without replacing configurations or rebuilding a brain. This is an interface change,
not a new learning or retention result. The committed browser pack retains its own 0.79.0
wheel, source hashes and trained checkpoints; new packs use 0.80.0.

## Senses and motors

Twenty-two inputs for a two-wheel body: four direction cells for the nearest robot and four
for the ring's edge (ahead, left, behind, right, cosine-tuned), closing and receding speed of
the nearest robot, a weapon within half a metre of the hull, speed forward and backward,
turning left and right, hit points, pain, damage dealt, outside the ring, each arm's angle and
reach, and a constant drive. Every motor is a slot of the one motor cortex: a wheel or leg is
three motor neurons (reverse, brake, forward), a spinner's switch two. Commands are read from
one settlement of the whole graph.

## The genes

| gene | founder | what it does |
| --- | --- | --- |
| `modules` | 48, 24 | two reciprocally connected regions; the second is the association cortex |
| `observers` | none | System 2 regions, expressed only on a developed System 1 |
| `trace_amplitude`, `trace_decay` | 0.3, 0.1 | the working trace: how strongly and how long the last state carries on; the library's 3.0 holds a continuing life in one state |
| `efference_amplitude` | 0 | the copy of the last command fed back as a sense; the reward-chamber point of 3.0 drowned these twenty-two senses; the library's composed default is also 0 |
| `episodic`, `consolidation` | on, 0.05 | the associative memory and the rate at which salient moments are written |
| `sensory_scale` | 4 | the weight of the sensory projection relative to the recurrent drive; at the composed 1.0 the policy was blind to its senses |
| `temperature` | 0.3 | the learner's softmax temperature: how wide an aroused brain samples |
| `eta`, `eta_bias` | 0.03, 0.003 | the actor's step in the nursery, and the bias step a tenth of it |
| `lam`, `gamma` | 0.6, 0.95 | eligibility decay and discount: credit reaches back about a second |
| `eta_critic` | 5 | the critic's normalised rate; a slow critic cannot carry delayed credit |

The table names the arena's blueprint genes. The public library names the reward rates
`actor_eta`, `actor_eta_bias`, `actor_lam`, `actor_gamma` and `actor_eta_critic`;
`trace_amplitude` and `trace_decay` map to `working_memory_amplitude` and
`working_memory_decay`. `learning_eta` is the rate for supplied teaching, which this
reward-only application does not use. `temperature` affects the sampling policy.

These arena settings are not general defaults. Plain `Brain.compose` keeps sensory scale
1, efference amplitude 0, working-trace amplitude 3, actor rate 1 and actor bias rate 0.05.
The chamber control chooses efference 3 and actor rate 0.1 explicitly. Compare candidate
values against the composed control and uniform random on each new body and task.

Arousal, the law that decides whether a moment is routine or learning:

| gene | founder | what it does |
| --- | --- | --- |
| `threshold` | 0.2 | the level at which the brain leaves routine; above the gene it stays calm through whole fights |
| `decay` | 0.9 | how long the level lingers after a surprise |
| `tolerance`, `floor` | 2.0, 0.1 | an error within this many usual errors is no surprise; the floor keeps the unit positive |
| `fast`, `slow` | 0.05, 0.005 | the rates of the recent and the long-run reward averages |
| `heat` | 2.0 | how much wider one motor slot samples when the brain wants |
| `youth` | 300 | moments of unconditional arousal at the start of a life |
| `value_surprise`, `record_surprise` | 1.0, 0 | the weight of a contradicted value forecast and of a contradicted memory record |
| `need` | 0.05 | reward per moment the body requires; the unmet share is a want of its own |

## The ring stage

On entering the ring every brain is retuned (`arena/brain.py:PAGE_STAGE`, applied by the page's
host and by the league's fights): `need` 0 and `heat` 0 (calm unless surprised, no wider
exploration), `temperature` 0.2, `reset` (the memory of the nursery's income forgotten, so
the ring's lower pay is no permanent want), and the actor's `eta` 0.001. The step is the
difference between learning and forgetting. Measured on six licensed brains over sixty
fights: at the nursery's 0.03 three fights undo the driving test and approach turns into
spinning in place; at 0.003 the test's mean fell from 0.57 to 0.34 and the burn rose again
after forty fights; at 0.001 the mean held at 0.49 with burn moments per fight between 14
and 31, about ninety kills per twenty fights and several different winners. A higher
arousal threshold is no remedy: at 0.3 or 0.5 the brains were calm throughout and one robot
won every fight.

For example, a stage changes the same living brain with one call:

```python
brain.retune(
    arousal={"need": 0.0, "heat": 0.0}, temperature=0.2,
    actor_eta=0.001, actor_eta_bias=0.0001, reset_arousal=True,
)
```

The application supplies this stage; the brain has not learned when to select it.
`reset_arousal` clears the arousal baselines only. Acquired parameters, working context,
associations and any outcome still owed to the last action continue through the stage.

## What pays

Nursery, per moment: metres closed on the target times 10, capped at 0.5; damage dealt minus
damage taken, divided by 20; the burn outside the standing ring at ten times its hit points;
a destroyed dummy or sparring partner 2.

Ring, per moment: damage dealt minus damage taken minus nine times the burn, divided by 20;
metres closed on the nearest rival times 3, capped at 0.3; a finished rival 2. At the end,
placement from +1 for the winner to -1 for the first out, delivered with the first
observation of the next fight.

## The driving test

Eight marks on a frozen greedy copy: approach (progress toward a target from eight bearings,
pass at 0.6), escape (from a hunting partner, 0.75), the closing ring (share of moments
outside at most 0.1), engagement (at least 100 damage dealt and more dealt than taken),
chase (a prey at 1 m/s, 0.3), facing (0.5), spinning in place (at most 0.1 of the test) and
stalling (at most 0.2). The score weighs the parts into one number in [-1, 1]; the test is
deterministic and gives the same number for the same brain file on any machine.
