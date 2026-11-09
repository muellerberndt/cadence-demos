"""Strategy scenarios: fixed held-out positions, never trained on.

Positions come from games between bots (seat 0 one of `voronoi20`, `safe`, `survivor`; seat 1
one of the school pool) on start seeds 2,000,000+, which no school, search or validation step
uses. At every moment a position is kept for each test whose condition holds; the set is
determined by the seed, so every brain is scored on the same positions.

- `pocket` (not being walled in): the rider's safe moves lead to rooms of different size, the
  largest at least 20 cells and the smallest under half of it. Correct: a move whose room is at
  least 0.9 of the largest.
- `cutoff` (walling the opponent in): among the safe moves that keep at least 0.9 of the largest
  room, the cells the opponent reaches first differ by 8 to 60. Correct: a move within a quarter
  of that spread of the move that leaves the opponent the fewest.
- `fill` (space-filling endgame): the two heads can no longer reach each other and the rider's
  room is at least 15 cells. The rider plays on alone from there (the opponent is removed);
  score: cells filled over the cells of the room. `survivor` is the reference.

`tournament`: frozen games against each pool opponent on start seeds 2,100,000+.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import school
from .behaviour import INF, _dist, _room, _territory
from .world import DC, DR, Arena, mulberry32, turn

SEED = 2_000_000
RIDERS = ("voronoi20", "safe", "survivor")
OPPS = ("voronoi", "voronoi20", "survivor", "chaser", "hugger", "racer", "safe")


def _snap(arena: Arena) -> dict:
    return {"size": arena.size, "grid": list(arena.grid), "heads": [list(h) for h in arena.heads],
            "headings": list(arena.headings), "tick": arena.tick}


def restore(s: dict) -> Arena:
    a = Arena(s["size"], seed=0)
    a.grid = list(s["grid"])
    a.heads = [tuple(h) for h in s["heads"]]
    a.headings = list(s["headings"])
    a.tick = s["tick"]
    return a


def options(arena: Arena) -> dict[int, dict]:
    n, grid = arena.size, arena.grid
    h = arena.headings[0]
    r0, c0 = arena.heads[0]
    theirs = arena.heads[1]
    out = {}
    for k in range(3):
        hk = turn(h, k)
        r, c = r0 + DR[hk], c0 + DC[hk]
        if not arena.free(r, c) or (r, c) == theirs:
            continue
        grid[r * n + c] = 1
        out[k] = {"room": _room(grid, n, (r, c)), "territory": _territory(grid, n, (r, c), theirs)}
        grid[r * n + c] = 0
    return out


def separated(arena: Arena) -> bool:
    n = arena.size
    a = _dist(arena.grid, n, arena.heads[0])
    hr, hc = arena.heads[1]
    return not any(0 <= hr + DR[k] < n and 0 <= hc + DC[k] < n and a[(hr + DR[k]) * n + hc + DC[k]] < INF
                   for k in range(4))


def classify(arena: Arena) -> dict[str, list[int]]:
    """Which tests this position belongs to, with the correct moves of each."""
    found = {}
    opts = options(arena)
    if len(opts) >= 2:
        rooms = {k: v["room"] for k, v in opts.items()}
        top = max(rooms.values())
        if top >= 20 and min(rooms.values()) < 0.5 * top:
            found["pocket"] = [k for k in rooms if rooms[k] >= 0.9 * top]
        if not separated(arena):
            keep = {k: v["territory"] for k, v in opts.items() if v["room"] >= 0.9 * top}
            if len(keep) >= 2:
                best, worst = min(keep.values()), max(keep.values())
                spread = worst - best
                if 8 <= spread <= 60:
                    found["cutoff"] = [k for k in keep if keep[k] <= best + 0.25 * spread]
    if separated(arena) and _room(arena.grid, arena.size, arena.heads[0]) >= 15:
        found["fill"] = []
    return found


def build(path: Path, games: int = 400, per_test: int = 300) -> dict:
    sets = {"pocket": [], "cutoff": [], "fill": []}
    for g in range(games):
        s = SEED + g
        arena, draw = Arena(24, seed=s), mulberry32(s)
        rider, opp = school.POOL[RIDERS[g % 3]], school.POOL[OPPS[g % len(OPPS)]]
        filled_once = False
        while not arena.over:
            for test, good in classify(arena).items():
                if test == "fill":
                    if filled_once:
                        continue
                    filled_once = True
                if len(sets[test]) < per_test and (test != "pocket" or arena.tick % 2 == 0):
                    sets[test].append({"position": _snap(arena), "good": good, "game": s})
            arena.step((rider(arena, 0, draw), opp(arena, 1, draw)))
    path.write_text(json.dumps(sets))
    return {k: len(v) for k, v in sets.items()}


def fill_play(policy, snap: dict) -> float:
    """Ride alone from a walled-apart position; cells filled over the room's cells."""
    arena = restore(snap)
    n = arena.size
    room = _room(arena.grid, n, arena.heads[0])
    # Remove the opponent: its head stays a wall, it never moves again.
    filled = 0
    while filled < room:
        a = policy(arena, 0)
        h = turn(arena.headings[0], a)
        r, c = arena.heads[0][0] + DR[h], arena.heads[0][1] + DC[h]
        if not arena.free(r, c):
            break
        arena.headings[0] = h
        arena.grid[r * n + c] = 1
        arena.heads[0] = (r, c)
        filled += 1
    return filled / room


def score(policy, sets: dict, reset=None) -> dict:
    out = {}
    for test in ("pocket", "cutoff"):
        hits = 0
        for item in sets[test]:
            if reset:
                reset()
            hits += policy(restore(item["position"]), 0) in item["good"]
        out[test] = {"correct": hits, "positions": len(sets[test]), "rate": hits / max(len(sets[test]), 1)}
    fills = []
    for item in sets["fill"]:
        if reset:
            reset()
        fills.append(fill_play(policy, item["position"]))
    out["fill"] = {"positions": len(fills), "mean": sum(fills) / max(len(fills), 1)}
    return out


def tournament(policy, reset=None, games: int = 24, weights=None) -> dict:
    from . import r3

    pol = policy
    if reset:
        pol.reset = reset
    return r3.tournament(pol, 2_100_000, games, weights)


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def baseline_policy(name: str):
    bot = school.POOL[name]
    draw = mulberry32(7)
    return lambda arena, seat: bot(arena, seat, draw)

