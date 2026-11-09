"""Opponents and the teacher. Each bot maps (arena, seat) to a relative action.

`voronoi` is the decent player the brain is bootstrapped against: it looks one move ahead
for both cycles and scores each pair by the cells it reaches before the opponent (a Voronoi
partition by breadth-first distance); once the cycles are walled apart it fills its own room,
hugging walls. `survivor` only maximizes the room it can still reach; `safe` picks uniformly
among moves that do not crash at once; `uniform` is the uniform-random baseline.
"""

from __future__ import annotations

from collections import deque

from .world import ACTIONS, DC, DR, STRAIGHT, Arena, turn

INF = 1 << 20


def _next(arena: Arena, seat: int, action: int) -> tuple[int, int, int]:
    h = turn(arena.headings[seat], action)
    r, c = arena.heads[seat]
    return r + DR[h], c + DC[h], h


def _distances(grid: list[int], n: int, start: tuple[int, int]) -> list[int]:
    dist = [INF] * (n * n)
    r0, c0 = start
    dist[r0 * n + c0] = 0
    queue = deque([(r0, c0)])
    while queue:
        r, c = queue.popleft()
        d = dist[r * n + c] + 1
        for k in range(4):
            rr, cc = r + DR[k], c + DC[k]
            if 0 <= rr < n and 0 <= cc < n:
                i = rr * n + cc
                if grid[i] == 0 and dist[i] == INF:
                    dist[i] = d
                    queue.append((rr, cc))
    return dist


def _free_neighbours(grid: list[int], n: int, r: int, c: int) -> int:
    count = 0
    for k in range(4):
        rr, cc = r + DR[k], c + DC[k]
        if 0 <= rr < n and 0 <= cc < n and grid[rr * n + cc] == 0:
            count += 1
    return count


def _score(grid: list[int], n: int, mine: tuple[int, int], theirs: tuple[int, int]) -> tuple[int, bool]:
    """Cells I reach first minus cells they reach first; whether we still share a room."""
    # The heads themselves are occupied; distances start from them through free cells.
    a = _distances(grid, n, mine)
    b = _distances(grid, n, theirs)
    shared = False
    for k in range(4):
        rr, cc = theirs[0] + DR[k], theirs[1] + DC[k]
        if 0 <= rr < n and 0 <= cc < n and a[rr * n + cc] < INF:
            shared = True
            break
    score = 0
    for i in range(n * n):
        if a[i] < b[i]:
            score += 1
        elif b[i] < a[i]:
            score -= 1
    return score, shared


ORDER = (STRAIGHT, 0, 2)  # tie-break: straight, then left, then right


def voronoi(arena: Arena, seat: int) -> int:
    n = arena.size
    other = 1 - seat
    grid = arena.grid
    best, best_value = STRAIGHT, -INF * 4
    for action in ORDER:
        r, c, _ = _next(arena, seat, action)
        if not arena.free(r, c):
            value = -INF * 2
        else:
            worst = INF * 4
            for reply in ORDER:
                rr, cc, _ = _next(arena, other, reply)
                they_die = not arena.free(rr, cc) or (rr, cc) == (r, c)
                if (rr, cc) == (r, c):
                    v = -INF  # head-on: both die
                elif they_die:
                    v = INF
                else:
                    grid[r * n + c] = 1
                    grid[rr * n + cc] = 1
                    score, shared = _score(grid, n, (r, c), (rr, cc))
                    if not shared:
                        # Walled apart: my room against theirs, wall-hugging inside it.
                        mine = sum(1 for d in _distances(grid, n, (r, c)) if 0 < d < INF)
                        theirs = sum(1 for d in _distances(grid, n, (rr, cc)) if 0 < d < INF)
                        v = 4 * (mine - theirs) - _free_neighbours(grid, n, r, c)
                    else:
                        v = 4 * score
                    grid[r * n + c] = 0
                    grid[rr * n + cc] = 0
                worst = min(worst, v)
            value = worst
        if value > best_value:
            best, best_value = action, value
    return best


def survivor(arena: Arena, seat: int) -> int:
    n = arena.size
    best, best_value = STRAIGHT, -INF
    for action in ORDER:
        r, c, _ = _next(arena, seat, action)
        if not arena.free(r, c):
            continue
        arena.grid[r * n + c] = 1
        room = sum(1 for d in _distances(arena.grid, n, (r, c)) if 0 < d < INF)
        value = 4 * room - _free_neighbours(arena.grid, n, r, c)
        arena.grid[r * n + c] = 0
        if value > best_value:
            best, best_value = action, value
    return best


def safe(arena: Arena, seat: int, draw) -> int:
    options = [a for a in range(ACTIONS) if arena.free(*_next(arena, seat, a)[:2])]
    if not options:
        return STRAIGHT
    return options[int(draw() * len(options))]


def uniform(arena: Arena, seat: int, draw) -> int:
    return int(draw() * ACTIONS)


def chaser(arena: Arena, seat: int, draw=None) -> int:
    """A player with a habit: it heads for the cell in front of the opponent to cut it off,
    and only falls back to keeping room when no move gets closer. Baitable."""
    n = arena.size
    other = 1 - seat
    h = arena.headings[other]
    tr, tc = arena.heads[other][0] + 2 * DR[h], arena.heads[other][1] + 2 * DC[h]
    best, best_value = None, INF
    for action in ORDER:
        r, c, _ = _next(arena, seat, action)
        if not arena.free(r, c):
            continue
        arena.grid[r * n + c] = 1
        room = sum(1 for d in _distances(arena.grid, n, (r, c)) if 0 < d < INF)
        arena.grid[r * n + c] = 0
        if room < 8:
            continue
        value = abs(r - tr) + abs(c - tc)
        if value < best_value:
            best, best_value = action, value
    return survivor(arena, seat) if best is None else best


def _apply(arena: Arena, seat: int, action: int):
    """Move one cycle in place for the look-ahead; returns an undo record, or None if it dies."""
    r, c, h = _next(arena, seat, action)
    if not arena.free(r, c):
        return None
    record = (seat, arena.heads[seat], arena.headings[seat], r * arena.size + c)
    arena.grid[r * arena.size + c] = 1 + seat
    arena.heads[seat] = (r, c)
    arena.headings[seat] = h
    return record


def _undo(arena: Arena, record) -> None:
    seat, head, heading, index = record
    arena.grid[index] = 0
    arena.heads[seat] = head
    arena.headings[seat] = heading


def _leaf(arena: Arena, seat: int) -> int:
    n = arena.size
    score, shared = _score(arena.grid, n, arena.heads[seat], arena.heads[1 - seat])
    if shared:
        return 4 * score
    mine = sum(1 for d in _distances(arena.grid, n, arena.heads[seat]) if 0 < d < INF)
    theirs = sum(1 for d in _distances(arena.grid, n, arena.heads[1 - seat]) if 0 < d < INF)
    return 4 * (mine - theirs) - _free_neighbours(arena.grid, n, *arena.heads[seat])


def _round(arena: Arena, seat: int, depth: int) -> int:
    """Max over my moves, min over their replies (simultaneous moves), `depth` rounds."""
    best = -INF * 4
    for action in ORDER:
        mine = _apply(arena, seat, action)
        if mine is None:
            value = -INF * 2
        else:
            worst = INF * 4
            for reply in ORDER:
                r, c, _ = _next(arena, 1 - seat, reply)
                if (r, c) == arena.heads[seat]:
                    v = -INF  # head-on
                else:
                    theirs = _apply(arena, 1 - seat, reply)
                    if theirs is None:
                        v = INF
                    else:
                        v = _leaf(arena, seat) if depth == 1 else _round(arena, seat, depth - 1)
                        _undo(arena, theirs)
                worst = min(worst, v)
                if worst <= best:
                    break
            value = worst
            _undo(arena, mine)
        best = max(best, value)
    return best


def voronoi2(arena: Arena, seat: int, draw=None, depth: int = 2) -> int:
    """Two rounds of look-ahead for both cycles, scored as `voronoi` scores one round: a player
    that sees cut-offs and walls coming a move earlier. `depth` sets the rounds."""
    best, best_value = STRAIGHT, -INF * 8
    for action in ORDER:
        mine = _apply(arena, seat, action)
        if mine is None:
            value = -INF * 3
        else:
            worst = INF * 4
            for reply in ORDER:
                r, c, _ = _next(arena, 1 - seat, reply)
                if (r, c) == arena.heads[seat]:
                    v = -INF
                else:
                    theirs = _apply(arena, 1 - seat, reply)
                    if theirs is None:
                        v = INF
                    else:
                        v = _round(arena, seat, depth - 1)
                        _undo(arena, theirs)
                worst = min(worst, v)
            value = worst
            _undo(arena, mine)
        if value > best_value:
            best, best_value = action, value
    return best


# ---- players with a fixed habit: what a life against one person looks like -----------------

def hugger(arena: Arena, seat: int, draw=None) -> int:
    """Turns left whenever it can keep room doing so, else straight, else right: it hugs
    walls counter-clockwise. Predictable, and its spiral can be cut off."""
    n = arena.size
    for action in (0, STRAIGHT, 2):
        r, c, _ = _next(arena, seat, action)
        if not arena.free(r, c):
            continue
        arena.grid[r * n + c] = 1
        room = sum(1 for d in _distances(arena.grid, n, (r, c)) if 0 < d < INF)
        arena.grid[r * n + c] = 0
        if room >= 12:
            return action
    return survivor(arena, seat)


def racer(arena: Arena, seat: int, draw=None) -> int:
    """Rides straight for long lanes and turns toward the bigger open side only when blocked
    within three cells: a player who races the opponent along walls."""
    n = arena.size
    h = arena.headings[seat]
    r, c = arena.heads[seat]
    clear = 0
    while clear < 3 and arena.free(r + DR[h] * (clear + 1), c + DC[h] * (clear + 1)):
        clear += 1
    if clear >= 3:
        return STRAIGHT
    return survivor(arena, seat)


HABITS = {"chaser": chaser, "hugger": hugger, "racer": racer}


def voronoi3(arena: Arena, seat: int, draw=None) -> int:
    """Three rounds of look-ahead (with pruning inside the deeper rounds)."""
    return voronoi2(arena, seat, draw, depth=3)
