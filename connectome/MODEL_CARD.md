# Model card: the zebrafish brainstem and the Platynereis larva

The demo runs two Cadence rate patch nets compiled from measured animal wiring. Neither is a
`cadence-net` checkpoint: each is an exported net (`cadence.brain-payload/1`) that the page runs
in JavaScript (`web/brain.js`). They do not depend on the `cadence-net` release.

## The fish: zebrafish hindbrain

| | |
| --- | --- |
| Demo | Connectome, the fish page (`connectome/web/fish.html`) |
| File | `web/data/brain.json` · 1.1 MB · SHA-256 `2ac2885d67d1c25e…` |
| Engine | Cadence rate patches in JavaScript (`web/brain.js`), lesson settings in `web/dictionary.js` |
| Wiring | Vishwanathan et al. 2024, *Nat Neurosci* 27:2340: 2,884 neurons, 44,969 connections, 75,195 synapses |
| Plastic part | the gaze connections into the integrator population (`_Int_`) |

### What it sees and does

The compiled neurons keep their recorded partners and synapse counts. Signs, dynamics and the
body mapping are declared: Ve2 vestibular neurons inhibitory, every other neuron excitatory; a
rate unit of slope 0.25 at threshold 0. Saccade commands and the vestibular push drive the
circuit; the integrator's activity sets the eye position. A fixed pilot supplies swimming,
hunting and escape; it is not learned.

### How it learns

Every synapse starts at 0.8 of the selected gain, a leaky integrator whose gaze drifts back
within a second. A lesson uses the circuit's own activity as feedback: one second after a
saccade the integrator's state is saved, and at the next saccade (or after 10 s of fixation),
if the state slipped by more than 5%, the net takes a finite contrastive lesson toward a
declared target: 95% of the saved activity for "hold your gaze", a quarter of it for "let it
return". Every synapse reads its own two endpoints in the nudged and free phases (β 3, η 0.01,
50 steps, tolerance 1e-4, relative steps, efficacy cap 8, signs kept); biases stay.

### How it was measured

`web/data/learning_release.json` (node, 3 seeds × 2 sides × 2 stimulus levels = 12 runs; phases
hold 600 s, return 150 s, stress 120 s, recovery 240 s of fish time):

| Reading | Range over 12 runs |
| --- | --- |
| Untaught fish, gaze held at 12 s | 0.00 |
| After "hold your gaze", at 12 s / 24 s | 0.77–0.87 / 0.61–0.76 |
| After "let it return", at 12 s | 0.01–0.04 |
| After recovery practice, at 12 s | 0.74–1.02 |
| Runs that hold, return and recover | 12 / 12 |

`web/data/learning_reteach.json` repeats the protocol with direct reteaching (hold, return,
hold): 12 / 12 hold, return and recover; recovery at 12 s 0.79–0.89.

### In the page

The fish learns while the visitor teaches it. **Pause learning** keeps the acquired weights,
**Reset learning** restores the compiled ones, and **Test its gaze** compares copies of the
current and starting weights without disturbing the live fish. Nothing is saved between
visits.

## The larva: Platynereis dumerilii

| | |
| --- | --- |
| Demo | Connectome, the larva page (`connectome/web/index.html`) |
| File | `web/data/larva_brain.json` · 2.7 MB · SHA-256 `a1fb9564d3952bae…` |
| Wiring | Verasztó et al. 2025, *eLife* 13:RP97964 (CATMAID project 11): 25,609 cells, 18,970 connections, 32,202 synapses |
| Plastic part | none: the weights stay fixed |

Every cell is excitatory unless its type names an inhibitory transmitter (none does). The page
drives the photoreceptors and mechanosensors and runs the compiled net to the muscles and
ciliary bands at 0.8 of the selected gain. The receipt `web/data/receipt_platynereis.json`
records the compilation and its checks against permuted and degree-matched null wirings.

## Limits

- The wiring is measured; the dynamics, signs, gains and body mappings are declared choices,
  listed in the receipts and on the page's "Model choices" tab.
- The fish's hindbrain volume covers one side; sides are not distinguished in the compiled net.
- The learning readings come from the seeded assay in node, not from visitors' sessions.
- The compiler that builds these files is not published; its exported nets and receipts are.

## Licence

GPL-3.0, as Cadence. The wiring belongs to its authors' published datasets, cited above.
