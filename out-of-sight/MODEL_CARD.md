# Model card: the place module's development file (a feed-forward baseline)

This card describes the file the Out of sight page runs. It is the place module's development
file and a baseline by the project's rules: every synapse of its brain runs from the inputs
toward the outputs, so an answer is complete after three sweeps. A version that settles, with
the same regions and calls, takes its seat when it arrives, with its own card.

| | |
| --- | --- |
| Demo | Out of sight (`out-of-sight/`) |
| File | `site/pack/module/place-dev0.npz` · 957,040 bytes · SHA-256 `268a36746e4e95b1…` · format `cadence-module/1` (arrays and one JSON record, no pickled object) |
| Library | `cadence-net` 0.98.0, a wheel built from the library's branch lane-099-space; it holds cadence.space and cadence.modules, which PyPI's 0.98.0 does not (SHA-256 `36e529caeacc06cd…`), CPU, in Pyodide 314.0.7 |
| Loaded by | `cadence.load_module(path)`, then `cadence.space.Space.load(module, track=True, records=12, practice=0.0)` (`site/pack/py/spacebrain/place_host.py`) |
| Size | 946 neurons, 138,112 synapses: `place` 32, `moved` 18, `motion` 56, `unseen` 8, `heard` 320, `felt` 256, `hidden` 128, `shift` 64, `spread` 16, `found` 48 |
| Date | 2026-11-12 |

## What the program does and what the brain does

`Space` is a program beside the brain, as a long-term memory is. It holds each thing's place
between moments (two numbers and the radius of its area), writes a camera's report into it,
adds the brain's answer to it and keeps the records. The brain holds no place. It answers three
things for a thing whose place may have moved: how far the place moves in this step (`shift`),
how far off the place may be (`spread`), and the place a cue or the arm's joint readings name
(`found`). The peak drawn in the `place` region is the program's place, shown to the brain.

- **Inputs:** `place` (the held place, 16 tuned units an axis), `moved` (the copy of the arm's
  command, for the arm's own hand), `motion` (the thing's last seen movement: the slope of the
  line through its reports), `unseen` (the moments since it was seen), `heard` (a cue: 20
  directions by 16 distances from the ear), `felt` (the arm's joint readings, 16 by 16).
- **Outputs:** `shift` (32 units an axis, up to 6 cm a step), `spread` (16 units from 2 mm to
  2 m), `found` (24 units an axis over the plane).
- **One moment on the page:** the cues go to their rows (`hear`), the brain answers
  (`predict`), the reports go to their rows (`assign`) and the places are written (`observe`).
  Reports and cues carry what a thing looks like and no name. The answer for the hand is its
  row's place and a circle that holds it nine times in ten (`where`).
- **The sight evidence:** where the library's `observe` takes `in_sight`, the page's worker says
  for each predicted place whether the camera would see a thing there, and a place predicted in
  sight for three moments with no report is put halfway along its hidden path. The wheel this
  file runs on does not hold that call, so no flag is passed.
- **The ear:** the module's ear stands at (0.95, 1.35). A cue heard at the page's body is given
  to the module as the direction and distance of the same point from its own ear.

## How it was trained

By the library's tracking chamber, as the file's own record states: "benchmarks/tracking curriculum(founder=0, 2000 scenes), lessons that hold only reports". Development founder 0.
Its record's readings, in centimetres: a person's hand 0.64 in view and 15.86 out of view; the
arm's own hand 1.09 in view and 12.51 out of view.

## How it was measured on the page

The promise is read from a scripted scenario: the module as its file holds it, the same route by
scene steps (0.5 m/s into the pillar's shadow, 70 moments at rest there, back), the camera's
noise from one seed. The scene is also a scene file of the tracking chamber,
`tests/fixtures/promise-scene.json` (323 steps, 91 out of view; `tools/export_promise.mjs`).
Three runs with lessons on and three with lessons off (`evidence/promise_runs.json`); bounds
5 cm in view, 10 cm hidden, 0.85 for the circle, 5 cm after the return:

| Sight evidence | Lessons | In view | Hidden, mean | Hidden, last | Circle holds the hand | Circle's radius | Held back | After return | Lessons taken | A moment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | on | 1.0 cm | 36.4 cm | 86.4 cm | 0.23 | 1.4 cm to 18.5 cm | - | 0.2 cm | 319 | 62 ms |
| none | on | 1.0 cm | 36.3 cm | 86.3 cm | 0.23 | 1.4 cm to 18.5 cm | - | 0.2 cm | 319 | 54 ms |
| none | on | 1.0 cm | 36.4 cm | 86.5 cm | 0.23 | 1.4 cm to 18.6 cm | - | 0.2 cm | 319 | 49 ms |
| none | off | 1.0 cm | 33.3 cm | 80.2 cm | 0.24 | 1.6 cm to 18.9 cm | - | 0.3 cm | 0 | 12 ms |
| none | off | 1.0 cm | 33.3 cm | 80.2 cm | 0.24 | 1.6 cm to 18.9 cm | - | 0.3 cm | 0 | 11 ms |
| none | off | 1.0 cm | 33.3 cm | 80.2 cm | 0.24 | 1.6 cm to 18.9 cm | - | 0.3 cm | 0 | 9 ms |

On the same rows the chamber's Kalman filter lay 28 cm from the hidden hand and the last seen
position 16 cm. With lessons off the three runs are the same to the last digit and a moment
takes 9 to 12 ms of the scene's 33 ms; with lessons on it takes 49 to 62 ms. The hand stops in
the shadow, and the module carries its place on along the last seen movement: the promise's
bound is not held, with lessons or without. The library of this pack takes no sight evidence
(`library_takes_sight_evidence` in the evidence file), so every run reads without it.

- One knock: 16 knocks at one place with the cue's own error of 6 cm put the place 14 cm from the
  true one on average, 27 cm at the most (measured natively through the page's host).

## In the page

Lessons are off unless the visitor switches them on (Details): the module arrives trained. With
them on, the space teaches the brain from the camera's reports of every thing in view. A lesson is made of six reports in a row and lands up
to five moments after the last of them; with the camera off no lesson is taken. No span of
reports is left unread (`practice=0.0`). A new brain (Details) is the module as its file holds
it. A visitor's drag is held to 0.7 m/s and the arm's command to 0.1 rad a step, the range the
module was raised in. Nothing of the brain is saved in the browser.

## Limits

- A feed-forward baseline: its answers do not come from a settled exchange between regions.
- Out of view, its error passes 10 cm after 20 to 30 moments of movement, and a hand that
  stops in the shadow can be carried on.
- With the camera off and the hand moving, expect 20 to 40 cm beyond about 100 moments.
- Places are the room's own. A turn of the body changes what is seen and no stored place; the
  small map turns the places for display. A body that moves is not modelled.
- One development founder. These are a page's readings on one run, not the gates of
  [cadence#320](https://github.com/muellerberndt/cadence/issues/320).

## Licence

GPL-3.0, as Cadence.
