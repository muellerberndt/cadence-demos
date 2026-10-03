# Atari Arcade

Brains born at server start learn Atari games while you watch. Each brain is a
Cadence 0.71.0 **System 1** brain on raw screen pixels in the Python edition. It begins as a
hatchling and watches a scripted teacher play. Once its own answers agree with
the teacher's actions often enough it takes the controls, and from then on it
keeps learning from the reward of its own actions. The page shows the game
beside the settled brain: the retina, the association cortex and its working
trace, the motor cortex with one neuron per action, the value the critic
expects, and the score of every life with a skill badge from noob to legend.

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
from cadence import ActorCriticConfig, Brain, LearnerConfig

brain = Brain.compose(
    7056, n_actions, seed=seed,                 # 84 x 84 screen, one motor neuron per action
    learning=LearnerConfig(                     # the teacher's lessons
        beta=0.1, temperature=0.2, tolerance=3e-3, free_steps=1024, nudged_steps=12,
        eta_bias=0.02, eta=0.003, momentum=0.9, normalize=0.99, normalize_floor=1e-4),
    reward=ActorCriticConfig(                   # learning from reward
        gamma=0.97, lam=0.9, eta=0.001, eta_critic=0.3, momentum=0.9, normalize=0.99),
)
```

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

The Python edition runs on the main brain of **Cadence 0.71.0**, `Brain.compose`,
installed as `cadence-net==0.71.0`. Its teacher and reward eligibility phases
retain the demo's finite budgets; upgrading the package does not enable
qualified teaching. Whole-brain actions still require equation qualification.

| Part | Size | Role |
| --- | --- | --- |
| Sensory neurons | 7,056 | The screen, one neuron per pooled pixel |
| Association cortex | 64 | Reads the screen; exchanges activity with the motor cortex |
| Working trace | 64 | Holds the association cortex's activity of the moments before |
| Motor cortex | one neuron per action | The policy; neurons inhibit one another |
| Critic (basal ganglia) | reads the association cortex | Expected return; its error is the dopamine signal |
| Associative memory | 7,056 by actions | Reward recalled for each action in a similar screen |

A Freeway brain (three actions) has 7,187 neurons and 456,070 synapses; an
Atlantis brain (four actions) has 7,188 and 456,204. All of them settle
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
`lam=0.9`, rather than `Brain.compose`'s default `0.9` and `0.8`; both teacher
and reward updates use `momentum=0.9` and `normalize=0.99`. See the
[brain guide](https://github.com/muellerberndt/cadence/blob/v0.71.0/docs/brain.md)
and [continuous interaction](https://github.com/muellerberndt/cadence/blob/v0.71.0/docs/continuous.md).

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
one processor core. `requirements.txt` pins `cadence-net==0.71.0`.

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
(`cadence-net==0.70.0`, Python 3.11, NumPy 2.4.6, one BLAS thread per brain, an
AWS c7i.16xlarge shared with other jobs). Each run has two brains born from one
seed: one keeps learning after the takeover, the other receives no outcome at
all (the frozen twin). Each lived at least twelve whole games at the controls.
The reports are in [evidence/headless-070/](evidence/headless-070/); each one
binds the hashes of `server.py` and `headless_control.py` it ran.

| Game | Seed | Teacher alone | Takeover: lessons / agreement / time | Living: mean (lives) | Living: last five | Living: best | Frozen twin: mean (lives) | Faults / refused | Brain ms per screen: p50 / p95 | Checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Atlantis | 0 | 2,000 | 500 / 1.0 / 33.0 s | 2,000 (13) | 2,000 | 2,000 | 2,008 (13) | 0 / 0 | 74 / 117 | pass |
| Atlantis | 1 | 2,000 | 500 / 1.0 / 33.9 s | 2,000 (13) | 2,000 | 2,000 | 2,000 (13) | 0 / 0 | 70 / 102 | pass |
| Atlantis | 2 | 2,000 | 500 / 1.0 / 33.5 s | 1,969 (13) | 2,000 | 2,000 | 1,938 (13) | 0 / 0 | 74 / 110 | pass |
| Carnival | 0 | 540 | 2000 / 0.783 / 123.0 s | 422 (12) | 448 | 640 | 543 (15) | 0 / 0 | 64 / 88 | fail: living_holds_or_beats_frozen |
| Carnival | 1 | 540 | 2000 / 0.733 / 124.0 s | 485 (12) | 424 | 860 | 707 (15) | 0 / 0 | 62 / 83 | fail: expert_via_selfplay, living_holds_or_beats_frozen |
| Carnival | 2 | 540 | 2000 / 0.758 / 129.2 s | 454 (13) | 456 | 700 | 492 (15) | 0 / 0 | 64 / 92 | fail: living_holds_or_beats_frozen |
| Freeway | 0 | 21.5 | 500 / 1.0 / 37.9 s | 22.7 (12) | 22.2 | 26.0 | 23.4 (12) | 0 / 0 | 46 / 81 | pass |
| Freeway | 1 | 21.5 | 500 / 1.0 / 39.3 s | 21.9 (12) | 22.6 | 24.0 | 22.7 (12) | 0 / 0 | 47 / 86 | pass |
| Freeway | 2 | 21.5 | 500 / 1.0 / 39.8 s | 22.7 (12) | 23.4 | 25.0 | 22.8 (12) | 0 / 0 | 46 / 85 | pass |
| SpaceInvaders | 0 | 225 | 1313 / 0.9 / 86.2 s | 207 (13) | 141 | 435 | 183 (13) | 0 / 0 | 67 / 100 | fail: expert_via_selfplay, living_holds_or_beats_frozen |
| SpaceInvaders | 1 | 225 | 1519 / 0.9 / 97.3 s | 249 (17) | 262 | 315 | 251 (13) | 0 / 0 | 60 / 86 | fail: living_holds_or_beats_frozen |
| SpaceInvaders | 2 | 225 | 1370 / 0.9 / 88.9 s | 237 (12) | 241 | 325 | 215 (15) | 0 / 0 | 65 / 95 | pass |

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

- **Freeway and Atlantis reach the teacher's level in every seed.** Freeway
  lives average 21.9 to 22.7 against a teacher of 21.5, with single lives up to
  26. Atlantis holds the teacher's 2,000. Both brains take the controls after
  500 lessons, 33 to 40 seconds after birth, with every one of the last 120
  answers in agreement.
- **Space Invaders and Carnival keep playing after the takeover.** Space
  Invaders lives average 207 to 249 against a teacher of 225; Carnival 422 to
  485 against 540. Their teachers depend on the player's position, so the
  agreement there (0.90 for Space Invaders at the gate, 0.73 to 0.78 for
  Carnival at the 2,000-lesson limit) is read from the pixels. They do not pass
  every check, and they stay out of the published pair.
- **No brain faulted and no decision was refused** in any of the 24 brains.
  Brain processing per screen, collected during watching and play, took 46 to 74 ms
  at the median and 81 to 117 ms at the 95th percentile on that shared host;
  the live page showed about 100 ms on an Apple M4 laptop.

What they do not show:

- **A gain from reward.** The frozen twin does as well as the living brain in
  Freeway and Atlantis and better in Carnival. In these runs learning from
  reward keeps the taught skill; it does not improve on it. Freeway's and
  Atlantis's teachers are a single held action, and a random policy scores far
  more in Atlantis than its teacher does.
- **Repeatable timing.** The game does not wait for the brain, so which screens
  a brain sees depends on the machine. Two brains from one seed take over at
  slightly different lesson counts.

Against the 0.50.0 demo this replaces: its recorded Freeway lives were 17, 21,
16, 26, 21, 21 against a teacher of 21 after a takeover at 174 s, and its
Atlantis lives were 2000 five times after 288 s (the receipts of its browser
edition). Carnival and Space Invaders fell into holding one action after the
takeover and scored far below their teachers
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

The 0.50.0 browser edition this replaces recorded 17, 21, 16, 26, 21, 21 for
Freeway after a takeover at 174 s and 2000 five times for Atlantis after 288 s.

`emulator/` rebuilds `emulator.js` (`npm install && npm run build`). The ROM
images are the ones shipped with `ale-py` 0.12.1; see `web/THIRD_PARTY.md`.
[floatingpragma.io/demos/atari-arcade](https://floatingpragma.io/demos/atari-arcade/)
serves a pinned copy of this folder.
