# Parrot (preview)

> **Preview.** A development build of the parrot page, published so that its code can be read and
> run. It does what [What works](#what-works) lists, with the limits under
> [What it does not do](#what-it-does-not-do). It runs on the released `cadence-net` 0.100.0; the
> parts of the brain that the library does not release live in this folder.

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

**Not understood.** A sound it makes nothing of brings a **?** by the parrot, and a line by the
Pistachio button says what to do: say it again, or pick a question from the list. An answer it
guessed brings the same **?** first, and the line says to give it a pistachio if the answer is
right and to say it again if not. A single word it only guessed brings the **?** and the line too, and moves
its attention nowhere. After you click a thing it says nothing by itself for three seconds, so a
question asked at once is heard; and a word it says by itself stops when a voice comes in over it,
as a bird stops calling. The ear tells another voice from its own by what the page plays: it learns
how loud its own voice comes back to it, and a voiced sound well above that is someone else. The
brain view's Voice box shows a word while it is said.

`site/tests/test_sound_symbols.py` checks these on the real page in a headless Chromium. Its
sections:

- `presets`: every listed question plays into the ear. The utterance is taken for its meaning by
  its record's link (no guess), every word is known as it is spoken, the answer is right, it is said
  with the sound linked to the word in the parrot's own rendering, and Whisper reads that sound as
  the word. A pistachio after an answer pays the brain's lesson and the links.
- `mic`: through a stand-in microphone, in Listen to me, a word in a voice the parrot never heard
  is kept as one utterance and said back within a second of the keeping; then six first hearings,
  each said back within 1.5 s of the utterance's end, with the machine as found and with every
  core kept busy.
- `first`: a first visit with what is on screen alone, from Listen to me to a question and a
  pistachio; then a question in the visitor's own voice (a voice in no record), answered right
  when understood, and when guessed the hint by the Pistachio button, a right guess paid and the
  question understood when asked again; and a sound it cannot make out (the visitor's question
  played backwards), with the **?** and the hint to say it again.
- `false`: sounds that are no speech (a cough, a breath, typing, a click, a door, a fan and others)
  and the parrot's own voice from the loudspeaker; none may be kept as an utterance, said back or
  answered.
- `robust`: the microphone refused, a reload in the middle of an exchange, a sound while it speaks,
  the switch pressed at any moment; after each the page answers a listed question. Then a question
  in a voice in no record asked 0.5, 3.0 and 3.5 s after a click on a thing: heard and answered
  right each time.

`evidence/sound_flow.json` holds the readings of these sections from development.

`evidence/clean_clone_20261115.json` holds runs from a fresh clone, on a machine shared with
other jobs. With every section in one go, all five passed: every listed question, asked twice, was
taken for its meaning by its record's link, followed word by word, answered right and said in the
parrot's rendering, which Whisper read as the word; the six steps of the first visit passed; no
sound that is no speech was kept; the `robust` cases passed. The `mic` section sits at the edge of
its own window. Over seven runs the visitor's word was kept and linked every time, and it was said
back within the test's four seconds in three; where the log shows a later sound, it came 3.6 to
4.4 s after the word. The same action inside `first` passed in three of three runs.

**The say-back's delay.** In the build those runs read, each sound that became one the parrot can
say sent the audio of every kept sound to the page again, and the say-back waited for it. This
build sends the changed sounds alone, and the memory's picture goes to the page two and a half
seconds after a change, outside the moment a sound is answered in. The `mic` section times six
first hearings of a voice in no record from each utterance's end and passes where each say-back
starts within 1.5 s and the middle one within 1.2 s, once with the machine as found and once with
one busy process a core. Readings from a fresh clone on a ten-core machine shared with other
jobs: 0.57 to 0.67 s as found (median 0.63 s, load average 12) and 0.56 to 0.80 s with ten busy
processes (median 0.68 s, load average 17); over four voices in no record, clean and through a
laptop's microphone, 47 utterances said back a median 0.64 s after their end (at most 0.77 s).
The answer to a visitor's own question in Curious starts a median 1.07 s after the question's end
(73 of 76 within 1.5 s). `evidence/sound_flow.json` and `evidence/fresh_clone_parrot_voices.json`
hold these readings.

## What it does not do

- **Free speech.** It does not take a sentence apart from its sound. The ear matches a whole
  utterance to the sounds it keeps, and the matched record's link, or the vote of the records
  nearest it, names the meaning: a word, or one of the questions the brain was taught. The wordings it knows are the ones the starting memory
  holds. Where each word begins inside a question's record was marked when the starting memory was
  built, from Whisper's word times.
- **Any voice at once.** A voice it has never heard is understood less often than the starting
  voice. The starting memory holds one woman's questions and answer words and thirty-six other
  voices (men and women, young to old, American, British, Australian and Indian), each heard once
  saying every question and answer word: 1,606 records, their audio not shipped. A visitor's
  utterance is taken for what the records nearest it agree on. On four voices in no record (a
  British man, an Australian man, an Indian woman, an American woman), 288 takes of the listed
  questions and ten answer words, heard for the first time: 241 taken for the right meaning, 8 for
  a wrong one and 39 for none with clean takes (the questions 153 of 156 right, none wrong; the
  words 88 of 132 right, 8 wrong); 215 right and 10 wrong through a laptop's microphone with the
  room's noise 20 dB below the voice; 147 right and 15 wrong at 10 dB. After one paid hearing of an
  utterance, that visitor's other takes of it: 175 of 200 right and 3 wrong (clean; the questions
  103 of 108, none wrong). The starting
  memory with four other voices read 170 right and 7 wrong of the same 288. In Curious, a sound
  with no meaning the parrot knows is a guess among the questions about the thing in focus; a
  pistachio after a right answer links the sound to that meaning. `evidence/sound_flow.json`
  holds these readings and the routes measured on the way.
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

- **The released Cadence library**: `cadence-net` 0.100.0 from PyPI, unchanged, in the folder as
  `site/pack/cadence_net-0.100.0-py3-none-any.whl`.
- **The parts of the brain the library does not release**, in the page's own package
  (`site/pack/py/parrotbrain/`): `meaning/` (the answering brain's host, its senses and its build),
  `parrot/` (the parrot's body, eyes, map, focus and voice) and `words/`, carried from the library's
  development branches
  [`lane-0100-meaning`](https://github.com/muellerberndt/cadence/tree/lane-0100-meaning) and
  [`lane-0100-parrot`](https://github.com/muellerberndt/cadence/tree/lane-0100-parrot) with their
  imports of the library made absolute; and the hearing layer (`sounds.py`, `host.py`), the page's
  own. `site/pack/manifest.json` names the commits.
- **The trained brain**, `site/pack/trained/`: `brain.npz` and `spec.json`, with `version.json`
  (its training step, its readings, what it gets wrong) and `probes.json`.
- **In the browser**: Python through Pyodide in a web worker, which checks the SHA-256 of every
  pack file against the manifest before it runs anything; three.js for the room and the brain view.

On 0.100.0 the library does two things the page did itself: a record told again moves toward the
new take (`LongTermMemory(blend=True)`, the record strength of cadence#336; the page lays the take on
the record's timeline first), and the carried host of the answering brain is the meaning lane's at
613bcbc6, with the `exact` rule removed. These stay in the folder, and why:

- **Equal senses and senses by name** (`senses=`, `code=units`): the trained brain's weights were
  learned through the meaning lane's own mixed code; the library's door draws its own fixed code,
  which those weights do not read.
- **The map read of one attended thing** (`Map.thing_at`): the answering brain's glimpse comes from
  the page's description of the room, as its training world reported things; the body's map holds
  places, not the colour and material that brain was trained on.
- **The pistachio with an open slot** (`learning.OPEN`): the carried host teaches the reply's word
  with the second slot at 0, as its training did; leaving that slot open changes what a pistachio
  teaches.
- **"It moved", "it appeared" and the focus they draw** (`cadence.surprise`): the carried focus
  weighs a thing's move against its usual move on its own scale; the library's per-unit surprise
  uses another, so its focus would move at other moments.
- **The ear, the follower and the sound memory's vote and lessons** (`host.py`, `sounds.py`): no
  library feature takes their place.

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
none. `--only presets` runs the list alone and needs no such folder, `--rounds` sets how often
each question is asked (two by default), and `--busy` sets the busy processes of the `mic`
section's loaded pass (one a core by default).

```sh
node parrot/site/tests/dsp_parity.mjs          # the page's ear against the library's front end
node parrot/site/tests/voice_roundtrip.mjs     # the voice's bands to sound and back
```

## Credits

Every third-party asset, with its source, author and licence, is in
[ATTRIBUTION.md](ATTRIBUTION.md). The voices are generated with ElevenLabs. Cadence is GPL-3.0.
