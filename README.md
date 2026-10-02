# Cadence demos

Small example applications for [Cadence](https://github.com/muellerberndt/cadence):
brains that learn from experience through bounded patches, local relations,
readback and settlement. Each demo shows one simple use of the library. Its own README says which
Cadence features it demonstrates and how it is built.

> **Early research.** Cadence is under heavy early research. These demos are
> imperfect and change as the library changes.

## What the demos show

Animal and human brains learn from experience and not by backpropagation with
gradient descent. Cadence is designed the same way, and the demos pick out what
that gives a brain that has to run a body:

- **Live learning.** A brain learns while it runs. There is no training phase
  followed by a frozen deployment, and no difference between training and
  inference.
- **Adapting to new conditions.** When the body or the world changes, the live
  brain adjusts from what it measures, without being told what changed.
- **Evolving brains.** The layout of a brain can be inherited, mutated and
  selected, so its size and shape are earned by what they cost and return.
- **Answers that settle.** An action is the settled state of the whole brain,
  and a brain that does not settle refuses to answer.
- **Learning without backpropagation.** Connections change from locally
  available activity while the brain runs, so the learning can happen on the
  device that carries the brain.

## The brain in Cadence 0.70.0

Cadence builds one continuing brain. **System 1** is the default: an
animal-like brain with perception, plastic connections, memory, action and
private imagination. **System 2** is optional: observing regions add recursive
feedback inside the same brain. Every brain is one settlement, in which patches
repair their disagreement together.

Beside the main `Brain.compose` interface, the library keeps advanced engines
such as record patches and the population solver, where populations of patches
settle one joint energy and observers read prediction errors.

## The demos

| Demo | What it shows | Runs on |
| --- | --- | --- |
| [Rover Lab](rover-lab/) | A live model that adapts when its body changes, with no difference between training and inference | Cadence 0.70.0, population solver |
| [Patch World](patch-world/) | Brains that learn in the browser and evolve across generations | JavaScript version of the 0.70.0 population solver |
| [Atari Arcade](atari-arcade/) | Brains that learn Atari games from pixels: a teacher first, then reward | Cadence 0.70.0, `Brain.compose` (System 1); in the browser, a JavaScript version of it |
| [Amen](amen/) | A record patch composing jungle tracks in the browser | A brain trained on Cadence 0.11.0 |

Rover Lab, Patch World and Atari Arcade run on Cadence 0.70.0. Amen runs the
earlier engine it was built and recorded on.

## [Rover Lab](rover-lab/): a body model that keeps learning

A simulated rover learns how its wheel commands turn into motion. Weaken its
right wheel and watch a learning Cadence brain adjust its predictions and keep
reaching targets, beside a frozen copy, an adaptive estimator and a small neural
network. The brain is three small populations of patches that read the motor
commands and one another's states and settle together. Error-reading observers
are an optional extra arm.

```sh
cd rover-lab
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py        # http://localhost:8670
```

See the [Rover Lab README](rover-lab/README.md).

## [Patch World](patch-world/): evolution prices the brain

A conserved-mass world under a moving sun, in one page. Each creature inherits
a body plan, develops a small settling brain from it, learns within one life,
and pays mass for every patch, relation and repair sweep. The founders have no
observers; mutation can add observer stages, and energy and death decide whether
they stay. Click a creature to watch its brain settle.

```sh
cd patch-world
python3 -m http.server 8080       # http://localhost:8080/
```

See the [Patch World README](patch-world/README.md).

## [Atari Arcade](atari-arcade/): learning Atari games

Brains born at server start learn Atari games from the raw screen while you
watch. Each one is a System 1 brain built with `Brain.compose`. It watches a
scripted teacher play, takes the controls once its own answers agree often
enough, and then keeps learning from the reward of its own actions. The page
shows the game beside the settled brain. Freeway and Atlantis
also run entirely in the browser, on a JavaScript version of the same brain
(`atari-arcade/web/`).

```sh
cd atari-arcade
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py        # http://localhost:8668
python3 -m http.server 8080 --directory web   # the browser edition at http://localhost:8080/
```

See the [Atari Arcade README](atari-arcade/README.md).

## [Amen](amen/): a jungle composer in the browser

One record patch learned jungle tracks as events per half-beat: a slice of a
drum break, a sub-bass note, a change flag and a texture. Nothing on the page is
recorded. Press the button and the brain computes a track from silence in the
browser, hearing each half-beat it plays, then renders it through the
instrument.

```sh
python -m http.server -d amen/web 8803   # open http://localhost:8803 and press CUT A DUB
```

See the [Amen README](amen/README.md).
