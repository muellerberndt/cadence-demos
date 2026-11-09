"""A large, full-field brain on cadence-net 0.95.2, bred by a genetic search.

A genome names the brain (layout, sense, apical share, teaching point and its rate, trace
amplitude and decay, lateral weight, temperature, sensory scale) and its short school
(corpus lessons, rows per lesson, DAgger games). One evaluation raises one brain on one core:

1. watching: lessons from the `voronoi3` corpus, replayed through the full-field sense;
2. DAgger: the brain rides its own games against the school pool; `voronoi2` labels every
   position the brain reaches and the label is the lesson;
3. a frozen tournament against the fixed pool (`voronoi`, `voronoi2`, `hugger`, `survivor`,
   `racer`, `chaser` and the round-2 brains Viper, Lynx and Hawk) from start seeds the school
   never saw.

The recall memory is off (`recall=False`); the working trace (the aftertrace of the last
interpretation) is on at the genome's amplitude.
"""

from __future__ import annotations

import os
import random
import time
import traceback
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from . import bots, corpus, school
from .field import make_sense3
from .senses import make_sense
from .world import Arena, mulberry32

LAYOUTS = {
    "deep2w": (256, 256), "deep3w": (256, 256, 128), "deep3x": (384, 256, 128), "deep3n": (256, 128, 32),
    "wide2": (512, 128), "wide2x": (768, 128), "wide3": (512, 128, 64), "wide3x": (768, 128, 64),
    "flat256": (256,), "flat512": (512,), "deep2": (256, 128), "deep3": (256, 128, 64),
    "deep4": (384, 192, 128, 64), "deep4w": (512, 256, 128, 64),
}
SPACE: dict[str, list[Any]] = {
    "layout": list(LAYOUTS),
    "sense": ["field", "field_lite"],
    "apical": [0.1, 0.25, 0.5],
    "teaching": ["deep", "normalized"],
    "eta_scale": [0.3, 1.0, 3.0, 10.0],
    "temperature": [0.05, 0.1, 0.2],
    "lateral": [-1.0, -0.5, 0.0],
    "trace_amp": [0.0, 0.3, 1.0, 3.0],
    "trace_decay": [0.0, 0.5, 0.8],
    "sensory": [0.5, 1.0, 2.0],
    "rows": [16, 32],
    "watch": [400, 800, 1200],
    "dagger": [32, 64],
}
FOUNDER = {"layout": "deep3", "sense": "field", "apical": 0.25, "teaching": "deep", "eta_scale": 1.0,
           "temperature": 0.1, "lateral": -0.5, "trace_amp": 1.0, "trace_decay": 0.0, "sensory": 1.0,
           "rows": 32, "watch": 800, "dagger": 32}

# Fitness weights over the fixed tournament pool.
POOL_WEIGHTS = {"voronoi2": 2.0, "voronoi": 2.0, "viper": 1.0, "lynx": 1.0, "hawk": 1.0,
                "hugger": 1.0, "survivor": 1.0, "racer": 0.5, "chaser": 0.5, "safe": 0.5}
SCHOOL = ("voronoi", "voronoi20", "survivor", "chaser", "hugger", "racer", "voronoi40", "voronoi2")
# TRON_TEACHER=ab5 labels the DAgger stage with the 10-ply
# alpha-beta, TRON_DEEP=1 restricts the layouts to the deep ones and drops the flat ones.
if os.environ.get("TRON_DEEP"):
    SPACE["layout"] = ["deep2", "deep2w", "deep3", "deep3n", "deep3w"]
    SPACE["apical"] = [0.0, 0.1, 0.25, 0.5]
    SPACE["teaching"] = ["deep", "normalized"]
    SPACE["watch"] = [800, 1200, 2000]
    SPACE["dagger"] = [64, 128]
BUDGET_MS = 40.0  # contended CPU; the deep brain ships on a device, not the page
PRIOR = Path(os.environ.get("TRON_PRIOR", "runs/r3/prior"))
CORPUS = Path(os.environ.get("TRON_CORPUS", "runs/r3/corpus3.jsonl"))


def random_genome(rng: random.Random) -> dict[str, Any]:
    return {k: rng.choice(v) for k, v in SPACE.items()}


def mutate(g: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    g = dict(g)
    for k in rng.sample(list(SPACE), rng.choice([1, 2, 3])):
        g[k] = rng.choice(SPACE[k])
    return g


def cross(a: dict[str, Any], b: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in SPACE}


def key(g: dict[str, Any]) -> str:
    return "|".join(f"{k}={g[k]}" for k in SPACE)


def compose(g: dict[str, Any], seed: int, backend: str = "cpu"):
    from cadence import Brain

    n_in = make_sense3(g["sense"])[1]
    modules = LAYOUTS[g["layout"]]
    shape = dict(modules=modules, seed=seed, recall=False)
    if backend != "auto":
        shape["backend"] = backend
    if len(modules) > 1 and g.get("apical"):
        shape["apical"] = g["apical"]
    probe = Brain.compose(8, 3, modules=modules, recall=False, teaching=g["teaching"], seed=0,
                          **({"apical": g["apical"]} if len(modules) > 1 and g.get("apical") else {}))
    base = probe.learner.config
    cfg = replace(base, eta=base.eta * g["eta_scale"], eta_bias=base.eta_bias * g["eta_scale"],
                  temperature=g["temperature"])
    return Brain.compose(
        n_in, 3, **shape, learning=cfg, arousal=True, lateral=g["lateral"],
        working_memory_amplitude=g["trace_amp"], working_memory_decay=g["trace_decay"],
        scales={"sensory": g["sensory"]},
    )


def policy(brain, sense: str):
    see = make_sense3(sense)[0]
    timing = {"cpu": 0.0, "moves": 0}

    def play(arena, seat):
        t = time.process_time()
        # settle from rest before every move, the state the lessons train (a deep
        # reciprocal brain can hold a second, warm state that lessons never correct); every
        # brain has a working-trace amplitude of 0, so the reset loses nothing
        brain.reset()
        a = int(brain.act(see(arena, seat)[None, :], greedy=True)[0])
        timing["cpu"] += time.process_time() - t
        timing["moves"] += 1
        return a
    play.timing = timing
    return play


@lru_cache(maxsize=None)
def _prior(name: str):
    from cadence import Brain

    return Brain.load(str(PRIOR / f"{name}.npz"))


def opponent(name: str):
    """(arena, seat, draw) -> action, for a bot or a round-2 brain riding seat 1."""
    if name in ("viper", "lynx", "hawk"):
        brain = _prior(name)
        see = make_sense("eye")[0]

        def play(arena, seat, draw):
            brain.reset()
            return int(brain.act(see(arena, seat)[None, :], greedy=True)[0])
        play.reset = brain.reset
        return play
    return school.POOL[name]


def match(pol, name: str, seeds) -> dict[str, Any]:
    opp = opponent(name)
    w = l = d = 0
    for s in seeds:
        arena = Arena(24, seed=s)
        draw = mulberry32(s)
        if hasattr(opp, "reset"):
            opp.reset()
        if hasattr(pol, "reset"):
            pol.reset()
        while not arena.over:
            arena.step((pol(arena, 0), opp(arena, 1, draw)))
        w += arena.winner == 0
        l += arena.winner == 1
        d += arena.winner is None
    n = len(seeds)
    return {"wins": int(w), "losses": int(l), "draws": int(d), "score": (w + 0.5 * d) / n}


def pool_weights() -> dict[str, float]:
    """The tournament pool: the bots, and earlier brains (Viper, Lynx, Hawk) where their files
    are in TRON_PRIOR (they are optional; without them the pool is the bots alone)."""
    return {k: w for k, w in POOL_WEIGHTS.items()
            if k not in ("viper", "lynx", "hawk") or (PRIOR / f"{k}.npz").exists()}


def tournament(pol, base_seed: int, games: int, weights=None) -> dict[str, Any]:
    weights = weights or pool_weights()
    out = {name: match(pol, name, [base_seed + 1000 * i + k for k in range(games)])
           for i, name in enumerate(weights)}
    out["strength"] = sum(weights[o] * out[o]["score"] for o in weights) / sum(weights.values())
    return out


def frozen(brain):
    from cadence import Brain
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        twin = Brain.load(brain.save(os.path.join(folder, "b.npz")))
    twin.reset()
    return twin


@lru_cache(maxsize=1)
def _corpus():
    return corpus.load(CORPUS)


def watch(brain, sense: str, lessons: int, rows: int, seed: int) -> dict[str, Any]:
    """Corpus lessons: a greedy settle, then the teacher's move as the lesson."""
    games = _corpus()
    see = make_sense3(sense)[0]
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(games))
    streams = [corpus.Replay([games[i] for i in order], start=k, step=rows) for k in range(rows)]
    agree = seen = refused = 0
    brain.reset()
    for _ in range(lessons):
        x = np.stack([see(s.arena, 0) for s in streams])
        y = np.array([s.teacher_move() for s in streams])
        try:
            got = np.asarray(brain.act(x, greedy=True)).reshape(-1)
            agree += int((got == y).sum())
            seen += rows
            brain.lesson(x, y)
        except RuntimeError:
            refused += 1
            brain.reset()
        for s in streams:
            s.advance()
    brain.reset()
    return {"agreement": agree / max(seen, 1), "refused": refused}


def _teacher():
    if os.environ.get("TRON_TEACHER") == "ab5":
        from . import absearch
        return lambda arena, seat: absearch.search(arena, seat, 5)[0]
    return bots.voronoi2


def dagger(brain, sense: str, games: int, rows: int, seed: int, teacher=None) -> dict[str, Any]:
    """The brain rides; the teacher labels each position it reaches; the label is the lesson."""
    teacher = teacher or _teacher()
    see = make_sense3(sense)[0]
    rng = random.Random(seed)

    def fresh():
        s = rng.randrange(1 << 30)
        return {"arena": Arena(24, seed=s), "draw": mulberry32(s), "opp": SCHOOL[rng.randrange(len(SCHOOL))]}

    k = min(rows, 8)
    riders = [fresh() for _ in range(k)]
    done = refused = agree = seen = 0
    scores = []
    brain.reset()
    while done < games:
        x = np.stack([see(r["arena"], 0) for r in riders])
        y = np.array([teacher(r["arena"], 0) for r in riders])
        try:
            own = np.asarray(brain.act(x, greedy=True)).reshape(-1)
            brain.lesson(x, y)
        except RuntimeError:
            refused += 1
            brain.reset()
            own = y
        agree += int((own == y).sum())
        seen += k
        for i, r in enumerate(riders):
            a = r["arena"]
            a.step((int(own[i]), school.POOL[r["opp"]](a, 1, r["draw"])))
            if a.over:
                scores.append(1.0 if a.winner == 0 else 0.5 if a.winner is None else 0.0)
                done += 1
                riders[i] = fresh()
    brain.reset()
    return {"agreement": agree / max(seen, 1), "refused": refused, "own_score": float(np.mean(scores))}


def evaluate(g: dict[str, Any], seed: int, tour_seed: int, *, games: int = 8, keep: str | None = None,
             scale: float = 1.0) -> dict[str, Any]:
    t0 = time.time()
    out: dict[str, Any] = {"genome": g, "key": key(g), "seed": seed, "tour_seed": tour_seed}
    try:
        brain = compose(g, seed)
        out["neurons"], out["synapses"] = int(brain.connectome.n), int(len(brain.connectome.pre))
        out["watch"] = watch(brain, g["sense"], int(g["watch"] * scale), g["rows"], seed)
        out["dagger"] = dagger(brain, g["sense"], int(g["dagger"] * scale), g["rows"], seed)
        twin = frozen(brain)
        pol = policy(twin, g["sense"])
        pol.reset = twin.reset
        out["tournament"] = tournament(pol, tour_seed, games)
        out["act_ms"] = 1e3 * pol.timing["cpu"] / max(pol.timing["moves"], 1)
        cost = max(out["act_ms"] - BUDGET_MS, 0.0) / BUDGET_MS
        out["fitness"] = out["tournament"]["strength"] - 0.25 * cost
        if keep:
            Path(keep).parent.mkdir(parents=True, exist_ok=True)
            brain.save(keep)
    except Exception as error:  # a design that cannot be raised is a dead design
        out["error"] = "".join(traceback.format_exception_only(type(error), error)).strip()
        out["trace"] = traceback.format_exc()[-1500:]
        out["fitness"] = -1.0
    out["wall_s"] = round(time.time() - t0, 1)
    return out
