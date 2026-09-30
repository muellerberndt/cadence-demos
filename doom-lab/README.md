# Cadence Doom Lab

A demo that shows a small, early **baby** Cadence model being trained in the
browser. The brain learns basic Doom control from a finite bootstrap and
practice on its own experience. The page shows native gameplay, the brain's
settled activity, and a live learning feed: the reward the baby collects for
killing the monster, each admitted repair, retention-gate outcomes and champion
promotions. You can import/export models and control guarded continued
learning. Python runs ViZDoom and the Cadence brain locally.

[v1/PLAN.md](v1/PLAN.md) outlines the full training plan for an autonomous
Doom player — bootstrap, autonomous practice, navigation, doors, survival and
reserved-map transfer. That plan cannot currently be executed for lack of
compute resources; this demo runs the confirmed small models and guarded
browser practice only.

## What works

The confirmed Basic-combat actors are **ad9** and **9b97**. Their separate
reserved Linux confirmations achieved **63/64** and **64/64** wins, respectively,
with positive paired native-return improvements over the original founder.
They use 2,020 pixel/history inputs, 20 action choices and 52 patches with
three declared levels. Actions come from qualified, unclamped equilibria.

These results establish limited Basic-combat competency and selected autonomous
learning gains. They do not establish general Doom mastery.

## Brain layout

The confirmed actors use **recursive observer settlement**: `scene` and `aim`
read pixels/history, two reflection populations observe successive live states
and exact prediction errors, and the policy observes the second reflection
alongside direct sensory/history inputs. All 52 patches settle jointly under
the bundled, source-verified Cadence 0.50.0 runtime.

The builder's `observer=False` control uses ordinary state-coupled settlement
with state-only population connections. Flat settlement instead reads supplied
inputs directly and is a useful baseline for simpler control relations. These
are three supported design patterns using one settlement rule; the confirmed
actors alone do not isolate the value of recursive observation. See the
[layout guide](https://github.com/muellerberndt/cadence/blob/main/docs/VARIANTS.md)
and [performance guide](https://github.com/muellerberndt/cadence/blob/main/docs/PERFORMANCE.md).

## Run the prepared demo

Use Python 3.12 (the prepared Mac deployment uses 3.12.6) and the pinned dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open **http://localhost:8666** and press **RESUME**. The prepared registry selects
`confirmed-ad9`; the model dropdown also offers the separately confirmed
`confirmed-9b97`. Learning starts off. **AUTOLEARN** starts a separate candidate
learner; candidates must retain the baseline's wins and pass the native gate
before replacement. **ROLLBACK**, **IMPORT** and **EXPORT** retain
explicit model ownership. Importing a model does not activate it or enable
learning. Pausing gameplay and pausing learning are separate controls.

Basic uses ViZDoom's bundled scenario. Shareware full-map assets are needed
only for later full-map experiments. The new default demo does not claim those
levels are solved. Linux measurements do not automatically transfer to macOS;
each deployed copy binds its actual native engine, source and validation receipt.

For a new environment without the prepared `data/` registry, follow
[deployment and reproduction](docs/DEPLOYMENT.md). The app uses the exact
hash-verified source under `runtime/`, not an arbitrary installed Cadence release.
Original checkpoint bytes remain in `models/`; imported deployment copies live
under `data/models/` and new practice state stays in its own wave directory.

## How it learns

1. A finite set of starter demonstrations bootstraps the Cadence brain.
2. The brain plays through qualified settlements and records what it actually did.
3. Native simulator workers reconstruct selected states, try the action choices,
   then continue with a frozen Cadence actor. Complete outcome records supply
   versioned preference targets.
4. The public common repair rule admits new experience mixed with retention
   replay into a separate candidate. Native skill/retention evaluations decide
   whether it becomes the champion.

This is simulator-assisted autonomous practice. The actor receives visible
pixels and its own history; it has no map coordinates or teacher fallback.
Observer populations read live states and prediction errors within the same
coupled equilibrium. This bounded, self-reading structure, its feedback, and
its retained evidence distinguish the experiment from a generic neural policy.

## Documentation

| Location | Contents |
| --- | --- |
| [v1/PLAN.md](v1/PLAN.md) | Full training plan for an autonomous Doom player; not currently executable for lack of compute resources |
| [docs/MODELS.md](docs/MODELS.md) | Model manifest, exact identities and winner categories |
| [docs/COMPONENTS.md](docs/COMPONENTS.md) | Network, sensors, memory, action, repair, feedback and runtime contracts |
| [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) | Everything tried, measured successes, failed attempts and limitations |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Setup, validation, packaging, controls and verification |
| `models/`, `inventory/`, `runtime/` | Original weights, the model manifest and verifier, and the pinned core |
| `evidence/` | Compact receipts and local validations |

Serialized contracts, receipts and AWS paths keep their original `v3` schema
strings; those are exact identifiers, not another supported application.
