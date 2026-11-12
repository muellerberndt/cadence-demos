# Model card: the untrained baseline (the Out of sight page's stand-in brain)

This card describes the brain the page runs while the trained place module is raised. It is a
control: a plain composed brain with nothing that holds a place between moments. It does not
keep the page's promise, and the page says so. The trained module's card replaces this one.

| | |
| --- | --- |
| Demo | Out of sight (`out-of-sight/`) |
| File | none: composed in the page's worker by `site/pack/py/spacebrain/host.py` when the page loads |
| Library | `cadence-net` 0.98.0, the PyPI wheel (SHA-256 `7eb6faec5e4fe785…`), CPU backend, float64, in Pyodide 314.0.7 |
| Composition | `Brain.compose(inputs=75, actions=40, slots=2, modules=(96,), seed=0, recall=False, temperature=0.05)` |
| Size | 307 neurons (75 sensory, 96 association, 96 prefrontal, 40 motor), 24,096 synapses |
| Beside the brain | `LongTermMemory(width=48, value_width=48, capacity=12, cosine=True, revise=0.9)`: the records of the things |
| Date | 2026-11-12 |

## What it sees and does

- **Inputs (75 values, fixed population codes):** the camera's report of the hand, x and y, 16
  tuned inputs each over the plane, all dark while the hand is out of view; one input that is on
  while the hand is in view; the arm's two joint readings, 12 tuned inputs each over the joint's
  limits; the arm's two commands as a copy, 9 tuned inputs each over ±0.25 rad.
- **Outputs (40 motor neurons in two slots):** 20 units for x and 20 for y, each with a preferred
  position; each slot is read as one softmax at temperature 0.05. The place is the mean of the
  preferred positions under each slot's shares, the spread their standard deviation, and the
  area at 0.90 the most likely cells of the x-by-y product that hold nine tenths of it. The
  ring on the page is the ellipse of the two spreads at that rate.
- **One moment:** `Brain.act(x, greedy=True)` in a continuing stream. The working trace (a copy
  of the association region's last state, `prefrontal`) is the one thing carried from moment to
  moment. A settle that finds no qualified state gives no answer, and the page counts it.
- **The things:** each thing's key is a fixed unit vector drawn from its name; its value is a
  population code of its place (24 tuned units an axis). A thing the camera reports, or that
  the ear hears (a direction and a distance from the ear), is written; a thing out of view is
  read. The page gives every report its thing's name. The tracking chamber does not: there a
  learner keeps each thing's identity itself.

## How it was trained

It was not. The brain is born when the page loads. On the page, at every moment the camera
reports the hand, the report is a lesson after the answer: `Brain.lesson(x, label)`, the label
the nearest unit to the report on each axis. With `recall=False` the learner stands at
`surprise=False`, so every such moment teaches (step 0.5, 12 nudged sweeps, cross-entropy
nudge). No lesson uses a position the camera did not give. The visitor can switch the lessons
off (Details) and start a new brain.

## How it was measured

On the page only, by `tools/check_page.py` in headless Chromium (`evidence/page_check.json`,
12 November 2026): the tutorial's five steps performed with the mouse, from birth.

| Reading | Baseline | Bound |
| --- | --- | --- |
| In view: place to true hand, mean of the last 60 moments of the first step | 4.8 cm (after 358 lessons) | 5 cm |
| Hidden behind the pillar: place to true hand, mean over the hidden moments | 16 cm | 10 cm |
| the last seen position, the same moments | 15 cm | – |
| the constant-velocity Kalman filter (q 1e-5, r 0.01, not the chamber's fitted values), the same moments | 12 cm | – |
| Share of hidden moments whose stated area holds the true hand | 1.00 | 0.85 |
| Back in view: place to true hand, 10 moments | 19 cm | 5 cm |
| The cup moved unseen: its record to the place it was last seen at | 0.0 cm | 3 cm |
| After one knock: the record to the true place (the cue's own error: 12 cm) | 2.2 cm | three times the cue's error |
| The brain's answer for one moment, in the worker | 24 ms, on a machine under heavy load from other work | – |

The baseline's readings change from load to load: the brain is born at each load and learns
from the moments the check's drags give it (in view it has read between 3 cm and 20 cm). Its
stated area is as wide as the table while the hand is hidden, which is why it holds the hand.

## In the page

Learning while the visitor plays, at seen moments only. The visitor can switch the lessons off,
start a new brain, undo a move and reset the scene. Nothing of the brain is saved in the
browser: a reload is a new brain. The browser keeps one flag, that the tutorial was seen.

## Limits

- It holds no place while the hand is out of view. Its answer then leans on the working trace
  and slides away from the hand; the page check's promise step fails on it.
- Its stated area is the spread of a softmax. It was not calibrated, and it is not gated.
- A cue rewrites a thing's record whole; cues are not combined.
- It is one founder (seed 0) with no held-out reading. The numbers above certify the page's
  plumbing and nothing about spatial object awareness.

## Licence

GPL-3.0, as Cadence.
