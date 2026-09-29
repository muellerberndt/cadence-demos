# Doom Lab

A Cadence brain plays shareware Doom in your browser — and you can teach it
by playing, watch it settle in a live 3D view of its nervous system, and swap
brains while the game runs.

The player is a Deep Recursive Settlement Network: two grayscale retinas
(a coarse full-frame periphery and a high-resolution fovea band at weapon
height) feed processing populations whose recursive observers read live
states and exact prediction errors, all settling in one joint equilibrium.
Eight motor outputs are settled patch states — there is no policy network,
no backprop, and the game engine's internals are never shown to the brain:
**pixels in, buttons out**.

## Run it

Python 3.11+, then:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
./get_wad.sh                      # fetches the freely distributable shareware WAD
python server.py                  # then open http://localhost:8666
```

## The lab

- The AI **plays automatically** when the page opens; **PAUSE/RESUME** and
  **RESET** (world only, never the brain) are in the top bar.
- **Model dropdown**: hot-swaps brains mid-game behind a loading screen that
  lifts only when the new brain is live and the 3D viewer has rebuilt.
  **EXPORT** downloads the current brain as one portable file; **IMPORT**
  installs one after full checkpoint validation. Models are
  checkpoint+norms pairs in `data/models/` — drop new ones in and they
  appear without a restart.
- **The brain view**: retina planes feed the population clouds and motor
  column; sampled real connections glow with their source's live activity
  (blue-gray retina wiring, violet state readback, amber prediction-error
  readback), and every committed witness batch sends a green wave through
  the network. Drag to rotate, wheel to zoom; the settle dot + sweep count
  sit in the corner.
- **RETINA** outlines exactly what the brain sees over the live game;
  **TRAINING** opens learning-curve charts fed by the training receipts in
  `data/models/`; **FULLSCREEN** (default) runs the arena full-bleed with
  the brain floating beside it.
- Kills flash the arena; episode rollovers flash RESPAWN; a stuck player is
  restarted by the environment and counted openly.
- Teaching-by-playing exists in the code (`TEACH` mode over the WebSocket:
  your frames and buttons become witnesses, admitted while you play) but is
  not in the spectator UI: against large brains, live admission is too slow
  to feel. Train offline instead — see [TRAINING.md](TRAINING.md).

## What is honestly claimed

Learning here is Cadence's supervised witness admission: batches commit only
when the whole settlement qualifies, and refusals change nothing. Teaching
is imitation of you; there is no reward-driven credit assignment in this
demo. The foresight variant additionally predicts measured next-decision
outcomes (health/ammo deltas, kill events, view change) — targets supplied
by reality, not by a teacher. Trained brains are evaluated against a
marginal-action control and a matched non-observer control before any claim
about them is made; see [TRAINING.md](TRAINING.md).

## Files

| File | Role |
| --- | --- |
| `server.py` | The lab: game loop, witness queue, live trainer, MJPEG + WebSocket UI |
| `brainlab.py` | The student: learning brain, shadow reader, model registry, import/export |
| `doomlab.py` | ViZDoom harness, retinas, action space, scripted privileged teacher |
| `wadmap.py` | WAD geometry reader, walk grid, damage-aware A* routing |
| `layouts.py` | Candidate brain layouts, including the matched control and the foresight variant |
| `norms.py` | Fitted input standardization (the conditioning that makes settling fast) |
| `collect.py`, `train_sweep.py`, `train_self.py`, `evaluate.py`, `dagger.py` | The training pipeline — see [TRAINING.md](TRAINING.md) |
| `train_flagship.py` | The lineage trainer: full-feature brains, hourly resumable checkpoint exports |
