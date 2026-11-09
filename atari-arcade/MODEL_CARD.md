# Model card: the Atari Arcade brain

| | |
| --- | --- |
| Demo | Atari Arcade (`atari-arcade/`) |
| File | none: born in the page/server at start |
| Library | `cadence-net` 0.95.2 (`Brain.compose` in [arcade_brain.py](arcade_brain.py); `backend="cpu"`, float64, in the server and in Pyodide alike) |
| Composition | `Brain.compose(7056, n_actions, seed=seed, recall=False, learning=LearnerConfig(...), actor_*=...)`; `describe()`: inputs 7,056, slots `(n_actions,)`, modules `(64,)`, no observers, no apical compartment, recall off, teaching `"custom"` |
| Size | Freeway (3 actions) 7,187 neurons, 456,064 synapses; Atlantis (4) 7,188, 456,192; Carnival and Space Invaders (6) 7,190, 456,448 |
| Date | 2026-11-09 |

## What it sees and does

- **Inputs:** 7,056 sensory neurons, one per pixel of the screen's luminance pooled to 84 by 84,
  minus a fixed background (the mean of 300 screens of random play taken before birth),
  doubled. One frame, no frame stack, no emulator memory.
- **Outputs:** one motor neuron per action of the game's minimal action set: Freeway NOOP, UP,
  DOWN; Atlantis NOOP, FIRE, RIGHTFIRE, LEFTFIRE; Carnival and Space Invaders NOOP, FIRE, RIGHT,
  LEFT, RIGHTFIRE, LEFTFIRE.
- **Inside:** an association cortex of 64 neurons, a working trace of 64 (amplitude 3.0,
  carrying the association cortex's previous activity), a critic reading the association
  cortex, and an associative memory of reward per action (7,056 by actions, consolidation
  0.05).
- **One decision:** the whole brain settles warm from the stream's last state, at most 1,024
  sweeps to a tolerance of 3e-3. While watching, the brain's own answer is read greedily and
  not executed. After the takeover, `brain.step` samples the action from the settled motor
  activations and learns from the previous action's outcome in the same call. No search. A solve that does
  not settle is refused; the body holds its last action and nothing is credited.

## How it was trained

It is not trained offline. Every brain is born from its seed when the page or server starts
and learns live in the game:

1. **Watching.** A scripted teacher plays: Freeway always UP, Atlantis always the centre
   gun, Carnival and Space Invaders by the player's position read from emulator memory (the
   brain never sees it). Each screen the brain gets to see is one lesson,
   `brain.learner.step(drive, [teacher_action])`, with `LearnerConfig(beta=0.1,
   temperature=0.2, tolerance=3e-3, free_steps=1024, nudged_steps=12, eta=0.003,
   eta_bias=0.02, momentum=0.9, normalize=0.99, normalize_floor=1e-4)`.
2. **Takeover.** After at least 500 lessons once 90% of the last 120 greedy answers agree with
   the teacher, or after 2,000 lessons at the latest. The browser also waits for the teacher's
   first whole game.
3. **Living on reward.** Every decision is `brain.step(screen, reward=sign(reward since the
   last decision), done=...)`, with `actor_gamma=0.97, actor_lam=0.9, actor_eta=0.001,
   actor_eta_bias=0.0001, actor_eta_critic=0.3` (small actor rates for a long reward life).

The recall memory, the 0.95 default, is off: it adds two regions as wide as the input and
made each decision about six times slower with no gain on Freeway (below). Learning happens
on one CPU core per game, at the game's pace (60 emulator steps a second). The headless run is
`python headless_control.py --seed 0 --games Freeway --episodes 12 --out report.json`.

## How it was measured

`headless_control.py`, two brains per seed: one keeps learning after the takeover, its frozen
twin receives no outcome. Twelve or more whole games at the controls each; one Apple M4 Mac
shared with other jobs. Receipts in [evidence/headless-0952/](evidence/headless-0952/).

| Game | Teacher alone | Seeds passing every check | Living brain, mean of all lives (by seed) | Living, last five lives | Frozen twin, mean |
| --- | --- | --- | --- | --- | --- |
| Freeway | 21.4 | 3 of 3 | 22.5, 22.0, 22.2 | 22.8, 22.0, 23.0 | 23.0, 23.3, 23.2 |
| Atlantis | 2,000 | 3 of 3 | 2,008, 2,000, 2,000 | 2,020, 2,000, 2,000 | 1,946, 2,000, 2,008 |
| Space Invaders | 225 | 2 of 3 | 247, 253, 166 | 303, 339, 156 | 250, 180, 216 |
| Carnival | 540 | 0 of 3 | 497, 282, 413 | 232, 176, 504 | 789, 260, 677 |

- Takeover: Freeway and Atlantis at 500 lessons with agreement 1.0 (60 to 66 s after birth for
  Atlantis, about 240 s for Freeway on the loaded host); Space Invaders 554 to 939 lessons;
  Carnival 1,594 to 2,000 lessons at agreement 0.875 to 0.9.
- Faults and refusals: 0 in all 24 brains.
- Brain time per screen (handler, median / 95th percentile): 41 to 117 ms / 97 to 519 ms.
- Recall on ([evidence/recall-0952/](evidence/recall-0952/), Freeway seed 0): passes, living
  mean 22.2, but 717 ms per screen at the median against 113, 1,150 decisions in its life
  against 5,528.

## In the page

The browser edition (`web/`) runs Freeway and Atlantis; the brain learns all the time the page
is open, by the same calls as the server. Nothing is saved: a reload is a new birth from seed
0. The visitor can change the game's speed, not the brain. The page draws the brain as a brain
seen from the side, from its state at each view: activations, the settle replayed from rest
sweep by sweep, the weights of about 780 drawn synapses and the count of synapses that moved,
the critic's value and dopamine, and the phase (README, "The brain view"). Measured by
`check_page.py` ([evidence/page_check.json](evidence/page_check.json), headless Chromium on the
loaded Mac): both brains took the controls 39 to 52 s after the page opened (500 and 656
lessons) and then played at a median of 79 to 81 ms per screen, the brain view drew a frame in
18.1 ms on average, with no fault, refusal or page error.

## Limits

- Reward adds no measured gain: the frozen twin does as well as the living brain in Freeway
  and Atlantis and better in Carnival; in Carnival and one Space Invaders seed the living
  brain drifts into holding one action.
- Freeway's and Atlantis's teachers are a single held action; matching them shows the brain
  learns from pixels which action the teacher holds, not a model of the game.
- Timing depends on the host: the game does not wait for the brain, so a slower machine
  means fewer screens seen and a later takeover. Two brains from one seed can take over at
  different lesson counts.
- The per-screen lessons are a bootstrap control, not the general Cadence operating recipe;
  the settlement residual and the badge certify only their declared tests.

## Licence

GPL-3.0, as Cadence.
