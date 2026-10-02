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

## Play it in the browser

[floatingpragma.io/demos/atari-arcade](https://floatingpragma.io/demos/atari-arcade/)
runs the two games that reach expert, Freeway and Atlantis, with nothing
behind the page. `web/` holds an Atari 2600 core ([6502.ts](https://github.com/6502ts/6502.ts))
behind an ALE-style game interface (`emulator/ale.js`, bundled into
`emulator.js`), a JavaScript port of the Cadence 0.50.0 reference engine
(`cadence.js`: the seeded wiring, the joint repair, batch admission, the
Reinforcement helper and Python's `random` module), and the server's loop
(`arcade.js`). Each game gets two web workers: the emulator, which never waits
for the brain, and the brain, one serial owner. A brain is born from seed 0
with exactly the weights the library would give it. Two timing choices are
made explicit: the browser brain admits each frame at most once, where the
server's brain thread can append the same latest frame several times between
probes, and after the takeover it decides once per forty environment steps,
the cadence the server's torch brain had from its half-second decisions (a
JavaScript decision takes tens of milliseconds, and one-step transitions carry
rewards too rarely for the same learning). The games run at four times real
time, sixty agent steps a second.

```sh
cd web && python3 -m http.server 8080      # open http://localhost:8080/
```

`node parity.mjs` checks the port against the library on recorded fixtures
(`tools/make_parity_fixture.py` regenerates them with the real library):
wiring and newborn weights are identical bit for bit, settled states agree
within `tolerance / state_prior`, admission decisions, action choices and replay
samples are identical, and admitted parameters agree to 1e-4. Sweep counts
differ by a few percent because each patch's drive is summed with Neumaier
compensation where the library rounds exactly.

`node headless.mjs --game Freeway --episodes 5 --out receipts/freeway_living.json`
runs the browser pipeline without a browser, the game advancing at the page's
full speed beside the brain. The receipts in `receipts/` record the runs behind the published page: Freeway
took the controls after 174 s at 240 witnesses and 0.95 agreement and lived
17, 21, 16, 26, 21, 21 against its teacher's 21 (expert, best 26); Atlantis
took over after 288 s at 0.95 agreement and lived 2000, 2000, 2000, 2000, 2000
against 2000 (expert, best 2000). Neither run faulted.
`emulator/` rebuilds `emulator.js` (`npm install && npm run build`). The ROM
images are the ones shipped with `ale-py` 0.12.1; see `web/THIRD_PARTY.md`.

## Brain layout

Atari Arcade uses **recursive observer settlement**. Sensory columns read image
tiles; successive observers read the columns' live states and exact prediction
errors, with motor and value outputs taken from observer populations. Those
bounded patches and their readback settle together in the server's Cadence
engine. `requirements.txt` pins Cadence 0.50.0 source
`5d830d1bbb590c1837832b3bc9b6e1f811a4cd46`: the archived small-query, batch,
reward and arcade-wiring fixtures replay exactly against it. This preserves
the server's original API across changes to the library's default brain.
The browser carries its separate recorded engine; this dependency pin neither
ports that engine nor establishes a fresh gameplay result.

This layout explores learned perception and action with internal error feedback.
Flat settlement is a useful baseline for direct sensory relations; ordinary
state-coupled settlement tests learned intermediate representations without
error readback. All three share the library's settlement rule. See the
[layout guide](https://github.com/muellerberndt/cadence/blob/5d830d1bbb590c1837832b3bc9b6e1f811a4cd46/docs/VARIANTS.md)
and [interaction guide](https://github.com/muellerberndt/cadence/blob/5d830d1bbb590c1837832b3bc9b6e1f811a4cd46/docs/LIVE.md).

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
