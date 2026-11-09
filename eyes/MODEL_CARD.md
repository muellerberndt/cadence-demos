# Model card: the foveated eye (Eyes page) and its window-eye control

| | |
| --- | --- |
| Demo | Eyes (`eyes/`) |
| File | `web/pack/brain.npz` · 217,809 bytes · SHA-256 `c9a8f6caaf8e4277…` |
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
own shape is the nearest one and moves it as a competent eye would; the eye's own shape darts on
a tenth of the ticks. Every frame is one lesson: after the free answer, `Learner.step` teaches the
shape's true position, warm from the answer's own settled state, with the quadratic nudge (step
0.1, bias step 0.01, momentum 0). 20,000 lessons over 996 scenes and 2,975 darts, seed 1, on
nine shapes (disc, ring, square, frame, triangle, diamond, cross, bar, face). Run on the 0.95.x
`"mlx"` backend in float32 (`evidence/fovea-v1x8-s1-run.json`), 2,729 s on an Apple M4 running
other jobs. `pack.py` stores it for the CPU in float64 with the cross-entropy nudge and answer
tolerance 0.03.

```sh
python raise_eye.py --out runs/eye-s1 --seed 1 --backend mlx   # leave --backend out off a Mac
python pack.py --run runs/eye-s1
```

## How it was measured

Right after raising, frozen, at tolerance 0.003 (`evidence/fovea-v1x8-s1-summary.json`; seeds
10,001+):

| Reading | Trials | Eye | Centre guess | Random |
| --- | --- | --- | --- | --- |
| First glance, own shape within 3 px of the centre: centred | 100 | 0.99 | 1.00 | 0.04 |
| ... 3 to 12 px out | 100 | 0.82 | 0.07 | 0.07 |
| ... 12 to 34 px out | 100 | 0.61 | 0.05 | 0.10 |
| First glance, shapes never seen (stars, tees, ells) | 300 | 0.78 (0.81, 0.77, 0.75) | 0.38 | 0.05 |
| Faces | (in the 300 above) | 0.91 | – | – |
| Own shape jumps 10 / 20 / 30 px: centred again within 3 frames | 60 each | 0.92 / 0.48 / 0.27 | – | – |
| Another shape jumps: the eye stays on its own | 60 each | 1.00 | – | – |
| Unchanged frame costs zero sweeps | all | 1.00 | – | – |

As the page runs it (tolerance 0.03), against the control (`evidence/comparison.json`, `compare.py`;
60 trials per jump, 600 frames per scene, 2 seeds):

| Test | Foveated eye | Window eye (control) |
| --- | --- | --- |
| Own shape jumps 10 px: centred after 1 / 3 frames | 0.82 / 0.98 | 0.42 / 0.65 |
| ... 20 px | 0.12 / 0.48 | 0.00 / 0.00 |
| ... 30 px | 0.02 / 0.23 | 0.00 / 0.00 |
| Another shape jumps 10 / 20 / 30 px: stays on its own | 1.00 / 1.00 / 1.00 | 0.87 / 0.88 / 0.75 |
| Four shapes moving: frames on the eye's own shape | 1.00, 0.99 | 0.79, 0.79 |
| Eight shapes moving | 0.93, 0.87 | 0.80, 0.75 |

**The control:** `controls/window-eye.npz` (131,737 bytes, SHA-256 `d7866ecd5b4c3050…`), a 26×26
window at full resolution, 13 bins of 2 px, V1 4×5/2, 1,355 neurons, 29,600 synapses, raised on
eight shapes without faces (run `visual4-wide-s2`, cadence-net 0.74.0, quadratic nudge;
`controls/window-eye.json`). It was loaded and saved once by cadence-net 0.94.0 into the
checkpoint format 0.95.2 reads; frozen, it answers the window dart test exactly as the original.

## In the page

Frozen: no lessons in the page. The visitor adds, drags and removes shapes, opens an eye on a
shape, and freezes or animates the world; nothing is saved in the browser. Up to six web workers
each hold a copy of the brain. The page check (`evidence/page_check.txt`, headless Chrome):
the brain loads in Pyodide in 26.7 s; six eyes on six moving shapes, 6.00 of 6 on their own
shapes over 30 samples; a still world, 4 ms per frame and zero sweeps; a shape dragged 20 px in
150 ms is centred again, 1.7 px away; no console errors.

## Limits

- No learning in the page; continued closed-loop learning made eyes worse in development.
- A shape that jumps 30 px between two answers is found again on about a quarter of trials.
- When two shapes pass through each other, an eye can go on with the other one.
- Grayscale only. The readings certify these assays, not general vision.
- Pyodide's NumPy is 32-bit; `tracker/eye_host.fit_32_bit_numpy` casts the counts of one
  `np.repeat` call in the library's learning module.

## Licence

GPL-3.0, as Cadence.
