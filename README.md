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
- **Declared learning mechanisms.** The brains repair from local relations
  and measured outcomes, and each README states the learning rule it uses.

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

Atari Arcade shows the settled state behind every action, and Eyes shows the
whole brain settling for one eye's stream. The library README has
[the full comparison](https://github.com/muellerberndt/cadence#how-a-cadence-brain-differs-from-a-feed-forward-network).

## The demos

| Demo | What it shows | Runs on |
| --- | --- | --- |
| [Atari Arcade](atari-arcade/) | Brains that learn Atari games from pixels: a teacher first, then reward | `Brain.compose` (System 1); in the browser, the released library itself, in Pyodide |
| [Eyes](eyes/) | One brain that follows every shape you drag with its own eye, from the page's pixels only | A hand-wired connectome run by `cadence.Brain`; in the browser, the released library itself, in Pyodide |
| [Connectome](connectome/) | Teach a fish gaze circuit to hold, return and hold again on measured wiring; explore a larva with fixed connections | Cadence rate patches in JavaScript, with plastic fish connections and declared body models |
| [Robot Arm](robot-arm/) | A Franka Panda that picks up a block and places it in the bin you choose, under contact physics; move the bin while it carries the block and it follows | A deep `Brain.compose` taught by a scripted teacher in MuJoCo; in the browser, MuJoCo as WebAssembly and the released library itself, in Pyodide |

Atari Arcade and Robot Arm run on `Brain.compose`, and Eyes on a hand-wired
connectome run by `cadence.Brain`. Each demo's README names the Cadence version it was
built with.

## [Atari Arcade](atari-arcade/): learning Atari games

Brains born at server start learn Atari games from the raw screen while you
watch. Each one is a System 1 brain built with `Brain.compose`. It watches a
scripted teacher play, takes the controls once its own answers agree often
enough, and then keeps learning from the reward of its own actions. The page
shows the game beside the settled brain. Freeway and Atlantis also run entirely
in the browser: an Atari core and the released Cadence wheel, in Pyodide, in
web workers (`atari-arcade/web/`).

```sh
cd atari-arcade
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py        # http://localhost:8668
python3 -m http.server 8080 --directory web   # the browser edition at http://localhost:8080/
```

See the [Atari Arcade README](atari-arcade/README.md).

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

## [Connectome](connectome/): teach a compiled circuit

Measured animal wiring becomes a running Cadence patch net. Teach the fish **hold your
gaze**, then **let it return**, then hold again on the same brain. Its connection strengths
change through practice. Pausing learning retains them; reset starts them over.

The fish learns its gaze response from declared activity feedback. A fixed pilot supplies
swimming, hunting and escape. The Platynereis larva demonstrates a whole-body connectome
with fixed weights. The two preprints behind the construction are
[Agreement and Surprise](https://philpapers.org/rec/MUEAAS-2) and
[Cadence: Learning Through Local Patch Settlement](https://philpapers.org/rec/MUECAP-2).

```sh
python -m http.server -d connectome/web 8800   # open http://localhost:8800/
```

See the [Connectome README](connectome/README.md) to run, teach and check the demo.
| [Robot Arena](robot-arena/) | Robots assembled from parts, each with one continuing brain wired to every motor, raised in a nursery, evolved on a big machine and fighting live in the browser with a brain inspector | `Brain.compose` with one motor slot per motor, learning through `Brain.live`; in the browser, the released library itself, in Pyodide |

## [Robot Arena](robot-arena/): the Cadence Showcase League

Robots are built from a parts catalogue: a chassis, wheels or legs, arms with a spike, a
hammer or a spinner. Each robot is one continuing `Brain.compose` life whose motor cortex
has one slot per motor, so every motor is commanded by the same settled state; nothing
sits between the brain and the body. A newborn is raised in a nursery against a dummy
(progress and damage pay, ramming and the burn hurt), then fights ranked royales in a ring
that closes. Uniform random with the same body is the baseline of every count; a frozen
newborn is the control for learning. The leagues in the folder were raised on a laptop and
evolved for an hour on 192 vCPUs: lineages of mutants of the best bodies and genes, the
weakest third retired each generation.

The page (`robot-arena/showcase-app/`) runs the best six live in a web worker, the released
library in Pyodide, saves each brain in the browser after every fight and restores it on
the next visit; click a robot to watch its senses, its association cortex settling, the
motor slots and the arousal law deciding between routine and learning. The limits are
measured in `robot-arena/STATUS.md`: the brains learn to find and hit, the ranking moves
with what they learn, and their tactics are coarse.

See the [Robot Arena README](robot-arena/README.md) to run the league, the page and the
scripted check of the page's promise.

## [Robot Arm](robot-arm/): pick and place under contact physics

A Franka Panda in MuJoCo picks up a block and places it in the bin that a lit lamp names. Its
brain is one deep `Brain.compose` with three hidden regions and the apical compartment. It learned
the job during its life by imitating a scripted teacher. A disclosed inverse-kinematics reflex
turns its centimetre moves into joint targets. Read frozen on fresh trials, the page's brain places
0.955 of the blocks under randomized physics. On the hardest held-out physics it places 0.465,
where the teacher places 0.295. It also follows a target bin moved to places it never trained
with.

The page runs MuJoCo 3.17 as WebAssembly and the trained brain in Pyodide, and draws every neuron
after each decision. Drag the block and the bins, press Run, and move the bin while the arm
carries the block.

```sh
python -m http.server -d robot-arm/site 8830   # open http://localhost:8830/
```

See the [Robot Arm README](robot-arm/README.md) to train the brain, read it and check the page.
