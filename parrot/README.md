# Parrot (preview)

> **Preview.** A development build of the parrot page, published so that its code can be read and
> run. It does what [What works](#what-works) lists, with the limits under
> [What it does not do](#what-it-does-not-do). It runs on a development build of the Cadence
> library, included in this folder; it does not run on a released `cadence-net`.

## What it shows

**A brain that hears sound and answers in sound, with sounds as its symbols.** An African Grey
parrot sits on a perch among a few things, and its brain is drawn beside it as a bird's brain. A
question from the list plays as a woman's spoken sentence and reaches the parrot's ear. Each sound
the ear keeps is linked to a meaning, a word or a question: each word of a question it knows
lights as it is spoken, and a word that names a thing on the table lights that thing's tag. A
trained Cadence brain settles on an answer word, and the answer brings back the sound kept for
that word, which the parrot says. A pistachio after a right answer pays the brain's lesson and the
links of the sounds used. One switch holds two ways of attending: **Curious**, in which the parrot
looks at the things and answers a question about the thing in focus, and **Listen to me**, in
which it looks at you, keeps what it hears and says it back. Everything runs in the browser; there
is no server.

Why it matters for Cadence: a sound is a memory that is read in both directions. The ear keeps each
utterance (a word or a whole spoken phrase) as a record in the library's long-term memory
(`cadence.LongTermMemory`), and synapses link the record to its meaning (`cadence.SynapticMemory`).
Hearing reads from a sound to its meaning; speaking reads the same synapses backwards, from a word
to its sound. The answer between the two is the settled state of one trained `Brain`.

The page is a step of the parrot goal
([cadence#331](https://github.com/muellerberndt/cadence/issues/331)); the trained brain comes
from [cadence#334](https://github.com/muellerberndt/cadence/issues/334).

**Video.** [A recording of an earlier build of this page](https://www.youtube.com/watch?v=amR3cnrmgDo);
for the video the voices were re-recorded and the picture was timed to them.

## Run it locally

```sh
git clone https://github.com/muellerberndt/cadence-demos.git
cd cadence-demos
python3 -m http.server 8842 --directory parrot/site
```

Open <http://localhost:8842/> in Chrome. Any static file server works. The first load fetches
Pyodide and NumPy from jsDelivr and the fonts from Google Fonts, then the brain from the folder (a
file of tens of megabytes), so it takes a while. Sound plays from the first click on the page.

The page starts in **Curious**. Under **Ask it**, pick a question and press **Ask**; throw a
**Pistachio** after a right answer. Press **Listen to me** and say a word: the parrot keeps it and
says it back. The microphone is optional for the list: its questions reach the ear inside the
page. With the microphone on (`localhost` is a secure page, the browser asks first), the ear hears
you. Nothing is recorded or sent anywhere.

`?mic=off` starts with the microphone off, `?look=anime` picks the anime body,
`?layout=classic` shows the earlier panels, and `?brain=composed|placeholder|off` picks another
brain or none.

## What works

**Spoken questions, answered in sound.** The questions of the list under **Ask it**, each in the
room the page starts with (an apple, a block, a cup, a key and a green ball). Each plays as a
woman's spoken sentence. The ear takes the whole utterance for the question its record is linked
to, and the brain hears that question's words. The page puts the thing a listed question is about
in focus.

| Question | Thing in focus | Taken for | Answer |
| --- | --- | --- | --- |
| What is this? | the key | what is this | key |
| What colour? | the block | what colour is this | blue |
| Is this white? | the cup | is this white | yes |
| Where is the cup? | the cup | where is the cup | behind |
| Can you eat it? | the apple | can you eat this | yes |
| What colour is the apple? | the apple | what colour has the apple | red |
| Where is the ball? | the green ball | where is the ball | right |
| What shape is the apple? | the apple | what shape has the apple | round |
| Is this red? | the apple | is this red | yes |
| What colour is this? | the cup | what colour is this | white |
| Where is it? | the cup | where is the thing in focus | behind |
| What colour is the cup? | the cup | what colour has the cup | white |

**A pistachio.** After an answer, a pistachio pays one small lesson of the brain and the links of
the sounds used.

**Listen to me.** A word said to it is kept as one utterance and said back.

`site/tests/test_sound_symbols.py` checks these on the real page in a headless Chromium. Its
sections:

- `presets`: every listed question plays into the ear. The utterance is taken for its meaning by
  its record's link (no guess), every word is known as it is spoken, the answer is right, it is said
  with the sound linked to the word in the parrot's own rendering, and Whisper reads that sound as
  the word. A pistachio after an answer pays the brain's lesson and the links.
- `mic`: through a stand-in microphone, in Listen to me, a word in a voice the parrot never heard
  is kept as one utterance and said back.
- `first`: a first visit with what is on screen alone, from Listen to me to a question and a
  pistachio.
- `false`: sounds that are no speech (a cough, a breath, typing, a click, a door, a fan and others)
  and the parrot's own voice from the loudspeaker; none may be kept as an utterance, said back or
  answered.
- `robust`: the microphone refused, a reload in the middle of an exchange, a sound while it speaks,
  the switch pressed at any moment; after each the page answers a listed question.

`evidence/sound_flow.json` holds the readings of these sections from development.

`evidence/clean_clone_20261115.json` holds a run from a fresh clone, on a machine shared with
other jobs. Every listed question, asked twice, was taken for its meaning by its record's link,
followed word by word, answered right and said in the parrot's rendering, which Whisper read as
the word; no sound that is no speech was kept; the `robust` cases passed. In that first run, under
heavy load, the `mic` word was kept and was not said back within the test's four seconds, one step
of `first` missed its window, and one of the four answers in the own-voice part of `false` was
wrong. Run again by themselves, the three sections passed.

## What it does not do

- **Free speech.** It does not take a sentence apart from its sound. The ear matches a whole
  utterance to the sounds it keeps, and the matched record's link, or the vote of the records
  nearest it, names the meaning: a word, or one of the questions the brain was taught. The wordings it knows are the ones the starting memory
  holds. Where each word begins inside a question's record was marked when the starting memory was
  built, from Whisper's word times.
- **Any voice at once.** A voice it has never heard is understood far less often than the starting
  voice, until it has been heard and paid with a pistachio. The starting memory holds one woman's
  questions and answer words and four other voices heard once each. In Curious, a sound with no
  meaning the parrot knows is a guess among the questions about the thing in focus; a pistachio
  after a right answer links the sound to that meaning. `evidence/sound_flow.json` holds the
  development readings on voices in no record.
- **Every question type.** Some question types are answered wrong and are left out of the list: a
  listed question is one the brain answered right on every pass of `site/tools/check_presets.py`.
  The brain's version file (`site/pack/trained/version.json`) records what it gets wrong, among
  them a thing's material on some things, "is this" with a colour on some things, and the colour
  and roundness of the green ball. In rooms other than the starting one it is right less often:
  the same file records .887 on fresh rooms, and .787 where the pairs of kind and colour are ones
  it never saw.
- **More than one thing at a time.** It answers about the thing in focus and binds one attended
  thing at a time. The page moves the focus: to the thing a listed question is about, to a thing
  whose name is heard, or to the thing you click. Questions about the whole room are not in the
  list.
- **Words bound inside the trained brain.** The link between a sound and its meaning is held in
  the hearing layer's records and synapses, beside the trained brain. The trained brain receives
  each word of a question as the code its training drew for that word.
- **Sight through the drawn eyes.** The trained brain does not see the rendered room. The page
  reports each thing to it from a table of its kind, colour and material, as the readings of its
  training world: shape and size, hue and lightness, surface, direction and distance. No input
  names a kind or a colour.
- **A voice made by the brain.** The brain picks the answer word. The sound the parrot says is a
  recording: the starting sounds and the parrot's rendering of each answer word were made ahead of
  time and ship with the page (see [ATTRIBUTION.md](ATTRIBUTION.md)).
- **Learning its words in the browser from nothing.** The trained brain was trained ahead of time,
  outside the browser, and the starting sounds with their links ship with the page; every start
  begins from them. In the page a pistachio after an answer is one small lesson for the brain and
  for the links of the sounds used. A pistachio's lesson can unsettle a neighbouring answer: in
  development about one answer in a hundred flipped after a paid answer. In this build the brain
  takes its own lesson only where it would not give the paid answer by itself, and in the reading
  taken with that rule the probe answers stood (`evidence/sound_flow.json`). The brain
  switch also holds an entry that starts the same brain with an empty memory of sounds
  (`?brain=trained-nowords`). That entry is an experiment, and this README claims nothing for it.

The shape answer is "round" or "no": the brain's voice has no word for another shape.

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
| `site/index.html`, `styles.css`, `flow.css`, `app.js` | the page and its loop: the room, the two ways of attending, the questions, the focus, sound, the pistachio |
| `site/scene.js`, `parrot.js`, `rig.json`, `looks.js`, `looks/` | the room, the parrot's rig and its two bodies |
| `site/dsp.js`, `ear-worklet.js`, `audio.js` | the ear (the library's log-mel front end in JavaScript, in an audio worklet) and the voice |
| `site/voice/` | the starting sounds with their links to meanings (`words.json`), the parrot's renderings (`parrot/`), the listed questions as sound (`questions/`, `questions.json`) |
| `site/brain3d.js`, `brainscan.js`, `brainlive.js`, `atlas.js`, `memview.js`, `brainview.js` | the brain view |
| `site/worker.js`, `site/pack/` | the brain in Pyodide: the manifest, the hosts (`py/parrotbrain/`: `sounds.py` the hearing layer's memories, `host.py`, `page.py`, `trained.py` the trained brain), the calls, the wheel, the trained brain |
| `site/help.html`, `site/brain-explainer.html` | the help page and the brain explainer |
| `site/tools/` | `build_words.py` (the starting sounds and question clips), `check_presets.py` (which questions go on the list), `build_pack.py` (the manifest), `fetch_assets.py`, `prepare_look.py`, `make_calls.py`, `check_page.py`, `check_text.py`, `shoot_looks.py` |
| `site/tests/` | `test_sound_symbols.py` with `flow_checks.py` and `room.py` (the checks above), `test_sound_memory.py`, `test_words.py`, `dsp_parity.mjs`, `voice_roundtrip.mjs`, fixtures |
| `evidence/` | the readings behind the checks and the help page's numbers |
| `ATTRIBUTION.md` | every asset with its source, author and licence |

## Checks

```sh
python3 -m http.server 8842 --directory parrot/site &
python parrot/site/tests/test_sound_symbols.py --url http://localhost:8842/ --out <dir> \
    --voices <dir> --whisper <python with mlx-whisper> --only presets,mic,first,false,robust
```

The test needs Python with `playwright` (and its Chromium) and `numpy`, `ffmpeg` on the path, and
for the Whisper reading a Python with `mlx-whisper` (Apple silicon). `--voices` takes a folder of
visitors' takes, one folder a voice, in voices the starting memory never heard; the folder ships
none. `--only presets` runs the list alone and needs no such folder, and `--rounds` sets how often
each question is asked (two by default).

```sh
node parrot/site/tests/dsp_parity.mjs          # the page's ear against the library's front end
node parrot/site/tests/voice_roundtrip.mjs     # the voice's bands to sound and back
```

## Credits

Every third-party asset, with its source, author and licence, is in
[ATTRIBUTION.md](ATTRIBUTION.md). The voices are generated with ElevenLabs. Cadence is GPL-3.0.
