# Walkers

Three walkers on three treadmills see the same drive every moment. A step on the other foot
than the last one earns a step forward; a repeated foot is a stumble. Nobody tells them what to
do: the world pays, that is all. Two of the walkers are Cadence brains born in the page from the
same founder weights and learning there, in your browser, from that pay alone. One carries a copy
of its own last command; the other does not, and nothing in what it sees says which foot moved
last. The third flips a coin. Freeze the floor, flash a distractor, erase the first walker's copy
of its last step, or start over with new walkers.

```sh
python -m http.server -d walker/web 8799     # open http://localhost:8799/
```

## What it demonstrates

- **Learning from the world's pay, in the browser.** The released `cadence-net` 0.76.0 wheel
  runs in Pyodide in a web worker, unmodified apart from one compatibility shim (see Limits).
  Every walker is born in the page; there is no raised brain and no teacher. The brain learns
  through `Brain.live`: aroused and learning through a youth of 100 moments, then routine while
  its outcomes match its forecasts, aroused again when they do not or when its need goes unmet.
- **The efference copy.** The first walker carries a copy of the command it just issued: one
  neuron per motor neuron, driven by the one-hot of the last step and read by the association
  region through a plastic projection. The working trace, a copy of the settled state before the
  decision, carries nothing of a sampled choice; the command copy does. What to do after what it
  did is learned. The second walker is the same brain with the copy's founder value, zero.
- **Routine is equilibrium.** Once the beat is found, the first walker walks it from one settle
  per moment and learns nothing: no aroused moment, no learning sweeps, the glow turns green.
  The second walker never earns and stays restless; the page shows what each mode costs.
- **A beat that is carried, not seen.** Erase the copy and the walker loses at most a step of
  phase, because the next step rewrites the copy and the beat lives in the learned projection.
  Freeze the floor and it steps on through the silence.
- **Answers that settle.** Each step is the settled state of the whole brain; a brain that does
  not settle refuses to answer, and a refused answer is shown as a missed step, never invented.

## How it is built

| Path | What |
| --- | --- |
| `walker/world.py` | the beat paid by the world, the moments (drive, frozen floor, flash) and the track |
| `walker/host.py` | what the page's worker runs in Pyodide: one `Brain.live` moment per message, the readings, the copy erased, snapshot and restore |
| `pack.py` | packs the released wheel and the sources for the page (`web/pack/`) |
| `web/` | the page: `walker.js` (the treadmills, the coin, the drawing, the sound), `worker.js` (Pyodide and the two brains), `walker.css` |
| `check_page.py` | the page's promise, tried end to end in a headless Chrome |
| `tests/` | the rule, the host, the continuation; with `CADENCE_REPO` set, parity with the chamber's brains action for action |
| `evidence/` | the page check's receipt |

The brains are the reward-rhythm chamber's `live` and `nocopy` arms
([`benchmarks/rhythm/protocol-reward-2.json`](https://github.com/muellerberndt/cadence/blob/main/benchmarks/rhythm/protocol-reward-2.json)
in the Cadence repository): `Brain.compose(4, 2, modules=(32,))` at the chamber's declared
operating point (working trace 0.3, actor rate 0.1, eligibility decay 0, discount 0.95, critic
rate 5) with `efference_amplitude=3.0, efference_decay=0.0` and the key-door nursery's arousal
genes with a youth of 100 moments and a need of 0.5, half a perfect walker's income. The host's
first 200 moments on a chamber seed are identical to the chamber's own, action for action
(`tests/test_host.py`). The page's worker loads Pyodide 314.0.7 from jsDelivr and checks the
Cadence wheel and the sources against the SHA-256 in `web/pack/manifest.json`.

## What the chamber measured

The page shows one founder per seed. The chamber's receipts give the picture over founders
(`benchmarks/rhythm/results/` in the Cadence repository, each verified):

- reward/2, fresh seeds 401 to 405: four of five walkers with the copy learn the beat (1.00 of
  their last 64 steps changed foot), none had it from birth, all five are calm in that window and
  continue identically from a mid-life checkpoint; the fifth settles into a limp of two changed
  steps in three. The walker without the copy stays at 0.37 to 0.49 and restless on every founder.
  A coin stays near 0.5; a tabular learner given the same one bit reaches 0.90 to 0.97.
- reward/1, seeds 301 to 305, with a longer eligibility decay: three of five, one of them from
  birth, two limps; kept as a failed freeze. reward/3, seeds 501 to 505, with a need above the
  limp's income: no limp and five of five at 1.00, but two had the beat from birth, so its gate on
  learned beats fails as declared.

## Limits

- One founder per seed. The receipts above are the claim; a page run is one life. Some seeds
  limp (two changed steps in three, paid above the need, calm in it), and some founders have
  the beat from birth: the frozen founder is not on the page, so a seed that alternates from its
  first steps may not have learned it.
- The copy carries one step of history. The walker steps on through a frozen floor instead of
  waiting; longer delays, more feet and a pause it should wait through are not measured here.
- Pyodide's numpy is 32-bit, and the library's learning module gets a numpy whose `repeat` casts
  its counts (`walker/host.py`, `fit_32_bit_numpy`); nothing else is changed.
- The sound is a tick and a tock for the first walker's feet and a thud for a stumble, nothing
  more. No number on this page is a benchmark; the ms per moment is one machine's.

## Check

```sh
python -m venv .venv && .venv/bin/pip install -r walker/requirements.txt
.venv/bin/python walker/pack.py
CADENCE_REPO=../cadence .venv/bin/python -m pytest -q walker/tests
.venv/bin/python walker/check_page.py --receipt walker/evidence/page_check.txt
```
