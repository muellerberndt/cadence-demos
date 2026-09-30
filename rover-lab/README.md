# Cadence Rover Lab

A simulated rover learns a body model from executed wheel commands and measured
motion. The browser shows its path beside frozen Cadence, an adaptive dynamics
estimator and a small neural baseline. Weaken the right wheel, watch the
consequence predictions change, then restore the body and test the learned state.

## Brain layouts

Rover Lab implements all three Cadence settlement patterns with four patches
each. **Flat settlement** predicts motion directly from the two motor inputs.
**Ordinary state-coupled settlement** adds body and integration populations whose
live states feed the motion population. **Recursive observer settlement** adds
exact prediction-error readback to those population connections. All use the
same patch law and settlement engine; the browser comparison uses the recursive
layout, while `evaluate.py --variants` includes the flat and composed controls.

The flat model is the inexpensive starting point for a simple body relation.
The other layouts test whether learned intermediate states or error feedback
improve adaptation enough to justify their cost. See the
[layout guide](https://github.com/muellerberndt/cadence/blob/main/docs/VARIANTS.md)
and [performance guide](https://github.com/muellerberndt/cadence/blob/main/docs/PERFORMANCE.md).

## Run

Use Python 3.11 or later from this workspace:

```sh
cd cadence-demos/rover-lab
python3 -m pip install -r requirements.txt
python3 server.py
```

Open **http://localhost:8670**. Preparation executes a finite motor curriculum;
the page reports its progress. **Run automatic demo** starts a fresh comparison:
normal wheels, a weakened right wheel, restoration with learning paused, and
restoration with learning resumed. **Start/Pause**, **Weaken wheel**, **Restore**
and **Resume learning** allow manual inspection. Manual interventions produce an
exploratory receipt outside the automatic demonstration gate.
If the port is occupied, use `python3 server.py --port 8672` and open
`http://localhost:8672`.

The app reads the sibling `cadence/src` checkout. Its model snapshots bind the
exact Cadence implementation and adapter source. An independently installed
`cadence-net==0.50.0` is a fallback for an isolated copy; checkpoints require
matching implementation sources. The server binds only to `127.0.0.1`.

## What the models receive

Each command has two motor values. The supplied body integrates differential
drive kinematics and returns normalized forward velocity and turning velocity.
The models receive those commands and measured consequences. Wheel strength,
phase labels, goals and change announcements never enter a model's inputs.
Every model controls its own rover with the same sensor interface, target
sequence, transition allowance and supplied heading-aware action selector.
Their trajectories, and therefore their actual witnesses, can differ.

Cadence is an observer-like self-reading system: bounded software patches have
local states and ports; observer populations read states and prediction errors
within the same coupled settlement; measured records drive the common repair
rule. The displayed patch states come from the qualified executed-command solve.
Hypothetical action forecasts use pure, unclamped settlements. They provide no
teaching targets. The browser displays forecast error against subsequent motion,
separately from internal patch prediction errors.

The action selector is application code. It compares predicted motion against a
desired forward speed and heading correction. Motor actions are not learned
outputs of a policy patch. Controller coefficients, architecture and replay
settings are hand-set controls and candidate genes; this package performs no
evolution search.

Frozen and learning Cadence start from identical bootstrap snapshots. Frozen
Cadence keeps its parameters while its activity follows commands. The adaptive
baseline is affine recursive least squares with forgetting. The MLP uses two
24-unit tanh hidden layers and Adam, following the changing-body comparison's
architecture with two inputs and outputs. All learners receive the same number
of measured/replayed presentations; each MLP presentation takes one Adam step.
This update schedule differs from the historical comparison's minibatches.

## Measurement and evidence

The [two-seed development screen](evidence/screen-02/summary.json) uses a right
wheel at 35% strength. Its weakened-body targets completed were **10/10 for
learning Cadence, 5/10 for frozen Cadence, 10/10 for the adaptive estimator and
5/10 for the MLP**. Learning Cadence accumulated about 14% less target distance
than its frozen copy. All four models completed all normal-body targets. These
are development observations, without a reserved confirmation or a demonstrated
advantage over the adaptive estimator.

The **100 ms timing gate failed**: Cadence's weakened-phase 95th-percentile
command age was about 407–510 ms on the measured machine. The viewer therefore
runs at best effort and reports deadline misses. The screen's exact source
files are preserved under [evidence/screen-02/source](evidence/screen-02/source/),
with hashes in its freeze. The live package includes persistence and run-failure
handling fixes; the archived screen binds its own implementation. Reserved
confirmation and depth comparison outcomes are outside this evidence bundle.

[protocol.json](protocol.json) declares seeds, perturbation range, experience
budgets, phase durations, controller settings and numerical demonstration gates.
Each target trial resets the pose, with its target drawn from the same seeded
schedule for all models. Brains and replay persist. The body restoration probe
disables learning without swapping weights or restoring an old model. Its scores
are reported separately from subsequent relearning.

The sensing-to-command timer includes learning the preceding actual transition,
replay, all candidate forecasts and action activation. Compute time, serial
queue delay, command age and 100 ms deadline misses are separate measurements.
Rendering frame rate is unrelated. The simulator waits for computations and
slows under load; these measurements do not provide a hard real-time guarantee.

Run the bounded screen and independently verify its transition evidence:

```sh
python3 evaluate.py --seeds 17 29 --out evidence/my-development
python3 verify.py evidence/my-development/seed-17.json
python3 verify.py evidence/my-development/seed-29.json
python3 evaluate.py --confirmation --variants --out evidence/my-confirmation
python3 -m pytest -q test_rover.py
```

Output directories must be empty. Each run writes its protocol/source freeze
before execution and retains every scheduled seed. `--variants` adds flat and
state-reading controls to the recursive model at equal total patch count and
experience allowance. Parameter counts, effective wiring and measured compute
cost differ; equal patch count does not imply equal useful capacity. These
comparisons alone do not establish a causal benefit from recursive readback.

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
controls, protected memory, useful recursive depth, or physical robot performance.
