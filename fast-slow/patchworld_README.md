# Patch World routine bootstrap

This experiment teaches public Cadence brains a small local foraging routine,
then runs their frozen parameters in the original JavaScript Patch World body.
`patch-world/core.js` remains unchanged. The Python actor receives the nine local
food counts and chooses one of north/east/south/west/eat/wait. Its public settlement
must qualify before its selected action reaches the body; a refusal executes a
disclosed wait and fails the qualification gate.

The original substrate updates, body action rules, stochastic metabolism and mass
conservation remain active. Population is restricted to one organism, optional
world rules are off, and the organism's old JavaScript brain is replaced by the
adapter. This does **not** migrate the browser brain, test reproduction or ecology,
or establish reward learning. The teacher is an explicit local-food scoring rule
adapted from `cadence-world/world/settling.py`; labels enter the public
`observe_batch(..., source="estimate")` API. Live execution has no teacher or
parameter updates. Reflex and random controls are recorded separately.

## Frozen comparison

| Layout | Patches | Connections | Parameters |
| --- | ---: | ---: | ---: |
| Flat, direct food inputs | 6 | 54 | 60 |
| Two perception patches plus motor column | 8 | 84 | 92 |
| Two perception patches plus motor observer | 8 | 96 | 104 |

All use the same public patch law, parameter prior `0.1`, qualification tolerance
`1e-6`, and settlement allowance `2048`. Five seeds receive the same 96 training
rows for 20 epochs, with matched order across layouts for each seed: 120 accepted
batch admissions, 1,920 row presentations per arm. Development rows do not select
checkpoints. Each arm has a 60-second allowance, three workers run concurrently,
and all 15 planned outcomes are retained. These layouts have unequal capacity;
timing differences are descriptive and do not isolate recursive benefit.

The 48 held-out rows were independently generated but not deduplicated: eight
rows repeat training inputs. The original gate remains unchanged. The independent
verifier additionally reports accuracy on the 40 novel rows, as a descriptive
check. The 24 development rows include three training-input repeats.

## Verified result, 2026-10-01

All 15 arms completed and passed the frozen acquisition/qualified-body gate.
Every layout reached 100% action agreement on both all 48 held-out rows and the
40 novel rows. Newborn agreement ranged from 12.5% to 43.75%.

All learned actors survived the 96-tick native check and ate 62–69 times; newborns
ate 0–3 times and three died early. Random controls ate 8–20 times and the supplied
reflex ate 56–68 times. These short, seeded trajectories demonstrate acquisition
and execution of the supplied routine, not a general survival guarantee.

Mean whole-arm time was 4.03 seconds for flat, 15.08 for composed and 23.53 for
observer. This includes offline training, all checks and four native trajectories;
it is not inference latency. The receipt separates returned work by phase.
Recorded CPU seconds refer to the Python process and exclude Node subprocesses.
Native metabolism retains the body's original stochastic, bounded per-tick charge;
it is not a model of total hardware cost. Offline training is not retrospectively
charged to the body.

The [verification receipt](evidence/patchworld-bootstrap-20261001/verification.json)
binds the [protocol](evidence/patchworld-bootstrap-20261001/protocol.json), all 15
outcomes, 1,800 accepted admissions and 6,383 returned solver calls. Verification
replayed every completed arm's newborn/development/held-out and native brain query,
plus 11,329 native body RPCs, checking predictions, qualification, work, snapshot
custody, sensed inputs, actual actions, body state hashes and exact mass conservation.
It did not numerically replay training. Complete outcomes must have no pending
solver or body intent; malformed or missing outcomes cannot pass. The collector
has limited startup/interruption recovery, stated explicitly in the receipt.

The full evidence archive stays on AWS; its identity and size are in the
[archive receipt](evidence/patchworld-bootstrap-20261001/archive-receipt.json).
The candidate core was commit `ab3cad2`; exact Python source hashes are frozen in
the protocol. Node was `v22.20.0`, with its binary hash bound as well. No claim of
JavaScript/Python brain-engine numerical parity is made.

## Reproduction

Use the exact source-bound candidate core and Node binary from the protocol.
From this repository, with `PYTHONPATH` pointing to that core's `src` directory:

```bash
python fast-slow/patchworld_bootstrap.py freeze \
  --root /path/to/new-run --core patch-world/core.js
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python fast-slow/patchworld_bootstrap.py run \
  --root /path/to/new-run --core patch-world/core.js
python fast-slow/patchworld_verify.py /path/to/new-run \
  --core patch-world/core.js
```

Freeze refuses an existing directory. The runner verifies source, data and Node
identity before training. Keep bulk outputs on AWS. The verifier's hard-coded
collector pin intentionally rejects changed experiment code; a changed experiment
requires a separate protocol and receipt.

The focused tests require Node and perform no training:

```bash
PYTHONPATH=/path/to/candidate/src:fast-slow python -m pytest -q \
  fast-slow/test_patchworld_bootstrap.py fast-slow/test_patchworld_verify.py
```
