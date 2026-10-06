# Cadence demos

Small example applications for [Cadence](https://github.com/muellerberndt/cadence):
brains that learn from experience through bounded patches, local relations,
readback and settlement. Each demo demonstrates a specific mechanism and names
its implementation and evidence. These are bounded examples, not complete
recipes for the intended continuing brain.

> **Early research.** Cadence is under heavy early research. These demos are
> imperfect and change as the library changes.

## What the demos show

Cadence's functional target is an animal-like continuing brain that acquires
reusable knowledge, retains context and adapts to witnessed outcomes. This is
a software design goal, not a claim that these demos reproduce biological
learning or can learn every human task. The demos expose parts of that goal:

- **Live learning.** Acquired knowledge can remain useful while the same brain
  continues acting and learning. Bootstrap, ordinary settled behavior and
  evidence-driven repair have distinct roles and costs. A new observation
  need not trigger a supervised update.
- **Adapting to new conditions.** When the body or the world changes, the live
  brain adjusts from what it measures, without being told what changed.
- **Evolving brains.** The layout of a brain can be inherited, mutated and
  selected, so its size and shape are earned by what they cost and return.
- **Answers that settle.** An action is the settled state of the whole brain,
  and a brain that does not settle refuses to answer.
- **Declared learning mechanisms.** The equilibrium candidates repair from
  local relations and measured outcomes. Amen retains a separate record-patch
  engine with the adjoint learning rule disclosed in its README; its results
  do not certify the common brain's learning rule.

## The brain in Cadence

The intended application builds one continuing brain through `Brain.compose`.
**System 1** is the default and may be deep and modular: an
animal-like brain with perception, plastic connections, memory, action and
private imagination. **System 2** is optional: observing regions add recursive
feedback inside the same brain. Its reciprocal patches settle together, using
short-term context and durable acquired knowledge. The canonical
[world-model guide](https://github.com/muellerberndt/cadence/blob/main/docs/world-model.md)
specifies the operating model for new applications.

Bootstrap should acquire reusable regularities of the task's world. Normal
behavior continues from useful retained state and reads that knowledge. A
witnessed mismatch or failure can admit local repair, attached to the actual
observation or executed action. Declare what each memory writes, retains,
reads and clears, and preserve correction identity across delay, retry and
save/load. A memory object that never affects behavior is insufficient.

The goal is competent repeated behavior with low recurring work after
acquisition. Test it against cold-reset and independent-input controls, memory
interventions, novel events and an explicit repair schedule control. Account
for initial acquisition, memory, sensing, all solves, replay and refused work.
Neither a small residual nor a demo's `pass` or `WIN` label proves correct
behavior, low physical energy or a performance advantage.

Beside the main `Brain.compose` interface, the library keeps advanced engines
such as record patches and the population solver, where populations of patches
settle one joint energy and observers read prediction errors.

## How a Cadence brain differs from a feed-forward network

A conventional independent-input MLP control computes its answer in one pass
and uses a separate supervised update. Such a control is useful for comparison;
the ongoing state, memory and repair contract must be tested separately.

A Cadence brain reaches its answer by settling. Its patches are connected in
both directions. Each patch repairs its own disagreement with the patches it
reads, and the repairs repeat until the whole brain agrees within a tolerance.
That equilibrium supplies the candidate answer. Agreement with the equations
does not establish agreement with the world; behavior must be checked against
what actually happens.

When observed evidence calls for learning, the declared local rule repairs the
relevant relations so that later free behavior can improve. Continuing state
and acquired knowledge should make familiar situations cheaper to handle.
Whether that works is measured; replacing every independent classification
update with an iterative solve does not establish this operating model.

A Cadence brain can be deep. Depth adds populations or regions to the one
settlement, and the learning stays local at every depth.

| | Feed-forward deep network | Cadence brain |
| --- | --- | --- |
| An answer | The output of one pass through the layers | The settled state of the whole brain, a consensus among its patches |
| Influence while answering | Input to output only | Both ways: patches read one another and settle together |
| Learning | An output error sent backwards through every layer | An outcome disturbs the equilibrium, local repair settles a new one |
| Depth | More layers in the forward and the backward pass | More patches in the same settlement |
| Lifetime in this comparison | Independent inputs and explicit supervised updates | Bootstrap, continuing settled behavior and witnessed local repair |

Rover Lab and Patch World draw the patches and their prediction errors while
they settle, Atari Arcade shows the settled state behind every action, and Eyes
shows the whole brain settling for one eye's stream. Amen
runs a record patch, an advanced engine whose learning rule is stated in its
section below. The library README has
[the full comparison](https://github.com/muellerberndt/cadence#how-a-cadence-brain-differs-from-a-feed-forward-network).

## The demos

| Demo | What it shows | Runs on |
| --- | --- | --- |
| [Rover Lab](rover-lab/) | A live body model that adapts from measured motion after a motor bootstrap | The population solver; in the browser, a JavaScript version of it |
| [Patch World](patch-world/) | Brains that learn in the browser and evolve across generations | A JavaScript version of the population solver |
| [Atari Arcade](atari-arcade/) | Brains that learn Atari games from pixels: a teacher first, then reward | `Brain.compose` (System 1); in the browser, a JavaScript version of it |
| [Amen](amen/) | A record patch composing jungle tracks in the browser | A brain trained with `RecordPatchNet`; the page runs a JavaScript version of its forward pass |
| [Eyes](eyes/) | One brain that follows every shape you drag with its own eye, from the page's pixels only | A hand-wired connectome run by `cadence.Brain`; in the browser, the released library itself, in Pyodide |
| [Key door](keydoor/) | One continuing creature, fed and calm, that starves, rouses and searches when you move its key, and settles again | `Brain.compose` through `Brain.live`; in the browser, the released library itself, in Pyodide |

Rover Lab and Patch World run on the population solver, Atari Arcade on
`Brain.compose`, Amen on a record patch, Eyes on a hand-wired connectome
run by `cadence.Brain`, and Key door on `Brain.compose` through `Brain.live`, the
routine-and-repair loop of one continuing life. Each demo's README names the
Cadence version it was built with.

## [Rover Lab](rover-lab/): a body model that keeps learning

A simulated rover learns how its wheel commands turn into motion. Weaken its
right wheel and watch a learning Cadence brain adjust its predictions and keep
reaching targets, beside a frozen copy, an adaptive estimator and a small neural
network. The brain is three small populations of patches that read the motor
commands and one another's states and settle together. Error-reading observers
are an optional extra arm. The whole lab also runs in the browser, on a
JavaScript version of the same solver (`rover-lab/web/`).

```sh
cd rover-lab
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py        # http://localhost:8670
python3 -m http.server 8080 --directory web   # the browser edition at http://localhost:8080/
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
instrument. The brain was trained from random parameters in 78 CPU minutes on a
laptop. Its slow parameters learn by a gradient step over
32 half-beats that is kept only when a replay confirms it, and its records are
written in one shot.

```sh
python -m http.server -d amen/web 8803   # open http://localhost:8803 and press CUT A DUB
```

See the [Amen README](amen/README.md).

## [Eyes](eyes/): one brain, an eye on every shape

Shapes on a large surface, each followed by its own eye, by one Cadence brain
that runs in the browser tab and sees only the page's pixels. Each eye sees
sharply at its centre and coarsely around it, and sees what changed since the
last frame, so when you drag a shape away one saccade can bring it back. When
nothing moves, the brain settles nothing. The brain was raised offline and runs
frozen in the page, on the released Cadence wheel in Pyodide.

```sh
python -m http.server -d eyes/web 8797   # open http://localhost:8797/
```

See the [Eyes README](eyes/README.md).
