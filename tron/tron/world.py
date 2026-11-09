"""The arena: two light cycles on a square grid, moving at once, one cell per tick.

Everything here is plain integers so that the JavaScript twin (web/js/world.js) plays the
same game move for move. A cycle dies when its next cell is outside the arena or already
holds a trail; two cycles entering the same cell both die. The world supplies the problem
and the outcome, never an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Headings: 0 north (row - 1), 1 east, 2 south, 3 west. Actions are relative to the heading.
DR = (-1, 0, 1, 0)
DC = (0, 1, 0, -1)
LEFT, STRAIGHT, RIGHT = 0, 1, 2
ACTIONS = 3


def turn(heading: int, action: int) -> int:
    return (heading + action - 1) % 4


def mulberry32(seed: int):
    """A 32-bit generator with an exact JavaScript twin (web/js/world.js)."""
    state = seed & 0xFFFFFFFF

    def draw() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return draw


@dataclass
class Arena:
    size: int = 24
    seed: int = 0
    grid: list[int] = field(default_factory=list)  # 0 empty, 1 + seat for a trail
    heads: list[tuple[int, int]] = field(default_factory=list)
    headings: list[int] = field(default_factory=list)
    alive: list[bool] = field(default_factory=list)
    tick: int = 0
    over: bool = False
    winner: int | None = None  # 0, 1, or None for a draw / not over

    def __post_init__(self) -> None:
        if not self.grid:
            self.reset(self.seed)

    def reset(self, seed: int) -> None:
        """Point-symmetric starts drawn from the seed: the two seats face the same problem."""
        n = self.size
        draw = mulberry32(seed)
        self.seed = seed
        row = n // 4 + int(draw() * (n // 2))
        col = 2 + int(draw() * (n // 4))
        heading = int(draw() * 4)
        if heading == 3:  # never start facing the near wall
            heading = 1
        self.grid = [0] * (n * n)
        self.heads = [(row, col), (n - 1 - row, n - 1 - col)]
        self.headings = [heading, (heading + 2) % 4]
        for seat, (r, c) in enumerate(self.heads):
            self.grid[r * n + c] = 1 + seat
        self.alive = [True, True]
        self.tick = 0
        self.over = False
        self.winner = None

    def inside(self, r: int, c: int) -> bool:
        return 0 <= r < self.size and 0 <= c < self.size

    def free(self, r: int, c: int) -> bool:
        return self.inside(r, c) and self.grid[r * self.size + c] == 0

    def step(self, actions: tuple[int, int] | list[int]) -> tuple[bool, bool]:
        """Both cycles move at once. Returns who died this tick."""
        if self.over:
            raise RuntimeError("the round is over; reset the arena")
        targets = []
        for seat in (0, 1):
            h = turn(self.headings[seat], int(actions[seat]))
            self.headings[seat] = h
            r, c = self.heads[seat]
            targets.append((r + DR[h], c + DC[h]))
        died = [not self.free(*targets[seat]) for seat in (0, 1)]
        if targets[0] == targets[1]:
            died = [True, True]
        for seat in (0, 1):
            if not died[seat]:
                r, c = targets[seat]
                self.grid[r * self.size + c] = 1 + seat
                self.heads[seat] = targets[seat]
        self.tick += 1
        self.alive = [not d for d in died]
        if died[0] or died[1] or self.tick >= self.size * self.size:
            self.over = True
            if died[0] != died[1]:
                self.winner = 1 if died[0] else 0
        return died[0], died[1]
