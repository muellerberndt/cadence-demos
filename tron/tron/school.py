"""Raising a brain and measuring it.

Watching: the Voronoi bot rides seat 0 against an opponent from the pool; the brain sees that
seat through its sense, answers freely (a greedy settle, so no unexecuted action collects
eligibility) and takes the bot's move as the lesson for that moment.

Weaning in turns: the brain rides. In corrected stretches the bot's move is executed and taught
as above; in stretches alone the brain's own sampled move is executed and `step` learns from the
world's outcome (crash -1, opponent's crash +1, double crash -0.5). Mochi's finding: correction
on every moment gives a brain that never learns to ride alone.

Each batch row is one continuing stream that lives through game after game.

Assays are frozen: a saved copy plays greedily from held-out seeds. The living assay keeps one
stream in `Brain.live`, the page's loop, against players with habits.
"""

from __future__ import annotations

import os
import tempfile
import time

import numpy as np

from . import bots
REWARD = {"win": 1.0, "loss": -1.0, "draw": -0.5}  # the world's pay: win, loss, both crash
from .senses import make_sense
from .world import STRAIGHT, Arena, mulberry32


def noisy_voronoi(eps: float):
    def play(arena, seat, draw):
        if draw() < eps:
            return bots.safe(arena, seat, draw)
        return bots.voronoi(arena, seat)
    return play


POOL = {
    "voronoi": lambda a, s, d: bots.voronoi(a, s),
    "voronoi20": noisy_voronoi(0.2),
    "voronoi40": noisy_voronoi(0.4),
    "survivor": lambda a, s, d: bots.survivor(a, s),
    "chaser": lambda a, s, d: bots.chaser(a, s),
    "safe": bots.safe,
    "voronoi2": bots.voronoi2,
    "voronoi3": bots.voronoi3,
    "hugger": bots.hugger,
    "racer": bots.racer,
}
SCHOOL_POOL = ("voronoi20", "survivor", "safe", "voronoi", "chaser", "voronoi40")


class Stream:
    """One row: a game in progress against an opponent from the pool."""

    def __init__(self, size: int, rng: np.random.Generator, seed: int, pool=SCHOOL_POOL):
        self.size, self.rng, self.pool, self.count = size, rng, pool, seed * 1_000_003

    def next(self):
        self.count += 1
        self.arena = Arena(self.size, seed=self.count & 0xFFFFFFFF)
        self.opponent = self.pool[int(self.rng.integers(len(self.pool)))]
        self.draw = mulberry32(self.count & 0xFFFFFFFF)
        return self


def outcome(arena: Arena) -> tuple[float, bool]:
    if not arena.over:
        return 0.0, False
    if arena.winner == 0:
        return REWARD["win"], True
    if arena.winner == 1:
        return REWARD["loss"], True
    return REWARD["draw"], True


def _lesson(brain, x, labels):
    """One `Brain.lesson` on the rows."""
    brain.lesson(x, labels)


def watch_corpus(brain, sense, games, *, rows=8, lessons=1000, seed=0):
    """Watch the corpus: row i plays games seed*rows+i, seed*rows+i+rows, ... (wrapping).
    Returns (agreement on all moments, agreement where the teacher turned)."""
    from .corpus import Replay

    see = make_sense(sense)[0]
    streams = [Replay(games, (seed * rows + i) % len(games), rows) for i in range(rows)]
    hits = turns = turn_hits = 0
    for _ in range(lessons):
        x = np.stack([see(s.arena, 0) for s in streams])
        teacher = np.array([s.teacher_move() for s in streams])
        own = brain.act(x, greedy=True)
        _lesson(brain, x, teacher)
        hits += int(np.sum(own == teacher))
        mask = teacher != STRAIGHT
        turns += int(mask.sum())
        turn_hits += int(np.sum((own == teacher) & mask))
        for s in streams:
            s.advance()
    return hits / (lessons * rows), turn_hits / max(turns, 1)


def fidelity(brain, sense, games, *, limit=60):
    """A frozen copy rides along held-out teacher games (one stream, greedy, its working trace
    on): agreement with the teacher on all moments, on the teacher's turns, and on moments
    where a cut-off or a pocket was on offer."""
    from . import behaviour
    from .corpus import Replay

    see = make_sense(sense)[0]
    twin = frozen_copy(brain)
    counts = {"all": [0, 0], "turns": [0, 0], "cutoff": [0, 0], "pocket": [0, 0]}
    for g in games[:limit]:
        twin.reset()
        replay = Replay([g], 0, 1)
        for t in range(len(g["moves"])):
            teacher = replay.teacher_move()
            own = int(twin.act(see(replay.arena, 0)[None, :], greedy=True)[0])
            hit = int(own == teacher)
            counts["all"][0] += hit
            counts["all"][1] += 1
            if teacher != STRAIGHT:
                counts["turns"][0] += hit
                counts["turns"][1] += 1
            offered = behaviour.moment(replay.arena, teacher)
            for key in ("cutoff", "pocket"):
                if key in offered:
                    counts[key][0] += hit
                    counts[key][1] += 1
            if t == len(g["moves"]) - 1:
                break
            replay.arena.step(g["moves"][t])
            replay.t += 1
    return {k: {"agree": (h / n if n else None), "moments": n} for k, (h, n) in counts.items()}


def watch(brain, sense: str, *, size=24, rows=8, lessons=1000, seed=0):
    """Returns (agreement on all moments, agreement where the bot turned)."""
    see = make_sense(sense)[0]
    rng = np.random.default_rng(seed)
    streams = [Stream(size, rng, seed * 64 + i).next() for i in range(rows)]
    hits = turns = turn_hits = 0
    for _ in range(lessons):
        x = np.stack([see(s.arena, 0) for s in streams])
        teacher = np.array([bots.voronoi(s.arena, 0) for s in streams])
        own = brain.act(x, greedy=True)
        _lesson(brain, x, teacher)
        hits += int(np.sum(own == teacher))
        mask = teacher != STRAIGHT
        turns += int(mask.sum())
        turn_hits += int(np.sum((own == teacher) & mask))
        for i, s in enumerate(streams):
            s.arena.step((int(teacher[i]), POOL[s.opponent](s.arena, 1, s.draw)))
            if s.arena.over:
                s.next()
    return hits / (lessons * rows), turn_hits / max(turns, 1)


def wean(brain, sense: str, *, size=24, rows=8, moments=1000, stretch=50, seed=0):
    """Alternate corrected and alone stretches. Returns the reward per game alone."""
    see = make_sense(sense)[0]
    rng = np.random.default_rng(seed + 7)
    streams = [Stream(size, rng, seed * 64 + 32 + i).next() for i in range(rows)]
    brain.reset()
    pending = False
    reward = np.zeros(rows)
    done = np.zeros(rows, bool)
    alone_games = alone_reward = 0.0
    for k in range(moments):
        corrected = (k // stretch) % 2 == 0
        x = np.stack([see(s.arena, 0) for s in streams])
        if corrected:
            if pending:
                # The last move alone gets its outcome; the action step issues is replaced
                # by a greedy act, which keeps nothing pending.
                brain.step(x, reward=reward, done=done)
                pending = False
            teacher = np.array([bots.voronoi(s.arena, 0) for s in streams])
            brain.act(x, greedy=True)
            _lesson(brain, x, teacher)
            moves = teacher
        else:
            if pending:
                moves = brain.step(x, reward=reward, done=done)
            else:
                moves = brain.step(x)
            pending = True
        reward = np.zeros(rows)
        done = np.zeros(rows, bool)
        for i, s in enumerate(streams):
            s.arena.step((int(moves[i]), POOL[s.opponent](s.arena, 1, s.draw)))
            if s.arena.over:
                r, _ = outcome(s.arena)
                reward[i], done[i] = r, True
                if not corrected:
                    alone_games += 1
                    alone_reward += r
                s.next()
    if pending:
        x = np.stack([see(s.arena, 0) for s in streams])
        brain.step(x, reward=reward, done=done)
        brain.act(x, greedy=True)  # clears the pending sample: nothing awaits an outcome
    brain.reset()
    return alone_reward / max(alone_games, 1)


def frozen_copy(brain):
    from cadence import Brain

    with tempfile.TemporaryDirectory() as folder:
        twin = Brain.load(brain.save(os.path.join(folder, "b.npz")))
    twin.reset()
    return twin


def brain_policy(brain, sense: str):
    see = make_sense(sense)[0]
    timing = {"cpu": 0.0, "moves": 0}

    def policy(arena, seat):
        t = time.process_time()
        a = int(brain.act(see(arena, seat)[None, :], greedy=True)[0])
        timing["cpu"] += time.process_time() - t
        timing["moves"] += 1
        return a
    policy.timing = timing
    return policy


def play(policy, opponent: str, *, size=24, games=16, seed=50_000):
    w = l = d = ticks = 0
    for g in range(games):
        arena = Arena(size, seed=seed + g)
        draw = mulberry32(seed + g)
        while not arena.over:
            arena.step((policy(arena, 0), POOL[opponent](arena, 1, draw)))
        ticks += arena.tick
        if arena.winner == 0:
            w += 1
        elif arena.winner == 1:
            l += 1
        else:
            d += 1
    return {"wins": w, "losses": l, "draws": d, "score": (w + 0.5 * d) / games, "ticks": ticks / games}


ASSAY = {"voronoi": 2.0, "voronoi20": 1.0, "survivor": 1.0, "chaser": 1.0, "safe": 0.5}
# Round 2 ladder (ROUND2_PROTOCOL.md): both look-ahead bots weigh 2.
LADDER2 = {"voronoi2": 2.0, "voronoi": 2.0, "voronoi20": 1.0, "survivor": 1.0, "chaser": 1.0,
           "hugger": 1.0, "racer": 1.0, "safe": 0.5}


def assay(brain, sense: str, *, size=24, games=16, seed=50_000, ladder=None):
    ladder = ladder or ASSAY
    twin = frozen_copy(brain)
    pol = brain_policy(twin, sense)
    out = {opp: play(pol, opp, size=size, games=games, seed=seed + 1000 * i) for i, opp in enumerate(ladder)}
    out["strength"] = sum(ladder[o] * out[o]["score"] for o in ladder) / sum(ladder.values())
    out["act_ms"] = 1e3 * pol.timing["cpu"] / max(pol.timing["moves"], 1)
    return out


def live(brain, sense: str, *, size=24, games=40, opponents=("chaser", "voronoi40", "voronoi20"), seed=70_000):
    """One stream in `Brain.live` for `games` games, as the page runs it. Returns per-game results."""
    see = make_sense(sense)[0]
    brain.reset()
    results = []
    carry = None
    calm = moments = 0
    t = time.process_time()
    for g in range(games):
        arena = Arena(size, seed=seed + g)
        draw = mulberry32(seed + g)
        opponent = opponents[g % len(opponents)]
        x = see(arena, 0)[None, :]
        move = int((brain.live(x) if carry is None else brain.live(x, reward=np.array([carry]), done=np.array([True])))[0])
        while True:
            arena.step((move, POOL[opponent](arena, 1, draw)))
            if arena.over:
                break
            move = int(brain.live(see(arena, 0)[None, :], reward=np.array([0.0]), done=np.array([False]))[0])
            moments += 1
            calm += int((brain.last_arousal or {}).get("mode") == "routine")
        carry, _ = outcome(arena)
        results.append({"opponent": opponent, "reward": carry, "ticks": arena.tick})
    # Deliver the last outcome so nothing is left pending.
    brain.live(see(Arena(size, seed=seed + games), 0)[None, :], reward=np.array([carry]), done=np.array([True]))
    brain.act(see(Arena(size, seed=seed + games), 0)[None, :], greedy=True)
    brain.reset()
    return {"games": results, "calm_share": calm / max(moments, 1), "cpu_s": time.process_time() - t}
