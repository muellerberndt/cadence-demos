# Cadence Arm

A Cadence brain picks up a block and places it in the bin you choose. You drag the block and
the bins, pick the target bin, and press Run. You can move the target bin while the arm is
carrying the block, and the arm follows it. Both the physics and the brain run in your browser.
There is no server.

- **Physics:** MuJoCo 3.17 compiled to WebAssembly (the official `@mujoco/mujoco` package)
  simulates a Franka Panda with contact physics.
- **The brain:** the real trained Cadence brain runs in a Web Worker in Python (Pyodide, with
  the released `cadence-net==0.91.1` wheel).
- **The view:** the page draws every neuron of the brain and the strongest synapses after each
  decision, along with its working memory over time.

## The brain

The brain is `B_D3b`, seed 3: a deep brain with an apical compartment and three layers of
256, 128 and 64 neurons, plus a working memory of 64 neurons and a motor population of 17
neurons. It has 791 neurons and 155,264 synapses in all. It learned the task during its life by
imitating a scripted teacher for 400 episodes, under widely randomized block mass, friction and
contact stiffness. It is the strongest arm brain trained so far:

| Reading (frozen brain, fresh trials) | Brain | Teacher |
| --- | --- | --- |
| Randomized physics, 200 trials | 0.955 | 0.955 |
| Hardest held-out physics (light, slippery, bouncy), 200 trials | 0.465 | 0.295 |
| Target bin moved to 5 positions never seen in training, 20 trials each | 19–20 of 20 at each | – |
| Target bin in the far corner (x 0.72, y 0.32), 20 trials | 10 of 20 | – |

The page reads the brain exactly as those trials did: `Brain.act(x, greedy=True)` on its
262-value observation, once per decision. The brain does not learn on this page; its synapses
stay frozen.

**What the brain senses (262 values):**
- where its hand is;
- where the block is, relative to the hand;
- where the target bin's release point is, relative to the hand;
- its seven joint angles and joint speeds;
- the gripper's opening, and whether it is closed and holding;
- its own last move (the efference copy);
- which lamp is lit.

**What it does:** each decision moves the hand by −2 to +2 cm along x, y and z and opens or
closes the gripper. An inverse-kinematics reflex turns the move into joint targets. The arm then
runs 100 physics steps of 2 ms, so 0.2 s of arm time per decision.

**Where you can put things.** The block may go anywhere in the area the brain trained on, plus 2 cm.
The bins may go within x 0.60–0.72 m and y −0.33 to +0.33 m, except the far corners. Inside that
band the brain was tested to place 19 or 20 of 20 blocks. In the far corners it placed 10 of 20.

## How the page was checked against the training code

- `tests/parity.mjs` loads the same physics model in MuJoCo WebAssembly. It replays recorded
  Python trials of this brain with `sim.js`. The observation matches Python to 1e-7 at every
  decision, the arm's joints to 1e-10, and the grasp and placement land on the same decisions.
- Under Pyodide, the brain host reproduces all 52 commands of a recorded trial exactly, at
  13 ms per decision on average.
- In headless Chrome, the page placed the block in bin A in 52 decisions, exactly as the Python
  trial did. With a mouse-dragged block and bin and bin B as the target, it placed the block in
  bin B. When bin B was dragged to a new place mid-carry, the block ended in the moved bin.

## Run it locally

```sh
python3 -m http.server 8830 --directory site   # from robot-arm/; then open http://127.0.0.1:8830/
```

The first visit downloads Pyodide and NumPy from jsDelivr, about 10 MB, and the page's own files,
about 20 MB; the browser caches them. `?autorun=A` or `?autorun=B` runs once at 4× speed as soon
as the brain is ready.

## Files

| Path | What |
| --- | --- |
| `index.html`, `styles.css`, `favicon.svg` | the page |
| `app.js` | three.js scene, placing things, the run loop |
| `sim.js` | the contact cell: MuJoCo, the IK reflex, grasp and release, the observation (a line-for-line port of `../arm2`) |
| `brainview.js` | the brain panel |
| `worker.js` | Pyodide, the Cadence wheel and the brain host, checked against `pack/manifest.json` |
| `pack/` | the wheel, `brain.npz`, `run.json`, the host (`py/armbrain/host.py`), `manifest.json` with SHA-256 |
| `assets/` | `cell.mjb` (the cell without the Panda's visual-only meshes, so the dynamics are identical) and the decimated visual meshes |
| `vendor/` | MuJoCo 3.17.0 WebAssembly (Apache-2.0), three.js 0.160.0 and its add-ons (MIT) |
| `tools/build.py` | rebuilds `assets/`, `vendor/` and `pack/` from `../arm2`, the checkpoint and the npm packages |
| `tools/record_trial.py`, `tools/moved_bins.py` | record a reference trial of the brain in Python; read the brain with a bin moved |
| `tests/parity.mjs`, `tests/fixtures/` | the parity test and its two recorded Python trials |

## Rebuild

```sh
python site/tools/build.py --brain <brain_best.npz> --run <run.json> \
  --wheel cadence_net-0.91.1-py3-none-any.whl --mujoco <@mujoco/mujoco 3.17.0> --three <three 0.160.0>
node site/tests/parity.mjs site/vendor/mujoco/mujoco.js site/assets/cell.mjb site/tests/fixtures/trial_a.json site/tests/fixtures/trial_b.json
```

The Franka Panda model comes from MuJoCo Menagerie (`assets/LICENSE-menagerie-panda`). Cadence is GPL-3.0.
