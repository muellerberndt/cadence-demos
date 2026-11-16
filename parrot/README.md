# Parrot

**What it shows.** A Cadence brain with real memory and a real state, running in real time in the
browser, that hears sound and speaks sound and uses sounds as symbols for things and meanings. Each
sound the parrot keeps is a record in the library's long-term memory, and synapses link the record
to what it means: hearing reads the links from a sound to its meaning, speaking reads them
backwards, from a word to its sound. Between the two, a trained Cadence `Brain` settles on the
answer. A pistachio after a right answer teaches the brain and the links.

An African Grey parrot sits on a perch with an apple, a block, a cup, a key and a green ball on the
table. Ask it a question about one of them, from the list or out loud: it follows the question
word by word, answers with a word, and says that word with the sound it keeps for it. Its brain is
drawn beside it as a bird's brain, live. Everything runs in the browser; there is no server.

Runs on `cadence-net` 0.101.0 (the wheel is in the folder) with the demo's own packages, in
Pyodide.

## Run it

```sh
git clone https://github.com/muellerberndt/cadence-demos.git
cd cadence-demos
python3 -m http.server 8842 --directory parrot/site
```

Open <http://localhost:8842/> in Chrome on a desktop or laptop. The first load fetches Pyodide and
NumPy from jsDelivr and then the brain from the folder (tens of megabytes). Sound plays from your
first click on the page. For the microphone the page must come from `localhost` or https; the
browser asks first, and nothing is recorded or sent.

## What to try first

1. Press **Ask** with *What is this?* selected. The parrot looks at the key, each word lights as it
   is spoken, and it answers "key" in its own voice.
2. Press **Pistachio**. It catches the nut, and the reward reaches its brain.
3. Pick another question from the list, such as *Where is the cup?* or *What colour is the apple?*
4. Click a thing on the table and ask about it out loud: "What colour is this?"
5. Press **Listen to me** and say a short word. It keeps the sound and says it back.

A **?** by the parrot means it did not understand. The line under the buttons says what to do: say
it again, or, when it guessed and the answer is right, give it a pistachio. After that pistachio it
understands that sound the next time.

The page's help (`site/help.html`) explains every part of the screen, and its brain explainer
(`site/brain-explainer.html`) how the brain answers.

## How it works

- **The ear** (`site/dsp.js`, `ear-worklet.js`) turns the microphone's sound into 40 frequency
  bands every 10 ms, the same arithmetic as the library's speech front end, and cuts it into
  utterances: from where a voice starts to the quiet after it.
- **The sound memory** (`site/pack/py/parrotbrain/sounds.py`) keeps each utterance as a record in
  `cadence.LongTermMemory`, keyed by a code of its sound made with `cadence.senses.Ear`. A new take
  is lined up in time with the records; the nearest records vote on what it means. A sound told
  again moves its record toward the new take (`blend`), so the record gets cleaner.
  `cadence.SynapticMemory` links each record to a meaning, and a pistachio strengthens the link.
  This part is the page's own code: it follows the rule of the library's bound records
  (`cadence.bound`, 0.101.0), in which a sound it said is an answer only once a pistachio pays it.
- **The trained brain** (`site/pack/trained/`) hears each word of the question as it is spoken and
  settles on an answer word at its turn. A pistachio after its answer is one small lesson.
- **The voice** plays the sound linked to the answer word. The page measures what it plays, and
  the ear learns how loud its own voice comes back; a voice well above that is someone else's, and
  a word it says by itself stops for it.

## Limits

- **Questions it was taught.** It understands the twelve questions of the list, in the wordings
  its starting memory holds, about the five things on the table, and single answer words. It
  matches a whole utterance to the sounds it keeps and does not take a free sentence apart.
- **New voices.** It starts with one woman's voice and thirty-six other voices. A voice it never
  heard is understood less often: on four such voices, 241 of 288 first hearings were taken for
  the right meaning, 8 for a wrong one and 39 for none (`evidence/sound_flow.json`). After one paid
  hearing, the same visitor's later takes were right 175 times in 200.
- **One thing at a time.** It answers about the thing in focus. The page moves the focus to the
  thing a question names or to the thing you click.
- **Its eyes.** The trained brain does not see the drawn room: the page reports each thing to it
  as its training world did (shape, size, hue, surface, direction, distance).
- **Its voice.** The brain picks the answer word; the sound it says was rendered ahead of time into
  a parrot voice and ships with the page. A word you teach it is said as a pitched-up copy of your
  own sound.
- **Learning.** The brain was trained ahead of time, outside the browser, through the meaning
  lane's own code. In the page a pistachio is one small lesson for the brain and for the links of
  the sounds used. Every visit starts from the shipped memory.
- **Wrong answers.** It gets some question types wrong, so they are not on the list: among them the
  material of some things and the colour of the green ball. `site/pack/trained/version.json` lists
  them.

## Checks

```sh
python3 -m http.server 8842 --directory parrot/site &
python parrot/site/tests/test_sound_symbols.py --url http://localhost:8842/ --out <dir> \
    --voices <dir> --whisper <python with mlx-whisper> --only presets,mic,first,false,robust
```

It plays every listed question into the page in a headless Chromium and checks the answer, the
word-by-word following and the sound said (read back by Whisper); a word said back within 1.5 s in
Listen to me; a first visit using only what is on screen; that coughs, clicks, typing and its own
voice through a loudspeaker are never kept as words; and recovery from a refused microphone, a
reload, a sound while it speaks and a question asked right after a click. `--only visitors` runs
the visitors' matrix. It needs Python with `playwright` and `numpy`, `ffmpeg`, and for the Whisper
reading a Python with `mlx-whisper`. `--voices` takes a folder of recorded takes in voices the
starting memory never heard (the folder ships none); `--only presets` needs none.
`evidence/fresh_clone_release_0101.json` holds a run from a fresh clone, and
`evidence/release_0101.json` the move to 0.101.0.

```sh
python3 parrot/site/tests/test_words.py        # hearing, keeping and strengthening a word
python3 parrot/site/tests/test_sound_memory.py # the sound memory's records and links
node parrot/site/tests/dsp_parity.mjs          # the page's ear against the library's front end
```

## Layout

| Path | What |
| --- | --- |
| `site/index.html`, `app.js`, `styles.css`, `flow.css` | the page and its loop |
| `site/scene.js`, `parrot.js`, `rig.json`, `looks.js`, `looks/` | the room and the parrot |
| `site/dsp.js`, `ear-worklet.js`, `audio.js` | the ear and the voice |
| `site/voice/` | the starting sounds and their meanings (`words.json`), the parrot's renderings, the listed questions as sound |
| `site/brain3d.js`, `brainscan.js`, `brainlive.js`, `atlas.js`, `memview.js` | the brain view |
| `site/worker.js`, `site/pack/` | the brain in Pyodide: the manifest (with the SHA-256 of every file, checked before anything runs), the hosts (`py/parrotbrain/`), the wheel, the trained brain |
| `site/pack/py/parrotbrain/` | `sounds.py` and `host.py` (the hearing, the page's own), `trained.py` and `page.py` (the trained brain's host), and `meaning/`, `parrot/`, `words/`, carried from the library's development branches [`lane-0100-meaning`](https://github.com/muellerberndt/cadence/tree/lane-0100-meaning) and [`lane-0100-parrot`](https://github.com/muellerberndt/cadence/tree/lane-0100-parrot) |
| `site/help.html`, `site/brain-explainer.html` | the help page and the brain explainer |
| `site/tools/` | building the starting sounds, the question list and the manifest |
| `site/tests/` | the checks above |
| `evidence/` | the readings behind the numbers |

## Licence

GPL-3.0, as the repository. Every third-party asset, with its source, author and licence, is in
[ATTRIBUTION.md](ATTRIBUTION.md). The voices are generated with ElevenLabs.
