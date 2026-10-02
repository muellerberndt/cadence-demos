# Cadence demos

Small example applications for [Cadence](https://github.com/muellerberndt/cadence):
brains that learn from experience through bounded patches, local relations,
readback and settlement. Each demo shows one simple use of the library. Its own README says which
Cadence features it demonstrates and how it is built.

> **Early research.** Cadence is under heavy early research. These demos are
> imperfect and change as the library changes.

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
| [Atari Arcade](atari-arcade/) | Brains that learn Atari games from a teacher, then from reward | Cadence 0.50.0 |
| [Amen](amen/) | A record patch composing jungle tracks in the browser | A brain trained on Cadence 0.11.0 |

Rover Lab and Patch World run on Cadence 0.70.0. Atari Arcade and Amen run the
earlier engines they were built and recorded on.

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

Brains born at server start learn Atari games while you watch. Each one watches
a scripted teacher, takes the controls once its actions agree often enough, and
keeps learning from every reward. The page shows the game beside the settling
brain. Freeway and Atlantis also run entirely in the browser at
[floatingpragma.io/demos/atari-arcade](https://floatingpragma.io/demos/atari-arcade/).

```sh
cd atari-arcade
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python server.py   # open http://localhost:8668
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
