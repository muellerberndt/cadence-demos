# Atari Arcade

Brains born at server start learn Atari games while you watch. Each brain is a
Cadence 0.89.0 **System 1** brain on raw screen pixels in the Python edition. It begins as a
hatchling and watches a scripted teacher play. Once its own answers agree with
the teacher's actions often enough it takes the controls, and from then on it
keeps learning from the reward of its own actions. The page shows the game
beside the settled brain: the retina, the association cortex and its working
trace, the motor cortex with one neuron per action, the value the critic
expects, and the score of every life with a skill badge from noob to legend.

The Python adapter composes with named actor overrides and the teacher's own learning
configuration (`learning=LearnerConfig(...)`, the way 0.89.0 takes a lesson's own steps). The
actor's running moments (`momentum`, `normalize`) left the library in 0.85.0, so the reward step
is the actor's own. `tests/test_brain_interface.py` checks that the factory builds the archived
explicit recipe less those two options, including short teacher/reward tapes and saved
continuation; it adds no numerical parity claim with earlier runtimes. For the former Python
installation, use [the source at 2a32c3e](https://github.com/muellerberndt/cadence-demos/tree/2a32c3e/atari-arcade)
and its `cadence-net==0.71.0` requirements. The browser engine, fixtures and measured
receipts below retain their historical versions.

This is a bounded teacher/reward demo. Its per-screen lessons are a bootstrap
control, not the general Cadence operating recipe. New work follows the
[world-model guide](https://github.com/muellerberndt/cadence/blob/main/docs/world-model.md):
acquire reusable relationships between perceptions, actions and consequences,
retain context and durable knowledge, and continue normal settled behavior.
Witnessed mismatches or failures may admit local repair tied to the actual
event. Deep System 1 is the foundation, with recursive System 2 optional.

The trace and associative store used here are specific mechanisms whose
participation must be measured; their presence alone does not establish an
acquired general world model. For a future candidate, specify memory write/read
ports, episode/reset boundaries and delayed correction identity. Never credit
the brain for an unexecuted proposed action. Compare continuing state with
reset and memory interventions and separate familiar-action cost from learning
and refusal costs. Low recurring work is the target; the scores, settlement
residuals and badges below do not guarantee it.

## What it demonstrates

- **Learning from pixels.** The brain's only input is the screen: 7,056
  luminance values, 84 by 84. No object positions, no emulator memory, no
  hand-made features.
- **A teacher first, then reward.** While the teacher plays, each watched
  screen is one lesson with the teacher's action as its label. After the
  takeover the only teaching signal is the game's reward for the actions the
  brain itself took.
- **A continuing brain through teacher and reward phases.** There is no model swap.
  The same brain answers and learns on every screen, before and after the
  takeover. After the takeover every decision is one call, `brain.step`.
- **A brain that takes its time beside a body that does not.** The game runs
  at its own pace and holds the brain's last action while the brain settles
  the next one.
- **The main `Brain.compose` interface.** The brain is the library's default
  System 1: plastic cortex, a working trace, a motor cortex, basal ganglia with
  a critic and dopamine, and an associative memory of rewarded actions. The
  demo sets step sizes, adaptive-update settings and reward-credit timescales.
- **Settling and refusal.** An action is read from the settled state of the
  whole brain. A solve that does not settle raises an error; the body then
  holds its last action and nothing is credited to the brain for that step.
- **Learning you can watch.** The page shows the live settled state, the
  strongest current synapses, the teacher agreement and the score curve. The
  brain itself runs in the local Python server on the released `cadence-net`
  package.
- **The same brain in the browser.** `web/` runs Freeway and Atlantis with
  nothing behind the page, on a JavaScript version of the brain that is checked
  against the Python library value for value.
- **A living brain beside a frozen twin.** `headless_control.py` runs two
  brains per game from one seed. One keeps learning after the takeover; the
  other receives no outcome at all. The report compares them.

## How it is built

The whole Cadence part is in [server.py](server.py). The following is this
demo's recorded teacher/reward configuration, not a prescription to reduce
new applications to independent screen classification. The brain is composed once:

```python
from cadence import Brain, LearnerConfig

brain = Brain.compose(
    7056, n_actions, seed=seed,                 # 84 x 84 screen, one motor neuron per action
    learning=LearnerConfig(                     # the teacher's lessons
        beta=0.1, temperature=0.2, tolerance=3e-3, free_steps=1024, nudged_steps=12,
        eta_bias=0.02, eta=0.003, momentum=0.9, normalize=0.99, normalize_floor=1e-4),
    actor_gamma=0.97, actor_lam=0.9, actor_eta=0.001, actor_eta_bias=0.0001,
    actor_eta_critic=0.3, actor_eligibility_steps=None,
)
```

The learning configuration's `eta` and `eta_bias` govern the supplied teacher's lessons;
`actor_eta` and `actor_eta_bias` govern actual reward through `step`.
`actor_eligibility_steps=None` retains this demo's inheritance of the learner's
12-step nudged budget. These measured pixel settings are application choices,
not new library defaults.

While the teacher plays, each screen the brain gets to see is one lesson. The
brain first gives its own answer, read greedily from its settled state, and
then learns the teacher's action as the label of that screen:

```python
drive = brain.stimulus(screen)                     # the screen, the working trace, memory
own = brain.act(screen, greedy=True)               # the brain's own answer; not executed
brain.learner.step(drive, np.array([teacher_action]))   # the lesson
```

The teacher is at the controls, so the brain's answer is only compared with the
teacher's action. A greedy read carries no eligibility, so nothing is credited
to the brain for an action it did not take. The brain takes the controls after
at least 500 lessons once 90% of its last 120 answers agreed, or after 2,000
lessons at the latest. From then on every decision is one call. The reward and
the episode end describe the time since the brain's previous decision:

```python
action = brain.step(screen, reward=reward, done=done)
```

A decision that does not settle raises `RuntimeError`. The runner counts it as
refused; the body keeps holding its last action and nothing is credited to the
brain for that stretch.

The rest is ordinary application code. Each game has two threads. The body
thread steps the emulator sixty times a second, four times the console's
speed, with the teacher's action while the brain watches and the brain's last
action afterwards. The brain thread is the sole owner of the brain: it always
takes the latest screen, each screen at most once. The server exposes the game
frame, the settled state and a sample of the strongest synapses to the page in
`static/`. [headless_control.py](headless_control.py) runs the same runners
without a browser.

## Brain layout

The Python edition runs on the main brain of **Cadence 0.89.0**, `Brain.compose`,
installed as `cadence-net==0.89.0`. Its teacher and reward eligibility phases
retain the demo's finite budgets; upgrading the package does not enable
qualified teaching. Whole-brain actions still require equation qualification.

| Part | Size | Role |
| --- | --- | --- |
| Sensory neurons | 7,056 | The screen, one neuron per pooled pixel |
| Association cortex | 64 | Reads the screen; exchanges activity with the motor cortex |
| Working trace | 64 | Holds the association cortex's activity of the moments before |
| Motor cortex | one neuron per action | The policy; no lateral synapses between them since 0.85.0 |
| Critic (basal ganglia) | reads the association cortex | Expected return; its error is the dopamine signal |
| Associative memory | 7,056 by actions | Reward recalled for each action in a similar screen |

A Freeway brain (three actions) has 7,187 neurons and 456,064 synapses; an
Atlantis brain (four actions) has 7,188 and 456,192. All of them settle
together for every decision, and an answer is accepted only when the whole
state satisfies the neural equations to tolerance.

This is System 1 without observers. `Brain.compose(..., observers=(8,))` would
add System 2 regions to the same settlement; this demo does not use them. Each
synapse steps on a running mean of its own contrasts divided by their running
size (`momentum` and `normalize`), because most pixels are quiet most of the
time. The constructor's default step sizes suit small inputs: on these 7,056
pixels they did not get a brain past the most frequent label of a
screen-dependent teacher in our trials, so the learning configuration above is
part of the demo. Reward uses discount `gamma=0.97` and eligibility decay
`lam=0.9`, rather than `Brain.compose`'s default `0.9` and `0.8`. The teacher's
lessons use `momentum=0.9` and `normalize=0.99`; the reward step is the actor's
own. See the
[start guide](https://github.com/muellerberndt/cadence/blob/v0.89.0/docs/start.md)
and [learning from reward](https://github.com/muellerberndt/cadence/blob/v0.89.0/docs/reward.md).

## Run

Use Python 3.11 or later:

```sh
cd cadence-demos/atari-arcade
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Open **http://localhost:8668**. `ARCADE_GAMES` selects the games (default
`Atlantis,Freeway,Carnival,SpaceInvaders`), `ARCADE_PUBLIC=1` locks the speed
control, `ARCADE_HOST` and `ARCADE_PORT` bind the server. Each game needs about
one processor core. `requirements.txt` pins `cadence-net==0.89.0`.

## What the brain receives

The emulator is the Arcade Learning Environment (`ALE/<Game>-v5`): the game's
minimal action set, four frames per decision, sticky actions off. The screen's
luminance is pooled to 84 by 84. A fixed background, the mean of 300 screens of
random play taken before the brain is born, is subtracted and the difference is
doubled. That is the brain's whole input: one frame, no frame stack.

The brain decides as fast as it settles, about ten times a second on a laptop
core, so one action is held for a few emulator steps. The reward it learns from
is the sign of the game's reward since its previous decision. The teachers are
scripts. Freeway's always presses UP and
Atlantis's always fires the centre gun; Carnival's and Space Invaders' read the
player's position from emulator memory. That reading never reaches the brain.
The skill badge compares the brain's last five lives with the teacher's own
games: three played alone before the brain was born, and the ones the brain
watched.

Cadence is an observer-like self-reading system: bounded regions with local
state exchange activity through their synapses, settle together, read the
settled state back as the action, and keep the outcome of that action as
changed synapses, a critic and a memory. The page draws measured values only:
activations of the settled state, their change since the last decision, and
current synaptic weights.

## Measurement and evidence

`headless_control.py` ran every game for three seeds on the released package
(`cadence-net==0.89.0`, Python 3.13.7, NumPy 2.5.4, one BLAS thread per brain, one game per
run and three runs at a time on an Apple arm64 laptop shared with other jobs). Each run has
two brains born from one seed: one keeps learning after the takeover, the other receives no
outcome at all (the frozen twin). Each lived at least twelve whole games at the controls.
The reports are in [evidence/headless-089/](evidence/headless-089/); each one binds the
hashes of `server.py` and `headless_control.py` it ran.

| Game | Seed | Teacher alone | Takeover: lessons / agreement / time | Living: mean (lives) | Living: last five | Living: best | Frozen twin: mean (lives) | Faults / refused | Brain ms per screen: p50 / p95 | Checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Atlantis | 0 | 2,000 | 500 / 1.0 / 26.5 s | 2,000 (13) | 2,000 | 2,000 | 2,000 (13) | 0 / 0 | 37 / 57 | pass |
| Atlantis | 1 | 2,000 | 500 / 1.0 / 28.1 s | 2,046 (13) | 2,000 | 2,600 | 2,008 (13) | 0 / 0 | 34 / 55 | pass |
| Atlantis | 2 | 2,000 | 500 / 1.0 / 27.2 s | 2,000 (13) | 2,000 | 2,000 | 2,000 (13) | 0 / 0 | 14 / 52 | pass |
| Carnival | 0 | 540 | 2000 / 0.892 / 166.1 s | 438 (12) | 396 | 1,020 | 449 (16) | 0 / 0 | 61 / 140 | fail: expert_via_selfplay |
| Carnival | 1 | 540 | 1669 / 0.9 / 141.0 s | 213 (12) | 208 | 440 | 440 (21) | 0 / 0 | 54 / 124 | fail: expert_via_selfplay, living_holds_or_beats_frozen |
| Carnival | 2 | 540 | 1628 / 0.9 / 144.2 s | 457 (12) | 484 | 920 | 579 (22) | 0 / 0 | 49 / 122 | pass |
| Freeway | 0 | 21.7 | 500 / 1.0 / 32.0 s | 23.7 (12) | 24.0 | 27.0 | 22.1 (12) | 0 / 0 | 37 / 60 | pass |
| Freeway | 1 | 21.7 | 500 / 1.0 / 28.9 s | 23.4 (12) | 23.4 | 26.0 | 23.6 (12) | 0 / 0 | 36 / 57 | pass |
| Freeway | 2 | 21.7 | 500 / 1.0 / 29.0 s | 23.0 (12) | 23.2 | 28.0 | 22.8 (12) | 0 / 0 | 38 / 61 | pass |
| SpaceInvaders | 0 | 225 | 746 / 0.9 / 44.3 s | 248 (12) | 215 | 530 | 275 (12) | 0 / 0 | 50 / 84 | pass |
| SpaceInvaders | 1 | 225 | 566 / 0.9 / 32.7 s | 337 (12) | 309 | 650 | 178 (15) | 0 / 0 | 42 / 71 | pass |
| SpaceInvaders | 2 | 225 | 711 / 0.9 / 45.6 s | 285 (12) | 282 | 425 | 204 (15) | 0 / 0 | 42 / 72 | pass |

"Teacher alone" is the mean of the teacher's own games. A check line passes when
both brains took the controls, neither faulted, the living brain's last five
lives average at least 80% of the teacher, and the living brain's last five are
no lower than 90% of the frozen twin's last five.

The timing columns summarize the living brain's retained `think_seconds`
samples (at most 20,000). Each sample times one complete brain-loop handler:
either a watched screen's greedy answer and teacher lesson, or a screen at the
controls with feedback and the next action. It also includes that handler's
bookkeeping and visualization work, handled refusals, and any caught fault's
0.5-second backoff. It excludes the body's emulator stepping and pixel
preprocessing, waiting for a fresh screen, and HTTP/browser rendering. These
receipts do not separate watching from play, so they cannot establish a
post-takeover decision-only latency. The live page shows the median of the
latest 200 samples from that same stream. Its rolling window may eventually
contain only play; the phase of each retained sample is not recorded. These
are elapsed wall times under the host's load, not operation counts.

What the runs show:

- **Freeway, Atlantis and Space Invaders pass every check on every seed.** Freeway
  lives average 23.0 to 23.7 against a teacher of 21.7, with single lives up to 28.
  Atlantis holds the teacher's 2,000, with a best life of 2,600. Both take the controls
  after 500 lessons, 27 to 32 seconds after birth, with every one of the last 120 answers
  in agreement. Space Invaders' living brains end at 215, 309 and 282 against a teacher of
  225, after a takeover at 566 to 746 lessons.
- **Carnival reaches its teacher on one seed.** Its living brain's last five lives average
  484 on seed 2, 396 on seed 0 and 208 on seed 1, against a teacher of 540. Its teacher and
  Space Invaders' depend on the player's position, so the agreement there (0.89 to 0.90) is
  read from the pixels.
- **No brain faulted and no decision was refused** in any of the 24 brains. Brain processing
  per screen, collected during watching and play, took 14 to 61 ms at the median and 52 to
  140 ms at the 95th percentile on that laptop.

What they do not show:

- **A reliable gain from reward.** The living brain ends above its frozen twin in Space
  Invaders on seeds 1 and 2 (309 against 174, 282 against 216) and in Freeway on seed 0,
  level with it elsewhere, and below it in Carnival on seed 1 (208 against 364). Freeway's
  and Atlantis's teachers are a single held action, and a random policy scores far more in
  Atlantis than its teacher does.
- **Repeatable timing.** The game does not wait for the brain, so which screens a brain sees
  depends on the machine and its load. Two brains from one seed take over at slightly
  different lesson counts.

On 0.70.0 ([evidence/headless-070/](evidence/headless-070/), one game per run on an AWS
c7i.16xlarge shared with other jobs) seven of the twelve checks passed: Freeway and Atlantis
on every seed and Space Invaders on seed 2; Carnival on none. Between the two releases the
actor's reward step lost its running moments (0.85.0), the motor slot's lateral inhibition
went from -0.5 to 0.0 (0.85.0), and the actor now credits the policy that sampled each action
(0.79.0).

Carnival and Space Invaders can still fall into holding one action after the
takeover and score far below their teachers
([#1](https://github.com/muellerberndt/cadence-demos/issues/1)).

```sh
.venv/bin/python headless_control.py --seed 0 --games Freeway --episodes 12 --out report.json
```

## The browser edition

`web/` runs Freeway and Atlantis with nothing behind the page, using the
retained JavaScript implementation of the 0.70.0 brain and its loop. Its
browser fixtures and measurements keep that version identity.

```sh
cd web && python3 -m http.server 8080      # open http://localhost:8080/
```

- `cadence.js` is a JavaScript version of the 0.70.0 System 1 brain that
  `Brain.compose` builds with its default processing region: settling with the
  qualified answer and its refusal, lessons, acting, learning from reward, the
  working trace and the associative memory, for one stream. It includes NumPy's
  seeding and generator, so a brain is born with exactly the weights the library
  gives the same seed and samples its actions from the same draws.
- `arcade.js` is the server's loop: the retina, the teachers, watching, the
  takeover gate, living on reward, the scores and the badge.
- Each game gets two web workers: the emulator, which never waits for the brain,
  and the brain, one serial owner. The emulator is an Atari 2600 core
  ([6502.ts](https://github.com/6502ts/6502.ts)) behind an ALE-style game
  interface (`emulator/ale.js`, bundled into `emulator.js`).

Two things differ from the server edition. The page has no teacher games played
before birth, so the brain takes the controls only after it has also watched one
whole game of the teacher; the badge needs that score. And JavaScript brain
processing takes about 30 ms per screen at the median of its unseparated timing
samples, so the browser brain sees more of the game's screens than the Python
one does.

`node parity.mjs` checks `cadence.js` against values recorded with the released
0.70.0 package. To regenerate `fixtures/parity_system1.json`, run
`tools/make_parity_fixture.py` in a separate environment pinned to 0.70.0.
Newborn efficacies are identical bit for bit for three and
four actions. On two recorded tapes of watched lessons, decisions with rewards,
an episode end, a frozen stretch and a reset, every answer, sampled action and
sweep count is identical, and activations, values, dopamine and every parameter
agree within 1e-9 (observed: 1e-10 on a small brain whose every parameter is
compared, 3e-12 on a brain of the arcade's size). The two engines add the same
products in a different order, so the last digits differ.

`node headless.mjs --game Freeway --episodes 6 --out receipts/freeway_living.json`
runs the browser pipeline without a browser, the game advancing by the brain's
own time. The receipts in `web/receipts/`:

| Game | Takeover | Teacher's game | Lives at the controls | Refused / faults | Brain ms per screen: p50 / p95 |
| --- | --- | --- | --- | --- | --- |
| Freeway | 1,005 lessons, agreement 1.00, 118 s after birth | 21 | 23, 25, 23, 19, 23, 19 | 0 / 0 | 30 / 49 |
| Atlantis | 500 lessons, agreement 1.00, 45 s after birth | 2000, 2000 | 2000 eight times | 0 / 0 | 27 / 39 |

Browser `think_ms` similarly combines watched lessons and play, retaining at
most 20,000 samples. It times the brain's handler and its bookkeeping and
visualization work, including handled refusals, but excludes uncaught faults,
emulator/retina work and rendering. The page shows the median of the latest
200 samples. These timings also do not isolate post-takeover decisions.

`emulator/` rebuilds `emulator.js` (`npm install && npm run build`). The ROM
images are the ones shipped with `ale-py` 0.12.1; see `web/THIRD_PARTY.md`.
