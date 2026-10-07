# From connectome to Cadence

Two animal connectomes running as Cadence rate patch nets. Teach the zebrafish's gaze
circuit to hold, return, and hold again on the same acquired brain. Explore the
Platynereis larva's compiled sensory and motor circuit, whose weights stay fixed.

The mathematical background: [Agreement and Surprise: Global Equilibrium from Local
Repair](https://philpapers.org/rec/MUEAAS-2) and [Cadence: Learning Through Local Patch
Settlement](https://philpapers.org/rec/MUECAP-2).

## Run

```sh
python3 -m http.server 8000 --directory web
```

Open [the fish](http://localhost:8000/fish.html) or [the larva](http://localhost:8000/).
Use HTTP; module imports and data loading need it. Deploy by serving `web/` as a static
site. No application server is required.

## Teach the fish

1. Expand **Teach this fish**, choose **hold your gaze**, and press **Teach this lesson**.
   Automatic eye movements provide lessons; practice ends by pausing learning and testing the response.
2. Choose **let it return** and teach again on the same brain.
3. Switch back to **hold your gaze** and compare the response after another practice.

**Time: 1×** is always visible beside the teaching panel. Click to choose 1×, 4× or 8×;
teaching keeps your chosen speed. Use 8× for faster practice.

**Pause learning** retains acquired weights. **Reset learning** restores the starting
weights and clears activity. **Test its gaze** compares copies of current and starting
weights without teaching or disturbing the live fish. For manual eye movements, allow
at least four seconds of fish time between requests.

The teacher uses the circuit's own activity as feedback. The gaze connections learn;
a fixed pilot supplies swimming, hunting and escape.

## Check

```sh
sh tests/run_all.sh                  # engine checks and seeded learning assays
python tools/check_site.py           # browser pages
python tools/check_learning_ui.py    # visible practice, pause, test and reset
python tools/scenario_fish.py        # compiled-weight fish behavior
python tools/scenario_larva.py       # larva behavior
```

## Source

`web/brain.js` runs the rate patches and weight updates; `web/life.js` connects them to
the fish's continuing life. `web/dictionary.js` declares the model and lesson settings.
The compiler preserves recorded connection partners and synapse counts; dynamics and
body mappings are declared. The compiler itself is not published, but its exported nets
ship in `web/data/`.

Contributor records: [learning release](web/data/learning_release.json),
[direct reteaching](web/data/learning_reteach.json), and the retained historical records
in `receipts/` and `web/data/`.

GPL-3.0, the license of Cadence.
