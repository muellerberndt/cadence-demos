# Out of sight

Hide the hand behind the blind spot, and the brain keeps knowing where it is.

A table seen from above: a robot arm, a hand, a cup, a wrench and a box, and a camera in the
corner whose view a pillar and the arm cut into light and shadow. A Cadence brain is asked at
every moment where the hand is, in view and out of view. The page is one screen: the scene on
the left, with the brain's answer drawn on it (a glowing peak inside the area the brain says
holds the hand nine times in ten, and a pin for every thing it remembers), and on the right the
whole brain, every neuron and every synapse, laid out as a brain seen from the side. The scene
and the brain run in the browser. There is no server.

This is the demonstration page of
[cadence#320](https://github.com/muellerberndt/cadence/issues/320), spatial object awareness:
a map that holds where things are while they are out of view.

> **Status: under construction on the branch `space`.** The page runs the **untrained
> baseline**: a plain composed brain (`Brain.compose` with `PopulationCode` inputs, asked for
> the hand's place as two motor slots of 20 units), born when the page loads and taught the
> camera's report at every moment the hand is in view. It holds no place between moments
> beyond its working trace, so it does not keep the promise above: the page check below reads
> 28 of 32 checks, and the four it fails are the brain's own. The trained place module takes
> its seat through `site/pack/manifest.json`; the model card arrives with it.

![The hand hidden behind the pillar, the place part's card open](docs/baseline-hidden-card.jpg)

## What a visitor does

Everything is direct: there is no panel of switches.

- **Drag the hand** with the mouse or a finger, into the pillar's shadow and out of it.
- **Drag the pillar**, and the shadow moves with it. **Tap the camera** to switch it off:
  nothing is in view.
- **Drag a thing** (the cup, the wrench, the box) while the camera cannot see it: its pin stays
  at the place it was last seen.
- **Tap a thing** to knock on it: the ear hears the direction and the distance of the sound, and
  the record moves without sight. A dashed pin came from a sound.
- **Undo** takes the last move back; **Reset** puts everything where it stood.

A tutorial of five steps, which the visitor performs, opens on the first visit: follow, hide,
return, move the cup while it is hidden, knock. It can be skipped and played again.

Keys, with the scene in focus: `1` to `5` choose the hand, the cup, the wrench, the box or the
pillar; the arrows move it; `K` knocks on it; `C` switches the camera; `H` shows or hides what
the camera cannot see; `Z` is undo and `R` reset. In the brain, `Tab` moves from part to part.

## The brain explains itself

Nothing is written over the brain until the visitor points at something. Every part (a
population, the records, a fibre tract) opens a card on hover, on a tap and on keyboard focus:
its name, the role it plays, what it does in one or two plain sentences, and what it is doing at
this moment, written from the brain's live state ("It says the hand is at (-0.17, 0.71) m,
unseen for 25 moments. Uncertainty 99 cm, up from 92 cm when the hand was last seen."). Cards of
population codes draw the peak over their tuned units as it stands.

**Follow the position** steps through the path of a position in eight stages, each with its
part ringed and its live numbers: what the camera reports; how a position becomes activity; the
place and what holds it; how it moves while unseen; how sight corrects it; doubt; things that
stay put; the answer. The texts are in `site/cards.js`, keyed by the brain's kind: they describe
the baseline brain, and the three stages the trained place module does another way say so on
their cards.

Every population sits in the region whose role it plays. The page names the role; it claims
nothing about what the neurons are.

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
- A settle that finds no qualified state gives no answer; the page counts it (Details, "No
  answer").

## Details

One switch, off until asked for, holds the rest: the last seen position and a constant-velocity
Kalman filter as thin markers and their distance from the true hand on a chart (both are ports
of the tracking chamber's controls); the map the brain holds; the settle's sweeps and residual;
the arm's own hand in place of a person's; recorded scenes; and **Load a scene**, which replays
a scene file of the tracking chamber (`cadence-tracking-scene/1`, also by dropping the file on
the page). A replay gives the brain exactly what the file holds: its reports, its in-view flags,
its commands and joint readings. Scenes of one thing and of several read alike.

## Run it locally

```sh
python3 -m http.server 8840 --directory site   # from out-of-sight/; then open http://127.0.0.1:8840/
```

The first visit downloads Pyodide and NumPy from jsDelivr (about 10 MB) and the page's own
files (about 1 MB). `?tour=1` starts the tutorial and `?tour=0` skips it, `?autoplay=N` plays
recorded scene `N`, `?renderer=2d` draws the brain with Canvas2D, `?wave=0` turns the
sweep-by-sweep replay off, `?details=1` opens the details and `?sound=0` keeps the knock silent.

## Files

| Path | What |
| --- | --- |
| `site/index.html`, `site/styles.css`, `site/favicon.svg` | the page |
| `site/app.js` | the loop, dragging and tapping, undo and reset, the tutorial, the cards, scene files |
| `site/world.js` | the scene's geometry, the camera's view, the ear's cue, the step and the scene file reader: a port of the tracking chamber's world |
| `site/controls.js` | the last seen position and the Kalman filter: a port of the chamber's controls |
| `site/scene.js` | the scene, the map and the chart |
| `site/brain.js` | the brain view (WebGL2, with a Canvas2D fallback) and its self-explaining parts |
| `site/cards.js` | what every part says about itself, and the eight stages of a position's path |
| `site/worker.js` | Pyodide, the Cadence wheel and the host, checked against `pack/manifest.json` |
| `site/pack/` | the wheel, the host (`py/spacebrain/host.py`), `reaches.json`, `manifest.json` with SHA-256 |
| `tools/build.py` | builds `site/pack/` from the released wheel, with the place module's files where given |
| `tools/record_scenes.py` | records the parity fixtures and the page's scenes with the Python world |
| `tools/check_page.py` | the promise in headless Chromium; writes `evidence/page_check.json` |
| `tests/parity.mjs`, `tests/fixtures/` | the parity test of `site/world.js` and `site/controls.js`, its recorded steps and the chamber's example scene |

## Checks

```sh
node tests/parity.mjs                    # the page's world and controls against the Python ones
python tools/check_page.py --shots docs  # the promise, with the mouse a visitor uses
```

**Parity.** `tests/parity.mjs` replays 340 steps recorded by the tracking chamber's Python world
(`benchmarks/tracking` of the library's branch `lane-099-space` at c3b6d611: the arm's own hand
on a sweep; a person's hand that keeps its line, slows, stops and turns; things that are carried
and that sound) with the same commands, moves, sounds and standard normal draws. Every true
position, camera report, ear cue and joint reading agrees to 1e-12 and every in-view flag is the
same, as is the camera's view at 4,515 points of the plane. Five scene files (the chamber's
example, the least a file may hold, the arm's own hand, a room of four things) read into the
same arrays as the chamber's own reader gives, and the stage replays each one row for row. The
last seen position and the Kalman filter agree with the chamber's on three scenes to 1e-12.

**The promise.** `tools/check_page.py` performs the tutorial's five steps with real pointer
input and reads what the brain did at each from the page's own record, against bounds set
before the trained brain was read: in view the place within 5 cm of the hand; hidden, within
10 cm, with the stated area holding the hand on at least 85 of 100 moments, no lesson, and the
place part's card showing a position and a growing uncertainty; back in view, within 5 cm and
the uncertainty lower; the cup's record at the place it was last seen while it is moved unseen;
after one knock, within three standard deviations of the cue's own error of the true place.
It then opens every part's card by hover and by keyboard, steps through the eight stages, tries
undo, the camera, reset, the details switch and a scene file, and measures the frame time on a
desktop (WebGL2), a phone-sized touch screen and the Canvas2D view.

The reading on the **untrained baseline** (`evidence/page_check.json`, 12 November 2026): 28 of
32 checks. The page's own checks pass: the tutorial's steps complete on a visitor's input, the
cards and the stages open, undo, reset and the scene file work, and a frame takes 16.7 ms at the
median and 16.8 ms at the 95th percentile with the brain view on (the brain answers a moment in
14 ms in the worker). The four that fail are the brain's: 20 cm in view after 245 lessons from
birth, 15 cm while hidden (the last seen position 17 cm, the Kalman filter 14 cm), an
uncertainty that does not grow, and 19 cm after the return. The baseline is not the model.

Cadence is GPL-3.0.
