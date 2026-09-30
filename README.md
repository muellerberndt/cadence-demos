# Cadence demos

The official demos for [Cadence](https://github.com/muellerberndt/cadence):
brains that learn from experience through bounded patches, local relations,
readback and settlement. Each demo shows how one or more of Cadence's
settlement design patterns is implemented in a working application.

> **Early research.** Cadence is under heavy early research. The
> implementations in these demos are imperfect and change as the library
> changes. Each demo's README states what its brain learns and where it falls
> short.

## Three settlement design patterns

Cadence 0.50.0 supports three design patterns through the same patch law and
settlement engine. They are choices for a task, and one brain can combine them.

| Pattern | What patches read | A useful starting point for |
| --- | --- | --- |
| Flat settlement | Fixed sensory inputs only | Small, fast sensor-to-output relations and a low-cost baseline |
| State-coupled settlement | Sensors and other populations' live states | Learned intermediate representations and sensory fusion |
| Recursive observer settlement | Live states and exact prediction errors, including other observers' | Testing whether feedback about internal mismatches improves behavior |

Flat brains also settle. State-coupled populations take part in one joint
solve; observers add error readback to that same solve. Choose the smallest
layout that learns the behavior, then measure the benefit and cost of added
coupling. The [design-pattern guide](https://github.com/muellerberndt/cadence/blob/main/docs/VARIANTS.md)
has runnable examples of each, and the
[performance guide](https://github.com/muellerberndt/cadence/blob/main/docs/PERFORMANCE.md)
explains their costs.

## Which demo shows which pattern

| Demo | Design pattern | Engine |
| --- | --- | --- |
| [Rover Lab](rover-lab/) | All three, side by side on one task | Sibling Cadence 0.50.0 checkout |
| [Doom Lab](doom-lab/) | Recursive observer settlement, with a state-coupled control | Bundled Cadence 0.50.0 runtime |
| [Atari Arcade](atari-arcade/) | Recursive observer settlement | Cadence from its Git branch, without a commit pin |
| [Patch World](patch-world/) | Recursive observer settlement, with evolving observer depth | Separate JavaScript implementation |
| [Amen](amen/) | Legacy record patch, older than the three patterns | Browser engine running an archived Cadence 0.11.0 brain |

Rover Lab is the place to compare the three patterns on the same body and the
same data.

## [Rover Lab](rover-lab/): three patterns on a changed body

A differential-drive rover learns motion consequences from executed wheel
commands and odometry. Flat, state-coupled and recursive observer layouts of
four patches each learn the same body; the browser comparison runs the
recursive one. Weaken the rover's right wheel and compare continued Cadence learning
with a frozen copy, an adaptive estimator and a small MLP. The local viewer
shows trajectories, actual patch readback, restoration probes and replayable
evidence. Cadence supplies the learned body model inside a shared heading
controller.

```sh
cd rover-lab
python3 -m pip install -r requirements.txt
python3 server.py                 # http://localhost:8670
```

See the [interface and measurement contract](rover-lab/README.md). Timing is
best effort; the receipt records the 100 ms deadline gate separately from
target-reaching performance.

## [Doom Lab](doom-lab/): recursive observers playing Doom

A demo that trains a small, early **baby** Cadence brain in the browser. It
controls Doom from visible pixels and its own executed-action history. The
browser shows the game, settled brain activity, a live feed of rewards and
learning events, model import/export, and guarded autonomous practice; Python
runs the native engine and brain. The current application is **Doom Lab V1**.

The brain uses recursive observer settlement. Scene and aim populations read
pixels and history, two reflection populations observe their live states and
exact prediction errors, and the policy observes the second reflection. All 52
patches settle jointly.

The approach is a finite basic-skills bootstrap followed by learning from the
brain's own gameplay. Parallel simulator branches supply measured consequences;
Cadence's common repair rule updates candidate brains. A candidate replaces the
champion only after native gameplay and retained-skill checks. Within the brain,
bounded patches, sensory/motor ports, state/error readback and a common coupled
settlement form an observer-like self-reading system. There is no external
policy optimizer or scripted fallback choosing student actions.

Two selected Basic-combat descendants passed separate reserved confirmations:
**63/64 and 64/64 wins**, with higher native return than their respective
founder comparisons. These are single-room results, and navigation is work in
progress. The aim is a **Doom baby that acquires skills through its own
experience**, growing toward full gameplay.

```sh
cd doom-lab
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# Prepare a source/platform-validated deployment as described in the README.
python server.py                 # http://localhost:8666
```

The prepared local demo uses the confirmed `ad9` brain, with `9b97` available
as another confirmed model. Immutable winners live under `doom-lab/models/`;
deployed copies and new learning state are separate. The exact historical
Cadence runtime is pinned with the app.

- [Run the demo and understand its limits](doom-lab/README.md)
- [Every saved model and selected local artifacts](doom-lab/docs/MODELS.md)
- [Experiments and results](doom-lab/docs/EXPERIMENTS.md)
- [Components and contracts](doom-lab/docs/COMPONENTS.md)
- [Development plan](doom-lab/v1/PLAN.md)

## [Atari Arcade](atari-arcade/): recursive observers learning Atari games

Brains born at server start learn Atari games while you watch: each one
watches a scripted teacher, takes the controls once its decoded actions
agree often enough, and keeps learning from every reward. Sensory columns
read image tiles, and successive observers read their live states and exact
prediction errors. The page shows the game beside the brain as one settling
organ with cortical columns and live fibers, a gamepad lit by the executed
action, and the convergence numbers through a skill badge from noob to
legend. Four games are wired; two degrade in self-play and say so.

```sh
cd atari-arcade
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python server.py   # open http://localhost:8668
```

See the [Atari Arcade README](atari-arcade/README.md).

## [Patch World](patch-world/): evolving observer depth in one page

A conserved-mass world under a moving sun, whose creatures carry deep
recursive settlement brains implemented in JavaScript: an inherited body plan
(width, depth, fan-in, senses, plasticity), one joint settle per tick, learned
relations within one life, and a metabolism that prices every patch, relation
and repair sweep in mass. Three views show the substrate, the union of the
living observers' records, and one creature's own beliefs beside its settling
brain. Evolution, biting, hoarding and speech are all open niches; energy and
death are the only selection, and no depth advantage is claimed.

```sh
cd patch-world
python3 -m http.server 8080       # http://localhost:8080/
```

A headless probe and receipts are included; see
[the world's contract and its numbers](patch-world/README.md).

## [Amen](amen/): a jungle composer in the browser

One record patch learned jungle tracks as events per half-beat: a slice of a
drum break, a sub-bass note, a change flag and a texture. This legacy mechanism
is older than the three settlement patterns. Nothing on the page is recorded:
press the button and the brain computes a track from silence in the browser in
seconds, hearing each half-beat it plays, then renders it through the
instrument. The page carries its own engine and the archived brain of an
earlier Cadence release, reproduced against the sealed run by a parity test;
its model card states exactly what is supplied and learned.

```sh
python -m http.server -d amen/web 8803   # open http://localhost:8803 and press CUT A DUB
```

Receipts and checks: `python amen/verify.py` from the repository root; see
[the Amen README](amen/README.md).
