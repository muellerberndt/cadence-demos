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
window. The published configuration serves Atlantis and Freeway. The
loop follows the bootstrap-then-life pattern from the library's LIVE
guide: witness admission during watching, an agreement gate, then
record-only feedback with budgeted replay pulses under one serial owner
per brain.

## Run it

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
ARCADE_GAMES=Atlantis,Freeway .venv/bin/python server.py
# open http://localhost:8668
```

`ARCADE_GAMES` selects the games, `ARCADE_PUBLIC=1` locks the speed
control, `ARCADE_HOST`/`ARCADE_PORT` bind the server.
`headless_control.py` runs the same pipeline without a browser and
checks takeover, fault-freedom, and that a living brain holds or beats
a frozen twin on identical seeds.
