# Patch World

An evolving world in one page. A conserved-mass torus under a moving sun,
inhabited by creatures whose brains are deep recursive settlement networks in
the [Cadence](https://github.com/muellerberndt/cadence) model — born from an
inherited body plan, settled jointly every tick, learning within one life, and
paying mass for every patch, every relation and every repair sweep. Nothing
tells them to graze, hunt, hoard or speak; whatever you see them doing, they
found.

## Brain layout

Patch World uses **recursive observer settlement**: perception reads the senses,
and observer stages read live states and prediction errors within one coupled
solve. Its genome varies observer depth. The implementation is the local
JavaScript `core.js`, with the numerical differences described below; the page
does not run the Python package.

Cadence 0.50.0 also supports flat settlement for direct sensory relations and
ordinary state-coupled settlement for learned intermediate representations.
All three library patterns use one settlement engine. This world explores
selection under the cost of observer depth; it provides no flat or state-only
control establishing a benefit from recursion. See the
[layout guide](https://github.com/muellerberndt/cadence/blob/main/docs/VARIANTS.md)
and [performance guide](https://github.com/muellerberndt/cadence/blob/main/docs/PERFORMANCE.md).

## Run it

```sh
python3 -m http.server 8080
```

Open [http://localhost:8080/](http://localhost:8080/). The page is one file;
it loads three.js and two typefaces from a CDN and nothing else.

Keys `1` `2` `3` switch the view — what is, what is known by the living
observers together, what one creature believes — and space pauses. Drag to
orbit, wheel to zoom, shift-drag to pan. Click a creature to open its brain:
the sensed window, the stages settling live with their prediction errors, the
action values, and the solve counts. The checkboxes seed the next world with
different physics. The clock runs as many ticks as fit each frame and the
counters show the achieved rate beside the requested one.

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
of recursive observer stages (one to four), the fan-in, the parameter prior,
the horizon, the exploration, the discount, the symbols it can utter, a mask
naming which sense groups reach the brain at all, and a wiring seed.

The brain it develops is an observer-like self-reading system: bounded patches
with local state, each predicting its inputs through one learned relation
(`p = tanh(b + w·signals)`, `e = x − p`), a perception population reading the
masked senses, and every stage above reading the senses too while observing
the states and prediction errors of all earlier stages. One joint energy
couples all of it; a tick is one settle, and the settled policy states are the
action values. With a horizon above zero the creature searches through
hypothetical settles of the readings its moves would produce. Learning is
anchored parameter repair toward a one-step value target of the mass that
followed its own action. A solve that does not reach stationarity refuses and
retains nothing: a refused settle waits, in the open, and the counts are on
the page.

Metabolism prices the whole apparatus — existence, every sensed unit, every
patch, every relation, every accepted repair sweep, settling, imagining and
learning alike — so a deeper or wider observer is a metabolic trade rather
than a free win, and the population's brains are whatever survives that trade.

## The engine, disclosed

`core.js` implements the Cadence patch law and repair rule in JavaScript so a
whole population runs in a browser tab: the same energy, exact analytic
gradients with transitive error feedback, projected-gradient repair with
sufficient-decrease backtracking and the Barzilai–Borwein secant step, and
anchored learning with refusal custody. It is a reimplementation, not the
`cadence-net` engine: tolerance `1e-3` against the library default `1e-6`,
small sweep budgets, quiet transitions admitted every fourth tick while
rewarding ones always are, `tanh` by table interpolation with error below
`1e-5`, and no event custody or checkpoints. No depth advantage is claimed
from this page; it shows what selection does with the price of depth, and the
lifetime tables are the only evidence it offers.

## Measure it

```sh
node probe.js '{"ripen":true,"rock":true,"bite":true,"carry":true}' 6000 1 '{"read":0.0001}' > receipts/run.jsonl
python3 summarize.py receipts
```

The probe runs the same `core.js` headless and prints population statistics,
lifetime-at-death tables by patch count, depth, width and horizon, the mask
census, solve-qualification rates and symbol statistics. `receipts/` holds two
6,000-tick seeds of the page's world: the ecology holds 352 and 375 creatures
with mass conserved and 96–100 per cent of solves qualifying; one move of
lookahead through hypothetical settles is carried by 91 and 72 per cent of the
final populations; the two-stage plan outlives its one- and three-stage
neighbours in both lifetime tables; every sense group stays read; symbols
stay at chance. Selection under a price, not a matched-control comparison.
