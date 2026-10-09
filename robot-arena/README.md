# Cadence Showcase League

Robots assembled from parts, each with one continuing Cadence brain wired to every motor.
A robot is nursed alone until it can drive, aim and stay inside a ring. Then it fights
six-robot royales for the rest of its life and keeps learning from every fight. Nothing is
reset between fights, and the page runs the fights live in your browser and saves every
brain there.

![The page](docs/showcase-page.png)

## See it

```sh
cd showcase-app && npm install && npm run build && npx vite preview --port 4173
```

Open http://localhost:4173/. `public/pack/` holds six licensed brains, the arena's Python and
the cadence-net wheel; Pyodide runs them in a worker. What to watch:

- the ladder's last column, the driving test each brain arrived with (eight marks: approach,
  escape, the closing ring, engagement, chase, facing, no spinning, no stalling);
- the "getting better" row: damage per robot per fight and moments in the burn, first third
  of your fights against the last third, and the share of calm moments;
- the brain inspector of the selected robot: its senses, the one settled state, the chosen
  command per motor, and the arousal level that decides whether it learns this moment.

Returning visitors get their own league back; "Reset the brains to how they arrived" starts
over.

## How a robot learns

**Nursery.** Alone with a dummy and a sparring partner, immortal, headless, tens of times
faster than real time. The world pays metres closed on the target, damage dealt and a
destroyed dummy; it charges damage taken and burns outside a standing ring. Nobody tells
the brain which motor is which.

**Driving test.** A frozen greedy copy of the brain is tested in open space: approach from
eight bearings, escape, come in when the ring closes, engage, chase, face the rival, no
spinning, no stalling. The score ranks brains and picks the roster; the marks are in the
page's manifest.

**Ring.** Six robots, a ring closing to 3.5 m over 2000 moments; damage dealt pays, damage
taken and the burn cost, closing on the nearest rival pays, finishing a rival pays a trophy,
placement pays at the end. In the ring the brain runs on a stage: calm unless surprised, a
sharp sampling temperature, and an actor step a thirtieth of the nursery's, so a fight
refines what the nursery built instead of overwriting it.

The settings behind this are in [docs/brain.md](docs/brain.md).

## Train your own league

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export OMP_NUM_THREADS=1
STAGE=$(.venv/bin/python -c 'import json; from arena.brain import PAGE_STAGE; print(json.dumps(PAGE_STAGE))')
.venv/bin/python -m arena --league league init                    # the stock bodies and two random twins
.venv/bin/python -m arena --league league nursery --moments 100000 --workers 8
.venv/bin/python -m arena --league league licence --all --workers 8
.venv/bin/python -m arena --league league royale --fights 20 --size 6 --duration 2400 --zone-moments 2000 --zone-end 3.5 --stage "$STAGE"
.venv/bin/python -m arena --league league dashboard               # league/index.html, replays with the inspector
cd showcase-app && ../.venv/bin/python pack.py --league ../league --robots 6 && npm run build
```

`python -m arena evolve --help` breeds lineages: mutants of body and genes are born with
newborn brains, raised, fought on the stage and ranked by the driving test; the best of
every lineage stay with their brains. `tests/` checks the physics, the senses, the brain
wrapper, the nursery, the royale and the page's pack.

## From showcase to game

The same pieces carry a multiplayer game: players assemble a body from the parts catalogue
and name it; the server nurses it (a nursery is a few minutes of CPU) and hands back its
driving test; matchmaking by Elo fills six-robot rooms; the fight runs on the server with
the replay streamed, or in every browser from the same seed; brains live on between fights,
so a robot that lost learns from it; a season ends with lineages, where the top robots'
mutants enter the next season. Everything a player could fake stays server-side: the brain
file, the fight seed, the replay.

## Layout

`arena/` the parts catalogue, physics, senses, brain wrapper, nursery, royale, licence,
league, evolution and dashboard; `viewer/` the isometric replay page and the league page;
`showcase-app/` the page and its packer; `league-live/` the roster the page ships with;
`tests/` the checks; `docs/` the brain settings and screenshots.
