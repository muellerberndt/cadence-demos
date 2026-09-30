# Model verification

Start with [the model guide](../docs/MODELS.md) and
[the model manifest](../models/manifest.json).

`models/manifest.json` is the immutable-original catalogue: for every saved
snapshot it records the exact file and checkpoint hashes, category, contracts
and pinned evidence. Current app deployments under `data/models/` are
separately derived packages with their own platform/source identities.
Schema strings and absolute AWS paths inside bundles and receipts are exact
identifiers and are not rewritten.

`checkpoint_sha256` hashes exact snapshot text. `canonical_snapshot_sha256`
hashes the parsed snapshot with sorted keys. `parameters_sha256` hashes weights
and biases alone. These are intentionally different identities: an
admission/event change, query-budget variant, normalization change or export
wrapper can matter even when learned parameters are equal.

Verify the saved files, evidence hashes, runtime pins and documentation links
from the workspace root:

```sh
python3 cadence-demos/doom-lab/inventory/verify_inventory.py
```

This command is read-only and uses no network, engine or training code. To
record a dated receipt, add `--out /path/to/verification.json`.

Do not rerun a historical confirmation to regenerate any receipt. Numerical
outcomes remain bound to their original candidate, native environment, seed
set, freeze and receipt.
