# Model card: the place module's development file place-keeplong-2 (a feed-forward baseline)

This card describes the file the Out of sight page runs. It is a development file of the place
module and a baseline by the project's rules: every synapse of its brain runs from the inputs
toward the outputs, so an answer is complete after three sweeps. It comes from development
founder 2 and was raised with practice spans of 80 steps. A version that settles takes its seat
when it arrives, with its own card.

| | |
| --- | --- |
| Demo | Out of sight (`out-of-sight/`) |
| File | `site/pack/module/place-keeplong-2.npz` · 966,534 bytes · SHA-256 `2e84b17e7e1d7082…` · format `cadence-module/1` (arrays and one JSON record, no pickled object) |
| Library | `cadence-net` 0.98.0, a wheel built from the library's branch lane-099-space at 1ee53f9e; it holds cadence.space and cadence.modules, which PyPI's 0.98.0 does not (SHA-256 `e3ad21502cd17ffb…`), CPU, in Pyodide 314.0.7 |
| Loaded by | `cadence.load_module(path)`, then `cadence.space.Space.load(module, track=True, records=12, practice=0.0, course=True)` (`site/pack/py/spacebrain/place_host.py`) |
| Size | 954 neurons, 139,648 synapses: `place` 32, `moved` 18, `motion` 56, `unseen` 8, `heard` 320, `felt` 256, `hidden` 128, `shift` 64, `spread` 16, `found` 48, `keep` 8 |
| Date | 2026-11-12 |

## What the program does and what the brain does

`Space` is a program beside the brain, as a long-term memory is. It holds each thing's place
between moments (two numbers and the radius of its area), writes a camera's report into it,
moves it by the brain's answers and keeps the records. The brain holds no place. It answers four
things for a thing whose place may have moved: how far the place moves in this step (`shift`),
how much of its last seen movement a thing keeps in this step (`keep`), how far off the place
may be (`spread`), and the place a cue or the arm's joint readings name (`found`). The peak
drawn in the `place` region is the program's place, shown to the brain.

- **Inputs:** `place` (the held place, 16 tuned units an axis), `moved` (the copy of the arm's
  command, for the arm's own hand), `motion` (the thing's last seen movement: the slope of the
  line through its reports), `unseen` (the moments since it was seen), `heard` (a cue: 20
  directions by 16 distances from the ear), `felt` (the arm's joint readings, 16 by 16).
- **Outputs:** `shift` (32 units an axis, up to 6 cm a step), `spread` (16 units from 2 mm to
  2 m), `found` (24 units an axis over the plane), `keep` (8 units from 0 to 1).
- **On its course:** the page runs this file with `course=True`, as it was raised. A thing that
  moves by itself is moved by its last seen movement times the share the brain's `keep`
  answers, in place of the `shift`; the arm's own hand is moved by the `shift`.
- **One moment on the page:** the cues go to their rows (`hear`), the brain answers
  (`predict`), the reports go to their rows (`assign`) and the places are written (`observe`).
  Reports and cues carry what a thing looks like and no name. The answer for the hand is its
  row's place and a circle that holds it nine times in ten (`where`).
- **The sight evidence:** the page gives `observe` a function that says whether the camera
  would see a thing at a place, from the scene as it stands (`in_sight=`). A thing that goes out
  of view while moving is looked ahead for along its seen movement; it is carried no farther
  than the middle of its hidden stretch and waits there, with a radius that reaches .90 of the
  way back to where it was last seen. A thing at rest whose own place the camera sees, with no
  report from there for three moments, is marked gone: its radius becomes the room's, and the
  page says the brain does not know where it is.
- **The arm's own hand:** the space is given the copy of the arm's command. The arm's joint
  readings are passed only where the pack says the module was raised with them
  (`--space '{"joints": true}'`); this file was raised without them.
- **The ear:** the module's ear stands at (0.95, 1.35). A cue heard at the page's body is given
  to the module as the direction and distance of the same point from its own ear.

## How it was trained

By the library's tracking chamber, as the file's own record states: "benchmarks/tracking curriculum(founder=2, 2000 scenes), lessons that hold only reports". The record
names its arm "feed-forward baseline" and says "founder 2 is a development founder". It was
raised on its course, with practice spans of 80 steps.

## How it was measured on the page

The promise is read from a scripted scenario: the module as its file holds it, the same route by
scene steps (0.5 m/s into the pillar's shadow, 70 moments at rest there, back), the camera's
noise from one seed. The scene is also a scene file of the tracking chamber,
`tests/fixtures/promise-scene.json` (323 steps, 91 out of view; `tools/export_promise.mjs`),
and the page's first scene is `tests/fixtures/promise-merged-shadows-scene.json`.
In the default scene, three runs with lessons on and three with lessons off, and one of each
with the sight evidence withheld; the same, one run each, in the page's first scene, where the
pillar's shadow and the arm's join (`evidence/promise_runs.json`). Bounds: 5 cm in view, 10 cm
hidden, 0.85 for the circle, 5 cm after the return. The first scene has no bound: it is read as
a stated limit.

| Scene | Sight evidence | Lessons | In view | Hidden, mean | Hidden, last | Circle holds the hand | Circle's radius | Held back | After return | Lessons taken | A moment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| default | given | on | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.6 cm to 17.0 cm | 80 moments, from hidden moment 12 | 0.3 cm | 319 | 58 ms |
| default | given | on | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.6 cm to 17.0 cm | 80 moments, from hidden moment 12 | 0.3 cm | 319 | 59 ms |
| default | given | on | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.6 cm to 17.0 cm | 81 moments, from hidden moment 11 | 0.3 cm | 320 | 54 ms |
| default | given | off | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.5 cm to 17.0 cm | 80 moments, from hidden moment 12 | 0.3 cm | 0 | 9 ms |
| default | given | off | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.5 cm to 17.0 cm | 80 moments, from hidden moment 12 | 0.3 cm | 0 | 10 ms |
| default | given | off | 1.0 cm | 4.6 cm | 15.7 cm | 1.00 | 3.5 cm to 17.0 cm | 80 moments, from hidden moment 12 | 0.3 cm | 0 | 10 ms |
| default | none | on | 1.0 cm | 40.8 cm | 83.6 cm | 0.25 | 2.7 cm to 43.0 cm | - | 0.2 cm | 319 | 59 ms |
| default | none | off | 1.0 cm | 38.2 cm | 80.6 cm | 0.34 | 2.9 cm to 43.4 cm | - | 0.8 cm | 0 | 12 ms |
| first (shadows joined) | given | on | 1.0 cm | 27.7 cm | 51.1 cm | 0.98 | 3.6 cm to 49.0 cm | 56 moments, from hidden moment 36 | 0.3 cm | 319 | 66 ms |
| first (shadows joined) | given | off | 1.0 cm | 27.2 cm | 51.1 cm | 0.98 | 3.5 cm to 49.0 cm | 53 moments, from hidden moment 39 | 0.3 cm | 0 | 11 ms |
| first (shadows joined) | none | on | 1.0 cm | 41.2 cm | 84.3 cm | 0.25 | 2.6 cm to 42.8 cm | - | 0.2 cm | 319 | 69 ms |
| first (shadows joined) | none | off | 1.0 cm | 38.2 cm | 80.6 cm | 0.34 | 2.9 cm to 43.4 cm | - | 0.8 cm | 0 | 9 ms |

In the default scene the place lies 4.6 cm from the hidden hand on average (15.7 cm at the last
hidden moment, as the hand comes back out) and the circle holds the hand on 1.00 of the hidden
moments, lessons on or off; the place is held back from hidden moment 12. The circle states .90 and
holds 1.00: it is wider than it needs to be. In the page's first scene, where the pillar's
shadow and the arm's join, the place lies 27.2 cm from the hidden hand and the circle holds it on
0.98: a stated limit. There the hidden stretch has no lit end, the place waits at the middle of
a stretch that runs to the room's edge, and the circle is wide enough to hold the hand. With the
sight evidence withheld the place runs on in either scene: 38.2 cm and 0.34.

On the same rows the chamber's Kalman filter lay 28 cm from the hidden hand and the last seen
position 16 cm. With lessons off the three runs are the same to the last digit and a moment
takes 9 to 10 ms of the scene's 33 ms; with lessons on it takes 54 to 59 ms.

- The page check (`evidence/page_check.json`): 42 of 42; every check passes.
- One knock: the cup's record lay 14 cm from the cup, against three times the cue's own error,
  26 cm. The knock's error is drawn from a seeded stream, and the reading repeats.

## In the page

Lessons are off unless the visitor switches them on (Details): the module arrives trained. With
them on, the space teaches the brain from the camera's reports of every thing in view. A lesson
is made of six reports in a row and lands up to five moments after the last of them; with the
camera off no lesson is taken, and the rule that marks a resting thing gone does not act while
lessons are on. No span of reports is left unread (`practice=0.0`). A new brain (Details) is the
module as its file holds it. A visitor's drag is held to 0.7 m/s and the arm's command to
0.1 rad a step, the range the module was raised in. Nothing of the brain is saved in the browser.

## Limits

- A feed-forward baseline: its answers do not come from a settled exchange between regions.
- Where two shadows join, as in the page's first scene, the hidden stretch has no lit end: the
  place waits 27.2 cm from the hand on average, inside a circle wide enough to hold it
  (0.98). A stated limit.
- The circle is wider than it needs to be: in the default scene it states .90 and holds the
  hand on 1.00 of the hidden moments.
- Without the sight evidence (`?sight=0`, or the camera off) the place runs on: 38.2 cm and
  0.34 in the default scene.
- A hand that goes into the shadow after a pause, or slowly, can be taken as at rest: its place
  stays where it was last seen. Where the camera sees that place, the space marks it gone and
  the page says the brain does not know where the hand is; a place that comes to rest just
  inside the shadow's edge is not marked.
- A cue does not take the gone mark away in the space; the page shows a place named by a cue
  after the mark as a heard place.
- The module was raised on up to about 100 moments of a moving hand it does not see.
- Places are the room's own. A turn of the body changes what is seen and no stored place; the
  small map turns the places for display. A body that moves is not modelled.
- One development founder. These are a page's readings on one run, not the gates of
  [cadence#320](https://github.com/muellerberndt/cadence/issues/320).

## Licence

GPL-3.0, as Cadence.
