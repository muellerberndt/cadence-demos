# Key door

One continuing Cadence creature walks a corridor in a browser tab: floor, a chest, a lamp, a
few levers, a door. The key is in the chest; opening the door with the key pays, and touching
anything without a key costs. The creature arrives mid-life, raised through 500 trips, fed and
calm: it answers every cell from one settle and learns nothing. Move the key to the lamp and
watch it starve, rouse, search at a cost, find the key in the lamp, and settle again. The brain
learns in the page, in Pyodide, on the released library.

```sh
python -m http.server -d keydoor/web 8798     # open http://localhost:8798/
```

## What it demonstrates

- **Routine and repair in one life.** While fed, the creature's arousal stays below its
  threshold: every answer is the greedy choice of one qualified settle, with no learning, no
  memory write and no eligibility. When its food stops, its need is unmet, it is roused,
  samples at a raised temperature, keeps eligibility, learns from every outcome and writes
  memory; when it is fed again it returns to routine. The page shows the mode, the want, the
  level and the heat of every moment, and the share of moments in each mode.
- **Delayed credit across distractors.** Taking the key pays nothing; its worth arrives at the
  door, after the levers. The creature learns to take it at the chest, and after the move at
  the lamp, and to leave the levers alone.
- **Useful exploration at a cost.** The search after the move touches the chest, the levers
  and the lamp and pays for every wrong touch; the chart shows the wrong interactions per trip
  rising during the search and falling once the key is found. The probability of interacting
  at every kind of cell, under the behaviour that acted and under the base policy, is read
  from the living brain.
- **Exactly-once outcomes and a saved continuation.** The outcome of every action is delivered
  with the next observation, once; a trip cut before the door ends with `done` clear and its
  forecast carries over; a refused answer keeps its outcome in the brain for one retry and is
  reported. Save the brain mid-trip and restore it: it continues from the saved moment while
  the world goes on.
- **A newborn, for contrast.** Start a newborn brain at the same operating point and watch it
  acquire the task from nothing, at delay 2, 5 or 10.

## What the creature is

The frozen protocol of Cadence's key-door nursery (`benchmarks/keydoor`, issue 111 of the
library): `Brain.compose(6, 2, modules=(32,))` with `ArousalConfig(need=0.03)` at the
founders, working-trace amplitude 0.3, consolidation 0.25, actor rate 0.1 with a bias rate of
0.01, eligibility decay 0.95, discount 0.95 and critic rate 5.0, through `Brain.live`. The
world is the chamber's: 14 cells per trip, the levers varying by one, a cost of 0.25, one trip
in twenty cut before the door. The creature shipped with the page was raised through rule A
for 500 trips at delay 5 (`raise_creature.py --seed 5 --delay 5`): fed on all of its last 50
trips with 0.08 wrong interactions per trip, aroused on 0.1% of the moments of its second
half, the first 20-trip window at 90% fed from trip 47. It is saved at the end of a trip with
the door's outcome pending, exactly as the page resumes it. Nothing of rule B was lived before
the page: the key moves only when you move it.

## How it is built

| Path | What |
| --- | --- |
| `keydoor/world.py` | the corridor, its outcomes, the cut trips and the exactly-once feedback |
| `keydoor/host.py` | what the page's worker runs in Pyodide: one moment at a time, the readings, the messages |
| `raise_creature.py` | raises the creature through rule A and saves it |
| `pack.py` | packs a raised creature for the page (`web/pack/`): the brain, the released wheel, the sources, a manifest with their hashes |
| `web/` | the page: `keydoor.js` (the corridor, the charts, the controls), `worker.js` (Pyodide and the creature) |
| `check_page.py` | the page's promise, tried end to end in a headless Chrome |
| `tests/` | the world against the chamber's code, the host's messages, the continuation, a refusal |
| `evidence/` | receipts |

The world module is compared against the chamber's own (`tests/test_world.py`, with
`CADENCE_REPO` pointing at a Cadence checkout): the same corridor sequence per seed, the same
constants, the same operating point and need as the frozen protocol.

## Limits

- The page runs one creature at one delay; the chamber's evidence, with its controls and its
  confirmation seeds, is in the library's `benchmarks/keydoor/README.md`. This page is a
  demonstration of the mechanism, not a measurement.
- A fed and calm creature does not unlearn a cheap habit: routine learns nothing by design.
  Some raised creatures touch the lamp while already holding the key; the shipped one does not.
- The search after the move can fail: the chamber recorded lives that latched after the key
  moved. The page's check requires the shipped creature to find the key within 150 trips on
  the check's own run; a visitor's run has its own chance.
- Pyodide's numpy is 32-bit; the host applies the same `np.repeat` shim as the Eyes demo. The
  brain is otherwise the released library, unmodified.
