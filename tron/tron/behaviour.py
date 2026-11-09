"""Strategy measured on real games: options that existed at a moment, and whether they were taken.

At every moment of the rider's (seat 0) game, before both cycles move, each of its three moves is
looked at with the opponent's head where it is:

- `cutoff`: the opponent's territory (cells it reaches before the rider, by breadth-first
  distance) after each safe move. If the safe moves differ by `CUT` to `CUT_MAX` cells in how
  far they shrink it, a cut-off was on offer; it was taken if the chosen move's shrink is
  within a quarter of that spread of the best. Larger spreads are choices between rooms, which
  `pocket` counts.
- `pocket`: the room the rider can still reach after each safe move. If one safe move leads into
  a room under half of the best one (and the best is at least 20 cells), a pocket was there; it
  was avoided if the chosen move keeps at least half of the best room.
- `parallel`: the opponent heads the same way one or two lanes over and the rider is ahead; the
  rider turned toward it (into its lane) or not. A count of a style, not of quality.
- `wall_in`: the first moment the two heads can no longer reach each other; won if the rider
  holds the bigger room then.

Rates are taken over opportunities only, so a rider that dies early cannot look good by never
meeting a choice. Each count is reported with its number of opportunities.
"""

from __future__ import annotations

from collections import deque

from .world import DC, DR, Arena, mulberry32, turn

INF = 1 << 20
CUT = 8
CUT_MAX = 60


def _dist(grid, n, start):
    dist = [INF] * (n * n)
    dist[start[0] * n + start[1]] = 0
    q = deque([start])
    while q:
        r, c = q.popleft()
        d = dist[r * n + c] + 1
        for k in range(4):
            rr, cc = r + DR[k], c + DC[k]
            if 0 <= rr < n and 0 <= cc < n:
                i = rr * n + cc
                if grid[i] == 0 and dist[i] == INF:
                    dist[i] = d
                    q.append((rr, cc))
    return dist


def _territory(grid, n, mine, theirs):
    a, b = _dist(grid, n, mine), _dist(grid, n, theirs)
    return sum(1 for i in range(n * n) if b[i] < a[i] and b[i] < INF)


def _room(grid, n, start):
    return sum(1 for d in _dist(grid, n, start) if 0 < d < INF)


def moment(arena: Arena, action: int) -> dict:
    n, grid = arena.size, arena.grid
    h = arena.headings[0]
    r0, c0 = arena.heads[0]
    theirs = arena.heads[1]
    options = {}
    for k in range(3):
        hk = turn(h, k)
        r, c = r0 + DR[hk], c0 + DC[hk]
        if not arena.free(r, c) or (r, c) == theirs:
            continue
        grid[r * n + c] = 1
        options[k] = {"territory": _territory(grid, n, (r, c), theirs), "room": _room(grid, n, (r, c))}
        grid[r * n + c] = 0
    out = {}
    if options:
        now = _territory(grid, n, (r0, c0), theirs)
        shrink = {k: now - v["territory"] for k, v in options.items()}
        best = max(shrink.values())
        spread = best - min(shrink.values())
        if CUT <= spread <= CUT_MAX:
            out["cutoff"] = action in shrink and shrink[action] >= best - 0.25 * spread
        rooms = {k: v["room"] for k, v in options.items()}
        top = max(rooms.values())
        if top >= 20 and min(rooms.values()) < 0.5 * top:
            out["pocket"] = action in rooms and rooms[action] >= 0.5 * top
    ho = arena.headings[1]
    if ho == h:
        right = (h + 1) % 4
        dr, dc = theirs[0] - r0, theirs[1] - c0
        forward = dr * DR[h] + dc * DC[h]
        side = dr * DR[right] + dc * DC[right]
        if 1 <= abs(side) <= 2 and forward < 0:
            toward = 2 if side > 0 else 0
            out["parallel"] = action == toward
    return out


def separation(arena: Arena) -> tuple[bool, int, int]:
    n = arena.size
    a = _dist(arena.grid, n, arena.heads[0])
    b = _dist(arena.grid, n, arena.heads[1])
    shared = any(a[i] < INF and b[i] < INF for i in range(n * n) if arena.grid[i] == 0)
    return (not shared, sum(1 for d in a if 0 < d < INF), sum(1 for d in b if 0 < d < INF))


class Tally:
    def __init__(self) -> None:
        self.counts = {k: [0, 0] for k in ("cutoff", "pocket", "parallel", "wall_in")}
        self._separated = False

    def see(self, arena: Arena, action: int) -> None:
        for key, taken in moment(arena, action).items():
            self.counts[key][0] += int(taken)
            self.counts[key][1] += 1

    def after(self, arena: Arena) -> None:
        if self._separated or arena.over:
            return
        apart, mine, theirs = separation(arena)
        if apart:
            self._separated = True
            self.counts["wall_in"][0] += int(mine > theirs)
            self.counts["wall_in"][1] += 1

    def new_game(self) -> None:
        self._separated = False

    def report(self) -> dict:
        return {k: {"taken": t, "opportunities": o, "rate": (t / o if o else None)} for k, (t, o) in self.counts.items()}


def measure(policy, opponent, *, games: int = 24, seed: int = 400_000, size: int = 24) -> dict:
    """policy(arena, seat); opponent(arena, seat, draw)."""
    tally = Tally()
    results = []
    for g in range(games):
        arena = Arena(size, seed=seed + g)
        draw = mulberry32(seed + g)
        tally.new_game()
        while not arena.over:
            a = policy(arena, 0)
            tally.see(arena, a)
            arena.step((a, opponent(arena, 1, draw)))
            tally.after(arena)
        results.append(arena.winner)
    out = tally.report()
    out["score"] = sum(1.0 if w == 0 else 0.5 if w is None else 0.0 for w in results) / games
    return out
