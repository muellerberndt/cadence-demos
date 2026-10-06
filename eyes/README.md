# Eyes

One Cadence brain runs in a browser tab and follows every shape on a large surface with its own
eye, seeing nothing but the page's pixels. Drag a shape, add more, or let them freeze, walk and
dart on their own. Each tracked shape has an eye that sees sharply at its centre and coarsely
around it, and also sees what changed since the previous frame. Every frame the brain answers,
for each eye, where its own shape is, and the eye moves there: a small correction, or one long
saccade after a shape you dragged away fast. While nothing moves, the brain stays in equilibrium
and settles nothing. The 3D view shows one eye's stream through the whole brain, every module
named.

```sh
python -m http.server -d eyes/web 8797     # open http://localhost:8797/
```

The page shows a raised visual brain at work; it does not learn. The brain was raised offline
with a lesson on every frame (an open-loop bootstrap), and the page runs it frozen. In
development, continuing to learn in closed loop from witnessed misses made every raised eye
worse, so the page runs the brain as the bootstrap left it. The brain is a hand-wired connectome
run by `cadence.Brain`, not a `Brain.compose` brain, and it has no working memory: an eye's
continuity is its own settled state, carried from frame to frame.

## What it demonstrates

- **Seeing from pixels, in the browser.** The released `cadence-net` 0.74.0 wheel runs in
  Pyodide in up to six web workers, unmodified apart from one compatibility shim (see Limits).
  The page draws its shapes into pixels, and each eye reads its receptors from those pixels and
  from nothing else. The brain is told only where to open an eye, when you point at a shape.
- **One brain, many eyes.** Every eye is one stream of the same brain. All streams settle
  together, each from its own previous equilibrium.
- **Work follows movement.** A frame in which nothing changed leaves every eye's state an
  equilibrium and costs zero sweeps; a moved shape makes its eye repair, about 32 sweeps.
- **Looking for a shape.** The foveated retina and its change channel let an eye find its shape
  again after the shape has jumped out of its centre, in one saccade.
- **Answers that settle.** Each answer is the settled state of the whole connectome: retina, V1,
  the collicular map and the gaze slots in one equilibrium. There is no feed-forward pass and no
  separate readout.

## How it is built

| Path | What |
| --- | --- |
| `tracker/fovea.py` | the foveated retina (`Fovea`), the world the eye was raised in (`FovealWorld`), the many-eye world (`FovealScene`) and the assays |
| `tracker/anatomy.py` | the connectome (`Anatomy`, `build`) |
| `tracker/eye_host.py` | what the page's workers run in Pyodide: pixels in, answers out |
| `raise_eye.py` | raises the brain and assays it |
| `pack.py` | packs a raised brain for the page (`web/pack/`) |
| `web/` | the page: `eyes.js` (the world, the mouse, the drawing), `shapes.js` (the renderer), `worker.js` (Pyodide and the brain), `brain_scan.js` (the brain view) |
| `check_page.py` | the page's promise, tried end to end in a headless Chrome |
| `compare.py` | the eye against its control, the window eye it replaced |
| `controls/` | the window eye's brain |
| `evidence/` | receipts |

`tracker/anatomy.py` writes the connectome as synapse lists and hands it to
`cadence.Brain(connectome, slots=(13, 13))`. The convolution is weight tying inside the library's
own learner: synapses of the same kernel entry share one efficacy through
`Learner(tie_groups=..., synapse_rate=...)`. Raising calls `Learner.step`, the library's local
contrast rule: the witnessed position nudges the gaze slots, the nudge spreads back through the
reciprocal synapses of the same graph, and every synapse changes by its own pre and post
activity. Nothing is propagated backwards through layers. The page's worker loads Pyodide 314.0.7
from jsDelivr and checks the Cadence wheel, the sources and the brain against the SHA-256 in
`web/pack/manifest.json`. `web/shapes.js` draws exactly the pixels of `tracker/shapes.py`
(`tests/test_shapes_js.py`), so the page shows the brain the images it was raised on. The brain
view (`web/brain_scan.js`, `tracker/atlas.py`) is the standard viewer of
[cadence-examples](https://github.com/muellerberndt/cadence-examples).

## Brain layout

| Region | Role | Neurons | Wiring |
| --- | --- | --- | --- |
| Retina | 25×25 receptors, two channels: brightness and change | 1,250 | held drive from the eye's receptors |
| V1 | 8 feature maps, 5×5 fields, stride 2 | 968 | one way from the retina; tied kernels over both channels |
| Superior colliculus map | 13×13 retinotopic sheet | 169 | reciprocal with V1, tied topographic; balanced topographic readout |
| Gaze slots | horizontal and vertical, 13 bins each | 26 | reciprocal with the map; one softmax per slot |

2,413 neurons and 74,612 synapses. The receptors sit one pixel apart out to 6 px and spread out
geometrically to 40 px, each pooling its patch, from one pixel at the centre to ten at the edge.
The 13 bins per axis group the receptors, three in the middle and then pairs, like the
superior colliculus's motor map: an answer is a saccade of 0, 2.5, 4.5, 7.1, 13.4, 25 or 40 px,
and a shape within 1.5 px of the centre leaves the eye still. Beyond the surface edge an eye
sees the background level, so it can centre a shape at the border.

## Run

```sh
cd eyes
python -m http.server -d web 8797       # the page, http://localhost:8797/
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q tests
.venv/bin/python check_page.py          # the promise, in a headless Chrome
.venv/bin/python compare.py             # the eye against its control
.venv/bin/python raise_eye.py --out runs/eye-s1 --seed 1   # raise the brain again
.venv/bin/python pack.py --run runs/eye-s1                 # and pack it for the page
```

The first load fetches Pyodide and NumPy from jsDelivr (about 10 MB); after that the browser
caches them. `tests/test_shapes_js.py` needs Node.

## What the brain receives

Each frame, for each eye: the brightness of its 625 receptors, pooled from the page's pixels
around its gaze, and the change of every receptor's patch since the previous frame. Change is
taken on the surface, so the eye's own saccades are not counted as change. That is all: no
positions, no shape identities, no labels. Where an eye opens is the player's choice; after that
only its answers move it.

While the brain was raised, every frame was a lesson. After its free answer, the world revealed
where the eye's own shape was, and `Learner.step` taught that position, warm from the answer's
own settled state. The label stayed the eye's own shape also when another shape passed nearer.
The world placed the eye only where its own shape was the nearest one, because a single still
frame cannot say which of several shapes is the eye's own, and the eye's own shape darted on a
tenth of the ticks, so the periphery was learned from moves that the change channel shows. Faces
are among the nine shapes it was raised on; stars, tees and ells it never saw.

## Measurement and evidence

The page's promise (`evidence/page_check.txt`, `check_page.py`, headless Chrome on a Mac): the
brain loads in Pyodide; six eyes on six moving shapes, 5.93 of 6 on average on their own shapes;
a still world costs zero sweeps; a shape dragged 20 px in 150 ms is centred in its eye again a
second later; no console errors.

The eye against its control, as the page runs them (`evidence/comparison.json`, `compare.py`;
the window eye sees a 26×26 window at full resolution and was raised on eight shapes without
faces; both run the same tests and seeds, faces included):

| Test | Foveated eye | Window eye (control) |
| --- | --- | --- |
| Its own shape jumps 10 px: centred on it again after one / three frames | 0.77 / 0.95 | 0.42 / 0.65 |
| ... jumps 20 px | 0.02 / 0.35 | 0.00 / 0.00 |
| ... jumps 30 px | 0.00 / 0.17 | 0.00 / 0.00 |
| Another shape jumps 10 / 20 / 30 px: the eye stays on its own | 1.00 / 1.00 / 1.00 | 0.87 / 0.88 / 0.75 |
| Four shapes moving on their own: eye frames on the eye's own shape (two seeds) | 0.99, 0.95 | 0.79, 0.79 |
| Eight shapes moving on their own | 0.94, 0.87 | 0.80, 0.75 |

60 trials per jump, 30 s at 20 frames per second per scene.

The raised brain, measured right after raising at its raised tolerance of 0.003
(`evidence/fovea-v1x8-s1-summary.json`): at first glance from rest, with the eye's own shape the
nearest one, it finds a shape within 3 px of its centre on 1.00 of trials, 3 to 12 px out on
0.85 and 12 to 34 px out on 0.65 (the centre guess: 1.00, 0.07, 0.05; random: 0.04, 0.07,
0.10). Faces 0.91; never seen: stars 0.85, tees 0.78, ells 0.72. After its own shape jumps 10,
20 or 30 px, it is centred on it again within three frames on 0.95, 0.55 and 0.32 of trials, and
it ignores another shape's jump on all of them. Every unchanged frame costs zero sweeps. Raising
took 20,000 lessons, 632 s on one core (Python 3.11, NumPy 2.4.6). `raise_eye.py --seed 1` runs
the same configuration and code; another platform may differ in the last bits and so in detail.

The page runs the brain at an answer tolerance of 0.03 (`pack.py --tolerance`): a moving frame
then settles in one 32-sweep chunk instead of about two, so the brain answers twice as often
while you drag, and a jump between two of its answers is half as long. Long jumps pay for it: a
20 px jump is found again within three frames on 0.35 of trials at 0.03 against 0.55 at 0.003,
a 30 px jump on 0.17 against 0.32. In Pyodide under Node a
moving frame costs about 15 ms for one eye and 28 ms for two, a still frame about 1 ms; the page
spreads the eyes over up to six workers.

## Limits

- No learning in the page.
- A shape that jumps 30 px between two answers is found again only some of the time; a fast
  drag works because the brain answers often enough that each step stays short.
- When two shapes pass through each other, an eye can go on with the other one.
- A second visual stage (V2) did not help this eye in development and costs five to ten times
  the compute; the page uses one.
- Pyodide's NumPy is 32-bit. Cadence 0.74.0 builds a learner with several slots by
  `np.repeat(..., slot_sizes)` on int64 counts, which a 32-bit NumPy refuses to cast.
  `tracker/eye_host.fit_32_bit_numpy` gives the library's learning module a NumPy whose `repeat`
  casts those counts; the library's files are unchanged. The same holds for `np.add.reduceat`
  on the transport above `dense_limit`, which this brain does not use.
- Grayscale only.

Built with Cadence 0.74.0 (`cadence-net` from PyPI) and Pyodide 314.0.7.
