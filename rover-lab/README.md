# Cadence Rover Lab

A simulated rover learns a body model from executed wheel commands and measured
motion. The browser shows its path beside frozen Cadence, an adaptive dynamics
estimator and a small neural baseline. Weaken the right wheel, watch the
consequence predictions change, then restore the body and test the learned state.

This is a bounded example of an acquired world model: learned relations predict
the consequences of wheel commands. The current demo teaches from each executed
transition and uses an application controller; it does not implement or prove
the complete continuing `Brain.compose` memory/repair protocol. For new work,
follow the [world-model guide](https://github.com/muellerberndt/cadence/blob/main/docs/world-model.md):
bootstrap reusable knowledge, retain relevant context, read durable knowledge
for normal settled behavior, and admit local repair from identified witnessed
mismatches or failures. Deep System 1 is the foundation; observers are optional.

Future comparisons must separate ordinary continuation from repair cost and
test memory writes, reads and retention. Bind each correction to its executed
command and measured consequence across delay and save/load. Compare continuing
and reset controls and preserve the existing adaptive and neural baselines.
Lower recurring work is a target, not an inference from a low solver residual
or a passed demonstration gate. The protocols and results below retain their
recorded implementation identity.

## What it demonstrates

- **A live model that adapts.** The rover's brain keeps learning from every
  executed command and its measured motion. When the wheel weakens, its
  forecasts follow the new body within a few seconds of driving. The frozen copy beside it
  shows what happens without that.
- **One life through bootstrap and adaptation.** There is no mode switch.
  The short motor curriculum at the start and the whole life afterwards use the
  same call, `brain.observe`, on the same brain. Forecasting and learning
  alternate every step.
- **Learning from what the body did.** Only executed commands and measured
  motion teach the brain. Wheel strength, the phase of the experiment and the
  change itself are hidden from it.
- **Control-loop timing on the record.** Every step's sensing-to-command time is
  measured against a 100 ms deadline, and misses are reported.
- **Learning you can watch in the browser.** The page shows the live brain's
  patch states and prediction errors, its forecasts against what the body then
  did, and both rovers' paths. In the Python edition the brain runs in a local
  server on the real `cadence-net` package. In the [browser edition](#browser-edition)
  the whole lab runs in the page.
- **Settling and refusal.** A forecast is the settled state of the whole brain.
  A solve that does not settle raises an error; it is never replaced by a guess.
- **Observers as an option.** The default brain couples its populations through
  live states. An extra arm adds error-reading observers for comparison.
- **A life you can save and resume.** A checkpoint holds every brain and the
  body, and the resumed life continues as the uninterrupted one would.

## How it is built

The whole Cadence part is in [models.py](models.py). This retained population
solver example declares the brain once:

```python
from cadence.experimental.equilibrium import Cortex

cortex = Cortex(seed=seed, parameter_prior=0.1)
motors = cortex.input("motors", shape=2)                      # left and right wheel command
body = cortex.column("body", patches=1, inputs=motors)
middle = cortex.column("integration", patches=1, inputs=(motors, body))
motion = cortex.column("motion", patches=2, inputs=(motors, body, middle))
cortex.output("motion_readout", shape=2, reads=motion)        # forward and turning velocity
brain = cortex.build()
```

The optional observer arm changes two lines:

```python
middle = cortex.observer("integration", patches=1, inputs=motors, observes=body)
motion = cortex.observer("motion", patches=2, inputs=motors, observes=(body, middle))
```

Every step of the rover's life then makes three kinds of call:

```python
# learn the consequence of the command that was just executed
brain.observe({"motors": last_command}, {"motion_readout": measured_motion}, source="witness")

# forecast each candidate command with a pure, unclamped settle
forecasts = [brain.settle({"motors": command})["outputs"]["motion_readout"] for command in candidates]

# settle on the command the controller chose, keeping the live activity
brain.step({"motors": chosen_command})
```

The rest is ordinary application code: [rover.py](rover.py) holds the simulated
body, the shared heading controller and the step loop for all models,
[server.py](server.py) serves the viewer in `static/`, [evaluate.py](evaluate.py)
runs headless screens, [verify.py](verify.py) recomputes a receipt without
importing the app, and [checkpoint.py](checkpoint.py) validates saved lives.
[web/](web/) holds the browser edition: the same brain, models, body and step
loop in JavaScript.

## Brain layout

Rover Lab runs on the population solver of **Cadence 0.70.0**,
`cadence.experimental.equilibrium`, installed as the released package
`cadence-net==0.70.0`.

The rover's brain has four patches in three populations: `body`, `integration`
and `motion`. They read the two motor inputs and one another's live states, and
all four settle together as one equilibrium. The two `motion` patches are the
forecast of forward and turning velocity. This state-coupled brain is the
default and the one the browser shows.

Observers are optional. `evaluate.py --observers` adds a fifth arm whose
`integration` and `motion` populations also read exact prediction errors inside
the same settlement. It has the same four patches, 22 parameters against 17,
and a higher compute cost. The comparison measures whether error readback
improves adaptation enough to pay for that cost.

Cadence 0.70.0 refuses to build a layout whose patches only read sensors, and
`test_rover.py` checks that refusal. Cadence's
main public entry for new integrated brains is `Brain.compose`. This lab's
continuous body model uses the separate population solver and keeps its own
equations and evidence; this choice does not limit the intended common brain
to discrete reward policies. See the
[brain guide](https://github.com/muellerberndt/cadence/blob/v0.70.0/docs/brain.md)
and the [population solver guide](https://github.com/muellerberndt/cadence/blob/v0.70.0/docs/equilibrium/README.md).

## Run

Use Python 3.11 or later:

```sh
cd cadence-demos/rover-lab
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Open **http://localhost:8670**. Preparation executes a finite motor curriculum;
the page reports its progress. **Run automatic demo** starts a fresh comparison:
normal wheels, a weakened right wheel, restoration with learning paused, and
restoration with learning resumed. **Start/Pause**, **Weaken wheel**, **Restore**
and **Resume learning** allow manual inspection. Manual interventions produce an
exploratory receipt outside the automatic demonstration gate.
If the port is occupied, use `server.py --port 8672` and open
`http://localhost:8672`.

`requirements.txt` pins `cadence-net==0.70.0`, and `models.py` refuses any other
version. Receipts and checkpoints bind the hashes of the installed solver files
and of the app sources; a checkpoint loads only under matching sources. The
server binds only to `127.0.0.1`.

## Browser edition

[web/](web/) is the same lab as static files. The rover body, the four models,
the controller and the step loop run in a worker beside the page at ten control
steps per second, and the page draws the state the worker publishes. This is
the edition at <https://floatingpragma.io/demos/rover-lab/>.

```sh
python3 -m http.server 8080 --directory web     # http://localhost:8080/
```

| File | What it holds |
| --- | --- |
| [web/cadence.js](web/cadence.js) | The population solver: `Cortex`, `Brain`, the joint repair of `_repair.settle` and Python's `random.Random`, following the released 0.70.0 sources line by line |
| [web/models.js](web/models.js) | The motion models of `models.py`: both Cadence layouts, the adaptive estimator and the MLP |
| [web/rover.js](web/rover.js) | The body, the heading controller, the step loop and the protocol of `rover.py` |
| [web/worker.js](web/worker.js), [web/app.js](web/app.js) | The real-time loop and the viewer |

The brain is declared as in Python:

```js
const cortex = new Cortex({ seed, parameter_prior: 0.1 });
const motors = cortex.input('motors', { shape: 2 });
const body = cortex.column('body', { patches: 1, inputs: motors });
const middle = cortex.column('integration', { patches: 1, inputs: [motors, body] });
const motion = cortex.column('motion', { patches: 2, inputs: [motors, body, middle] });
cortex.output('motion_readout', { shape: 2, reads: motion });
const brain = cortex.build();
```

and a step of the rover's life makes the same three calls, `brain.observe`,
`brain.settle` and `brain.step`.

The Python package is the reference. `node web/parity.mjs` checks the
JavaScript against values recorded with it by
[web/tools/make_parity_fixture.py](web/tools/make_parity_fixture.py):

- **Brains are born identical.** Both layouts receive the same wiring and the
  same weights for a seed, bit for bit.
- **The solver is the same computation.** The library takes two operations from
  the platform's C library, `tanh` and `pow`, whose last bit differs between
  platforms. With both replaced by plain arithmetic on both sides, all 720
  recorded solver calls return identical bits: states, errors, parameters,
  energy, stationarity and sweep counts.
- **Whole lives agree.** With each side's own `tanh`, a solve stops inside the
  solver's tolerance of the same stationary point. Over two automatic lives,
  every model issued the same command at all 960 steps and reached the same
  targets. Forecasts differed by at most 5e-6 and final parameters by at most
  8e-5.

`node web/test.mjs` checks behaviour that needs no reference: a life is a
function of its seed, a saved life continues exactly, the frozen copy never
changes, the return probe teaches no model, a forecast changes nothing, a
refused solve raises and commits nothing, and an uncoupled layout is refused.

`node web/headless.mjs` runs the automatic demonstration without a browser.
[web/receipts/automatic.json](web/receipts/automatic.json) holds the two
development seeds:

| Seed | Gate | Weakened-body targets, learning | Weakened-body targets, frozen | Target distance against frozen |
| --- | --- | --- | --- | --- |
| 17 | pass | 5/5 | 2/5 | 0.855 |
| 29 | pass | 5/5 | 3/5 | 0.868 |

These are the outcomes of the Python screen for the same seeds.
In a browser, one automatic run of seed 17 at the page's real-time pace
([web/receipts/browser-seed-17.json](web/receipts/browser-seed-17.json),
headless Chromium on an Apple M4) passed the complete gate with the same
targets and the same distance ratio. The learning arm's 95th-percentile command
age stayed between 5 and 8 ms per phase, with no deadline miss in 960 steps.

The browser edition differs from the Python edition in three ways. Its
checkpoints and receipts have their own formats (`rover-life-js-v1`,
`rover-evidence-js-v1`), carry no source hashes, and are not inputs to
`verify.py` or to the Python server. The page shows the four default models;
the observer arm exists in `rover.js` and is covered by the parity check. And
while the tab is hidden the life waits, because browsers slow the timers of
hidden tabs and the wait would be recorded as missed deadlines.

## What the models receive

Each command has two motor values. The supplied body integrates differential
drive kinematics and returns normalized forward velocity and turning velocity.
The models receive those commands and measured consequences. Wheel strength,
phase labels, goals and change announcements never enter a model's inputs.
Every model controls its own rover with the same sensor interface, target
sequence, transition allowance and supplied heading-aware action selector.
Their trajectories, and therefore their actual witnesses, can differ.

Cadence is an observer-like self-reading system: bounded software patches have
local states and ports; populations read one another's states, and observer
populations also read prediction errors, within the same coupled settlement;
measured records drive the common repair rule. The displayed patch states come
from the qualified executed-command solve. Hypothetical action forecasts use
pure, unclamped settlements. They provide no teaching targets. The browser
displays forecast error against subsequent motion, separately from internal
patch prediction errors.

The action selector is application code. It compares predicted motion against a
desired forward speed and heading correction. Motor actions are not learned
outputs of a policy patch. Controller coefficients, architecture and replay
settings are hand-set controls and candidate genes; this package performs no
evolution search.

Frozen and learning Cadence start from identical bootstrap snapshots. Frozen
Cadence keeps its parameters while its activity follows commands. The adaptive
baseline is affine recursive least squares with forgetting. The MLP uses two
24-unit tanh hidden layers and Adam. All learners receive the same number of
measured and replayed presentations; each MLP presentation takes one Adam step.

## Measurement and evidence

The [two-seed development screen](evidence/screen-03/summary.json) uses a right
wheel at 35% strength. Weakened-body targets completed: **10/10 for learning
Cadence, 5/10 for frozen Cadence, 10/10 for the adaptive estimator and 5/10 for
the MLP**. Learning Cadence accumulated 14% and 13% less target distance than
its frozen copy in the two seeds. Every model completed all normal-body targets.
The optional observer arm also completed 10/10 weakened-body targets, with
target distance within 0.2% of the default brain's and the same forecast error
to three decimals. These are
development observations, without a reserved confirmation, a demonstrated
advantage over the adaptive estimator, or a measured benefit from observers.

The complete demonstration gate, including the 100 ms timing checks, passes for
both seeds of that headless screen. The learning arm's 95th-percentile command
age stayed between 3 and 27 ms per phase, with 8 deadline misses in 1,920 steps.
Timing depends on machine load. One [live server run](evidence/live-01/seed-17.json)
recorded while other work used the machine reached all its body-recovery checks
and failed the timing check with a 159 ms 95th percentile in its first phase.
The viewer runs at best effort and reports deadline misses.

[protocol.json](protocol.json) declares seeds, perturbation range, experience
budgets, phase durations, controller settings and numerical demonstration gates.
Each target trial resets the pose, with its target drawn from the same seeded
schedule for all models. Brains and replay persist. The body restoration probe
disables learning without swapping weights or restoring an old model. Its scores
are reported separately from subsequent relearning.

The sensing-to-command timer includes learning the preceding actual transition,
replay, all candidate forecasts and action activation. Compute time, serial
queue delay, command age and 100 ms deadline misses are separate measurements.
Arms are served one after another within a step, so a later arm's command age
includes the work of the arms before it. Rendering frame rate is unrelated. The
simulator waits for computations and slows under load; these measurements do
not provide a hard real-time guarantee.

Run the bounded screen and independently verify its transition evidence:

```sh
python3 evaluate.py --seeds 17 29 --out evidence/my-development
python3 verify.py evidence/my-development/seed-17.json
python3 verify.py evidence/my-development/seed-29.json
python3 evaluate.py --confirmation --observers --out evidence/my-confirmation
python3 -m pytest -q test_rover.py
```

Output directories must be empty. Each run writes its protocol/source freeze
before execution and retains every scheduled seed. `--observers` adds the
error-reading observer layout at equal patch count and experience allowance.
Parameter counts, wiring and measured compute cost differ; equal patch count
does not imply equal useful capacity. The reserved confirmation seeds in
`protocol.json` are unused, and these comparisons alone do not establish a
causal benefit from error readback.

**Export receipt** records the actual live run. `verify.py` independently
recomputes wheel motion, trajectories, target hits, prediction errors, timing
accounting and gate outcomes. A valid receipt can report a failed learning gate.
Hash checks provide integrity and source identity, not authenticated execution.

**Save checkpoint** includes every brain, Adam moments, estimator covariance,
body pose, target schedule, replay, pending transition and counters. **Load
checkpoint** restores the whole life paused. Continuation tests compare resumed
decisions and learning with uninterrupted execution, excluding wall-clock timing.
Checkpoint restoration is a persistence test; it is separate from retention
after adapting to changed mechanics.

This is a small simulation of adaptive body modelling. A gain over frozen
Cadence does not establish an advantage over the competent adaptive or neural
controls, protected memory, useful observers, or physical robot performance.
