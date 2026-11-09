"""What a cycle sees. Three candidate senses over the same arena.

`eye` (the brain's sense): the playing field itself, seen from the rider's seat. The frame is
egocentric and turns with the cycle, so "a wall ahead" is the same input whatever the
compass heading, and the relative actions left/straight/right keep one meaning. A sharp
fovea of single cells around the head, and a coarse periphery of pooled blocks that covers
the whole arena at lower resolution, as a retina does. Two channels per receptor: how much
of it is blocked (walls and trails), and the opponent's head.

`board`: the whole arena at full resolution in compass coordinates, with both heads and the
heading. A control: the same information without the rider's frame.

`rays`: eight distances to the nearest obstacle plus the opponent's bearing. A hand-built
control, not the playing field.
"""

from __future__ import annotations

import numpy as np

from .world import DC, DR, Arena

# Fovea: forward -3..+5, sideways -4..+4 (9 x 9 single cells, the head at forward 0).
FOVEA_F = range(-3, 6)
FOVEA_S = range(-4, 5)
# Periphery: 7 x 7 blocks of 5 x 5 cells, centred two blocks ahead of the head's block.
BLOCK = 5
PERIPHERY_F = range(-2, 5)
PERIPHERY_S = range(-3, 4)


def _absolute(arena: Arena, seat: int, forward: int, side: int) -> tuple[int, int]:
    h = arena.headings[seat]
    right = (h + 1) % 4
    r, c = arena.heads[seat]
    return r + forward * DR[h] + side * DR[right], c + forward * DC[h] + side * DC[right]


def eye_size() -> int:
    return 2 * (len(FOVEA_F) * len(FOVEA_S) + len(PERIPHERY_F) * len(PERIPHERY_S))


def eye(arena: Arena, seat: int) -> np.ndarray:
    n = arena.size
    grid = arena.grid
    opponent = arena.heads[1 - seat]
    blocked, theirs = [], []
    for f in reversed(FOVEA_F):  # far rows first, as the rider sees them
        for s in FOVEA_S:
            r, c = _absolute(arena, seat, f, s)
            inside = 0 <= r < n and 0 <= c < n
            blocked.append(1.0 if not inside or grid[r * n + c] else 0.0)
            theirs.append(1.0 if (r, c) == opponent else 0.0)
    half = BLOCK // 2
    for bf in reversed(PERIPHERY_F):
        for bs in PERIPHERY_S:
            count = 0
            seen = 0.0
            for df in range(-half, half + 1):
                for ds in range(-half, half + 1):
                    r, c = _absolute(arena, seat, bf * BLOCK + df, bs * BLOCK + ds)
                    if not (0 <= r < n and 0 <= c < n) or grid[r * n + c]:
                        count += 1
                    if (r, c) == opponent:
                        seen = 1.0
            blocked.append(count / (BLOCK * BLOCK))
            theirs.append(seen)
    return np.array(blocked + theirs)


def board_size(n: int) -> int:
    return 3 * n * n + 4


def board(arena: Arena, seat: int) -> np.ndarray:
    n = arena.size
    blocked = np.array([1.0 if v else 0.0 for v in arena.grid])
    mine = np.zeros(n * n)
    theirs = np.zeros(n * n)
    r, c = arena.heads[seat]
    mine[r * n + c] = 1.0
    r, c = arena.heads[1 - seat]
    theirs[r * n + c] = 1.0
    heading = np.zeros(4)
    heading[arena.headings[seat]] = 1.0
    return np.concatenate([blocked, mine, theirs, heading])


RAY_DIRECTIONS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def rays_size() -> int:
    return len(RAY_DIRECTIONS) + 3


def rays(arena: Arena, seat: int) -> np.ndarray:
    n = arena.size
    out = []
    for f, s in RAY_DIRECTIONS:
        k = 1
        while True:
            r, c = _absolute(arena, seat, f * k, s * k)
            if not (0 <= r < n and 0 <= c < n) or arena.grid[r * n + c]:
                break
            k += 1
        out.append(1.0 / k)
    # The opponent's head in the rider's frame.
    h = arena.headings[seat]
    right = (h + 1) % 4
    dr = arena.heads[1 - seat][0] - arena.heads[seat][0]
    dc = arena.heads[1 - seat][1] - arena.heads[seat][1]
    forward = dr * DR[h] + dc * DC[h]
    side = dr * DR[right] + dc * DC[right]
    out += [forward / n, side / n, 1.0 / (1 + abs(forward) + abs(side))]
    return np.array(out)


SENSES = {"eye": (eye, lambda n: eye_size()), "board": (board, board_size), "rays": (rays, lambda n: rays_size())}


# ---- the second eye: what a rider needs for strategy ------------------------------------------
# A sense is a dict, part of a brain's genome and its meta:
#   fovea: odd side of the sharp square around the head (a third of it behind the head)
#   block, blocks: the periphery, blocks x blocks pooled squares of block x block cells
#   split: own and opponent trails on separate channels (else one "blocked" channel)
#   heading: the opponent's next cell marked, and its heading relative to the rider's (4)
EYE2_DEFAULT = {"fovea": 9, "block": 5, "blocks": 9, "split": True, "heading": True}


def _fovea_rows(side: int):
    behind = side // 3
    return range(side - 1 - behind, -behind - 1, -1), range(-(side // 2), side // 2 + 1)


def eye2_size(sense: dict) -> int:
    f, p = sense["fovea"] ** 2, sense["blocks"] ** 2
    fovea_channels = 3 if sense["split"] else 2  # mine-or-blocked, (theirs), their head
    periphery_channels = 3 if sense["split"] else 2
    fovea_channels += 1 if sense["heading"] else 0
    return fovea_channels * f + periphery_channels * p + (4 if sense["heading"] else 0)


def eye2(arena: Arena, seat: int, sense: dict) -> np.ndarray:
    n = arena.size
    grid = arena.grid
    mine_value, theirs_value = 1 + seat, 2 - seat
    other = 1 - seat
    head = arena.heads[other]
    h = arena.headings[other]
    ahead = (head[0] + DR[h], head[1] + DC[h])
    split, heading = sense["split"], sense["heading"]
    forward, sideways = _fovea_rows(sense["fovea"])
    a, b, c, d = [], [], [], []  # mine-or-blocked, theirs, their head, their next cell
    for f in forward:
        for s in sideways:
            r, col = _absolute(arena, seat, f, s)
            inside = 0 <= r < n and 0 <= col < n
            v = grid[r * n + col] if inside else -1
            if split:
                a.append(1.0 if (not inside or v == mine_value) else 0.0)
                b.append(1.0 if v == theirs_value else 0.0)
            else:
                a.append(1.0 if (not inside or v) else 0.0)
            c.append(1.0 if (r, col) == head else 0.0)
            d.append(1.0 if (r, col) == ahead else 0.0)
    pa, pb, pc = [], [], []
    size, blocks = sense["block"], sense["blocks"]
    half = size // 2
    for bf in range(blocks // 2, -(blocks // 2) - 1, -1):
        for bs in range(-(blocks // 2), blocks // 2 + 1):
            mine = theirs = 0
            seen = 0.0
            for df in range(-half, half + 1):
                for ds in range(-half, half + 1):
                    r, col = _absolute(arena, seat, bf * size + df, bs * size + ds)
                    inside = 0 <= r < n and 0 <= col < n
                    v = grid[r * n + col] if inside else -1
                    if split:
                        mine += (not inside) or v == mine_value
                        theirs += v == theirs_value
                    else:
                        mine += (not inside) or v != 0
                    if (r, col) == head:
                        seen = 1.0
            pa.append(mine / (size * size))
            if split:
                pb.append(theirs / (size * size))
            pc.append(seen)
    parts = [a] + ([b] if split else []) + [c] + ([d] if heading else []) + [pa] + ([pb] if split else []) + [pc]
    out = [v for part in parts for v in part]
    if heading:
        relative = (arena.headings[other] - arena.headings[seat]) % 4  # same, right, opposite, left
        out += [1.0 if relative == k else 0.0 for k in range(4)]
    return np.array(out)


def layout2(sense: dict) -> dict:
    """Where each channel sits in the input vector, for the page's retina view."""
    f, p = sense["fovea"] ** 2, sense["blocks"] ** 2
    names = ["fovea:" + ("mine" if sense["split"] else "blocked")] + (["fovea:theirs"] if sense["split"] else []) \
        + ["fovea:head"] + (["fovea:next"] if sense["heading"] else []) \
        + ["periphery:" + ("mine" if sense["split"] else "blocked")] + (["periphery:theirs"] if sense["split"] else []) \
        + ["periphery:head"]
    out, start = [], 0
    for name in names:
        width = f if name.startswith("fovea") else p
        side = sense["fovea"] if name.startswith("fovea") else sense["blocks"]
        out.append({"name": name, "start": start, "side": side})
        start += width
    if sense["heading"]:
        out.append({"name": "heading", "start": start, "count": 4, "labels": ["same", "right", "opposite", "left"]})
    return {"channels": out, "inputs": eye2_size(sense), **sense}


def make_sense(sense):
    """A callable (arena, seat) -> vector and its size, for a sense name or an eye2 dict."""
    if isinstance(sense, dict):
        return (lambda arena, seat: eye2(arena, seat, sense)), eye2_size(sense)
    fn, size = SENSES[sense]
    return fn, size(24)
