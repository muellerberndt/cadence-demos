# Tron

**What it shows.** Cadence brains play strong games. The deep brain sees the whole arena and
answers every move with one settle of the whole brain, in the browser, in real time (about 11 ms a
move, [evidence/page_check.json](evidence/page_check.json)). On its own it beat the `voronoi` bot in
102 of 128 games; with the page's look-ahead over the rules checking its moves, in 118
([evidence/search-readings.json](evidence/search-readings.json)). The page draws every neuron of
every settle, and a neuron's card says what it tracks. The brains are frozen while you play and
keep nothing from one move to the next: this demo shows strong play from settling brains, not
learning during life. [The help page](web/help.html) explains every part of the page.

Ride a light cycle against a Cadence brain that runs in your browser tab. The brain sees the
whole arena and answers every move with one settle of the whole brain; the panel beside the arena
draws every neuron of it as a brain seen from the side, sweep by sweep. Two brains are on the page:
a flat one of one region and a deep one of three regions whose deep layers decide four in five of
its moves. By default the brain proposes and a look-ahead over the rules checks it; BRAIN ALONE
plays the brain's settle and nothing else. Pick the brain and the player with the switches in the
header.

![A game against the deep brain + look-ahead: the arena on the left; on the right the brain seen from the side, the settle running from the visual cortex through L1, L2 and L3 to the motor strip, and beside it the look-ahead's value for each move, overruling the brain's pick (the amber arc)](docs/tron-deep.png)

![The flat brain: one association region of 256 neurons between the visual cortex and the motor strip](docs/tron-flat.png)

Runs on `cadence-net==0.95.2`.

## Play

```sh
python3 -m http.server 8831 --directory web   # from tron/; open http://localhost:8831/
```

`?brain=deep` (the default) or `?brain=flat` picks the brain, `?player=alone` the brain alone.
Arrows or WASD steer, space starts a round, M mutes; on a phone, swipe to steer and tap to ride.
Your record against each brain and player is kept in this browser, apart for each.

The first visit downloads Pyodide 314.0.7 and NumPy from jsDelivr. The wheel, the host sources and
the brain are in `web/pack/<flat|deep>/`; the worker checks each file against the SHA-256 in that
pack's `manifest.json` before anything runs. No server chooses the moves.

## The player: the brain proposes, a look-ahead checks it

Every tick the brain settles from rest on the field and its strongest motor neuron is its
proposal. Then a look-ahead over the game's rules ([`web/js/search.js`](web/js/search.js), in its
own worker) searches 4 rounds: each of its three moves, every reply of yours knowing it, and so on,
scoring the positions it reaches by the Voronoi territory (cells it reaches before you, less those
you reach first; the difference of the rooms once you are walled apart) and by who crashes first.
The brain's proposal gets a bonus of 8 cells at the root, so the look-ahead keeps it unless another
move is clearly better. No neural evaluation runs inside the search; it knows only the rules. It is
the alpha-beta of [`tron/absearch.py`](tron/absearch.py), checked value for value
([`tests/parity_search.mjs`](tests/parity_search.mjs): 2,632 searches, no difference), and it takes
6 ms at the median and at most 70 ms a move in the browser. The brain view shows its value for each
move beside the motor strip, and an amber arc when it overrules the brain.

Readings, 64 mirror pairs each, every move settled from rest
([`evidence/search-readings.json`](evidence/search-readings.json)):

| Player | `voronoi` | `voronoi2` | `voronoi3` | `ab5` |
| --- | --- | --- | --- | --- |
| Deep brain alone | 0.80 | 0.13 | 0.20 | 0.08 |
| Deep brain + look-ahead (the page) | 0.93 | 0.70 | 0.70 | 0.45 |
| Flat brain alone | 0.80 | 0.20 | 0.25 | 0.14 |
| Flat brain + look-ahead | 0.91 | 0.66 | 0.65 | 0.51 |

`voronoi2` and `voronoi3` look two and three rounds ahead, `ab5` is the same alpha-beta at 5
rounds with no brain. A 5-round look-ahead reads higher against `voronoi` and `voronoi2` but lower
against `voronoi3` and `ab5` (deep: 0.97, 0.79, 0.58, 0.30), so the page searches 4.

## The brains

Both are Cadence brains with three motor neurons (turn left, ride straight, turn right), no recall
memory and the working trace at amplitude 0: the flat one from `Brain.compose`, the deep one from
`Brain.compose(connectome=...)` with a custom anatomy (below). Every move is

```python
brain.reset()
move = brain.act(field(arena, seat)[None, :], greedy=True)
```

frozen and greedy, settled from rest. Nothing is learned while you play, so a round is fully
determined by the arena seed and your moves.

**The senses (2,470 inputs, [`tron/field.py`](tron/field.py)).** The whole 24 x 24 arena at full
resolution, turned so that the rider's heading points up: "a wall ahead" is the same input
whatever the compass heading. Four planes (blocked cells, the opponent's trail, its own head, the
opponent's head), a 9 x 9 fovea around its head (blocked cells, the opponent's head) and the
opponent's heading relative to its own.

| | Flat (Mako) | Deep (Mako Deep) |
| --- | --- | --- |
| Layout | one region of 256 | 256 → 128 → 32 |
| Neurons, synapses | 2,985 · 699,398 | 2,921 · 708,806 |
| Against `voronoi`, 256 games on seeds 2,200,000+ | 186-68-2, 0.73 | 192-64, 0.75 |
| Against `voronoi`, 256 games on seeds 7,000,000+ | 182-74, 0.71 | 190-66, 0.74 |
| Against Mako 1.0 and Mako 1.5, 256 games each | 0.54, 0.60 | 0.53, 0.49 |
| Against `voronoi3`, 128 games | 0.25 | 0.20 |

A mirror pair plays one arena seed twice, the brain in either seat; draws count half. `voronoi`
moves to the cell that leaves it the most cells it reaches before its opponent, one move ahead for
both riders; `voronoi3` looks three rounds ahead; Mako 1.0 and 1.5 are earlier flat brains of the
same line. The readings are in [`brains/`](brains/); the deep brain's were taken on 0.95.2
([`evidence/deep-readings.json`](evidence/deep-readings.json)), and the flat brain reads
48-16 on 0.95.2 over the first 32 pairs of the same seeds
([`evidence/reading-0952.json`](evidence/reading-0952.json)).

**The deep brain's deep layers play.** It was built from the flat line with a skip connection from
its first layer to the motor neurons, the skip weakened in stages while the deep pathway learned
the moves, and then taught by its own brain + tree search (below). With the deep pathway cut (its
73,920 synapses at zero) it changes 82% of its moves and loses every game against `voronoi`
([`evidence/deep-ablation.json`](evidence/deep-ablation.json)).

**The brain view.** By default the panel lays the brain out as seen from the side, front to the
left ([`web/js/anatomy.js`](web/js/anatomy.js)). Each population sits where the region whose role
it plays would: the field, the foveas and the heading as the visual cortex at the back; L1, L2
and L3 as association cortex from the back to the front; the prefrontal population, the working
trace, dark at the front pole because the trace is off; the three motor neurons as the motor strip.
Every pathway of the connectome is a curved tract, warm for excitatory and cool for inhibitory
synapses, as bright as the live sum of |weight x presynaptic activation| over its drawn synapses;
the field's projection into L1 runs through a relay drawn where the thalamus would sit. Below,
a selection nucleus shows the three motor neurons' activations and the greedy pick, the role the
basal ganglia play in an animal; the dopamine nucleus stays dark, since nothing rewards the brain
while you play. Each move plays as a wave: region by region, every neuron replays its own
recorded sweeps, and a curve shows the largest potential repair per sweep falling to rest. The
names say which role a population plays, not that it is that structure. `?view=layers` (the
LAYERS switch) shows the same brain layer by layer with what each layer knows.

The brain view draws what each layer computes: for each neuron, the event or number its firing
tracks best in played positions (a wall within two cells ahead, the opponent close on the right,
the share of the free board it reaches first), kept only where silencing or driving that neuron
changes the move. [`web/pack/deep/brain/ROLES.md`](web/pack/deep/brain/ROLES.md) and
[`web/pack/flat/brain/ROLES.md`](web/pack/flat/brain/ROLES.md) list them with their evidence
([`scripts/introspect.py`](scripts/introspect.py)).

## How they were raised

[TRAINING.md](TRAINING.md) gives every stage with its command, its hardware and time, and its
readings, and a smoke-scale run of each route that takes minutes. In short:

- **Flat:** a genetic search over `Brain.compose` settings (1,536 raisings), the winner raised by
  corpus lessons and DAgger, then expert iteration (an alpha-beta search with the brain's own move
  as a prior labels each position it reaches), selection between short branches, and self-play
  against its own past generations and a pool of bots and brains.
- **Deep:** a flat brain of the same line (Mako 1.6) grafted into the first layer of a
  (256, 128, 32) brain with a skip from that layer to the motor neurons, so it starts with the
  flat brain's play; self-play; then, five times, the skip halved and the deep pathway taught that
  brain's moves with the first layer and the skip frozen. Last, three generations of distillation
  from its own brain + tree search (200, then 400 simulations): the search's choice at each position the
  brain reaches is the lesson, and a generation is kept only if the brain alone beats its parent
  through a sequential test and holds against the previous deep brain
  ([`scripts/distil.py`](scripts/distil.py)). Against `voronoi` it went from 0.63 / 0.66 to
  0.75 / 0.74, against `voronoi3` from 0.10 to 0.20.

## Limits

- **The look-ahead knows the rules.** The default player's strength against the bots comes from
  the brain and the search together; the brain alone loses most games to bots that look two or more
  rounds ahead (the table above). The look-ahead is pessimistic: it assumes you answer each of its
  moves knowing it, and it scores positions by territory, not by a learned value.
- **A tree search guided by the brain's values** (`tron/mcts.py`) does not fit the page: at 8 and 16
  simulations a move takes 0.4 to 0.8 s in Pyodide against the 120 ms tick, and at those sizes it is
  no stronger than the brain alone ([`evidence/search-0952.json`](evidence/search-0952.json)).
- **Frozen while you play.** These brains do not learn from your games.
- **Settled is not right.** A settled state certifies the settle's equations at the tolerance,
  not the quality of the move.
- **Strength readings are per seed set.** Games from one start seed are correlated, so two seed
  sets of 128 pairs can differ by more than the interval of either.

## Layout

| Path | What |
| --- | --- |
| `web/` | the page: `js/main.js` (game, clock, record), `js/arena.js`, `js/anatomy.js`, `js/deep.js` and `js/ripple.js` (the brain views), `js/worker.js` (Pyodide), `js/search.js` and `js/search_worker.js` (the look-ahead) |
| `web/pack/flat/`, `web/pack/deep/` | the wheel, the host sources, the brain, its meta and its introspection, with `manifest.json` |
| `tron/` | the arena (`world.py`), the sense (`field.py`), the page's host (`fieldhost.py`), the bots (`bots.py`, `fastbots.py`, `absearch.py`), the schools and the search |
| `scripts/` | training, selection, self-play, the deep constructions, readings, introspection |
| `brains/` | each brain's meta: layout, readings, lineage; [MODEL_CARD.md](MODEL_CARD.md) describes both |
| `pack.py` | packs one brain into `web/pack/<slot>/` |
| `tests/` | the rules, the bots, the packs (`pytest`), `parity_search.mjs` (the page's look-ahead against `tron/absearch.py` on `fixtures/search.json`, made by `make_search_fixture.py`), and `play_check.py`, the page tried in headless Chromium |
| `evidence/` | readings on 0.95.2 and the page check |

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
.venv/bin/python -m playwright install --only-shell chromium
.venv/bin/python tests/play_check.py
```

Cadence and this example are GPL-3.0. See the [Cadence source](https://github.com/muellerberndt/cadence).
