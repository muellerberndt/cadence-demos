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

- **FULLSCREEN** (default): the arena full-bleed, the live brain floating in
  the corner.
- **STUDENT** — the loaded brain plays. Its settle qualification shows as the
  green/red dot; if it stands frozen for six seconds the environment restarts
  the episode and counts it openly ("auto-restarts").
- **TEACH** — click the game and play: `W A S D`, arrows to turn
  (`⇧`/`⌥`+arrows to strafe, classic style), `Ctrl`/mouse to fire, `Space` to
  use. Every fourth tic, your frame-and-buttons pair is queued as a witness
  and admitted into the brain through atomic batched settlement **while you
  play**. The 3D view ripples green on every committed batch.
- **RESET** restarts the episode (world state only — never the brain).
- **The brain view**: retina planes feed the scene/aim/integration/reflection
  clouds and the motor column; sampled real connections glow with their
  source's live activity (blue-gray retina wiring, violet state readback,
  amber prediction-error readback). Drag to rotate, wheel to zoom.
- **Models**: the dropdown hot-swaps brains mid-game. A model is a
  checkpoint + input-normalization pair in `data/models/`. **EXPORT**
  downloads the live brain as a single portable file; **IMPORT** installs one
  after full checkpoint validation. Two starter brains ship with the lab
  (both intentionally under-trained; see the tutorial to train real ones).

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
