# Out of sight

Hide the hand behind the blind spot, and the brain keeps knowing where it is.

A table seen from above: a robot arm, a hand, a cup, a wrench and a box, and a camera in the
corner whose view a screen and the arm cut into light and shadow. A Cadence brain is asked at
every moment where the hand is, in view and out of view. The page draws its answer on the
table (a glowing peak inside the area the brain says holds the hand nine times in ten), a pin
for every thing it remembers, the map it holds, and the whole brain: every neuron and every
synapse, laid out as a brain seen from the side. The scene and the brain run in the browser.
There is no server.

This is the demonstration page of
[cadence#320](https://github.com/muellerberndt/cadence/issues/320), spatial object awareness:
a map that holds where things are while they are out of view.

> **Status: under construction on the branch `space`.** The page runs the **untrained
> baseline**: a plain composed brain (`Brain.compose` with `PopulationCode` inputs, asked for
> the hand's place as two motor slots of 20 bins), born when the page loads and taught the
> camera's reading at every moment the hand is in view. It holds no place between moments
> beyond its working trace, so it does not keep the promise above; it is the stand-in that
> makes every pixel real state while the trained brain is raised. The model card, the promise
> test's reading and the frame times arrive with the trained brain.

## What a visitor can do

- **Drag the hand** with the mouse or a finger, into the screen's shadow and out of it, or play
  a recorded reach (scenes recorded by the tracking chamber's Python world).
- **Drag the screen**, or **switch the camera off**: nothing is in view.
- **Move a thing** (the cup, the wrench, the box) while the camera cannot see it: its pin stays
  at the old place until the thing is seen again.
- **Knock** on a thing: the ear hears the direction and the distance of the sound, and the
  record moves without sight. A dashed pin came from a sound.
- **Compare**: the last seen position and a constant-velocity Kalman filter's estimate as thin
  markers, and each estimate's distance from the true hand on the chart.
- **Hover** over a population of the brain to read what it holds and whose role it plays.

Keys, with the scene in focus: `1` to `5` choose the hand, the cup, the wrench, the box or the
screen; the arrows move it; `K` knocks on it; `C` switches the camera; `H` shows or hides what
the camera cannot see; `Space` plays the reach.

## What is drawn of the brain

Every population sits in the region of a brain seen from the side whose role it plays. The page
names the role; it claims nothing about what the neurons are.

| Population (baseline brain) | Plays the role of |
| --- | --- |
| `sensory`, the camera's report: 16 tuned inputs for x, 16 for y, and one input that is on while the hand is in view | visual cortex |
| `sensory`, the arm's joint readings: 12 tuned inputs a joint | somatosensory strip |
| `sensory`, the arm's commands as a copy: 9 tuned inputs a joint | motor strip and the copy of its commands |
| `association`, 96 neurons | association cortex |
| `prefrontal`, the working trace, 96 neurons | prefrontal working memory |
| `motor`, the place answer: 20 units for x, 20 for y, each axis one softmax | parietal and entorhinal map |
| the records, a `LongTermMemory` of 12 slots beside the brain, keyed by what a thing is | hippocampus |

- A synapse glows with the signal it carries, `|weight x presynaptic activation|`, warm where it
  excites and cool where it inhibits; all 24,096 are drawn, bundled into tracts between regions.
- Every third moment the settle plays sweep by sweep: the worker settles the brain again from
  the state the moment started from, under the same drive, for exactly the sweeps the answer
  took, and sends up to 16 of them. The host checks that the last sweep is the state the answer
  was read from and sends nothing otherwise.
- A lesson's changed synapses flash, gold where they grew and blue where they shrank, and the
  outline glows. Lessons happen only at moments the camera sees the hand.
- A record's cell lights when the record is read or written; its thumbnail shows the place it
  holds.
- A settle that finds no qualified state gives no answer; the page counts it under "No answer".

## Run it locally

```sh
python3 -m http.server 8840 --directory site   # from out-of-sight/; then open http://127.0.0.1:8840/
```

The first visit downloads Pyodide and NumPy from jsDelivr (about 10 MB) and the page's own
files (about 1 MB). `?autoplay=N` plays recorded reach `N` once the brain is ready,
`?renderer=2d` draws the brain with Canvas2D, `?wave=0` turns the sweep-by-sweep replay off and
`?sound=0` keeps the knock silent.

## Files

| Path | What |
| --- | --- |
| `site/index.html`, `site/styles.css`, `site/favicon.svg` | the page |
| `site/app.js` | the loop, the controls, the worker's client |
| `site/world.js` | the scene's geometry, the camera's view, the ear's cue and the step: a port of the tracking chamber's world |
| `site/controls.js` | the last seen position and the Kalman filter |
| `site/scene.js` | the scene, the map and the chart |
| `site/brain.js` | the brain view (WebGL2, with a Canvas2D fallback) |
| `site/worker.js` | Pyodide, the Cadence wheel and the host, checked against `pack/manifest.json` |
| `site/pack/` | the wheel, the host (`py/spacebrain/host.py`), `reaches.json`, `manifest.json` with SHA-256 |
| `tools/build.py` | builds `site/pack/` from the released wheel |
| `tools/record_scenes.py` | records the parity fixtures and the reaches with the Python world |
| `tests/parity.mjs`, `tests/fixtures/steps.json` | the parity test of `site/world.js` and its recorded steps |

## Checks

```sh
node tests/parity.mjs        # site/world.js against steps recorded by the Python world
```

`tests/parity.mjs` replays 400 recorded steps of the Python world (the arm's own hand on a
sweep; a person's hand that keeps its line, slows, stops and turns; things that are carried
and that sound) with the same commands, moves, sounds and standard normal draws. Every true
position, camera report, ear cue and joint reading agrees to 1e-12 and every in-view flag is
the same, as is the camera's view at 4,515 points of the plane.

Cadence is GPL-3.0.
