# From connectome to Cadence

A bounded example for the Cadence demos: two measured connectomes compiled into rate patch nets that run in the browser. The nets are frozen, one patch per cell with the recorded synapse counts as weights; nothing here learns, and every part the data cannot give is declared on the disclaimers page. The compiled wiring comes from the public [connectome compiler](https://github.com/muellerberndt/cadence-connectome-compiler), whose receipts bind the source tables and the compiled nets by digest.

Explore how an animal's measured wiring can become a running Cadence rate patch net.
Two browser scenes connect imported anatomy to declared senses, neuron dynamics and
body models. The [connectome compiler](https://github.com/muellerberndt/cadence-connectome-compiler)
preserves recorded connection partners and synapse counts; signs, gains and the neuron
response law turn those counts into a dynamical model.

The two preprints behind the site: [Agreement and Surprise: Global Equilibrium from Local
Repair](https://philpapers.org/rec/MUEAAS-2) and [Cadence: Learning Through Local Patch
Settlement](https://philpapers.org/rec/MUECAP-2).

The larva uses the whole-body reconstruction of a three-day-old Platynereis dumerilii
(Verasztó et al. 2025): 25,609 cells, including 2,664 neurons and 933 effector cells.
Its declared stimulus mappings drive identified sensory cells, and its body reads
activity from identified muscles and ciliated cells. The fish uses one reconstructed
side of a larval zebrafish hindbrain (Vishwanathan et al. 2024, 2,884 neurons), duplicated
for the display. Compiled oculomotor activity drives its modeled gaze hold; swimming,
hunting and escape use a labelled pilot. On both pages, cell activity and flashes from
the latest local updates make the model's response visible.

The explanation page separates the construction, its mathematical assumptions and the
numerical evidence. The disclaimers page records what is measured, declared and missing.
Four further pages expose the wiring ledger, a live gain slider, circuit checks against
shuffled wiring, and a spiking/rate comparison.

## What the evidence establishes

For the implemented rate update, `u_next = (1 - dt) u + dt (W phi(u) + d)`, with
`dt > 0`, a fixed point satisfies exactly `u = W phi(u) + d`. This identifies the
rate model's stationary states with its local patch consistency equations. It does not
by itself prove convergence, uniqueness, or equivalence to a spiking model.

A spiking model can share a stationary-rate description when an appropriate transfer
law and a justified rate reduction apply. The demo's sigmoid is a declared approximation.
Its retained LIF comparison reports cosine similarity 0.965 and rank correlation 0.97
over all 88 undriven cells, including silent cells under sustained drive. These measure a relative activity pattern;
they do not establish equal spike times, firing-rate magnitudes, trajectories or behavior.
The tested spiking scan also did not reproduce the rate model's graded persistence.

The [fish receipt](web/data/receipt_oculomotor.json) and
[larva receipt](web/data/receipt_platynereis.json) each report five successful scored
checks not used to select gain. Their protocols record exploratory runs and revisions,
so these are not blind validation. The fish's controls preserve degrees exactly and
match input strengths approximately. These comparisons support selected circuit
properties under the declared model; they do not establish a complete animal brain.

Browser/library parity tests check implementation consistency. The spiking fixture
checks 8,803 exact spike events at 0.1 ms resolution against the Python reference.
`node tests/evidence.mjs` rebuilds the rate run at the receipt's exact gain and
recomputes both reported correlations from its stored LIF rate vector. This does
not rerun the six original LIF trials. The
[cost receipt](web/data/cost.json) compares these implementations and declared time
scales, with different winners on different circuits; it is not a universal speedup
or an accuracy-matched benchmark. Retained receipts describe their recorded source and
protocol digests. Re-running current code is a separate check against those artifacts.

## Run it

The pages fetch their skeletons as gzip (`web/data/*.json.gz`) and inflate them in the browser (`DecompressionStream`, every current browser).

Everything runs in the browser from static files, so any static host works, GitHub Pages
included (`.github/workflows/pages.yml` runs the checks and publishes `web/`). Locally:

```
python3 -m http.server 8000 --directory web
```

and open `http://localhost:8000/`. The pages need http, not `file://`, for the worker and
the module imports.

## Check it

Node for the engine checks; a Python with `playwright` (and its Chromium) for the page checks; the export tools under `tools/` need the connectome compiler and its data and are kept for reproducibility.

```
sh tests/run_all.sh                 # node: engine parity, the two halves, spike-event parity, receipt metrics, body and closed loop
python tools/check_site.py          # every page in headless Chromium: no console errors (receipts/site_check.json)
python tools/scenario_fish.py       # the fish page's promises: the hold, the push, the switch, the tap (receipts/scenario_fish.json)
python tools/scenario_larva.py      # the larva page's promises: the lamp, the tap, the switch (receipts/scenario_larva.json)
```

## Rebuild the data

From this folder, with the compiler installed and the brainstem data in
`../connectome-research/data` (see the compiler's source adapter for the two public
repositories):

```
CONNECTOME_DATA=../connectome-research/data python tools/export_brain.py            # web/data/brain.json (the fish)
CONNECTOME_DATA=../connectome-research/data python tools/export_skeletons.py        # web/data/skeletons.json
CONNECTOME_DATA=../connectome-research/data python tools/export_larva_brain.py      # web/data/larva_brain.json (the larva)
CONNECTOME_DATA=../connectome-research/data python tools/export_larva_skeletons.py  # web/data/larva_skeletons.json
CONNECTOME_DATA=../connectome-research/data python tools/parity_cases.py && node tests/parity.mjs
node tests/twin.mjs
node tests/body.mjs
```

`receipts/brain_export.json` records the gain the protocol selected, the axial module's
attenuation and the digests of the tables and the connectome the payload was built from.

## What is compiled and what is declared

The larva: the imported graph supplies the connections between its sensory and effector
cells. Declared: the neuron response, sign rule (all cells excitatory in this export),
gain, sensory mappings, body response and time scale. The display uses 0.8 times the
protocol-selected gain, so its visible response is distinct from the scored protocol run.

The fish: the graph includes the oculomotor integrator, vestibular inputs and connections
into the axial module. The circuit protocol uses the authors' 343-cell oculomotor scope.
Declared: signs, gain, axial attenuation in the full display, neuron dynamics, stimulus
mapping, initial saccadic eye pulse, eye mechanics, mirrored second half and time scale.
The pilot supplies swimming, hunting and escape.

## License

GPL-3.0, the license of Cadence.
