# Model card: the what-where map

This card describes the map the Out of sight page runs: `cadence.space.map.Map`, the brain's
map of things. The map is the brain's own state: a sheet of cells whose settled activity is
carried from moment to moment. No list of things is given to it and none is kept beside it. A
thing enters the map at the moment a sense first reports it. The map's graph has no taught
synapse: it is wiring and carried activity.

| | |
| --- | --- |
| Demo | Out of sight (`out-of-sight/`) |
| File | `site/pack/map/page-map.npz` · 1,577 bytes · SHA-256 `6fc3a93cad2f5400…` · format `cadence-space-map/1` (the map's settings, its kinds' codes and an empty carried state; arrays and one JSON record, no pickled object) |
| Library | `cadence-net` 0.98.0, a development wheel built from the library's branch lane-099-space at fac45529 (git archive and pip wheel); it holds `cadence.space.map`, which PyPI's 0.98.0 does not (SHA-256 `70589f3fee4d2e69…`), CPU, in Pyodide 314.0.7 |
| Loaded by | `Map.load(path)` (`site/pack/py/spacebrain/map_host.py`); `trace` is switched on for the moments the brain view plays a settle's wave, and for every question |
| Size | 29,168 neurons, 39,936 synapses, none taught: `map` 13,312, `held` 13,312, `reference` 16, `where` 832, `what` 16, `clock` 832, `doubt` 832, `lost` 16 |
| Settings | 32 by 26 cells of 6.25 cm by 6.15 cm over a plane of 2 m by 1.6 m; 16 code units a cell, one a kind; `level` 0.02; `empty` "near", `reach` 0.15 m; `step` 0.15 m; `stride` 0.5 m; `margin` 0.02 m, the camera's error (the guide's founder) |
| Date | 2026-11-12 |

The development wheel and the map file sit on the branch `space` only. Before any pull request
they are replaced by the released wheel and the map the library ships.

## What the program does and what the brain does

The guide of the wheel's commit (`docs/space.md`, "What the brain does and what the program
does") states it row by row; the page's cards carry those rows beside the steps they belong to.
In short: the program beside the map copies the sheet's potentials to the next moment's drive on
the same neurons, turns a report (a kind and a place) into a drive on four cells, passes the
cells the camera sees as the settle's mask, finds a piece of activity whose place is seen empty
and drives it onto the unseen cells within reach, sets a question's cue, and reads the
inventory off the peaks. The brain (the map's graph) holds every place in its settled activity,
holds a seen cell at zero in every sweep, and settles `where` and `what` on a question's answer.
Lessons: none on either side.

## How the page drives it

At every moment of the scene (30 a second) the page sends one `moment`:

- `seen`: what the camera reports, a kind and a place for each thing in view, nothing for a thing
  out of view. Kinds: the hand 0, the arm's own hand 1, the apple 2, the bread 3.
- `lit`: what the camera sees, as a function of places, by the page's own rule for what the
  camera sees (`visible` of `site/world.js`, a port of the tracking chamber's rule): at the map's
  cells' middles the worker's flags for the moment, at any other place (where the map holds a
  thing) the worker asked through Pyodide; nothing while the camera is off.
- `felt`: for the arm's own hand, the place its joint readings name. The page works the place
  out from the readings (forward kinematics, a program's step) and gives it to the map as what
  the body's own sense reports.
- `heard`: the place a sound names, where a scene file holds a sound.

The page draws each thing from its inventory entry: its place, its cells (as soft light, each
cell by its activity on the map), its state and the moments since a sense wrote it. Two places
of one kind (a thing left where it was, and one sensed since) are two entries; the page follows
the one a sense wrote last. A question is a settle: a tap on a thing asks `where_is`, a tap on
the floor `what_is_at`.

## Readings on the page

The promise, replayed on the page from the two scene files of the tracking chamber (a hand goes
behind the pillar at 0.5 m/s, rests there for 70 moments and comes back; 323 moments, 91 of them
with the hand out of view), as `tools/check_page.py` reads it (`evidence/page_check-20261112-2350-70589f3f.json`,
2026-11-12 23:50, on the wheel of fac45529):

| Scene file | In view | Hidden, mean | Last seen, hidden | Kalman filter, hidden | The hand's cells hold it | Its cells, mean | Back in view | A moment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| the arm folded (`promise-scene.json`) | 1.2 cm | 10.7 cm | 15.5 cm | 27.8 cm | 1.00 | 39 | 1.0 cm | 13 ms |
| the arm's shadow joined to the pillar's (`promise-merged-shadows-scene.json`) | 1.2 cm | 10.7 cm | 15.5 cm | 27.8 cm | 1.00 | 39 | 1.0 cm | 11 ms |

The map holds the hand near where it vanished on every hidden moment, and its cells hold the
true hand on every hidden moment of both files. The page's readings are the model's own on the
same files: `tests/test_map_host.py` drives the host natively on the pack's wheel and map file and
reads the same inventory as `Map` driven directly. The map holds no randomness: replays read
alike to the digit (`tools/promise_runs.py`; `evidence/promise_runs-20261112-2326-c7088cf0.json`, on the wheel of 38820655).

The arm's own hand, out of the camera's view and moved by the arm, in the tutorial's last step:
0.5 mm from the hand on average over 60 hidden moments, 1.2 mm at worst (bound 1.5 cm).

A frame took 16.7 ms at the median and 16.7 ms at the 95th percentile with the
brain view and its bloom on (bounds 20 ms and 34 ms); a moment of the map, with its inventory and
every neuron's activity for the brain view, took 12.0 ms of the scene's 33 ms at the median. These
were read with the Mac's load average at 60 to 90 from other work: upper bounds.

## Limits

- The map moves nothing it does not sense. A hand that keeps going in the dark is held near where
  it vanished, within 30 cm (two reaches) of it; a hand that comes out farther away is found
  there as the same thing (within `stride`, 0.5 m) or as a new one. Learning how things move is
  the second stage of the model, and nothing on this page anticipates a movement.
- A thing whose place is seen empty with no cell out of sight within reach is known by its kind
  with no place ("not known where") until a sense reports it.
- Recognising a thing is not the map's work: the page tells the map the kind of each report.
- The arm's own hand is placed by its joint readings through the page's kinematics; a taught
  projection of the readings onto the map (`cadence.space.map.Sense`) is not on this page.
- One map file of the founder's settings. These are a page's readings, not the gates of
  [cadence#320](https://github.com/muellerberndt/cadence/issues/320).

## Licence

GPL-3.0, as Cadence.
