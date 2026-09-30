# Atari Arcade

Cadence brains born at server start learn Atari games while you watch.
Each brain begins as a hatchling, watches a scripted teacher play, takes
the controls once its decoded actions agree with the teacher often
enough, and keeps learning from every reward through `Reinforcement`.
The page shows the game, the brain as one settling organ with cortical
columns and live fibers, a gamepad lit by the executed action, and the
convergence numbers: teacher agreement, understanding as fallen repair
effort, witnesses, sweeps, and the lifetime score curve with a skill
badge from noob to legend.

The brains and emulators run in the Python server; the browser is the
window. Four games are wired: Atlantis, Freeway, Carnival and Space
Invaders. Carnival and Space Invaders still degrade in self-play
([#1](https://github.com/muellerberndt/cadence-demos/issues/1)); the
other two reach expert, and Freeway has beaten its teacher. The loop
follows the bootstrap-then-life pattern from the library's LIVE
guide: witness admission during watching, an agreement gate, then
record-only feedback with budgeted replay pulses under one serial owner
per brain.

## Brain layout

Atari Arcade uses **recursive observer settlement**. Sensory columns read image
tiles; successive observers read the columns' live states and exact prediction
errors, with motor and value outputs taken from observer populations. Those
bounded patches and their readback settle together in the server's Cadence
engine. `requirements.txt` installs the library from its Git branch without a
commit pin, so record the installed source when comparing runs.

This layout explores learned perception and action with internal error feedback.
Flat settlement is a useful baseline for direct sensory relations; ordinary
state-coupled settlement tests learned intermediate representations without
error readback. All three share the library's settlement rule. See the
[layout guide](https://github.com/muellerberndt/cadence/blob/main/docs/VARIANTS.md)
and [performance guide](https://github.com/muellerberndt/cadence/blob/main/docs/PERFORMANCE.md).

## Run it

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
# open http://localhost:8668
```

`ARCADE_GAMES` selects the games, `ARCADE_PUBLIC=1` locks the speed
control, `ARCADE_HOST`/`ARCADE_PORT` bind the server.
`headless_control.py` runs the same pipeline without a browser and
checks takeover, fault-freedom, and that a living brain holds or beats
a frozen twin on identical seeds.
