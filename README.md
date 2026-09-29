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

Start with the [Doom Lab README](doom-lab/README.md), then the
[training tutorial](doom-lab/TRAINING.md).
