# Amen Studio: a jungle composer that settles live

One Cadence brain learned jungle tracks as events per half-beat: a slice of a drum break,
a sub-bass note, a change flag and a texture. Nothing on the page is recorded: press the
button and the brain starts from silence, hears a count-in, and computes a track one
half-beat at a time — each half-beat is one settlement of the whole brain over the window
of events it actually played — while the page shows its populations settling. When the
track is computed it is rendered through the instrument and played, with every note and
the brain in time with the sound.

This is the successor of the earlier static Amen page in the deprecated
[cadence-examples](https://github.com/muellerberndt/cadence-examples) repository, whose
brain was trained on Cadence 0.11.0. This demo runs the current library itself behind the
page: the browser owns the studio, the playing rule and the instrument; Python owns the
brain. The page keeps its declared per-dub variety rules (see the model card on the page).

## Run it

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python server.py          # open http://localhost:8670 and press CUT A DUB
```

The server loads the brains under `models/`, serves the page, and answers one
`/settle` request per half-beat: a pure query of the trained brain over the heard
window, the clock and the wake flag. Queries admit nothing; the brain on disk never
changes. Torch is used for CPU tensor execution; no GPU is needed.

## What is here

- `server.py`: the brain behind the page. `GET /meta` describes the loaded brains
  (layout, populations, card figures); `POST /settle` settles one half-beat.
- `amen_stream.py`: the event encoding, vendored from the training project and kept
  byte-equivalent where they overlap — the brain was trained on exactly this encoding.
- `static/index.html`: the studio, in two columns: the studio and the sound on the left,
  the brain pinned on the right — the heard ring, the clock, the populations settling
  ring by ring (state in gold and cyan, prediction errors in red), the output scores,
  and the loop through the world.
- `static/client.js`: the page's line to the brain, and the playing rule: how an executed
  event is drawn from the brain's scores, and the declared per-dub variety on top.
- `static/kit/`: the instrument: 32 half-beat slices of a sampled drum break and twelve
  sub-bass notes as 16-bit wav. Whether these recordings may be redistributed has not
  been verified; the kit is a separate folder so it can be replaced.
- `models/<name>/brain.json`: one trained brain per entry in `models/index.json`, with
  its training run, receipt hash and held-out figures. Exported by the development
  project's `export_drsn_demo.py`, which refuses a brain whose free run from silence
  plays drums on fewer than half of the half-beats or bass on fewer than a quarter.

## The brain

Declared with the current `Cortex` builder: a `hearing` column reads the window of the
last events the brain played (71 event ports and a presence mask each), the clock and a
wake flag; a `groove` observer reads the live states and exact prediction errors of
hearing; a `playing` observer holds one patch per event port and observes both. All
populations settle into one equilibrium per half-beat, and the `event` output exposes
the playing patches. Temporal context is the supplied window, not learned recurrent
memory, and a settled state is a numerical qualification, not a claim of musicianship:
the dubs are judged by listening.
