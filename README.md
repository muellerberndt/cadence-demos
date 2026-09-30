# Cadence demos

The official demos for [Cadence](https://github.com/muellerberndt/cadence) —
Deep Recursive Settlement Networks: processing populations and their
recursive observers, learning and settling together.

## [Doom Lab](doom-lab/) — the canonical example

A settling brain plays shareware Doom in your browser, from pixels alone.
Play alongside it and it learns from you **while you play**; watch its
nervous system settle in a live, rotatable 3D view; hot-swap, import and
export brains without stopping the game. The full training pipeline is
included and documented: scripted privileged teacher, witness corpus
collection, batched settlement bootstrap with matched controls, DAgger
correction rounds, and a foresight variant that learns an action-conditioned
world model from measured outcomes.

```sh
cd doom-lab
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
./get_wad.sh
python server.py     # open http://localhost:8666
```

## [Atari Arcade](atari-arcade/) — the second canonical example

Brains born at server start learn Atari games while you watch: each one
watches a scripted teacher, takes the controls once its decoded actions
agree often enough, and keeps learning from every reward. The page
shows the game beside the brain as one settling organ with cortical
columns and live fibers, a gamepad lit by the executed action, and the
convergence numbers through a skill badge from noob to legend. Four
games are wired; two still degrade in self-play and say so.

```sh
cd atari-arcade
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python server.py   # open http://localhost:8668
```

Start with the [Doom Lab README](doom-lab/README.md), then the
[training tutorial](doom-lab/TRAINING.md), then the
[Atari Arcade README](atari-arcade/README.md).

## [Patch World](patch-world/) — an evolving world in one page

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
