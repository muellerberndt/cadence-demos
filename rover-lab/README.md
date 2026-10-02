# Cadence Rover Lab

A simulated rover learns a body model from executed wheel commands and measured
motion. The browser shows its path beside frozen Cadence, an adaptive dynamics
estimator and a small neural baseline. Weaken the right wheel, watch the
consequence predictions change, then restore the body and test the learned state.

## What it demonstrates

- **A live model that adapts.** The rover's brain keeps learning from every
  executed command and its measured motion. When the wheel weakens, its
  forecasts follow the new body within a few seconds of driving. The frozen copy beside it
  shows what happens without that.
- **No difference between training and inference.** There is no mode switch.
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
  did, and both rovers' paths. The brain itself runs in the local Python server
  on the real `cadence-net` package.
- **Settling and refusal.** A forecast is the settled state of the whole brain.
  A solve that does not settle raises an error; it is never replaced by a guess.
- **Observers as an option.** The default brain couples its populations through
  live states. An extra arm adds error-reading observers for comparison.
- **A life you can save and resume.** A checkpoint holds every brain and the
  body, and the resumed life continues as the uninterrupted one would.

## How it is built

The whole Cadence part is in [models.py](models.py). The brain is declared once:

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
main `Brain.compose` interface chooses discrete actions from reward. This lab
learns a continuous body model, which is the population solver's job. See the
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
