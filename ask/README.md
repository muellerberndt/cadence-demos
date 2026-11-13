# Ask the Parrot

Ask an African Grey parrot about its room. It answers in words it learned by being shown things.

An African Grey sits on its perch in a room seen from above, with a ball, a cup, a book, an apple
and a kettle around it. Type a question ("where is the ball?", "what colour is the cup?", "what is
red?", "what is behind you?") and the parrot answers in a speech bubble, in words its Cadence brain
learned from naming. Give it a pistachio for a right answer, or tell it the right one. Click a thing
it has no word for, name it three times, and ask about it. The whole brain is drawn live beside the
room: its lexicon (every word neuron, every concept neuron, every synapse between them), its map of
things and its motor, and a question plays through them as it settled. Every part explains itself
under a question mark; the help page ([`site/help.html`](site/help.html)) explains everything.

This is the demonstration page of the words lane of the library
([cadence#326](https://github.com/muellerberndt/cadence/issues/326), the steps in
[cadence#331](https://github.com/muellerberndt/cadence/issues/331)).

> **The page runs a development build** of `cadence-net`: the wheel of one commit of the library's
> words branch (`lane-0100-words`), version `0.99.0+words.<commit>`, in a folder of `site/pack/`
> named by the commit. The page's header says so. The brain is `cadence.words.Words`: its senses
> (the map of things, `cadence.space.map.Map(values={"colour": 6})`, and the body) and a lexicon
> learned from naming (`cadence.words.Lexicon`).

## Readings

The brain the page loads, raised by `tools/raise_brain.py --practice reward` (seed 1: naming, then
pistachios for right answers, the answer told only where there is nothing to find) and read on rooms
it never saw (`evidence/raised-20261113-2104-7e772d38.json`, on `0.99.0+words.7e772d38`):

| Reading | Right |
| --- | --- |
| Where and colour of the named kinds, 30 fresh rooms | 284 of 284 |
| of those, the four kinds named and never asked about in practice | 126 of 126 |
| "What is red?" and "what is behind you?" (both directions) | 150 of 150 |
| A thing out of view | 56 of 56 |
| A kind in a colour it never had in training | 32 of 32 |
| A word never taught or a thing not in the room: "i do not know" | 120 of 120 |
| A new word after three namings | 48 of 48 |
| The lexicon's synapses at zero | 0 of 284 |
| Pistachios earned while it learned what question words ask for | 112 of 152 answers (.71 in the first half, .76 in the second) |

6,656 learned parameters (the lexicon's synapse pairs); the map's wiring has no taught synapse.

**The promise test** (`tools/check_page.py`) performs the page's claim with the keyboard and the
mouse: questions both ways, the parrot turned and asked what is behind it (from memory), a
pistachio (its surprise above zero, synapses changed), the kettle named three times by typing and
then asked about three ways, a word never taught, and the six steps of the tutorial on a fresh page. Its expected answers come from the room's own geometry (`truth` in `site/room.js`), never
from the brain. Results in `evidence/promise-*.json`.

## The parrot

- **Eyes on the sides of its head.** Each eye sees a wide fan to its own side, from 10 degrees
  across the beak's line to 150 degrees back; the fans meet in front, and behind is a blind spot of
  60 degrees. The eyes report each thing they see: its kind, its colour and its place (the program's
  step; the retina, cadence#330, is the step that finds things in the eyes' images). The strip at
  the top draws what each eye sees.
- **A voice.** It answers in text: the brain's motor spells the word.
- **Ears.** A microphone button sits beside the question box, closed until the brain has ears
  (cadence#329); `site/ears.js` records 16 kHz sound for the host's `hear` command.
- **Pistachios.** A right answer earns one: the reward goes into the brain (`Words.reward(1)`), and
  the question's words of asking learn what the answer took, at the reward's surprise (the brain view
  shows it as dopamine). The parrot learned what "where" and "colour" ask for from pistachios. A wrong
  answer earns none; "tell it the right answer" gives the answer (`Words.practice`).

## Run it locally

```sh
python3 -m http.server 8850 --directory site   # from ask/; then open http://127.0.0.1:8850/
```

The first visit downloads Pyodide and NumPy from jsDelivr (about 10 MB) and the page's own files
(under 1 MB). `?tour=1` starts the tutorial and `?tour=0` skips it.

## Build the pack

```sh
python tools/build_wheel.py --repo PATH/TO/cadence --ref origin/lane-0100-words   # site/pack/<commit>/
PYTHONPATH=<the wheel, unpacked> python tools/raise_brain.py                      # site/pack/brain/parrot.npz + evidence/raised-*.json
python tools/build.py --commit <commit>                                           # site/pack/manifest.json
```

## Files

| Path | What |
| --- | --- |
| `site.json` | the demos site's entry: the claim, what to try, the evidence |
| `site/index.html`, `site/styles.css`, `site/favicon.svg` | the page |
| `site/help.html`, `site/help-screen.jpg` | the help page |
| `site/app.js` | the room by the pointer, questions, namings, pistachios, the tutorial, the speech bubble |
| `site/room.js` | the room, the parrot (original drawing), the eyes' fans and strips, the teacher's answers (`truth`) |
| `site/brain.js` | the brain view: the lexicon, the map of things, the motor, a question as it settled |
| `site/ears.js` | the microphone, for the brain's ears |
| `site/worker.js` | Pyodide, the wheel, the host and the brain file, checked against `pack/manifest.json` |
| `site/pack/<commit>/` | the wheel of that commit of the library, and `COMMIT` (its hash, branch and version) |
| `site/pack/py/askbrain/` | the host: `world.py` (the room, the eyes, the teacher's words), `brain.py` (the brain and its file), `host.py` (the page's messages, the story of a question) |
| `site/pack/brain/parrot.npz` | the raised brain: the lexicon's synapses, letters, words and lessons |
| `tools/build_wheel.py`, `tools/raise_brain.py`, `tools/build.py` | the pack, built |
| `tools/check_page.py` | the promise test |
| `tests/test_host.py` | the host natively on the pack's wheel and brain; the page's eyes against the host's |
| `evidence/` | the raised brain's readings, the promise test's runs |

## Checks

```sh
python -m pytest tests/test_host.py                       # the host, natively
python tools/check_page.py --shots shots                  # the promise test, on the page
python ../tools/check_explain.py . --shots shots          # the demos' shared gate
python ../tools/sync_shared.py --check                    # the shared files match
```

Cadence is GPL-3.0.
