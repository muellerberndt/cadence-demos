"""Minimal WAD reader: E1M1 THINGS (spawns) for teacher waypoint design."""
import math
import struct, sys

TYPES = {1: "PlayerStart", 3004: "Zombieman", 9: "ShotgunGuy", 3001: "Imp",
         2035: "Barrel", 2018: "GreenArmor", 2001: "Shotgun"}

def things(path="wads/doom1.wad", map_name="E1M1"):
    data = open(path, "rb").read()
    ident, n, dir_ofs = struct.unpack_from("<4sII", data, 0)
    lumps = []
    for i in range(n):
        ofs, size, raw = struct.unpack_from("<II8s", data, dir_ofs + 16 * i)
        lumps.append((raw.rstrip(b"\0").decode(), ofs, size))
    idx = next(i for i, (name, _, _) in enumerate(lumps) if name == map_name)
    name, ofs, size = next(l for l in lumps[idx:idx + 11] if l[0] == "THINGS")
    out = []
    for j in range(size // 10):
        x, y, ang, typ, flags = struct.unpack_from("<hhhhh", data, ofs + 10 * j)
        out.append({"x": x, "y": y, "angle": ang, "type": typ, "flags": flags})
    return out

if __name__ == "__main__":
    rows = things()
    for t in rows:
        label = TYPES.get(t["type"])
        if label and (t["flags"] & 1 or label == "PlayerStart"):  # easy-skill set
            print(f"{label:12s} x={t['x']:6d} y={t['y']:6d} angle={t['angle']}")


# ---- walkable-grid routing (teacher-side, privileged) ----

CELL = 16  # map units per grid cell; player radius is 16

def _lump(data, lumps, start, name):
    return next(l for l in lumps[start:start + 11] if l[0] == name)

def geometry(path="wads/doom1.wad", map_name="E1M1"):
    """Return (walls, steps): hard wall segments, and directional step
    segments ((a, b), allowed_crossing_unit_direction) for floor rises above
    stair height. Drops are passable in the allowed direction only."""
    data = open(path, "rb").read()
    _, n, dir_ofs = struct.unpack_from("<4sII", data, 0)
    lumps = []
    for i in range(n):
        ofs, size, raw = struct.unpack_from("<II8s", data, dir_ofs + 16 * i)
        lumps.append((raw.rstrip(b"\0").decode(), ofs, size))
    idx = next(i for i, (nm, _, _) in enumerate(lumps) if nm == map_name)
    _, vofs, vsize = _lump(data, lumps, idx, "VERTEXES")
    verts = [struct.unpack_from("<hh", data, vofs + 4 * j) for j in range(vsize // 4)]
    _, sofs, ssize = _lump(data, lumps, idx, "SIDEDEFS")
    side_sector = [struct.unpack_from("<h", data, sofs + 30 * j + 28)[0]
                   for j in range(ssize // 30)]
    _, cofs, csize = _lump(data, lumps, idx, "SECTORS")
    floor = [struct.unpack_from("<h", data, cofs + 26 * j)[0]
             for j in range(csize // 26)]
    _, lofs, lsize = _lump(data, lumps, idx, "LINEDEFS")
    walls, steps = [], []
    for j in range(lsize // 14):
        v1, v2, flags, special, _, front, back = struct.unpack_from(
            "<HHHhhhh", data, lofs + 14 * j)
        seg = (verts[v1], verts[v2])
        if back == -1 or bool(flags & 0x01):
            walls.append(seg)
            continue
        rise = floor[side_sector[back]] - floor[side_sector[front]]
        if abs(rise) > 24 and special == 0:
            (ax, ay), (bx, by) = seg
            length = math.hypot(bx - ax, by - ay) or 1.0
            # Front is right of v1->v2; the left normal points front->back.
            to_back = ((by - ay) / length, -(bx - ax) / length)
            to_back = (-to_back[0], -to_back[1])
            # Allowed crossing goes from the high floor to the low floor.
            steps.append((seg, to_back if rise < 0 else
                          (-to_back[0], -to_back[1])))
        # Small steps stay walkable and add no segment.
    return walls, steps

def walk_grid(walls, steps=()):
    import numpy as np
    segs = list(walls) + [seg for seg, _ in steps]
    xs = [x for seg in segs for x, _ in seg]
    ys = [y for seg in segs for _, y in seg]
    x0, y0 = min(xs) - CELL, min(ys) - CELL
    w = (max(xs) - x0) // CELL + 2
    h = (max(ys) - y0) // CELL + 2
    blocked = np.zeros((h, w), bool)

    def cells(seg):
        (ax, ay), (bx, by) = seg
        count = max(1, int(max(abs(bx - ax), abs(by - ay)) // (CELL // 2)))
        for t in range(count + 1):
            x = ax + (bx - ax) * t / count
            y = ay + (by - ay) * t / count
            yield int((y - y0) // CELL), int((x - x0) // CELL)

    for seg in walls:
        for cy, cx in cells(seg):
            blocked[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2] = True  # inflate
    one_way = {}
    for seg, direction in steps:
        for cy, cx in cells(seg):
            one_way[(cy, cx)] = direction
    return blocked, one_way, (x0, y0)

def astar(blocked, one_way, origin, start_xy, goal_xy):
    import heapq
    x0, y0 = origin
    def cell(p):
        return (int((p[1] - y0) // CELL), int((p[0] - x0) // CELL))
    start, goal = cell(start_xy), cell(goal_xy)
    h, w = blocked.shape
    def free(c):
        return 0 <= c[0] < h and 0 <= c[1] < w and not blocked[c]
    def passable(cur, nxt, dy, dx):
        # A one-way (drop) cell may be entered/left only along its direction.
        for c in (cur, nxt):
            direction = one_way.get(c)
            if direction is not None and dx * direction[0] - dy * direction[1] <= 0:
                return False
        return True
    def snap(c, name):
        if free(c):
            return c
        best, best_d = None, 1e18
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                cand = (c[0] + dy, c[1] + dx)
                d = dy * dy + dx * dx
                if d < best_d and free(cand):
                    best, best_d = cand, d
        if best is None:
            raise ValueError(f"{name} cell blocked at {c}")
        return best
    start, goal = snap(start, "start"), snap(goal, "goal")
    heap = [(0.0, start)]
    came, cost = {start: None}, {start: 0.0}
    moves = [(dy, dx, (dy * dy + dx * dx) ** 0.5)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    while heap:
        _, cur = heapq.heappop(heap)
        if cur == goal:
            break
        for dy, dx, step in moves:
            nxt = (cur[0] + dy, cur[1] + dx)
            if not free(nxt) or not passable(cur, nxt, dy, dx):
                continue
            c = cost[cur] + step
            if c < cost.get(nxt, 1e18):
                cost[nxt] = c
                came[nxt] = cur
                est = ((nxt[0] - goal[0]) ** 2 + (nxt[1] - goal[1]) ** 2) ** 0.5
                heapq.heappush(heap, (c + est, nxt))
    if goal not in came:
        raise ValueError("no path")
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    path.reverse()
    def visible(a, b):
        count = max(abs(a[0] - b[0]), abs(a[1] - b[1])) * 2
        for t in range(count + 1):
            y = a[0] + (b[0] - a[0]) * t / max(1, count)
            x = a[1] + (b[1] - a[1]) * t / max(1, count)
            c = (int(round(y)), int(round(x)))
            if blocked[c] or c in one_way:  # never smooth across a drop
                return False
        return True
    corners, anchor = [path[0]], 0
    for i in range(1, len(path)):
        if not visible(path[anchor], path[i]):
            corners.append(path[i - 1])
            anchor = i - 1
    corners.append(path[-1])
    return [(x0 + c[1] * CELL + CELL // 2, y0 + c[0] * CELL + CELL // 2)
            for c in corners]

def build_route(stops, path="wads/doom1.wad"):
    walls, steps = geometry(path)
    blocked, one_way, origin = walk_grid(walls, steps)
    route = []
    for a, b in zip(stops, stops[1:]):
        leg = astar(blocked, one_way, origin, a, b)
        route.extend(leg[1:])
    return route


# ---- full sector map: per-cell floor height and damage flag ----

DAMAGE_SPECIALS = {4, 5, 7, 11, 16}  # vanilla damaging floor types


def sector_map(path="wads/doom1.wad", map_name="E1M1"):
    """Rasterize sectors onto the walk grid: floor height and damage per cell.

    Returns (walls, cell_floor, cell_damage, origin, shape). Cells outside
    every sector have floor NO_SECTOR.
    """
    import numpy as np
    data = open(path, "rb").read()
    _, n, dir_ofs = struct.unpack_from("<4sII", data, 0)
    lumps = []
    for i in range(n):
        ofs, size, raw = struct.unpack_from("<II8s", data, dir_ofs + 16 * i)
        lumps.append((raw.rstrip(b"\0").decode(), ofs, size))
    idx = next(i for i, (nm, _, _) in enumerate(lumps) if nm == map_name)
    _, vofs, vsize = _lump(data, lumps, idx, "VERTEXES")
    verts = [struct.unpack_from("<hh", data, vofs + 4 * j) for j in range(vsize // 4)]
    _, sofs, ssize = _lump(data, lumps, idx, "SIDEDEFS")
    side_sector = [struct.unpack_from("<h", data, sofs + 30 * j + 28)[0]
                   for j in range(ssize // 30)]
    _, cofs, csize = _lump(data, lumps, idx, "SECTORS")
    n_sectors = csize // 26
    floor = [struct.unpack_from("<h", data, cofs + 26 * j)[0] for j in range(n_sectors)]
    special = [struct.unpack_from("<h", data, cofs + 26 * j + 22)[0]
               for j in range(n_sectors)]
    _, lofs, lsize = _lump(data, lumps, idx, "LINEDEFS")
    walls, boundaries = [], [[] for _ in range(n_sectors)]
    for j in range(lsize // 14):
        v1, v2, flags, _special, _, front, back = struct.unpack_from(
            "<HHHhhhh", data, lofs + 14 * j)
        a, b = verts[v1], verts[v2]
        fs = side_sector[front] if front != -1 else -1
        bs = side_sector[back] if back != -1 else -1
        if back == -1 or bool(flags & 0x01):
            walls.append((a, b))
        # A linedef bounds a sector only when that sector is on exactly one
        # side; self-referencing lines are interior decoration, not boundary.
        if fs != bs:
            if fs >= 0:
                boundaries[fs].append((a, b))
            if bs >= 0:
                boundaries[bs].append((a, b))

    xs = [x for seg in walls for x, _ in seg] or [0]
    ys = [y for seg in walls for _, y in seg] or [0]
    all_x = [x for segs in boundaries for seg in segs for x, _ in seg] + xs
    all_y = [y for segs in boundaries for seg in segs for _, y in seg] + ys
    x0, y0 = min(all_x) - CELL, min(all_y) - CELL
    w = (max(all_x) - x0) // CELL + 2
    h = (max(all_y) - y0) // CELL + 2

    cx = x0 + np.arange(w) * CELL + CELL / 2.0
    cy = y0 + np.arange(h) * CELL + CELL / 2.0
    gx = np.broadcast_to(cx, (h, w))
    gy = np.broadcast_to(cy[:, None], (h, w))
    NO_SECTOR = -32768
    cell_floor = np.full((h, w), NO_SECTOR, np.int32)
    cell_damage = np.zeros((h, w), bool)
    order = sorted(range(n_sectors), key=lambda s: -len(boundaries[s]))
    for s in order:
        segs = boundaries[s]
        if not segs:
            continue
        inside = np.zeros((h, w), bool)
        for (ax, ay), (bx, by) in segs:
            if ay == by:
                continue
            cond = (ay > gy) != (by > gy)
            with np.errstate(divide="ignore", invalid="ignore"):
                xat = ax + (gy - ay) * (bx - ax) / (by - ay)
            inside ^= cond & (gx < xat)
        cell_floor[inside] = floor[s]
        cell_damage[inside] = special[s] in DAMAGE_SPECIALS
    return walls, cell_floor, cell_damage, (x0, y0), (h, w)


def route_grid(path="wads/doom1.wad", map_name="E1M1"):
    """Blocked walls + floor/damage per cell, ready for climb-aware A*."""
    import numpy as np
    walls, cell_floor, cell_damage, origin, (h, w) = sector_map(path, map_name)
    x0, y0 = origin
    blocked = np.zeros((h, w), bool)
    margin = np.zeros((h, w), bool)
    for (ax, ay), (bx, by) in walls:
        count = max(1, int(max(abs(bx - ax), abs(by - ay)) // (CELL // 2)))
        for t in range(count + 1):
            x = ax + (bx - ax) * t / count
            y = ay + (by - ay) * t / count
            ccx, ccy = int((x - x0) // CELL), int((y - y0) // CELL)
            blocked[ccy, ccx] = True
            # Wall clearance is expensive, not forbidden: one-cell-wide
            # stairways must stay routable.
            margin[max(0, ccy - 1):ccy + 2, max(0, ccx - 1):ccx + 2] = True
    # Thin sectors (stair treads, door tracks) can miss every cell center.
    # Propagate floors into unfilled cells from filled neighbors first, then
    # block whatever genuinely lies outside the map.
    for _ in range(3):
        holes = cell_floor == -32768
        if not holes.any():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            shifted = np.roll(cell_floor, (dy, dx), (0, 1))
            take = holes & (shifted != -32768)
            cell_floor[take] = shifted[take]
            holes &= ~take
    blocked |= cell_floor == -32768
    return blocked, cell_floor, cell_damage, margin, origin


def astar_height(blocked, cell_floor, cell_damage, margin, origin, start_xy,
                 goal_xy, climb=24, damage_cost=60.0, margin_cost=6.0):
    import heapq
    x0, y0 = origin
    def cell(p):
        return (int((p[1] - y0) // CELL), int((p[0] - x0) // CELL))
    h, w = blocked.shape
    def free(c):
        return 0 <= c[0] < h and 0 <= c[1] < w and not blocked[c]
    def snap(c, name):
        if free(c):
            return c
        best, best_d = None, 1e18
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                cand = (c[0] + dy, c[1] + dx)
                d = dy * dy + dx * dx
                if d < best_d and free(cand):
                    best, best_d = cand, d
        if best is None:
            raise ValueError(f"{name} cell blocked at {c}")
        return best
    start, goal = snap(cell(start_xy), "start"), snap(cell(goal_xy), "goal")
    moves = [(dy, dx, (dy * dy + dx * dx) ** 0.5)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    heap = [(0.0, start)]
    came, cost = {start: None}, {start: 0.0}
    while heap:
        _, cur = heapq.heappop(heap)
        if cur == goal:
            break
        for dy, dx, step in moves:
            nxt = (cur[0] + dy, cur[1] + dx)
            if not free(nxt):
                continue
            if cell_floor[nxt] - cell_floor[cur] > climb:
                continue
            weight = damage_cost if cell_damage[nxt] else (
                margin_cost if margin[nxt] else 1.0)
            c = cost[cur] + step * weight
            if c < cost.get(nxt, 1e18):
                cost[nxt] = c
                came[nxt] = cur
                est = ((nxt[0] - goal[0]) ** 2 + (nxt[1] - goal[1]) ** 2) ** 0.5
                heapq.heappush(heap, (c + est, nxt))
    if goal not in came:
        raise ValueError("no path")
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    path.reverse()
    def crossable(a, b):
        count = max(abs(a[0] - b[0]), abs(a[1] - b[1])) * 2
        prev_floor = cell_floor[a]
        for t in range(count + 1):
            y = a[0] + (b[0] - a[0]) * t / max(1, count)
            x = a[1] + (b[1] - a[1]) * t / max(1, count)
            c = (int(round(y)), int(round(x)))
            if blocked[c] or cell_damage[c]:
                return False
            if cell_floor[c] - prev_floor > climb:
                return False
            prev_floor = cell_floor[c]
        return True
    corners, anchor = [path[0]], 0
    for i in range(1, len(path)):
        if not crossable(path[anchor], path[i]):
            corners.append(path[i - 1])
            anchor = i - 1
    corners.append(path[-1])
    return [(x0 + c[1] * CELL + CELL // 2, y0 + c[0] * CELL + CELL // 2)
            for c in corners]


def build_route_v2(stops, path="wads/doom1.wad"):
    blocked, cell_floor, cell_damage, margin, origin = route_grid(path)
    route = []
    for a, b in zip(stops, stops[1:]):
        route.extend(astar_height(blocked, cell_floor, cell_damage, margin,
                                  origin, a, b)[1:])
    return route


MONSTER_TYPES = {3004, 9, 3001, 3002, 58}  # zombie, sergeant, imp, demon, spectre


def auto_stops(map_name, path="wads/doom1.wad", limit=8, rng=None):
    """Spawn plus easy-flag monster positions, nearest-first; optionally
    shuffled (keeping spawn first) for route diversity across episodes."""
    rows = things(path, map_name)
    spawn = next((t["x"], t["y"]) for t in rows if t["type"] == 1)
    monsters = [(t["x"], t["y"]) for t in rows
                if t["type"] in MONSTER_TYPES and t["flags"] & 1]
    monsters.sort(key=lambda p: (p[0] - spawn[0]) ** 2 + (p[1] - spawn[1]) ** 2)
    monsters = monsters[:limit]
    if rng is not None:
        rng.shuffle(monsters)
    return [spawn] + monsters + [spawn]


_GRIDS = {}


def build_route_v3(map_name, path="wads/doom1.wad", rng=None):
    """Auto route for any map; unreachable legs are skipped, not fatal."""
    if map_name not in _GRIDS:
        _GRIDS[map_name] = route_grid(path, map_name)
    blocked, floors, damage, margin, origin = _GRIDS[map_name]
    route = []
    stops = auto_stops(map_name, path, rng=rng)
    position = stops[0]
    for target in stops[1:]:
        try:
            leg = astar_height(blocked, floors, damage, margin, origin,
                               position, target)
        except ValueError:
            continue
        route.extend(leg[1:])
        position = target
    if not route:
        raise ValueError(f"no routable stops on {map_name}")
    return route
