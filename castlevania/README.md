# Castlevania

A Cadence brain plays NES Castlevania from the screen. Every 12 frames its eye reads the
picture and a few RAM readings, the whole brain settles, and the settled motor slots press the
pad: left or right, up or down, whip, jump. The page shows the game beside what the eye sees,
the settled regions, the answer per slot and the recall memory filling as the game goes. The
brain plays frozen; nothing is learned while you watch.

![The brain jumping across the stage-2 underground, beside its brain view: eye maps, cortex, tracts, motor choice and recall memory](docs/castlevania.png)

Runs on `cadence-net==0.95.2` and `stable-retro==1.0.1`. The game is not included: you need your
own dump of the cartridge.

## Watch the brain play

[![The brain climbing the underground's exit stairs in stage 2; click for the highlights](docs/castlevania-highlights-poster.png)](docs/castlevania-highlights.mp4)

**Highlights** ([`docs/castlevania-highlights.mp4`](docs/castlevania-highlights.mp4), 1440p, 60
frames a second; [`720p`](docs/castlevania-highlights-720p.mp4); a short loop
[`docs/castlevania-highlights.webm`](docs/castlevania-highlights.webm)): two stretches of one
recorded game of the packed brain, frozen and greedy, no search, each played as recorded. A card
marks each cut, and a caption names the start and the life:

1. Start after 42 idle decisions, life 1 (0:00 to 0:57 of the game): the courtyard, the hall and
   up its stairs into stage 2.
2. The same game, life 3 (1:38 to 2:18): down the stage-2 staircase into the underground, across
   it, up its exit stairs and into stage 3, the giant bat's stage.

**The whole game, uncut** ([`docs/castlevania-run.mp4`](docs/castlevania-run.mp4), 1440p;
[`720p`](docs/castlevania-run-720p.mp4)): the same game from the first frame Simon can move to the
game over, with the page's brain view settling on every decision:

| Time | |
| --- | --- |
| 0:00 to 0:56 | Life 1: the courtyard and the hall, up the stairs at its end into stage 2 |
| 1:20 | Life 1 lost in stage 2, at the bottom-left staircase |
| 1:30 to 1:37 | Life 2: down into the underground; lost there |
| 1:45 to 2:14 | Life 3: down into the underground, across it, up its exit stairs, through stage 2's exit and into stage 3 |
| 2:14 to 2:53 | Life 3 in stage 3, towards the giant bat; lost there |
| 2:53 to 4:32 | Life 4: the fight with the giant bat, which loses 36 of its 64 health; game over |

The game's first block ends with that bat. The brain has not beaten it. The per-decision log is
[`evidence/castlevania-run.json`](evidence/castlevania-run.json).
[`record.py`](record.py) makes the videos from your own ROM (`python record.py --idle 42`,
`--scale 2` for 1440p): it plays the game and the brain and draws every frame with the page's own
renderer (`web/render.html` in a headless Chromium), piped to ffmpeg;
[`highlights.py`](highlights.py) cuts the highlights from that recording and its log.

**The recorded run beside the brain, in your browser** ([`player/`](player/)): a static page that
plays the game video and drives the brain view from the recorded trace, in step with play, pause,
seek and speed changes. Its live mode runs the brain itself in the tab (Pyodide and the released
wheel) on the recorded eye inputs and checks its buttons against the recording. See
[Player](#player) below.

Stage numbers here are the game's RAM counter: stage 0 is the courtyard and stage 1 the hall (the
screen shows both as STAGE 01), stage 2 is the screen's STAGE 02 and stage 3 its STAGE 03.

## Run it

```sh
cd castlevania
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m simon.rom ~/roms        # finds your Castlevania (U) (PRG1) dump and copies it in
.venv/bin/python server.py                  # open http://localhost:8846/
```

`simon.rom` checks every `.nes` file it is given (a file or a folder) and copies the one whose
SHA-1 without the 16-byte iNES header is `3dcb69a8c861c041aeb56c04e39adf6d332eda3a` to
`integration/Castlevania-Nes-v0/rom.nes`, which `.gitignore` keeps out of the repository.
stable-retro's own `python -m stable_retro.import` expects the other printing of the cartridge
(PRG0), so it does not apply here. The brain was raised on PRG1 and is only checked there.

The page polls the local server, which runs the FCEUmm core and the brain in one thread at the
game's speed (1x, 2x, 4x or as fast as the brain answers). New game powers the console on;
"start after N idle decisions" lets the game run on for N decisions first, which changes where
the enemies are when Simon starts.

## Player

[`player/`](player/) is a static page (no server, no ROM): the game video
([`docs/castlevania-game.mp4`](docs/castlevania-game.mp4), the game alone, the same run as the
videos above) beside the brain view, driven from a trace of that run
([`player/pack/trace.json.gz`](player/pack/trace.json.gz), 6.7 MB). The trace holds, per decision,
the first video frame it covers, the eye's exact input (float64), the settle (every second sweep,
as bytes), the projections, the strongest synapses, the choice per slot and the recall slots'
reads, and the frame each decision saw (for the recall view). The page follows the video's own
frame (`requestVideoFrameCallback` where the browser has it): play, pause, seek and speed changes
stay in step.

![The player at 2:31, in stage 3 below the giant bat, beside the recorded brain view](docs/player.png)

**Live** runs the brain itself in the tab: Pyodide, the released `cadence-net` 0.95.2 wheel, the
demo's own player code and the brain, each checked against `player/pack/manifest.json`'s SHA-256
(the page reads the pack from `<meta name="cadence-pack">`, else `pack/` beside it). It feeds the
recorded eye inputs in order from the game's start, settles each one for real, draws its own
state, and counts how many of its chosen buttons equal the recording's. If it falls behind the
video it says by how many decisions.

```sh
cd castlevania && python -m http.server 8846     # open http://localhost:8846/player/
python player/pack.py --trace <record.py --trace output>   # rebuild the pack
python player/check_player.py --live 60                    # the page's promise, headless
```

[`player/check_player.py`](player/check_player.py) (`player/evidence/player_check.json`, headless
Chromium on a c7i): the page plays, stays on the decision the video shows after a seek to 2:30, a
pause and 2x speed; frame time 16.7 ms (median and 95th percentile); live mode loaded in 6.3 s and
chose the recorded buttons on 60 of the first 60 decisions, 99 ms a decision (real time needs 200).
Pyodide's NumPy is 32-bit; one shim in `player/worker.js` (the same as the Eyes demo's) casts the
library's `np.repeat` slot counts to its index type.

## The brain view

The page draws the brain as an animal brain seen from the left, front on the left, and every mark
is that decision's real state. Hover a region for the population that plays its role.

- **Visual cortex** (back): the eye's four input maps, scene, motion, fovea ahead and fovea behind,
  and beside them the **body-sense strip**: the body readings and the one-hot stage, block, body
  state and floor. They are the sensory population, 827 neurons, clamped each decision. Their glow
  at the **thalamus** is the mean input.
- **Module 0** (256 neurons), the **association** region (128), the hub every other region reads
  and writes, and the **prefrontal** region (128), which carries the working trace. Each neuron is
  drawn at its activity sweep by sweep through the settle, coloured over its region's range at that
  decision.
- **Tracts** between regions: bundled curves whose width is |weight × presynaptic activity| summed
  over the projection, warm for excitatory flow and cool for inhibitory. Thin threads are the
  strongest single synapses of each projection.
- **Motor strip and striatum**: the ten motor neurons in their four slots, each choice's softmax
  probability, and the chosen one in red once the settle has finished.
- **Hippocampus**: the recall memory's 128 slots, one moment of this game each. Slots light gold
  when this decision's read attends them, and a thread runs from the brightest slot to the frame it
  holds. Below are the scene parts of what each read head recalls and of what each expects next.
- **The settle**: the sweep count and the largest change per sweep falling to the tolerance.
- **Dopamine, arousal, plasticity** are shown at their true state in frozen play: silent, off,
  zero synapses changed.

## The brain

```python
Brain.compose(827, 10, slots=(3, 3, 2, 2), modules=(256, 128), apical=0.25, arousal=True,
              memory_choice=True, recall=True, recall_heads=2, recall_action=True,
              recall_boundary=True, recall_position=32, recall_recency=0,
              learning=LearnerConfig(eta=0.2, eta_bias=0.02, beta=0.1, temperature=0.2,
                                     nudged_steps=32, nudged_fixed=True, qualified=False))
```

Two hidden regions (256 and 128 neurons) with the apical compartment, a prefrontal region that
carries the working trace, four motor slots, and a recall memory of 128 slots read by two heads,
whose keys include the command the body actually executed. 4,697 neurons (the recall memory's regions included) and 724,736 synapses
(`describe()` on the shipped file).

- **Acts.** Each decision `Brain.act(x, greedy=True)` settles the whole brain warm from the
  previous decision's state; the strongest motor neuron of each slot is the answer, held on the
  pad for 12 frames (five decisions a second at the game's speed).
- **Memories.** Synapses: written by lessons in training, frozen here. Working trace and recall
  memory: written at every act, read by the next settles, cleared when a new game starts
  (`Brain.reset`). The page shows how many recall slots are held.

## What the brain sees

827 numbers per decision ([`simon/eye.py`](simon/eye.py)):

| Slice | Count | Content |
| --- | --- | --- |
| scene | 192 | the gray frame, pooled to 12 x 16 cells |
| motion | 192 | the scene minus the previous decision's scene |
| fovea ahead | 192 | a 64 x 48 px window on Simon, 48 px ahead of him and 16 behind, pooled 4 x 4 |
| body | 12 | screen x and y, scroll, world x, health, lives, stage, facing, the last command's facing, whip and jump |
| fovea behind | 192 | the same window mirrored about Simon |
| stage, block, body state, floor | 47 | one-hot readings from RAM |

Simon's position, facing and body state come from RAM; everything inside the windows is pixels.
The page draws the four pixel maps and the one-hot readings. The red box on the game is the
fovea ahead, the blue box the fovea behind.

## How it learned

The brain imitated a scripted teacher ([`training/teacher.py`](training/teacher.py)) that reads
console RAM: routes for each stage (stairs, jumps, headings), the whip for enemies in reach, and a
savestate lookahead at the giant bat. The teacher alone reaches stage 4 on ten of ten power-on
starts. The brain never reads RAM beyond the eye's position readings.

1. **Pools.** Teacher games from power-on (24 idle offsets, with 0 to 15 percent of random
   actions) give 25,098 practice states: emulator savestates with the eye's observation, the
   teacher's memory and its next labels ([`training/harvest.py`](training/harvest.py)).
2. **Practice.** Segments of 40 decisions start at drawn practice states, weighted towards the
   hard places (the hall stairs, stage 2, the bat). Eight segments run side by side in one
   emulator. Every decision the teacher labels each stream's state, the brain takes one
   `Brain.lesson` on all eight rows, weighting rows at critical places three times, then acts;
   the teacher's action is executed ([`training/train.py`](training/train.py)).
3. **A wider eye.** The brain first learned 200,000 decisions this way, one stream at a time on
   an earlier release of the library, with the first 588 inputs of the eye. Its checkpoint was
   carried to this release, and [`training/widen.py`](training/widen.py) carried every learned
   array onto the full 827-input eye, the new inputs' synapses at zero: on 400 held-out
   positions the widened brain answers as before on every one.
4. **Stage 2.** 125,120 more decisions of practice on this release, eight streams, with the
   draw weighted to stage 2 (the staircase down to the underground, the water jumps, the way
   out): about an hour on one core of a c7i.
5. **Its own path (DAgger).** 100,160 decisions in which the brain drives and the teacher labels
   every state the brain reaches, with the same stage-2 draw: the lessons come from where the brain
   actually goes, including its own mistakes. Eight streams on one core of a c7i. For the last
   25,280 of them the teacher had learned to leave the low ledge past the underground's exit stairs
   (it jumps back left onto the floor), the place where the brain used to stand until its life ran
   out. Of the run's checkpoints, read every 25,000 decisions, the one at 425,280 is packed.

## Readings

Frozen and greedy from power-on, 1,500 decisions per start (`training/evaluate.py`; the receipt
is [`evidence/receipt.json`](evidence/receipt.json)). The checkpoints of the runs were compared on
nine selection starts and this one was picked there; nine fresh starts were read once, after the
pick.

| Starts (idle decisions) | Past the hall stairs | Down the stage-2 staircase and across the underground | Stage 3, the giant bat's stage |
| --- | --- | --- | --- |
| Fresh: 1, 5, 11, 17, 25, 31, 38, 45, 49 | 9 of 9 | 8 of 9 | 2 of 9 |
| Selection: 0, 3, 7, 10, 14, 21, 28, 35, 42 | 9 of 9 | 9 of 9 | 3 of 9 |
| The previous brain, fresh starts | 9 of 9 | 8 of 9 | 0 of 9 |
| The previous brain, selection starts | 9 of 9 | 6 of 9 | 0 of 9 |

Every start ends with its four lives lost (fresh starts: 20 deaths in stage 2, 5 in stage 1, 2 in
stage 3). Across the underground means down the staircase at the bottom left of stage 2 and on
through the underground. Where the brain reaches stage 3 it goes on to the giant bat's arena
(world x 664); on selection start 42 it takes 36 of the bat's 64 health before its last life ends.
A checkpoint replaces the packed brain only if it is no worse on both sets of starts and no start
leaves the brain standing still.

## Limits

- **Stage 2 and the bat.** The game's first block ends with the giant bat at stage 3. The brain
  reaches it on 2 of 9 fresh starts and has not beaten it. Elsewhere it loses its lives in stage 2:
  some starts stop a few pixels short of the bottom-left staircase's foot and hold down, which
  crouches; some cross the underground and drop past the staircase up and out onto the low ledge.
- **Imitation, not reward.** The brain learned from a teacher's labels; the world's reward
  played no part, and nothing is learned while you watch.
- **RAM in the eye.** Simon's position, facing, stage, block and body state come from RAM; the
  rest is pixels.
- **One cartridge.** Raised and checked on the PRG1 printing on stable-retro's FCEUmm core only.

## Train your own

Everything runs from the `castlevania/` folder with the ROM imported. The steps are CPU-bound; a
brain of this size takes about 20 ms per decision with eight streams on one core of a c7i, so a
run of 200,000 decisions takes a little over an hour, and the search phase about 0.4 s per
searched decision.

```sh
pip install -r requirements.txt pytest
python training/teacher.py --decisions 2500 --noops 0 1 2      # the teacher alone
for n in 0 2 4 6 8 10 12 14 16 18 20 22; do                     # the practice pool, one game per process
  python training/harvest.py --part train --train-noops $n --epsilons 0.0 0.05 0.15 --out runs/pool/parts/train_n$n &
done; wait
python training/harvest.py --part val --out runs/pool/parts/val_all
python training/merge_pools.py runs/pool
python training/train.py --config '{"name": "a", "seed": 0, "budget": 200000,
    "genes": {"memory_choice": true, "recall_heads": 2, "recall_action": true, "recall_boundary": true,
              "recall_position": 32, "recall_recency": 0, "apical": 0.25, "teach_eta": 0.2}}' --out runs/a
python training/train.py --config '{"name": "b", "seed": 0, "budget": 260000, "load": "runs/a/end.brain.npz",
    "load_decisions": 200000, "search_at": 200000}' --out runs/b          # then the search phase
python training/evaluate.py --brains runs/b/end.brain.npz --out runs/eval.json
python training/pack.py --brain runs/b/end.brain.npz --readings runs/eval.json --run runs/b/result.json
```

`train.py` options: `streams`, `segment`, `budget`, `draw` (the practice places and their
weights), `critical_weight`, `search_at`, `search_share` (0 runs the brain's own moves with the
teacher's labels, DAgger), `search_k`, `search_horizon`, `search_sims`, `c_puct`, `backend`
(`"mlx"` on Apple silicon), `load`. `--resume` continues a run from its newest checkpoint. Every
evaluation writes a checkpoint `d<N>.brain.npz` and a line per start to `readings.jsonl`.

**The search phase** is expert iteration at one ply, the AlphaZero recipe with the emulator as
the model: on a share of the rows, the brain's memory-free settle gives priors over the 36 pad
actions; its likeliest actions and the teacher's are each executed from the savestate and rolled
out 16 decisions by the teacher's heuristic; the rollouts' progress (world x, a new block, a
stage clear; less lost health and lives) and PUCT visits over the priors give visit shares, and
`Brain.lesson(x, targets=shares)` teaches them. Where the rollouts cannot tell the candidates
apart, the row is taught the teacher's label. The most visited action is executed. The search
is used in training only; the page plays the brain alone.

## Layout

| Path | What |
| --- | --- |
| `server.py`, `web/` | the local server and the page |
| `simon/` | the pad, the eye, the console (`Console`), the player, the ROM import |
| `brain/brain.npz` | the brain the page plays |
| `integration/Castlevania-Nes-v0/` | stable-retro's description of the game, with the PRG1 hash; your `rom.nes` goes here |
| `training/` | the teacher, the pools, the trainer with the search, the widening of a brain's eye, the evaluation |
| `evidence/` | the receipt of the shipped brain and its readings |
| `tests/` | the brain loads and answers on the released library, without a ROM |

```sh
.venv/bin/python -m pip install pytest && .venv/bin/python -m pytest tests -q
```

## Licence

GPL-3.0, as Cadence ([`LICENSE`](LICENSE)). The game and its ROM are Konami's and are not
distributed here.
