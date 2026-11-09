# Model card: the foveated eye (Eyes page) and its window-eye control

| | |
| --- | --- |
| Demo | Eyes (`eyes/`) |
| File | `web/pack/brain.npz` · 230,824 bytes · SHA-256 `40a36d28e2748e64…` |
| Library | `cadence-net` 0.95.2 (`Brain.load`, CPU, float64, as the page's workers load it in Pyodide) |
| Composition | not `Brain.compose`: a hand-wired connectome (`tracker/anatomy.py`) run by `cadence.Brain(connectome, slots=(13, 13))`; 1,250 inputs, 26 actions in two slots, no recall memory, no working trace |
| Size | 2,413 neurons, 74,612 synapses |
| Date | 2026-11-09 |

## What it sees and does

- **Inputs (1,250):** one eye's foveated retina, 25×25 receptors in two channels, brightness and
  the change of each receptor's patch since the previous frame. Receptors sit one pixel apart out
  to 6 px and spread geometrically to 40 px. Pixels only: no positions, identities or labels.
- **Regions:** retina 1,250 → V1 968 (8 tied feature maps, 5×5 fields, stride 2, one way) ↔
  superior colliculus map 169 (13×13, reciprocal, topographic) ↔ gaze slots 26.
- **Outputs (26 motor neurons):** horizontal and vertical gaze, 13 bins each, one softmax per
  slot; an answer is a saccade of 0 to 40 px.
- **One decision:** each eye is one stream; every frame all streams settle together, each warm
  from its own previous equilibrium, at an answer tolerance of 0.03 (raised at 0.003). A frame
  in which nothing changed costs zero sweeps. No search.

## How it was trained

Open-loop bootstrap in `FovealWorld` (`tracker/fovea.py`): the world places the eye where its
own shape is the nearest one and moves it as a competent eye would. In this raise the eye's own
shape darts on a fifth of the ticks, 8 to 40 px at a time (the declared world: a tenth, 8 to
34 px; the assays read the declared world). Every frame is one lesson: after the free answer,
`Learner.step` teaches the shape's true position, warm from the answer's own settled state, with
the quadratic nudge (momentum 0); the step is 0.1 (bias 0.01) for the first 50,000 lessons and
falls linearly to 0.02 (bias 0.002) by the last. 100,000 lessons over 4,976 scenes and 28,333
darts, seed 1, on nine shapes (disc, ring, square, frame, triangle, diamond, cross, bar, face).
CPU, float64 (`evidence/fovea-v1x8-s1-run.json`): 5,353 s on one core of a 64-core cloud machine
(Python 3.12, NumPy 2.5, `cadence-net[fast]`) that raised other eyes at the same time.
`pack.py` stores it for the CPU in float64 with the cross-entropy nudge and answer tolerance
0.03. It was picked from 24 recipes on two seeds each as the one whose every `compare.py`
reading is at least the 20,000-lesson eye's (first glance far 0.61; 20 / 30 px jumps 0.48 /
0.23 at the page's tolerance).

```sh
python raise_eye.py --out runs/eye-s1 --seed 1 --lessons 100000 --own-dart 0.2 --dart-px 8 40 \
    --eta-final 0.02 --decay-from 0.5        # --backend mlx raises on a Mac's GPU in float32
python pack.py --run runs/eye-s1
```

## How it was measured

Right after raising, frozen, at tolerance 0.003 (`evidence/fovea-v1x8-s1-summary.json`; seeds
10,001+):

| Reading | Trials | Eye | Centre guess | Random |
| --- | --- | --- | --- | --- |
| First glance, own shape within 3 px of the centre: centred | 100 | 1.00 | 1.00 | 0.04 |
| ... 3 to 12 px out | 100 | 0.88 | 0.07 | 0.07 |
| ... 12 to 34 px out | 100 | 0.73 | 0.05 | 0.10 |
| First glance, shapes never seen (stars, tees, ells) | 300 | 0.83 (0.84, 0.81, 0.85) | 0.38 | 0.05 |
| Faces | (in the 300 above) | 0.81 | – | – |
| Own shape jumps 10 / 20 / 30 px: centred again within 3 frames | 60 each | 0.93 / 0.68 / 0.53 | – | – |
| Another shape jumps 10 / 20 / 30 px: the eye stays on its own | 60 each | 0.98 / 1.00 / 1.00 | – | – |
| Unchanged frame costs zero sweeps | all | 1.00 | – | – |

As the page runs it (tolerance 0.03), against the control (`evidence/comparison.json`, `compare.py`;
60 trials per jump, 600 frames per scene, 2 seeds):

| Test | Foveated eye | Window eye (control) |
| --- | --- | --- |
| Own shape jumps 10 px: centred after 1 / 3 frames | 0.88 / 0.98 | 0.42 / 0.65 |
| ... 20 px | 0.18 / 0.77 | 0.00 / 0.00 |
| ... 30 px | 0.22 / 0.53 | 0.00 / 0.00 |
| Another shape jumps 10 / 20 / 30 px: stays on its own | 1.00 / 1.00 / 1.00 | 0.87 / 0.88 / 0.75 |
| Four shapes moving: frames on the eye's own shape | 1.00, 1.00 | 0.79, 0.79 |
| Eight shapes moving | 0.94, 0.87 | 0.80, 0.75 |

**The control:** `controls/window-eye.npz` (131,737 bytes, SHA-256 `d7866ecd5b4c3050…`), a 26×26
window at full resolution, 13 bins of 2 px, V1 4×5/2, 1,355 neurons, 29,600 synapses, raised on
eight shapes without faces (run `visual4-wide-s2`, cadence-net 0.74.0, quadratic nudge;
`controls/window-eye.json`). It was loaded and saved once by cadence-net 0.94.0 into the
checkpoint format 0.95.2 reads; frozen, it answers the window dart test exactly as the original.

## In the page

Frozen: no lessons in the page. The visitor adds, drags and removes shapes, opens an eye on a
shape, and freezes or animates the world; nothing is saved in the browser. Up to six web workers
each hold a copy of the brain. The page check (`evidence/page_check.txt`, headless Chrome on a
Mac running other jobs): the brain loads in Pyodide in 49.6 s; six eyes on six moving shapes,
5.40 of 6 on their own shapes over 30 samples; a still world, 19 ms per frame and zero sweeps; a
shape dragged 20 px in 150 ms is centred again, 0.4 px away; no console errors. Every sixth
frame the worker holding the selected eye replays that eye's settle sweep by sweep for the brain
view (an exact replay, checked against the answer's state); a frame carrying it took a median
142 to 147 ms against 92 to 106 ms for the other frames of the same run, the mean frame 8 to 17%
more than with `?wave=0`.

## Limits

- No learning in the page; continued closed-loop learning made eyes worse in development.
- A shape that jumps 30 px between two answers is found again on about half of the trials.
- Faces at first glance read 0.81, below the 20,000-lesson eye's 0.91.
- When two shapes pass through each other, an eye can go on with the other one.
- Grayscale only. The readings certify these assays, not general vision.
- Pyodide's NumPy is 32-bit; `tracker/eye_host.fit_32_bit_numpy` casts the counts of one
  `np.repeat` call in the library's learning module.

## Licence

GPL-3.0, as Cadence.
