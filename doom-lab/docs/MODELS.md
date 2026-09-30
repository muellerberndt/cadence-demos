# Models and evidence

The two confirmed **Basic-scenario** practice champions are local and verified. Neither establishes general Doom play, navigation acquisition, or useful recursive computation. The saved deep architectures and the confirmed action policies are different evidence categories.

The [model manifest](../models/manifest.json) identifies **14 saved Cadence snapshots**. All local originals were checked against their recorded file and checkpoint hashes. Saved bundles retain their original schema and metadata. Active app packages are separate derivatives under `data/models/`; a saved file does not authorize or imply its deployment.

## Confirmed Basic policies

| Model | Saved checkpoint | Training state | Native confirmation and boundary |
| --- | --- | --- | --- |
| Original founder | [307604135121](../models/ancestors/3076041351210d5818df542b23c167278a76ce59d7ceae531b52e05398f80ad8/bundle.json) | 64 accepted repairs; bootstrap ancestor | Required baseline and retention source; not a new practice improvement. |
| First H144 practice champion | [ad9b330cd1c1](../models/confirmed/ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc/bundle.json) | 68 accepted repairs | 63/64 successes versus founder 61/64; paired native-return gain 90.390625, prespecified 95% bootstrap interval [43.515625,136.78125]. [Confirmation and independent verification](../evidence/run3/final64_confirmation_02/README.md). |
| New-experience, old24 replay champion | [9b97de044740](../models/confirmed/9b97de044740965b8cc103b38e04e0042301896466ccb5dd08f24023c362be07/bundle.json) | 68 accepted repairs | 64/64 versus founder 53/64; gain 93.421875, interval [44.296875,145.6875]. This used separately collected experience and a selected replay-ratio gene. On these same cases ad9 scored 63/64; 9b97 did not establish a return advantage over ad9. [Second confirmation](../evidence/run3/second_confirmation_01/README.md). |

These are 52-state observer-like software patch systems: local patch states and ports, sensory populations, two intermediate readback populations, twenty settled policy patches, public query qualification, repair records and immutable evidence bundles. Their population sizes are `scene 8 → reflection1:8 → reflection2:8 → policy 20`, with `aim 8` also read by the first reflection. They settle jointly. The four input ports contain 640 peripheral pixels, 384 foveal pixels, 644 visual-history coordinates and 352 executed-action-history coordinates. The action ABI has twenty legal macros, four native tics per action, and query budget 512.

Their genotype includes direct pixel and motor-history inputs to the policy population. Causal tests therefore do **not** support attributing their strong Basic scores to useful deep recursion. The practice targets are bounded, centered **action preferences**, not Q-values: `0.8 * (uniform_probability_over_best_native_actions - 0.05)`. Twenty native counterfactual interventions use a fixed founder continuation for 144 tics, and all-action ties are skipped. Exact continuation, retention, native-reward and target contracts are inside each bundle.

## Development models and retained failures

| Saved model | Development result | Interpretation |
| --- | --- | --- |
| [Small D3, batch64, 97b76a53efa2](../models/development/97b76a53efa2dce1693c646c725c62a540dda4268ede879e344ad5baf35791f5/bundle.json) | 15/16 Basic, 406/406 qualified queries; budget 512 | Both direct policy bypasses disabled. Promising training endpoint, no fresh confirmation. The planned on-policy causal probe was staged but **never executed**. |
| [Small D3, u256, b6de81e8365a](../models/development/b6de81e8365aed8838f768d24d7630de55f90932714221a6cd9ed97452c044d6/bundle.json) | 16/16 Basic at budget 1024; 440/440 qualified | At original 512 budget it had 11 query failures and only 5/16 successes. The saved local variant explicitly uses 1024. Historical visual permutation changed 0/12 chosen actions; responsiveness and recursive benefit remain unproved. |
| [Medium D3, u256, c9aad970947d](../models/development/c9aad970947d2c67b10807f9337204cead8ce0a8177d1ed7e0b7ee11639b03b1/bundle.json) | 10/16 Basic at budget 1024 | At 512 it had 15 query failures and 1/16 successes. Retained as the medium-depth comparison, not a confirmed champion. |
| Other saved architecture comparisons | Small D1/u256:12/16; medium skip:14/16; large skip:11/16; earlier forced-small:9/16; large batch64:5/16 | All are listed with exact hashes and reasons in the manifest. These are development results and negative controls, not additional confirmed winners. |
| [Browser promotion7613231af59e](../models/rejected-promotions/7613231af59eab636afd49751e8d1f489d5cef568f9ee7f21e8f3dc73573e9ea/bundle.json) | Fresh confirmation59/64 versus actual starting ad9 64/64 | **Rejected for retention:** five successes lost, despite higher average return. Preserved as a historical promotion, not the active champion. [Browser confirmation](../evidence/run3/browser_confirmation_01/README.md). |
| Recovered abdb48 and native-navigation blend00ab8c | Saved under `models/diagnostic/` | abdb48 was selected after fifteen repeated gates and rejected. The native-navigation blend retained Basic in its small development gate but achieved0/16 fresh navigation goals. Neither is a navigation winner. |

Development cases were reused for selection. Their scores cannot be combined into a new independent confirmation. Query-budget variants can share identical snapshot hashes while being different executable policies; file hashes and full query contracts distinguish them.

## Exact runtime

The [runtime manifest](../runtime/cadence-996d7ffdd43f7def/manifest.json) pins all twelve Cadence 0.50.0 Python source files. The set digest is `996d7ffdd43f7deffae20272ea35948f2704a7aa2c466d2c5a90905b438deefb`; the seven implementation hashes embedded in every saved snapshot match this source set. License and packaging context are separately marked copies from the local Cadence repository. Linux and Mac native environments remain separately identified in deployment and evaluation receipts.

`admissions` means accepted public repair events. It must not be relabelled as examples, unique experiences, epochs or internal settling sweeps. Independently recorded row/epoch/update counts are kept where they exist; unsupported counts stay unstated.

[verify_inventory.py](../inventory/verify_inventory.py) checks every saved model file, embedded snapshot identity, pinned evidence hash and the runtime source set. From the workspace root, run `python3 cadence-demos/doom-lab/inventory/verify_inventory.py` for the read-only local check. It inspects files; it does not train a policy or run Doom. Bulk unselected weights and experience remain on AWS, covered by the workspace data catalogue.
