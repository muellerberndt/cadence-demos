# Run, validate and import a Doom Lab model

The default application is `server.py` with the sole `v1` package. It uses the
exact recovered Cadence source under `runtime/`. The browser is the interface;
the Python backend owns native gameplay, settlement, model state and learning.
Historical experiment sources and models remain separate from this deployment.

## Prepared local demo

From `cadence-demos/doom-lab`, use Python 3.12 and the pinned dependencies in
`requirements.txt`, then run `python server.py`. The default address is
`http://localhost:8666`. Press **RESUME** to play. The current pointer selects
`confirmed-ad9`; `confirmed-9b97` is another available model. The initial state
is paused with AUTOLEARN off.

The prepared Mac runtime uses Python 3.12.6 with the pinned packages in
[`requirements.txt`](../requirements.txt). Historical Linux runs used their
separately preserved Python 3.11.16 environment.

The migrated runtime passed its 16-case Mac operational checks:

| Original model | Basic wins | Qualified action queries | Receipt |
| --- | ---: | ---: | --- |
| ad9 | 16/16 | 595/595 | [ad9 local validation](../evidence/local_validation/ad9_mac_01/receipt.json) |
| 9b97 | 15/16 | 666/666 | [9b97 local validation](../evidence/local_validation/9b97_mac_01/receipt.json) |

Both had no fallback or execution errors; 9b97's remaining outcome was a native
timeout. The predeclared operational threshold was at least 12/16 wins with all
scheduled episodes complete and all queries qualified. These checks do not
replace the original 64-seed Linux confirmations, establish a success-rate
ordering between the two models, or establish full-game competence. Source,
native engine, original file and checkpoint identities are bound to the receipts.

The active registry lives in `data/models/<id>/bundle.json`, with a pointer at
`data/current_model.json`. Original winning files remain under `models/` and
are never edited by the game or learner. `DOOM_LAB_DATA` selects an isolated
registry/state directory; `DOOM_LAB_PORT` selects another port for staging.

## Preparing another environment

Install dependencies and retain the pinned core and original model files. An
arbitrary installed `cadence-net` package is not a replacement for the runtime
that generated these checkpoints. The native scenario shipped with ViZDoom is
sufficient for Basic; separate shareware WAD assets are for later full-map work.

First validate the original actor on the target machine. The following example
uses a new output directory; existing evidence is not overwritten:

```sh
DOOM_MODEL=models/confirmed/ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc/bundle.json
DOOM_FOUNDER=models/ancestors/3076041351210d5818df542b23c167278a76ce59d7ceae531b52e05398f80ad8/bundle.json

python -m v1.deployment evaluate \
  --bundle "$DOOM_MODEL" \
  --out evidence/local_validation/ad9_this_machine \
  --seed-start 1600000000 --episodes 16 --workers 2

python -m v1.deployment prepare \
  --bundle "$DOOM_MODEL" --founder "$DOOM_FOUNDER" \
  --evaluation evidence/local_validation/ad9_this_machine/receipt.json \
  --source-platform evidence/run3/ops/baby_remote_source_platform.json \
  --name confirmed-ad9 --data-dir data

python server.py
```

The preparer refuses failed, modified or mismatched native evidence, changed
source/core/platform, altered task contracts, and an existing destination model
directory. To retain an existing registry, choose a new name or an isolated
`--data-dir`; add `--no-activate` for an optional model. Repeat the validation
and preparation for 9b97 using its original file from [the model inventory](MODELS.md).

The fixed 16-case schedule is an operational test reused for deployment; it is
not a fresh research confirmation every time this command is run. A new skill
claim requires its own predeclared unused confirmation schedule.

## Packages and source identity

Original files preserve `cadence-doom-player-v3/1` and other historical contract
names. The active package is called `v1`, but changing serialized names would
falsify their identity. The preparer creates a new deployment/practice package,
retaining the original weights, target provenance and companion founder while
binding the new runtime and actual native platform.

The current local practice configuration uses H144 native feedback, four
feedback workers, two gate workers, eight new and eight retained rows per
repair, a four-update candidate lifetime, capture stride 64 and 32 fixed Basic
development seeds. These are declared controls, not universal optimum settings.
The separate historical 9b97 training used eight new and 24 old rows; its new
deployment does not rewrite that fact. Complete executed history is retained
even when only every 64th decision is selected for feedback.

The queue, state and journal have explicit size limits. A stopped learner can
retain its exact candidate, replay and pending experience. Reaching a storage
or qualification limit pauses/refuses work visibly; it does not silently drop
selected records. Large accumulated evidence belongs in the AWS custody system.

## Controls and model import

- **RESUME/PAUSE** controls gameplay. **AUTOLEARN** controls the separate
  candidate learner; it starts off and must be enabled explicitly.
- **RESET** resets the episode, not the saved brain. Native history starts anew.
- **Model selection** changes the active actor through the game owner's
  controlled handoff. Earlier practice state stays with its own model/wave.
- **EXPORT** returns the current portable deployment. **IMPORT** validates and
  installs a model without activating it or enabling its learner.
- **ROLLBACK** requests the previous eligible champion when one exists.
- **RETINA**, **TRAINING**, and the 3D view show observations, current actor
  state, qualification and learning status. A repair count is not a skill score.

Use an exported, target-compatible Lab package for direct UI import. Raw
training originals need target-platform validation and preparation first.
The app refuses incompatible task/engine identity and keeps held-out maps
in the evaluator. There is no teacher mode or calibrated decoder fallback in the
new single-version demo.

## Verification and restarting

The app has unit, independent tamper/concurrency, native, HTTP, WebSocket,
model round-trip and live video checks; run them with
`python -m pytest v1 test_server_contract.py`. Staged API checks covered
import/export, model switching, controls, qualified play and live video;
independent checks covered state ownership, tamper resistance and
display-state logic. Model-validation receipts are retained under
`evidence/local_validation/`. Browser visual inspection was not completed;
these API and logic checks do not certify rendered layout.

After a source, core or native engine change, repeat the corresponding
validation and create a new derived package/wave. Do not edit historical source
hashes to make an old package pass. Historical Linux trajectory reproduction
continues to use its archived Linux engine; macOS observations are not silently
substituted for it.
