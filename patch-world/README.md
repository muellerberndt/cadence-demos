# Patch World

An evolving world in one page. A conserved-mass torus under a moving sun,
inhabited by creatures whose brains follow the population solver of
[Cadence](https://github.com/muellerberndt/cadence) 0.70.0. Each brain is born
from an inherited body plan, settles jointly every tick, learns within one life,
and pays mass for every patch, every relation and every repair sweep. Nothing
tells the creatures to graze, hunt, hoard or speak; whatever you see them doing,
they found within the supplied world, action set and reward/selection rules.

This population experiment starts each new creature with fresh relations. It
is a specific evolutionary control, not a requirement to recreate a Cadence
brain for every observation or application session. New applications should
follow the [world-model guide](https://github.com/muellerberndt/cadence/blob/main/docs/world-model.md):
a bootstrapped continuing reciprocal patch brain, useful short-term context,
durable knowledge with declared writes and reads, normal settled behavior and
local repair of witnessed mismatches or failures. Deep System 1 can provide
that foundation; System 2 is optional.

The current page has no event custody or saved continuation, as disclosed
below. It therefore does not demonstrate exactly-once correction identity or
the full memory contract. A future continuation experiment must add and test
those mechanisms, retaining fresh-start, memory-intervention and repair-schedule
controls. Count routine and repair work separately. The world's metabolic mass
price is a declared simulation resource model, not measured physical energy;
qualified settlement and survival here do not guarantee general intelligence
or an efficiency advantage.

## What it demonstrates

- **Learning in the browser.** Every creature's brain learns while the page
  runs, inside the browser tab, from the mass that followed its own action.
  There is no server and no pre-trained model: a newborn starts with random
  relations.
- **No training mode.** Acting and learning are the same life. Each tick a
  brain settles on what it senses, acts, and repairs its relations from the
  outcome, for as long as it lives.
- **Brain evolution.** The brain's shape is inherited as a body plan and
  mutates at every birth: width, depth, observers, fan-in, senses, plasticity.
  Energy and death are the only selection, so the population's brains are the
  ones that pay for themselves.
- **Observers as an option.** The founders have plain state-coupled brains.
  Mutation can add observer stages that read prediction errors, and selection
  decides whether they stay.
- **Settling and refusal.** An action is the settled state of the whole brain.
  A solve that does not settle is refused and the creature waits.
- **Private imagination.** With a horizon above zero a creature settles the
  readings its moves would produce before it chooses, without touching its live
  state.

## How it is built

The page is `page.html` plus `core.js`, joined into the single file
`index.html` by `python3 build.py`. `core.js` holds the world, the genome, the
brain and the population with no page code in it, so the same file runs
headless under Node in `probe.js` and `test.js`.

The retained population-solver example writes a founder as three populations
that settle together, with one policy patch per action. This demonstrates that
engine's contract; use `Brain.compose` as the primary entry for new integrated
brains:

```python
from cadence.experimental.equilibrium import Cortex, Reinforcement

ACTIONS = ("north", "east", "south", "west", "eat", "wait")

cortex = Cortex(seed=7, fan_in=9, parameter_prior=0.3, tolerance=1e-3, settle_budget=64)
senses = cortex.input("senses", shape=106)
perception = cortex.column("perception", patches=10, inputs=senses)
stage = cortex.column("stage", patches=8, inputs=(senses, perception))
policy = cortex.column("policy", patches=6, inputs=(senses, perception, stage))
# an observer policy also reads the errors of the stages below:
# policy = cortex.observer("policy", patches=6, inputs=senses, observes=(perception, stage))
for index, name in enumerate(ACTIONS):
    cortex.output(name, shape=1, reads=policy, indices=(index,))
brain = cortex.build()

creature = Reinforcement(brain, actions=len(ACTIONS), action_input=None,
                         value_output=ACTIONS, discount=0.6, exploration=0.1, reward_scale=4.0)

decision = creature.act({"senses": reading})                 # settle, then choose
creature.feedback(reward, {"senses": next_reading},          # learn from what followed
                  decision_id=decision["decision_id"], executed_action=decision["action"])
```

[library_brain.py](library_brain.py) is that brain as a runnable script on a
toy feeding task. The page does the same in JavaScript, hundreds of brains at a
time: `core.js` develops each brain from its genome and implements the same
patch law, repair rule and value target. `parity.py` writes reference values
with the library and `node test.js` checks `core.js` against them.

Evolution is a few lines of `core.js`: a creature above its energy threshold
splits, the child takes half the energy and `mutate(genome)`, and a new brain
is developed from that genome with fresh relations.

## Brain layout

A creature's brain is one connected settlement. A perception population reads
the senses. Each stage above reads the senses and the live states of every
earlier stage, and the last stage's patches are the action values. All patches
repair one joint energy in a single solve per tick.

Observers are optional and inherited. A gene turns the top stages into
observers, which also read the exact prediction errors of every earlier stage
inside the same solve. The founders carry none. Mutation can add or remove an
observer stage, an observer spends a third of its fan-in on errors, and
selection decides whether the lineage keeps it.

Cadence 0.70.0 requires every patch to settle against other patches. The
developed wiring guarantees it: every patch above perception holds a chain of
contacts into the stage below, consecutive patches share a source, and
`test.js` develops 3,840 body plans across the gene ranges and three rule sets
and checks each for one connected component.

The brains run on `core.js`, a JavaScript implementation of the population
solver `cadence.experimental.equilibrium`, with the numerical differences
described below. The page does not run the Python package. Cadence's main
`Brain.compose` interface, with its working trace and associative memory, is a
different engine and is not part of this page. See the
[population solver guide](https://github.com/muellerberndt/cadence/blob/v0.70.0/docs/equilibrium/README.md).

## Run

```sh
python3 -m http.server 8080
```

Open [http://localhost:8080/](http://localhost:8080/). The page is one file;
it loads three.js and two typefaces from a CDN and nothing else. `index.html`
is built from `page.html` and `core.js` by `python3 build.py`.

Keys `1` `2` `3` switch the view: what is, what is known by the living
observers together, what one creature believes. Space pauses. Drag to orbit,
wheel to zoom, shift-drag to pan. Click a creature to open its brain: the sensed
window, the stages settling live with their prediction errors, the state rail
on the left and the red error rail of an observer on the right, the action
values, and the solve counts. **An observer** selects a creature that carries
observer stages. The checkboxes seed the next world with different physics. The
clock runs as many ticks as fit each frame and the counters show the achieved
rate beside the requested one.

## The world

One quantity, mass, in integer units, in exactly one place at every tick:
soil, food, or a creature. A band of sunlight crosses the torus and grows food
where it passes; food decays, soil diffuses, and everything a creature spends
returns to the soil under it. The optional rules are one flag each: ripening
food, rock, night, two kinds of ground, biting, carrying soil, slow digestion.
Splits are automatic above an inherited energy threshold; the child takes half
the energy and a mutated genome, never the parent's learned relations. Energy
and death are the only selection.

## The being

The genome is a body plan: the window radius, the perception width, the number
of stages above perception (one to four), the number of those stages that are
observers (zero to four, capped at the depth), the fan-in, the parameter prior,
the horizon, the exploration, the discount, the symbols it can utter, a mask
naming which sense groups reach the brain at all, and a wiring seed.

The brain it develops is an observer-like self-reading system: bounded patches
with local state, each predicting its own state through one learned relation
(`p = tanh(b + w·signals)`, `e = x − p`), ports onto the senses and onto other
patches, readback of live states and, in observer stages, of prediction errors.
One joint energy couples all of it; a tick is one settle, and the settled policy
states are the action values. With a horizon above zero the creature searches
through hypothetical settles of the readings its moves would produce; these
private settles leave its live state and relations untouched. Learning is
anchored parameter repair toward a one-step value target of the mass that
followed its own action. A solve that does not reach stationarity refuses and
retains nothing: a refused settle waits, in the open, and the counts are on
the page.

Metabolism prices the whole apparatus: existence, every sensed unit, every
patch, every relation, every accepted repair sweep, settling, imagining and
learning alike. A deeper, wider or observing brain is a metabolic trade, and
the population's brains are whatever survives that trade.

## The engine, disclosed

`core.js` implements the patch law and repair rule of the Cadence 0.70.0
population solver in JavaScript so a whole population runs in a browser tab:
the same energy, exact analytic gradients with transitive error feedback,
projected-gradient repair with sufficient-decrease backtracking, the
Barzilai–Borwein secant step with the library's step ceiling and its acceptance
rule at the rounding floor, fan-in-normalized initial relations with zero
biases, anchored learning with refusal custody, and the `Reinforcement`
helper's one-step value target.

`node test.js` compares it with the library. `parity.py` builds two small
brains with `cadence-net==0.70.0`, one state-coupled and one with an observer,
and writes the library's values to `fixtures/`. Loaded with the same graphs,
`core.js` reproduces the energy, the prediction errors and every derivative to
1e-12, the settled states to 1e-7, and the relations after one admitted witness
to 1e-7. The same file checks finite-difference derivatives in a developed
observer brain, refusal custody, private imagination, conserved mass and a
reproducible run.

It is a reimplementation, not the `cadence-net` engine. The page runs at
tolerance `1e-3` against the library default `1e-6`, with small sweep budgets.
Quiet transitions are admitted every fourth tick while rewarding ones always
are. `tanh` comes from table interpolation with error below `1e-5`; the library
comparison switches to exact `tanh`. Energies are added in floating point where
the library sums exactly, so the comparison solves stop at `1e-8`. There is no
event custody and there are no checkpoints. No observer or depth advantage is
claimed from this page; it shows what selection does with the price of depth
and of observation, and the lifetime tables are the only evidence it offers.

## Measurement and evidence

```sh
node test.js
node probe.js '{"ripen":true,"rock":true,"bite":true,"carry":true}' 6000 1 '{"read":0.0001}' > receipts/run.jsonl
python3 summarize.py receipts
```

The probe runs the same `core.js` headless and prints population statistics,
lifetime-at-death tables by patch count, depth, observer count, width and
horizon, the mask census, solve-qualification rates and symbol statistics.
`receipts/` holds two 6,000-tick seeds of the page's world.

In both runs the ecology holds around 430 to 440 creatures with mass conserved,
and at least 99 per cent of settles and every learning solve qualify. The
two-stage body plan outlives its shallower and deeper neighbours. Observer
stages spread to about half of one population and stayed rare in the other, and
in both runs creatures without observers lived longer than creatures with them.
Symbols stay at chance. Selection under a price, not a matched-control
comparison.
