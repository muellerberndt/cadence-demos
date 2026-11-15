# Parrot (preview)

> **Preview.** A development build of the parrot page, published so that its code can be read and
> run. It does what [What works](#what-works) lists, with the limits under
> [What it does not do](#what-it-does-not-do). It runs on a development build of the Cadence
> library, included in this folder; it does not run on a released `cadence-net`.

## What it shows

**A brain that hears sound and answers in sound, with sounds as its symbols.** An African Grey
parrot sits on a perch among a few things, and its brain is drawn beside it as a bird's brain. A
preset question plays as sound and reaches the parrot's ear. Each sound the ear keeps is linked to
a word: a heard word lights in the question's subtitle, and a word that names a thing on the table
lights that thing's tag in the brain view. A trained Cadence brain settles on an answer word, and
the answer brings back the sound kept for that word, which the parrot says. Everything runs in the
browser; there is no server.

Why it matters for Cadence: a word's sound is a memory that is read in both directions. The ear
keeps each sound as a record in the library's long-term memory (`cadence.LongTermMemory`), and
synapses link the record to a word (`cadence.SynapticMemory`). Hearing reads from a sound to its
word; speaking reads the same synapses backwards, from a word to its sound. The answer between the
two is the settled state of one trained `Brain`.

The page is a step of the parrot goal
([cadence#331](https://github.com/muellerberndt/cadence/issues/331)); the trained brain comes
from [cadence#334](https://github.com/muellerberndt/cadence/issues/334).

## Run it locally

```sh
git clone https://github.com/muellerberndt/cadence-demos.git
cd cadence-demos
python3 -m http.server 8842 --directory parrot/site
```

Open <http://localhost:8842/> in Chrome. Any static file server works. The first load fetches
Pyodide and NumPy from jsDelivr and the fonts from Google Fonts, then the brain from the folder (a
file of tens of megabytes), so it takes a while. Sound plays from the first click on the page.

Under **Ask it**, pick a question and press **Ask**. The microphone is optional: the preset
questions reach the ear inside the page. With the microphone on (`localhost` is a secure page, the
browser asks first), the ear hears you: a word it matches to a sound it keeps lights that word's
tag. Nothing is recorded or sent anywhere.

`?mic=off` starts with the microphone off, `?look=anime` picks the anime body,
`?layout=classic` shows the earlier panels, and `?brain=composed|placeholder|off` picks another
brain or none.

## What works

The preset questions under **Ask it**, each in the room the page starts with (an apple, a block, a
cup, a key and a green ball). The page puts the thing a preset is about in focus.

| Question | Thing in focus | Answer |
| --- | --- | --- |
| What is this? | the key | key |
| What color is this? | the block | blue |
| Is this white? | the cup | yes |
| Where is the cup? | the cup | behind |
| Can you eat this? | the apple | yes |
| What color has the apple? | the apple | red |
| Where is the ball? | the green ball | right |
| What shape has the apple? | the apple | round |
| Is this red? | the apple | yes |
| What color has the cup? | the cup | white |
| What shape has the block? | the block | no |

The shape answer is "round" or "no": the brain's voice has no word for another shape.

`site/tests/test_sound_symbols.py` checks every preset on the real page in a headless Chromium:
each word of the question is heard as sound (no text stands in), the answer is right, the answer
is said with a kept sound whose record is linked to the answer's word, and Whisper reads that
sound as the word. It then plays the word "apple" in a voice the parrot never heard through a
stand-in microphone, with the apple in focus, and checks that the apple's tag lights in the brain
view (after a pistachio, where the ear does not link the sound to "apple" at once).

## What it does not do

- **Natural sentences.** The preset questions are spoken one word at a time with short pauses.
  The ear cuts sound into single words at the quiet between them.
- **Free questions.** The Ask box holds the presets alone. A question spoken into the microphone
  is not answered as a question: the page takes each word it recognises by itself.
- **Every question type.** Some question types are answered wrong and are left out of the
  presets: a preset is a question the brain answered right on every pass of
  `site/tools/check_presets.py`. The brain's version file (`site/pack/trained/version.json`)
  records what it gets wrong, among them a thing's material on some things, "is this" with a
  colour on some things, and the colour and roundness of the green ball. In rooms other than the
  starting one it is right less often: the same file records .887 on fresh rooms, and .787 where
  the pairs of kind and colour are ones it never saw.
- **More than one thing at a time.** It answers about the thing in focus and binds one attended
  thing at a time. The page puts a thing in focus: the thing a preset is about, the thing a
  question names, or the thing you click. Questions about the whole room are not among the
  presets.
- **Words bound inside the trained brain.** The link between a sound and its word is held in the
  hearing layer's records and synapses, beside the trained brain. The trained brain receives each
  recognised word as the code its training drew for that word.
- **Sight through the drawn eyes.** The trained brain does not see the rendered room. The page
  reports each thing to it from a table of its kind, colour and material, as the readings of its
  training world: shape and size, hue and lightness, surface, direction and distance. No input
  names a kind or a colour.
- **A voice made by the brain.** The brain picks the answer word. The sound the parrot says is a
  recording: the starting sounds were made ahead of time and ship with the page, each with the
  parrot's rendering of it (see [ATTRIBUTION.md](ATTRIBUTION.md)).
- **Learning words from nothing in the browser.** The trained brain was trained ahead of time,
  outside the browser. The starting sounds and their links to words ship with the page, and every
  start begins from them. In the page, a pistachio after an answer is one small lesson, and a
  pistachio after a sound you make with a thing in focus links that sound to the thing's word.
- **A match for every sound.** The ear matches a sound to the nearest record it keeps, so a sound
  that is no word can be heard as one. Where the ear misses a word of a preset, the page sends the
  preset's words as text and says so in the browser console; the test counts such a question as
  failed.

The help page (`site/help.html`) and the brain explainer (`site/brain-explainer.html`) were written
during development. Parts of them describe earlier panels, the composed and the placeholder brain,
and trained brains that this folder does not include; each says so at its top. This README states
what the preview does.

## What it runs on

- **A development build of the Cadence library**, included in the folder:
  `site/pack/cadence_net-0.99.0-lane-meaning-568a0ad8-parrot-5fccf8cb.whl`. It is built from the
  library's development branches
  [`lane-0100-meaning`](https://github.com/muellerberndt/cadence/tree/lane-0100-meaning) and
  [`lane-0100-parrot`](https://github.com/muellerberndt/cadence/tree/lane-0100-parrot), which add
  `cadence.meaning` and `cadence.parrot`; `site/pack/manifest.json` names the commits. Its version
  field reads 0.99.0, and it is no released build.
- **The page does not run on the released `cadence-net` 0.99.1**, which has no `cadence.meaning`
  and no `cadence.parrot`. The library release that carries these features is in preparation.
- **The trained brain**, `site/pack/trained/`: `brain.npz` and `spec.json`, with `version.json`
  (its training step, its readings, what it gets wrong) and `probes.json`.
- **In the browser**: Python through Pyodide in a web worker, which checks the SHA-256 of every
  pack file against the manifest before it runs anything; three.js for the room and the brain view.

[Cadence](https://github.com/muellerberndt/cadence) is the library; its README explains how a
Cadence brain settles and learns.

## What is where

| Path | What |
| --- | --- |
| `site/index.html`, `styles.css`, `app.js` | the page and its loop: the room, the questions, the focus, sound, the pistachio |
| `site/scene.js`, `parrot.js`, `rig.json`, `looks.js`, `looks/` | the room, the parrot's rig and its two bodies |
| `site/dsp.js`, `ear-worklet.js`, `audio.js` | the ear (the library's log-mel front end in JavaScript, in an audio worklet) and the voice |
| `site/voice/` | the starting sounds with their links to words (`words.json`), the parrot's renderings (`parrot/`), the preset questions as sound (`questions/`) |
| `site/brain3d.js`, `brainscan.js`, `brainlive.js`, `atlas.js`, `memview.js`, `brainview.js` | the brain view |
| `site/worker.js`, `site/pack/` | the brain in Pyodide: the manifest, the hosts (`py/parrotbrain/`: `sounds.py` the hearing layer's memories, `host.py`, `page.py`, `trained.py` the trained brain), the calls, the wheel, the trained brain |
| `site/help.html`, `site/brain-explainer.html` | the help page and the brain explainer |
| `site/tools/` | `build_words.py` (the starting sounds and question clips), `check_presets.py` (which questions become presets), `build_pack.py` (the manifest), `fetch_assets.py`, `prepare_look.py`, `make_calls.py`, `check_page.py`, `check_text.py`, `shoot_looks.py` |
| `site/tests/` | `test_sound_symbols.py` (the check above), `test_sound_memory.py`, `test_words.py`, `dsp_parity.mjs`, `voice_roundtrip.mjs`, fixtures |
| `evidence/` | the readings behind the help page's numbers and the checks |
| `ATTRIBUTION.md` | every asset with its source, author and licence |

## Checks

```sh
python3 -m http.server 8842 --directory parrot/site &
python parrot/site/tests/test_sound_symbols.py --url http://localhost:8842/ --out <dir> \
    --apple <apple.wav> --whisper <python with mlx-whisper>
```

The test needs Python with `playwright` (and its Chromium) and `numpy`, `ffmpeg` on the path, and
for the Whisper reading a Python with `mlx-whisper` (Apple silicon). `--apple` takes a recording of
the word "apple" in a voice the page never heard; the folder ships none. `--skip-mic` leaves the
microphone part out, and `--rounds` sets how often each preset is asked (two by default).

```sh
node parrot/site/tests/dsp_parity.mjs          # the page's ear against the library's front end
node parrot/site/tests/voice_roundtrip.mjs     # the voice's bands to sound and back
```

## Credits

Every third-party asset, with its source, author and licence, is in
[ATTRIBUTION.md](ATTRIBUTION.md). The voices are generated with ElevenLabs. Cadence is GPL-3.0.
