# Parrot

An African Grey parrot on a low perch, with two eyes on the sides of its head, an ear, a voice, a
head and joints its brain moves, and a room where the visitor places things. It is the stage of the
parrot experiment (cadence#332, a step of cadence#331): can the parrot track and remember what it
sees through its two eyes, and learn a sense of distance from them. Its brain is drawn in 3D beside
it. Everything runs in the browser; there is no server.

The pack holds three brains, picked in the page's brain switch (`?brain=trained|composed|placeholder`):

- **trained tonight**: the composed body and hearing, with the brain the meaning lane trained overnight
  (cadence#334, `cadence.meaning.host.MeaningParrot`, its files in `site/pack/trained/` with
  `version.json` naming its step, founder and export). It hears typed questions (Ask it, under the
  brain) one word a moment and answers in its turn; a pistachio pays its last answer, a typed word
  corrects it. In its mind shows the facets of the thing in focus that the meaning lane's probes read
  from its state, where the lane exports `probes.json` beside the brain.
- **composed**: the parrot-brain lane's `cadence.parrot` (eyes, distance, focus, map) with the page's
  hearing layer.
- **placeholder**: a hand-written controller (a newborn that looks, hears and calls), with the
  interface the composed parrot brain's host keeps. What it hears is kept in the
Cadence library's own memories (`LongTermMemory` records and a `SynapticMemory`), from the shipped
`cadence-net` 0.99.0 wheel.

## Run it locally

```sh
python3 -m http.server 8842 --directory parrot/site   # then open http://localhost:8842/
```

`localhost` is a secure page, so the microphone works. `?look=anime` picks the anime parrot,
`?brain=trained|composed|placeholder` picks the brain, `?brain=off` skips the brain, `?view=front|side|head|feet` frames the parrot, `?test=1` runs the
scripted placements.

## What is where

| Path | What |
| --- | --- |
| `site/index.html`, `styles.css`, `favicon.svg` | the page: the room, the brain in 3D, the detail panel |
| `site/help.html` | the help page (what you see, why it matters, what you can do, how it works, the numbers, limits, credits) |
| `site/app.js` | the loop: the room, dragging and placing, the moments of the brain, the focus, sound, the pistachio |
| `site/scene.js` | the room: light probe, table, perch, the things at their real sizes |
| `site/parrot.js`, `site/rig.json` | the rig: bones, eye sockets, the eleven joints (critically damped servos, natural and combined limits), the drawn placeholder body |
| `site/looks.js`, `site/looks/` | the two bodies on the rig (realistic, anime), their fitted rigs |
| `site/eyes.js` | the two eyes: cube renders read off into each eye's image |
| `site/dsp.js`, `site/ear-worklet.js`, `site/audio.js` | the ear (the library's log-mel front end in JavaScript, in an audio worklet) and the voice (a filter-bank voice from the same frames) |
| `site/pistachio.js` | the pistachio: thrown, caught in the beak, eaten |
| `site/brain3d.js`, `site/atlas.js` | the brain in 3D: the planned parrot brain's regions and tracts, filled with the running brain |
| `site/memview.js` | the memory view: records, reads, synapses |
| `site/brainview.js` | the detail panel: populations, distance units with tuning curves and their silence switch, joints |
| `site/worker.js`, `site/pack/` | the brain in Pyodide: the manifest (SHA-256 of every file), the hosts (`py/parrotbrain/`: `host.py` the placeholder and hearing, `page.py` the composed, `trained.py` the trained brain beside the composed), the calls, the wheel (`cadence.parrot` and `cadence.meaning`), the trained brain's files (`trained/`, loaded only when that brain is picked) |
| `site/tools/` | `fetch_assets.py` (Poly Haven assets and their credits), `prepare_look.py` (a body onto the rig), `make_calls.py` (the calls from the recording), `build_pack.py`, `check_page.py` (the page check), `shoot_looks.py` with `look.html` (a body in the page's light) |
| `site/tests/` | `dsp_parity.mjs` (the ear against the library), `voice_roundtrip.mjs`, `test_sound_memory.py`, fixtures |
| `evidence/` | the readings the help page's numbers come from |

## Checks

```sh
node parrot/site/tests/dsp_parity.mjs            # largest difference 0.0007 (limit 0.001)
node parrot/site/tests/voice_roundtrip.mjs       # mean offset 0.00 nat, mean error 0.64 nat (limits 0.5, 1.3)
python parrot/site/tests/test_sound_memory.py    # one deep record for a word said ten times; noise writes none; once fades
python parrot/site/tools/check_page.py --shots <dir>   # end to end, the skin's stretch sweep, the head's rigidity, the distance units
python tools/check_explain.py parrot --shots <dir>     # the demos' shared gate
```

The stretch sweep's strict limit (no triangle edge beyond 1.25 times its rest length over every
joint and the head's turn with its tilt and cock) fails at the head's limits on both bodies (worst
5.7 on the realistic one); `evidence/page_check.json` holds the readings.

## Credits

- The realistic and the anime parrot: made for this page with Meshy (an image, then image to 3D),
  on the owner's paid plan; the anime parrot is an original design.
- The African Grey calls: cut from "Psittacus erithacus making some noise" by Amada44, Wikimedia
  Commons, CC BY 3.0, https://commons.wikimedia.org/wiki/File:Psittacus_erithacus_making_some_noise.ogg
  (SHA-1 536bd991cb9bbfd85febd7315571c848b22253e5); changed: cut into calls and turned into the
  ear's log-mel frames (`site/pack/calls.json`).
- Models, textures and the light probe: Poly Haven, CC0. Each asset, its page, authors, the files
  fetched with their MD5 and the SHA-256 of the file the page loads: `site/assets/CREDITS.json`.
- three.js 0.160.0 (MIT, `site/vendor/three/LICENSE`), Pyodide (MPL 2.0, from jsDelivr), the
  Cadence library 0.99.0 (GPL 3.0).
