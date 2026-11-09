"""What each layer of a full-field brain computes, and what some of its neurons are for: layers,
plain-word neuron roles with a causal check, linear probes and receptive fields, for the play
page's deep-layer view.

    python scripts/introspect.py --brain brain.npz --meta meta.json --out introspect.json

Writes the JSON and, next to it, ROLES.md (the decoded neurons per layer with their evidence).

1. Layers come from the connectome alone: populations ordered by their hop distance from the
   inputs along the synapses (`module_0` = L1, `module_1` = L2, ..., the last hidden layer
   `association`), then the working trace if its amplitude is not zero, then the motor
   neurons. Any depth and widths; connections that jump a layer are listed as skips.
2. Positions: the brain plays frozen and greedy, exactly as `tron.r3.policy` plays it (reset
   each game, `brain.act(field(arena, seat)[None, :], greedy=True)`), against `voronoi` from
   both seats, against a noisy `voronoi` (`voronoi20`) and against itself (two copies), on
   fresh seeds (9,100,000+). Every move's settled state (the last sweep of its free settle) is
   kept.
3. Features of each position, from the brain's seat and in its own frame: free cells ahead,
   left and right (to the first blocked cell); a crash one cell ahead, left, right; each
   rider's Voronoi territory share (free cells reached strictly first); the distance to the
   opponent's head and where it is (cells ahead, cells to the right); the distance to the
   nearest wall; whether the riders are walled apart; whether a cut-off move exists (a move
   after which, whatever the reply, the riders are walled apart with the larger room on the
   brain's side, or the opponent crashes); and the `voronoi` teacher's move. Thresholded
   events ("a wall within two cells ahead", "the opponent within 8 cells, to the right", ...)
   are built from them.
4. Roles: the neurons are nearly binary (a leaky sigmoid, floor -0.1, ceiling 1), so a neuron
   "fires" above the midpoint of its own 5th-95th percentile range. Its role is the event
   whose presence best matches its firing (phi, the correlation of two yes/no variables, with
   the firing rates with and without the event), or a number it tracks (Pearson r) when that
   fits clearly better; |phi| or |r| >= 0.3, else "mixed".
5. Causal check: the same games are replayed (the play is deterministic; every replayed move is
   checked against the first pass). On positions where a tested neuron's event holds, the brain
   is forked and the move read again with that neuron silenced (bias -30: held at its floor)
   and driven (bias +30: held at 1). Up to `--causal` neurons per layer (the strongest roles)
   are tested, with as many random neurons on random positions as the layer's null. A role is
   supported when silencing or driving changes the move on at least 15% of its positions, at
   least 3 times the null rate and on at least 5 positions; the effect is put in words (rides
   into walls more often, turns left more often, ...).
6. Layer probes: per layer, a linear readout of six features fitted on 80% of the games and
   scored on the other 20% (R^2 for numbers; balanced accuracy for classes, chance 1/k, with
   plain accuracy and the majority rate beside it). The weights are folded onto raw
   activations so the page can read them live: value = w . a + b (sigmoid for a yes/no,
   softmax over three moves).
7. Receptive fields: L1 as its input weights laid on the sense's planes; deeper layers as the
   weights propagated through the feed-forward synapses (skips included); the trace as the
   field of the neuron it traces; int8 per neuron with a scale.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import sys
import time
import warnings
from collections import deque
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tron import bots, school  # noqa: E402
from tron.field import field, field_size  # noqa: E402
from tron.fieldhost import retina  # noqa: E402
from tron.world import DC, DR, Arena, mulberry32  # noqa: E402

N = 24
INF = bots.INF
LABEL_MIN = 0.3
CLAMP = 30.0
NULL_MIN = 20  # trials a null needs before a clamp's effect can count as clear
CLASS_MIN = 10  # held-out cases of the rarer class a class probe needs
MOVES = ("left", "straight", "right")
DOING = ("turn left", "ride straight on", "turn right")

FEATURES = ["free_ahead", "free_left", "free_right", "crash_ahead", "crash_left", "crash_right", "own_share",
            "opp_share", "opp_dist", "opp_ahead", "opp_right", "wall_dist", "apart", "cutoff",
            "teach_left", "teach_straight", "teach_right"]

# Events: name -> (family, test, "fires when ...", "fires when ..." for the opposite).
EVENTS = {
    "wall_ahead": ("ahead", lambda f: f["free_ahead"] <= 2, "a wall is within two cells ahead", "the way ahead is open"),
    "open_ahead": ("ahead", lambda f: f["free_ahead"] >= 10, "a long run is open straight ahead", "the run ahead is short"),
    "left_blocked": ("left", lambda f: f["crash_left"] > 0, "the left is blocked", "the left is open"),
    "open_left": ("left", lambda f: f["free_left"] >= 8, "there is a long run open to the left", "the left is cramped"),
    "right_blocked": ("right", lambda f: f["crash_right"] > 0, "the right is blocked", "the right is open"),
    "open_right": ("right", lambda f: f["free_right"] >= 8, "there is a long run open to the right", "the right is cramped"),
    "edge": ("edge", lambda f: f["wall_dist"] <= 1, "it rides along the arena's edge", "it is away from the edges"),
    "opp_close": ("opponent", lambda f: f["opp_dist"] <= 5, "the opponent is close", "the opponent is far away"),
    "opp_close_right": ("opponent", lambda f: f["opp_dist"] <= 8 and f["opp_right"] >= 1, "the opponent is close, to the right", None),
    "opp_close_left": ("opponent", lambda f: f["opp_dist"] <= 8 and f["opp_right"] <= -1, "the opponent is close, to the left", None),
    "opp_front": ("opponent", lambda f: f["opp_ahead"] >= 2 and abs(f["opp_right"]) <= f["opp_ahead"], "the opponent is in front", None),
    "opp_behind": ("opponent", lambda f: f["opp_ahead"] <= -2, "the opponent is behind", "the opponent is not behind"),
    "opp_right_side": ("opponent", lambda f: f["opp_right"] >= 3, "the opponent is off to the right", None),
    "opp_left_side": ("opponent", lambda f: f["opp_right"] <= -3, "the opponent is off to the left", None),
    "big_territory": ("territory", lambda f: f["own_share"] >= 0.55, "it owns most of the free board", None),
    "small_territory": ("territory", lambda f: f["own_share"] <= 0.4, "the opponent owns most of the free board", None),
    "apart": ("apart", lambda f: f["apart"] > 0, "the riders are walled apart", "the riders still share a room"),
    "cutoff": ("cutoff", lambda f: f["cutoff"] > 0, "a cut-off move exists", None),
    "teach_left": ("teacher", lambda f: f["teacher"] == 0, "the teacher would turn left", None),
    "teach_straight": ("teacher", lambda f: f["teacher"] == 1, "the teacher would ride straight on", "the teacher would turn"),
    "teach_right": ("teacher", lambda f: f["teacher"] == 2, "the teacher would turn right", None),
}
# Numbers a neuron can track: name -> (family, "tracks ...", "rises as ...").
TRACKS = {
    "free_ahead": ("ahead", "tracks the room straight ahead", "rises as the room ahead shrinks"),
    "free_left": ("left", "tracks the room to the left", "rises as the left closes in"),
    "free_right": ("right", "tracks the room to the right", "rises as the right closes in"),
    "own_share": ("territory", "tracks its own territory share", "rises as its territory shrinks"),
    "opp_share": ("territory", "tracks the opponent's territory share", "rises as the opponent's territory shrinks"),
    "opp_dist": ("opponent", "tracks the distance to the opponent", "rises as the opponent comes closer"),
    "opp_ahead": ("opponent", "rises the further ahead the opponent is", "rises the further behind the opponent is"),
    "opp_right": ("opponent", "rises the further right the opponent is", "rises the further left the opponent is"),
    "wall_dist": ("edge", "tracks the distance to the nearest wall", "rises near the arena's walls"),
}
FAMILIES = {"ahead": "ahead", "left": "left", "right": "right", "edge": "edges", "opponent": "opponent",
            "territory": "territory", "apart": "walled apart", "cutoff": "cut-off", "teacher": "teacher",
            "motor": "moves", "mixed": "mixed", "silent": "silent"}
PROBES = [
    ("crash_ahead", "wall ahead", "bin"),
    ("free_ahead", "room ahead", "num"),
    ("own_share", "my territory", "num"),
    ("opp_dist", "distance to you", "num"),
    ("cutoff", "cut-off exists", "bin"),
    ("teacher", "teacher's move", "move"),
]


# ---- the connectome's layers ----------------------------------------------------------------
def layers_of(brain) -> tuple[list[dict], list[dict]]:
    c = brain.connectome
    pops = {k: np.asarray(v) for k, v in c.populations.items() if "/" not in k}
    names = sorted(pops, key=lambda k: int(pops[k][0]))
    owner = np.full(c.n, -1, dtype=np.int64)
    for i, k in enumerate(names):
        owner[pops[k]] = i
    pre, post = np.asarray(c.pre), np.asarray(c.post)
    w = np.asarray(brain.brain.weights, dtype=np.float64)
    pair = owner[pre] * len(names) + owner[post]
    links: dict[tuple[str, str], dict] = {}
    for k in np.unique(pair):
        a, b = names[k // len(names)], names[k % len(names)]
        if a == b:
            continue
        idx = pair == k
        links[(a, b)] = {"synapses": int(idx.sum()), "mean_abs": float(np.abs(w[idx]).mean())}
    depth = {"sensory": 0}  # hop distance from the inputs along the synapses
    frontier = deque(["sensory"])
    while frontier:
        a = frontier.popleft()
        for (x, y) in links:
            if x == a and y not in depth:
                depth[y] = depth[a] + 1
                frontier.append(y)
    wm = getattr(brain, "working_memory", None)
    trace_pop = getattr(wm, "target", None) if wm is not None else None
    trace_src = getattr(wm, "source", None) if wm is not None else None
    amp = float(getattr(wm, "amplitude", 0.0) or 0.0) if wm is not None else 0.0
    motor = "motor" if "motor" in pops else names[-1]
    hidden = [k for k in names if k not in ("sensory", motor, trace_pop) and k in depth]
    hidden.sort(key=lambda k: (depth[k], int(pops[k][0])))
    per_depth: dict[int, int] = {}
    for k in hidden:
        per_depth[depth[k]] = per_depth.get(depth[k], 0) + 1
    out, tally = [], {}
    for k in hidden:
        d = depth[k]
        tally[d] = tally.get(d, 0) + 1
        suffix = "abcdefgh"[tally[d] - 1] if per_depth[d] > 1 else ""
        out.append({"key": f"L{d}{suffix}", "name": f"L{d}{suffix}", "pop": k, "kind": "hidden", "depth": d})
    if trace_pop and trace_pop in pops and amp > 0:
        out.append({"key": "trace", "name": "trace", "pop": trace_pop, "kind": "trace", "source": trace_src,
                    "amplitude": amp, "decay": float(getattr(wm, "decay", 0.0)), "depth": depth.get(trace_src, 0) + 1})
    out.append({"key": "motor", "name": "motor", "pop": motor, "kind": "motor", "depth": depth.get(motor, len(out) + 1)})
    for L in out:
        L["start"], L["count"] = int(pops[L["pop"]][0]), int(len(pops[L["pop"]]))
    layer_of = {L["pop"]: L["key"] for L in out}
    layer_of["sensory"] = "inputs"
    dep = {L["pop"]: L["depth"] for L in out}
    dep["sensory"] = 0
    conns = []
    for (a, b), v in sorted(links.items(), key=lambda kv: (dep.get(kv[0][0], 99), dep.get(kv[0][1], 99))):
        if a not in layer_of or b not in layer_of:
            continue
        conns.append({"from": layer_of[a], "to": layer_of[b], **v,
                      "skip": bool(abs(dep[b] - dep[a]) > 1 and trace_pop not in (a, b))})
    return out, conns


# ---- features ------------------------------------------------------------------------------
def _ray(arena: Arena, r: int, c: int, h: int) -> int:
    k = 0
    while True:
        r, c = r + DR[h], c + DC[h]
        if not arena.free(r, c):
            return k
        k += 1


def _room(grid, start) -> int:
    return sum(1 for d in bots._distances(grid, N, start) if 0 < d < INF)


def _cutoff(arena: Arena, seat: int) -> bool:
    other = 1 - seat
    grid = arena.grid
    for action in (1, 0, 2):
        r, c, _ = bots._next(arena, seat, action)
        if not arena.free(r, c):
            continue
        good = True
        for reply in (1, 0, 2):
            rr, cc, _ = bots._next(arena, other, reply)
            if (rr, cc) == (r, c):
                good = False
                break
            if not arena.free(rr, cc):
                continue  # they crash: fine for the brain
            grid[r * N + c] = 1
            grid[rr * N + cc] = 1
            _, shared = bots._score(grid, N, (r, c), (rr, cc))
            ok = (not shared) and _room(grid, (r, c)) > _room(grid, (rr, cc))
            grid[r * N + c] = 0
            grid[rr * N + cc] = 0
            if not ok:
                good = False
                break
        if good:
            return True
    return False


def features(arena: Arena, seat: int) -> dict[str, float]:
    h = arena.headings[seat]
    left, right = (h + 3) % 4, (h + 1) % 4
    r, c = arena.heads[seat]
    orr, occ = arena.heads[1 - seat]
    f: dict[str, float] = {}
    for name, d in (("ahead", h), ("left", left), ("right", right)):
        f[f"free_{name}"] = _ray(arena, r, c, d)
        f[f"crash_{name}"] = float(not arena.free(r + DR[d], c + DC[d]))
    a = bots._distances(arena.grid, N, (r, c))
    b = bots._distances(arena.grid, N, (orr, occ))
    free = [i for i in range(N * N) if arena.grid[i] == 0]
    nf = max(len(free), 1)
    f["own_share"] = sum(1 for i in free if a[i] < b[i]) / nf
    f["opp_share"] = sum(1 for i in free if b[i] < a[i]) / nf
    shared = any(0 <= orr + DR[k] < N and 0 <= occ + DC[k] < N and a[(orr + DR[k]) * N + occ + DC[k]] < INF for k in range(4))
    dr, dc = orr - r, occ - c
    f["opp_dist"] = abs(dr) + abs(dc)
    f["opp_ahead"] = dr * DR[h] + dc * DC[h]
    f["opp_right"] = dr * DR[right] + dc * DC[right]
    f["wall_dist"] = min(r, c, N - 1 - r, N - 1 - c)
    f["apart"] = float(not shared)
    f["cutoff"] = float(shared and _cutoff(arena, seat))
    t = bots.voronoi(arena, seat)
    f["teacher"] = t
    for k, name in enumerate(MOVES):
        f[f"teach_{name}"] = float(t == k)
    return f


def crashes(arena: Arena, seat: int, move: int) -> bool:
    r, c, _ = bots._next(arena, seat, move)
    return not arena.free(r, c)


# ---- playing positions -----------------------------------------------------------------------
REST = os.environ.get("TRON_SETTLE_FROM_REST") == "1"  # meta "settle_from_rest": every move from rest


def _settled(brain, x):
    from cadence import record_settlements

    if REST:
        brain.reset()
    records = []
    with record_settlements(records.append):
        try:
            move = int(brain.act(x[None, :], greedy=True)[0])
        except RuntimeError:
            return None, None
    free = [r for r in records if r.nudge is None and r.steps > 0]
    if not free:
        return None, None
    return move, np.asarray(free[-1].activation[-1, 0, :], dtype=np.float32)


def _fork_move(brain, x, motor, neurons=None, bias=None):
    """The move and the settled motor state a copy of the brain (same stream state) reads,
    optionally with some neurons' biases set; the brain itself is untouched."""
    twin = copy.deepcopy(brain)
    if neurons is not None:
        b = np.array(twin.brain.bias, dtype=float)
        b[neurons] = bias
        twin.learner.brain = twin.brain.with_parameters(bias=b)
    try:
        move = int(twin.act(x[None, :], greedy=True)[0])
    except RuntimeError:
        return None, None
    return move, np.asarray(twin.basal_ganglia.state.activation)[0, motor].astype(float)


def play_chunk(job):
    """Pass 1 (tests is None): settled states and features of every brain move. Pass 2: the
    same games replayed; at positions where a test's event holds, the clamped moves."""
    warnings.filterwarnings("ignore")
    from cadence import Brain

    path, kind, seeds, n_in, tests, expect, thr = job
    brain = Brain.load(path, backend="cpu")
    twin = Brain.load(path, backend="cpu") if kind == "self" else None
    motor = np.asarray(brain.connectome.populations["motor"])
    rows, results, mismatches, checked, fork_diff = [], [], 0, 0, 0
    used = {t["id"]: 0 for t in (tests or [])}
    rng = np.random.default_rng(len(seeds) * 7919 + (seeds[0][1] if seeds else 0))
    for gi, s in seeds:
        for seat in ((0, 1) if kind != "self" else (0,)):
            arena = Arena(N, seed=s)
            draw = mulberry32(s)
            brain.reset()
            if twin is not None:
                twin.reset()
            while not arena.over:
                x = field(arena, seat)
                f = features(arena, seat)
                if REST:
                    brain.reset()
                snap = copy.deepcopy(brain) if tests is not None else None
                move, act = _settled(brain, x)
                if tests is not None and act is not None:
                    on_now = act > thr
                    todo = [t for t in tests if used[t["id"]] < t["quota"] and (
                        (EVENTS[t["event"]][1](f) == t["when"]) if t["event"] is not None
                        else (on_now[t["fire"]].mean() >= t["frac"] and rng.random() < t["p"]))]
                    if todo:
                        base, mb = _fork_move(snap, x, motor)
                        fork_diff += int(base != move)
                        for t in todo:
                            off, moff = _fork_move(snap, x, motor, t["neurons"], -CLAMP)
                            on, mon = _fork_move(snap, x, motor, t["neurons"], CLAMP)
                            if base is None or off is None or on is None:
                                continue
                            used[t["id"]] += 1
                            results.append((t["id"], base, off, on, crashes(arena, seat, base), crashes(arena, seat, off),
                                            crashes(arena, seat, on), int(f["teacher"]), mb, moff, mon))
                if move is None:
                    move = 1
                elif tests is None:
                    rows.append((gi, kind, arena.tick, move, f, act[n_in:], seat))
                if expect is not None:
                    checked += 1
                    mismatches += int(expect.get((gi, seat, arena.tick)) not in (None, move))
                if kind == "self":
                    y = field(arena, 1 - seat)
                    if tests is None:
                        g = features(arena, 1 - seat)
                        m2, act2 = _settled(twin, y)
                        if m2 is not None:
                            rows.append((gi, "self2", arena.tick, m2, g, act2[n_in:], 1 - seat))
                    else:
                        m2, _ = _settled(twin, y)
                    other = 1 if m2 is None else m2
                elif kind == "voronoi":
                    other = bots.voronoi(arena, 1 - seat)
                else:
                    other = school.POOL["voronoi20"](arena, 1 - seat, draw)
                arena.step((move, other) if seat == 0 else (other, move))
    return {"rows": rows, "results": results, "mismatches": mismatches, "checked": checked, "fork_diff": fork_diff}


# ---- statistics ------------------------------------------------------------------------------
def pearson(A: np.ndarray, F: np.ndarray) -> np.ndarray:
    """r between every column of A (positions x neurons) and of F (positions x features)."""
    a = A - A.mean(0)
    f = F - F.mean(0)
    sa = np.sqrt((a * a).sum(0))
    sf = np.sqrt((f * f).sum(0))
    r = (a.T @ f) / np.maximum(np.outer(sa, sf), 1e-12)
    r[sa < 1e-6, :] = 0.0
    r[:, sf < 1e-9] = 0.0
    return r


def _ridge(X, y, lam):
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def _softmax_fit(X, Y, lam, iters=400):
    """Multinomial logistic regression, class-balanced, L2, full-batch Adam."""
    n, d = X.shape
    k = Y.shape[1]
    cw = 1.0 / np.maximum(Y.mean(0), 1e-3) / k
    sw = (Y * cw).sum(1, keepdims=True)
    W = np.zeros((d, k))
    b = np.zeros(k)
    mW = vW = np.zeros_like(W)
    mb = vb = np.zeros_like(b)
    lr, b1, b2 = 0.05, 0.9, 0.999
    for t in range(1, iters + 1):
        Z = X @ W + b
        Z -= Z.max(1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(1, keepdims=True)
        G = (P - Y) * sw
        gW = X.T @ G / n + lam * W
        gb = G.mean(0)
        mW = b1 * mW + (1 - b1) * gW
        vW = b2 * vW + (1 - b2) * gW * gW
        mb = b1 * mb + (1 - b1) * gb
        vb = b2 * vb + (1 - b2) * gb * gb
        W -= lr * (mW / (1 - b1 ** t)) / (np.sqrt(vW / (1 - b2 ** t)) + 1e-8)
        b -= lr * (mb / (1 - b1 ** t)) / (np.sqrt(vb / (1 - b2 ** t)) + 1e-8)
    return W, b


def _balanced(pred, y, k):
    per = [float((pred[y == c] == c).mean()) for c in range(k) if (y == c).any()]
    return float(np.mean(per)) if per else 0.0


def fit_probe(A, y, kind, train, test, rng):
    """A probe on standardized activations, lambda picked on a split of the training games;
    weights folded onto raw activations, scored on the held-out games."""
    mu = A[train].mean(0)
    sd = A[train].std(0)
    live = sd > 1e-6
    sd = np.where(live, sd, 1.0)
    Z = (A - mu) / sd
    Z[:, ~live] = 0.0
    tr = np.flatnonzero(train)
    inner = rng.random(len(tr)) < 0.8
    fit_i, val_i = tr[inner], tr[~inner]
    if kind == "num":
        ym = y[train].mean()

        def r2(t, p):
            return 1 - ((t - p) ** 2).sum() / max(((t - t.mean()) ** 2).sum(), 1e-12)
        lam = max((0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0),
                  key=lambda L: r2(y[val_i], Z[val_i] @ _ridge(Z[fit_i], y[fit_i] - ym, L) + ym))
        w = _ridge(Z[train], y[train] - ym, lam)
        score = r2(y[test], Z[test] @ w + ym)
        lo, hi = np.percentile(y[train], [2, 98])
        return {"W": (w / sd)[:, None], "b": np.array([ym - (w * mu / sd).sum()]), "score": {"r2": float(score)},
                "lam": lam, "range": [float(lo), float(hi)]}
    k = 2 if kind == "bin" else 3
    yi = y.astype(int)
    Y = np.eye(k)[yi]
    best = None
    for lam in (1e-3, 1e-2, 1e-1, 1.0):
        W, b = _softmax_fit(Z[fit_i], Y[fit_i], lam)
        s = _balanced((Z[val_i] @ W + b).argmax(1), yi[val_i], k)
        if best is None or s > best[0]:
            best = (s, lam)
    W, b = _softmax_fit(Z[train], Y[train], best[1])
    pred = (Z[test] @ W + b).argmax(1)
    counts = np.bincount(yi[train], minlength=k)
    held = np.bincount(yi[test], minlength=k)
    score = {"balanced": _balanced(pred, yi[test], k), "chance": round(1 / k, 3),
             "accuracy": float((pred == yi[test]).mean()), "majority": float((yi[test] == counts.argmax()).mean()),
             "train_counts": counts.tolist(), "test_counts": held.tolist()}
    if held.min() < CLASS_MIN or counts.min() < 2 * CLASS_MIN:
        score["insufficient"] = True  # too few cases of a class to score it
    Wr = W / sd[:, None]
    Wr[~live] = 0.0
    br = b - (W * (mu / sd)[:, None]).sum(0)
    if kind == "bin":  # one logit: class 1 minus class 0
        Wr, br = (Wr[:, 1] - Wr[:, 0])[:, None], np.array([br[1] - br[0]])
    return {"W": Wr, "b": br, "score": score, "lam": best[1]}


# ---- roles ---------------------------------------------------------------------------------
def roles(A, F, E, enames, fnames):
    """Per neuron: firing threshold, best event by phi, best tracked number by r."""
    lo, hi = np.percentile(A, 5, axis=0), np.percentile(A, 95, axis=0)
    thr = 0.5 * (lo + hi)
    fire = (A > thr).astype(np.float64)
    phi = pearson(fire, E)
    tracks = [fnames.index(k) for k in TRACKS]
    r = pearson(A, F[:, tracks])
    out = []
    for i in range(A.shape[1]):
        rate = fire[:, i].mean()
        if hi[i] - lo[i] < 1e-3 or rate < 0.005 or rate > 0.995:
            out.append({"family": "silent", "role": "barely moves", "silent": True, "fires": round(float(rate), 3)})
            continue
        order = np.argsort(-np.abs(phi[i]))
        j = int(order[0])
        p = float(phi[i, j])
        tj = int(np.argmax(np.abs(r[i])))
        rv = float(r[i, tj])
        if max(abs(p), abs(rv)) < LABEL_MIN:
            out.append({"family": "mixed", "role": "mixed", "mixed": True, "fires": round(float(rate), 3),
                        "best": enames[j], "phi": round(p, 3), "r_best": list(TRACKS)[tj], "r": round(rv, 3)})
            continue
        if abs(rv) > abs(p) + 0.1:
            key = list(TRACKS)[tj]
            fam, pos, neg = TRACKS[key]
            out.append({"family": fam, "kind": "tracks", "key": key, "r": round(rv, 3), "role": pos if rv > 0 else neg,
                        "fires": round(float(rate), 3), "threshold": round(float(thr[i]), 4)})
            continue
        name = enames[j]
        fam, test, pos, neg = EVENTS[name]
        ev = E[:, j] > 0
        when = p > 0
        if not when and neg is None:  # no plain opposite: say when it is quiet
            text = f"falls silent when {pos}"
        else:
            text = f"fires when {pos if when else neg}"
        role = {"family": fam, "kind": "event", "key": name, "when": bool(when), "phi": round(p, 3), "role": text,
                "fires": round(float(rate), 3), "threshold": round(float(thr[i]), 4),
                "rate_with": round(float(fire[ev, i].mean()), 3) if ev.any() else None,
                "rate_without": round(float(fire[~ev, i].mean()), 3) if (~ev).any() else None,
                "event_share": round(float(ev.mean()), 3)}
        for j2 in order[1:]:
            n2 = enames[int(j2)]
            if EVENTS[n2][0] == fam or abs(phi[i, j2]) < LABEL_MIN:
                continue
            p2 = float(phi[i, j2])
            _, _, pos2, neg2 = EVENTS[n2]
            if p2 < 0 and neg2 is None:
                continue
            role["also"] = {"key": n2, "phi": round(p2, 3), "text": pos2 if p2 > 0 else neg2}
            role["role"] += f", and when {role['also']['text']}"
            break
        out.append(role)
    return out


def effect_words(c, null, them=False):
    """The clearest consequence of the two clamps, in words, and whether it is clear against
    the null: the move flips on >= 15% of the positions (>= 5 of them, >= 3x the null's flip
    rate), or the motor vote shifts the same way on >= 80% of them by >= 3x the null's mean
    shift (>= 10 positions)."""
    n = c["n"]
    best = None
    enough = null is not None and null["n"] >= NULL_MIN
    for clamp, verb in (("off", "silencing them" if them else "silencing it"), ("on", "driving them" if them else "driving it")):
        null_flip = null[f"changed_{clamp}"] if null else 0.0
        null_shift = null[f"shift_{clamp}"] if null else 0.0
        changed = c[f"changed_{clamp}"]
        flips = n >= 5 and round(changed * n) >= 5 and changed >= 0.15 and changed >= 3 * null_flip
        d = np.array(c[f"shift_{clamp}"])
        k = int(np.argmax(np.abs(d)))
        same = c[f"same_{clamp}"][k]
        graded = n >= 10 and abs(d[k]) >= max(0.01, 3 * null_shift) and same >= 0.8
        b_crash, x_crash = c["crash_base"], c[f"crash_{clamp}"]
        base, alt = np.array(c["moves_base"]), np.array(c[f"moves_{clamp}"])
        dm = alt - base
        m = int(np.argmax(np.abs(dm)))
        if x_crash - b_crash >= 0.1 and x_crash >= 2 * b_crash:
            ratio = x_crash / b_crash if b_crash > 0 else None
            what = (f"{verb} makes the brain ride into walls "
                    + (f"{ratio:.1f}x as often" if ratio else "where it never did")
                    + f" ({100 * b_crash:.0f}% -> {100 * x_crash:.0f}% of these positions)")
        elif b_crash - x_crash >= 0.1:
            what = f"{verb} makes the brain miss walls it rode into ({100 * b_crash:.0f}% -> {100 * x_crash:.0f}%)"
        elif abs(dm[m]) >= 0.1:
            what = (f"{verb} makes the brain {DOING[m]} {'more' if dm[m] > 0 else 'less'} often "
                    f"({100 * base[m]:.0f}% -> {100 * alt[m]:.0f}% of these positions)")
        elif flips:
            what = f"{verb} changes the move on {100 * changed:.0f}% of these positions"
        elif graded:
            what = (f"{verb} tilts the vote {'towards' if d[k] > 0 else 'away from'} {DOING[k].replace('ride ', 'riding ').replace('turn ', 'turning ')} "
                    f"(motor {d[k]:+.3f}, the same way on {100 * same:.0f}% of these positions; "
                    f"the move flips on {100 * changed:.0f}%)")
        else:
            what = f"{verb}: no clear effect (move flips on {100 * changed:.0f}%, largest vote shift {d[k]:+.3f})"
        clear = (flips or graded) and enough
        score = (2 if flips else 1 if graded else 0) + changed + abs(d[k])
        if best is None or score > best[0]:
            best = (score, clear, what, clamp)
    words = best[2] if enough else best[2] + f" [null too small: {null['n'] if null else 0} trials]"
    return best[1], words, best[3]


def summarize(results):
    groups = {}
    for x in results:
        groups.setdefault(x[0], []).append(x)
    out = {}
    for tid, xs in groups.items():
        n = len(xs)
        base = np.array([x[1] for x in xs])
        mb = np.array([x[8] for x in xs])
        c = {"n": n, "crash_base": float(np.mean([x[4] for x in xs])),
             "moves_base": np.bincount(base, minlength=3)[:3].astype(float) / n,
             "teacher_base": float(np.mean(base == np.array([x[7] for x in xs])))}
        for j, clamp in ((2, "off"), (3, "on")):
            mv = np.array([x[j] for x in xs])
            d = np.array([x[9 if clamp == "off" else 10] for x in xs]) - mb
            mean = d.mean(0)
            c[f"changed_{clamp}"] = float(np.mean(mv != base))
            c[f"crash_{clamp}"] = float(np.mean([x[5 if clamp == "off" else 6] for x in xs]))
            c[f"moves_{clamp}"] = np.bincount(mv, minlength=3)[:3].astype(float) / n
            c[f"teacher_{clamp}"] = float(np.mean(mv == np.array([x[7] for x in xs])))
            c[f"shift_{clamp}"] = mean.tolist()
            c[f"same_{clamp}"] = [float(np.mean(np.sign(d[:, k]) == np.sign(mean[k]))) if mean[k] != 0 else 0.0
                                  for k in range(d.shape[1])]
            c[f"abs_{clamp}"] = float(np.abs(d).max(1).mean())
        out[tid] = c
    return out


def null_of(cs):
    """The pooled null of random clamps: flip rate and mean largest motor shift."""
    if not cs:
        return None
    tot = sum(c["n"] for c in cs)
    return {"n": tot,
            "changed": sum(max(c["changed_off"], c["changed_on"]) * c["n"] for c in cs) / tot,
            "changed_off": sum(c["changed_off"] * c["n"] for c in cs) / tot,
            "changed_on": sum(c["changed_on"] * c["n"] for c in cs) / tot,
            "shift": sum(max(c["abs_off"], c["abs_on"]) * c["n"] for c in cs) / tot,
            "shift_off": sum(c["abs_off"] * c["n"] for c in cs) / tot,
            "shift_on": sum(c["abs_on"] * c["n"] for c in cs) / tot}


def causal_entry(c, null, them=False):
    clear, words, clamp = effect_words(c, null, them)
    r3 = lambda v: [round(float(t), 4) for t in v]  # noqa: E731
    return {"n": c["n"], "changed_off": round(c["changed_off"], 3), "changed_on": round(c["changed_on"], 3),
            "crash": [round(c["crash_base"], 3), round(c["crash_off"], 3), round(c["crash_on"], 3)],
            "moves_base": r3(c["moves_base"]), "moves_off": r3(c["moves_off"]), "moves_on": r3(c["moves_on"]),
            "vote_shift_off": r3(c["shift_off"]), "vote_shift_on": r3(c["shift_on"]),
            "teacher": [round(c["teacher_base"], 3), round(c["teacher_off"], 3), round(c["teacher_on"], 3)],
            "effect": words, "clamp": clamp, "clear": bool(clear)}


# ---- receptive fields ------------------------------------------------------------------------
def fields(brain, layers, n_in):
    c = brain.connectome
    pre, post = np.asarray(c.pre), np.asarray(c.post)
    w = np.asarray(brain.brain.weights, dtype=np.float64)
    rf = {}
    pops = {L["pop"]: L for L in layers}
    sens = pre < n_in
    for L in sorted(layers, key=lambda L: (L["kind"] == "trace", L["kind"] == "motor", L["depth"])):
        if L["kind"] == "trace":
            continue
        s, n = L["start"], L["count"]
        into = (post >= s) & (post < s + n)
        M = np.zeros((n, n_in))
        m = into & sens
        np.add.at(M, (post[m] - s, pre[m]), w[m])
        for src, R in rf.items():
            S = pops[src]
            if S["depth"] >= L["depth"]:
                continue  # feed-forward only: from shallower layers, skips included
            m = into & (pre >= S["start"]) & (pre < S["start"] + S["count"])
            if not m.any():
                continue
            C = np.zeros((n, S["count"]))
            np.add.at(C, (post[m] - s, pre[m] - S["start"]), w[m])
            M += C @ R
        rf[L["pop"]] = M
    for L in layers:
        if L["kind"] == "trace":
            rf[L["pop"]] = rf[L["source"]].copy() if L.get("source") in rf else np.zeros((L["count"], n_in))
    return rf


def pack_int8(M):
    scale = np.abs(M).max(1)
    q = np.round(127 * M / np.maximum(scale, 1e-12)[:, None]).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode(), [float(f"{v:.4g}") for v in scale]


# ---- ROLES.md --------------------------------------------------------------------------------
def roles_md(report) -> str:
    P = report["positions"]
    lines = [f"# Neuron roles: {report.get('title') or report.get('brain')}", "",
             f"Brain file `{report['brain_file']}`. {P['total']} settled positions from {P['games']} games "
             f"(seeds {P['seeds']}: against voronoi from both seats, against voronoi20, against itself). "
             f"Written by `scripts/introspect.py`.", "",
             "A neuron fires above the midpoint of its own 5th-95th percentile range. Its role is the "
             "thresholded event whose presence best matches its firing (phi), or a number it tracks (Pearson r) "
             f"when that fits clearly better; kept at |phi| or |r| >= {LABEL_MIN}, else mixed. "
             "Causal check: on positions where the event holds, the brain is forked and the move read with the "
             "neuron silenced (bias -30, held at its floor) and driven (bias +30, held at 1). A role is supported "
             "when a clamp changes the move on at least 15% of those positions, at least 3 times the rate for "
             "random neurons of the same layer on positions where they fire, and on at least 5 positions; or when it "
             "shifts the motor vote the same way on at least 80% of at least 10 positions, by at least 3 times the "
             "null's mean shift. A verdict "
             f"needs a null of at least {NULL_MIN} trials. Groups are judged against as many random neurons with "
             "similar firing rates.", "",
             f"Replay check: {report['causal']['replay_checked']} replayed moves, "
             f"{report['causal']['replay_mismatches']} different from the first pass; the unclamped fork read a different "
             f"move than the brain on {report['causal']['fork_unclamped_differs']} tested positions.", ""]
    for L in report["layers"]:
        labels = L["labels"]
        n_role = sum(1 for x in labels if x.get("kind") in ("event", "tracks"))
        n_sup = sum(1 for x in labels if x.get("supported"))
        n_mixed = sum(1 for x in labels if x.get("mixed"))
        n_sil = sum(1 for x in labels if x.get("silent"))
        cz = L.get("causal_null")
        lines += [f"## {L['name']} ({L['pop']}, {L['count']} neurons)", ""]
        if L["kind"] == "motor":
            lines += ["The three motor neurons are the moves (left, straight, right); the move is read from them.", ""]
        lines += [f"{n_role} with a role at |phi| or |r| >= {LABEL_MIN}; {n_sup} supported by the causal check "
                  f"(of {L.get('causal_tested', 0)} tested); {n_mixed} mixed; {n_sil} barely move."
                  + (f" Null: one random neuron, silenced or driven, flips the move on {100 * cz['changed']:.1f}% of "
                     f"random positions and shifts the largest motor vote by {cz['shift']:.4f} on average "
                     f"({cz['n']} trials)." if cz else ""), ""]
        sup = [(i, x) for i, x in enumerate(labels) if x.get("supported")]
        sup.sort(key=lambda t: -max(abs(t[1].get("phi", 0)), abs(t[1].get("r", 0))))
        if sup:
            lines += ["| neuron | role | evidence | causal effect |", "|---|---|---|---|"]
            for i, x in sup:
                lines.append(f"| {L['name']}.{i} | {x['role']} | {_evidence(x)} | {x['causal']['effect']} (n={x['causal']['n']}) |")
            lines.append("")
        gs = L.get("groups") or []
        if gs:
            lines += ["Groups (every neuron of the layer with that role, clamped together; null: as many random "
                      "neurons on random positions):", "", "| role | neurons | causal effect | null flips |",
                      "|---|---|---|---|"]
            for g in gs:
                c = g["causal"]
                lines.append(f"| {g['role']} | {len(g['members'])} | {c['effect']} (n={c['n']})"
                             f"{'' if c['clear'] else ', not clear'} | "
                             + (f"{100 * g['null']['changed']:.0f}%" if g.get("null") else "-") + " |")
            lines.append("")
        uns = [(i, x) for i, x in enumerate(labels) if x.get("kind") in ("event", "tracks") and not x.get("supported")]
        uns.sort(key=lambda t: -max(abs(t[1].get("phi", 0)), abs(t[1].get("r", 0))))
        if uns:
            lines += ["Correlated but not supported (untested, or no clear effect of the clamps):", ""]
            for i, x in uns[:12]:
                c = x.get("causal")
                lines.append(f"- {L['name']}.{i}: {x['role']} ({_evidence(x)})"
                             + (f"; tested n={c['n']}: move changed {100 * c['changed_off']:.0f}% silenced, "
                                f"{100 * c['changed_on']:.0f}% driven" if c else "; not tested"))
            if len(uns) > 12:
                lines.append(f"- and {len(uns) - 12} more")
            lines.append("")
        if n_mixed:
            lines += [f"Mixed ({n_mixed}): no single feature reaches |phi| or |r| {LABEL_MIN}; their best matches "
                      "are " + ", ".join(f"{k} ({v})" for k, v in _top_best(labels)) + ".", ""]
    return "\n".join(lines)


def _evidence(x):
    if x.get("kind") == "tracks":
        return f"r = {x['r']:+.2f}"
    s = f"phi = {x['phi']:+.2f}"
    if x.get("rate_with") is not None:
        s += f"; fires on {100 * x['rate_with']:.0f}% of positions with the event, {100 * x['rate_without']:.0f}% without"
    return s


def _top_best(labels):
    from collections import Counter

    return Counter(x["best"] for x in labels if x.get("mixed")).most_common(4)


# ---- main ------------------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--positions", type=int, default=5000, help="about this many settled positions")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--seed", type=int, default=9_100_000)
    ap.add_argument("--causal", type=int, default=20, help="neurons tested per layer (0: no causal check)")
    ap.add_argument("--quota", type=int, default=40, help="positions per tested neuron")
    a = ap.parse_args()
    warnings.filterwarnings("ignore")
    from cadence import Brain

    t0 = time.time()
    meta = json.loads(Path(a.meta).read_text())
    if meta.get("sense", "field") != "field":
        raise SystemExit("introspect reads full-field brains (meta sense 'field')")
    brain = Brain.load(a.brain, backend="cpu")
    n_in = field_size(N)
    if len(brain.connectome.populations["sensory"]) != n_in:
        raise SystemExit("the brain's inputs are not the full-field sense")
    layers, conns = layers_of(brain)
    games = max(10, a.positions // 200)  # about 200 positions a game (both seats, or both copies)
    plan = [("voronoi", games * 4 // 10), ("noisy", games * 3 // 10), ("self", games - games * 7 // 10)]
    split = []
    gi = 0
    for kind, k in plan:
        seeds = [(gi + i, a.seed + gi + i) for i in range(k)]
        gi += k
        step = max(1, (k + a.workers - 1) // a.workers)
        split += [(kind, seeds[lo:lo + step]) for lo in range(0, k, step)]
    with Pool(min(a.workers, len(split))) as pool:
        chunks = pool.map(play_chunk, [(a.brain, kind, sd, n_in, None, None, None) for kind, sd in split], chunksize=1)
    rows = [r for ch in chunks for r in ch["rows"]]
    t1 = time.time()
    game = np.array([r[0] for r in rows])
    moves = np.array([r[3] for r in rows])
    A = np.stack([r[5] for r in rows]).astype(np.float64)  # positions x non-sensory neurons
    F = np.array([[r[4][k] for k in FEATURES] for r in rows], dtype=np.float64)
    enames = list(EVENTS)
    E = np.array([[float(EVENTS[e][1](r[4])) for e in enames] for r in rows])
    teacher = np.array([r[4]["teacher"] for r in rows])
    rng = np.random.default_rng(0)
    ug = np.unique(game)
    test_games = set(rng.choice(ug, size=max(1, len(ug) // 5), replace=False).tolist())
    test = np.array([g in test_games for g in game])
    train = ~test

    # Roles per layer (the motor neurons are the moves).
    per_layer = {}
    for L in layers:
        lo = L["start"] - n_in
        idx = np.arange(lo, lo + L["count"])
        if L["kind"] == "motor":
            labs = [{"family": "motor", "kind": "move", "key": f"move_{MOVES[k] if k < 3 else k}",
                     "role": f"the move '{MOVES[k]}'" if k < 3 else f"motor {k}"} for k in range(L["count"])]
        else:
            labs = roles(A[:, idx], F, E, enames, FEATURES)
        per_layer[L["key"]] = labs

    # The causal check: the strongest roles of each layer, one at a time; every role shared by
    # at least three neurons of a layer, as a group; random neurons (and random groups of the
    # same sizes) on random positions as the nulls.
    tests = []
    thr_all = np.full(int(brain.connectome.n), np.inf)
    thr_all[n_in:] = 0.5 * (np.percentile(A, 5, axis=0) + np.percentile(A, 95, axis=0))
    if a.causal > 0:
        crng = np.random.default_rng(1)
        for L in layers:
            if L["kind"] == "motor":
                continue
            labs = per_layer[L["key"]]
            base = {"layer": L["key"], "quota": a.quota}
            cand = [(i, x) for i, x in enumerate(labs) if x.get("kind") in ("event", "tracks")]
            cand.sort(key=lambda t: -max(abs(t[1].get("phi", 0)), abs(t[1].get("r", 0))))
            for i, x in cand[: a.causal]:
                ev, when = (x["key"], x["when"]) if x["kind"] == "event" else (None, None)
                tests.append({**base, "id": f"{L['key']}:{i}", "neurons": [L["start"] + i], "event": ev, "when": when,
                              "fire": [L["start"] + i], "frac": 1.0, "p": 0.15})
            for i in crng.choice(L["count"], size=min(a.causal, L["count"]), replace=False):
                tests.append({**base, "id": f"{L['key']}:null:{int(i)}", "neurons": [L["start"] + int(i)],
                              "event": None, "when": None, "fire": [L["start"] + int(i)], "frac": 1.0, "p": 0.15,
                              "null": True})
            groups = {}
            for i, x in enumerate(labs):
                if x.get("kind") == "event":
                    groups.setdefault((x["key"], x["when"]), []).append(i)
            ranked = sorted(((k, v) for k, v in groups.items() if len(v) >= 3), key=lambda kv: -len(kv[1]))[:8]
            for (ev, when), members in ranked:
                gid = f"{L['key']}:group:{ev}:{int(when)}"
                tests.append({**base, "id": gid, "neurons": [L["start"] + i for i in members], "event": ev, "when": when,
                              "members": members})
                # The null group: as many neurons with firing rates like the members', tested where
                # as large a share of them fires as of the members on their event positions.
                rates = np.array([labs[i].get("fires", 0) for i in range(L["count"])])
                pool_i = [i for i in np.argsort(np.abs(rates - rates[members].mean())) if i not in members]
                rnd = crng.choice(pool_i[: max(3 * len(members), 30)], size=len(members), replace=False)
                lo_ = L["start"] - n_in
                fr = A[:, [lo_ + i for i in members]] > thr_all[[L["start"] + i for i in members]]
                evm = E[:, enames.index(ev)] > 0 if when else E[:, enames.index(ev)] == 0
                frac = float(np.clip(0.5 * (fr[evm].mean() if evm.any() else 0.5), 0.1, 0.5))
                tests.append({**base, "id": gid + ":null", "neurons": [L["start"] + int(i) for i in rnd], "event": None,
                              "when": None, "fire": [L["start"] + int(i) for i in rnd], "frac": frac, "p": 0.3,
                              "null": True})
    causal = {}
    mism = checked = fork_diff = 0
    if tests:
        # The first pass's moves by (game, seat, tick), to check the replay against.
        expect = {(r[0], r[6], r[2]): r[3] for r in rows if r[1] != "self2"}
        nj = max(1, len(split))
        jobs = []
        for kind, sd in split:
            tl = [{**t, "quota": max(2, -(-t["quota"] // nj) * 2)} for t in tests]
            exp = {k: v for k, v in expect.items() if k[0] in {g for g, _ in sd}}
            jobs.append((a.brain, kind, sd, n_in, tl, exp, thr_all))
        with Pool(min(a.workers, len(jobs))) as pool:
            res = pool.map(play_chunk, jobs, chunksize=1)
        allres = [x for ch in res for x in ch["results"]]
        mism = sum(ch["mismatches"] for ch in res)
        checked = sum(ch["checked"] for ch in res)
        fork_diff = sum(ch["fork_diff"] for ch in res)
        seen, kept = {}, []  # at most `quota` positions per test, in game order
        for x in allres:
            if seen.get(x[0], 0) < a.quota:
                seen[x[0]] = seen.get(x[0], 0) + 1
                kept.append(x)
        causal = summarize(kept)
    t2 = time.time()

    rf = fields(brain, layers, n_in)
    out_layers = []
    for L in layers:
        lo = L["start"] - n_in
        idx = np.arange(lo, lo + L["count"])
        labs = per_layer[L["key"]]
        null = null_of([causal[t["id"]] for t in tests if t["layer"] == L["key"] and t.get("null")
                        and ":group:" not in t["id"] and t["id"] in causal])
        tested = 0
        for i, x in enumerate(labs):
            c = causal.get(f"{L['key']}:{i}")
            if c is None:
                continue
            tested += 1
            x["causal"] = causal_entry(c, null)
            x["supported"] = x["causal"]["clear"]
        groups_out = []
        for t in tests:
            if t["layer"] != L["key"] or ":group:" not in t["id"] or t.get("null") or t["id"] not in causal:
                continue
            gnull = null_of([causal[t["id"] + ":null"]] if t["id"] + ":null" in causal else [])
            ce = causal_entry(causal[t["id"]], gnull, them=True)
            ev, when = t["event"], t["when"]
            text = EVENTS[ev][2] if when else (EVENTS[ev][3] or f"not: {EVENTS[ev][2]}")
            groups_out.append({"event": ev, "when": bool(when), "role": f"fires when {text}", "members": t["members"],
                               "causal": ce, "null": gnull})
        AL = A[:, idx]
        AL = A[:, idx]
        probes = []
        for key, title, kind in PROBES:
            y = teacher.astype(float) if key == "teacher" else F[:, FEATURES.index(key)]
            p = fit_probe(AL, y, kind, train, test, rng)
            probes.append({"key": key, "title": title, "kind": kind,
                           "w": [[float(f"{v:.5g}") for v in col] for col in p["W"].T],
                           "b": [float(f"{v:.6g}") for v in p["b"]],
                           "score": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p["score"].items()},
                           "lam": p["lam"],
                           **({"range": [round(v, 4) for v in p["range"]]} if "range" in p else {})})
        q, scale = pack_int8(rf[L["pop"]])
        out_layers.append({**L, "labels": labs, "probes": probes, "rf": q, "rf_scale": scale,
                           "causal_null": null, "causal_tested": tested, "groups": groups_out,
                           "act_lo": [round(float(v), 4) for v in np.percentile(AL, 5, axis=0)],
                           "act_hi": [round(float(v), 4) for v in np.percentile(AL, 95, axis=0)]})

    def count(L, pred):
        return sum(1 for x in L["labels"] if pred(x))
    report = {
        "schema": "cadence-tron-introspect/2",
        "brain": meta.get("name"), "title": meta.get("title"), "brain_file": Path(a.brain).name,
        "inputs": n_in, "retina": retina(N), "neurons": int(brain.connectome.n),
        "layers": out_layers, "connections": conns,
        "events": {k: {"family": v[0], "text": v[2], "opposite": v[3]} for k, v in EVENTS.items()},
        "tracks": {k: {"family": v[0], "text": v[1], "opposite": v[2]} for k, v in TRACKS.items()},
        "families": FAMILIES, "label_min": LABEL_MIN,
        "positions": {"total": int(len(rows)), "train": int(train.sum()), "test": int(test.sum()),
                      "games": int(len(ug)), "test_games": len(test_games),
                      "kinds": {k: int(sum(1 for r in rows if r[1] == k)) for k in ("voronoi", "noisy", "self", "self2")},
                      "seeds": f"{a.seed}+", "brain_moves": np.bincount(moves, minlength=3).tolist(),
                      "agree_with_teacher": round(float((moves == teacher).mean()), 3)},
        "causal": {"per_layer": a.causal, "quota": a.quota, "clamp_bias": CLAMP,
                   "replay_checked": checked, "replay_mismatches": mism, "fork_unclamped_differs": fork_diff},
        "summary": {L["key"]: {"neurons": L["count"],
                               "roles": count(L, lambda x: x.get("kind") in ("event", "tracks")),
                               "tested": L["causal_tested"], "supported": count(L, lambda x: x.get("supported")),
                               "groups": len(L["groups"]), "groups_clear": sum(1 for g in L["groups"] if g["causal"]["clear"]),
                               "mixed": count(L, lambda x: x.get("mixed")), "silent": count(L, lambda x: x.get("silent")),
                               "probes": {p["key"]: p["score"] for p in L["probes"]}} for L in out_layers},
        "wall_s": {"play": round(t1 - t0, 1), "causal": round(t2 - t1, 1), "total": round(time.time() - t0, 1)},
    }
    out = Path(a.out)
    out.write_text(json.dumps(report, separators=(",", ":")))
    (out.parent / "ROLES.md").write_text(roles_md(report))
    print(json.dumps({"out": str(out), "bytes": out.stat().st_size, "positions": report["positions"],
                      "causal": report["causal"], "summary": report["summary"], "wall_s": report["wall_s"]}, indent=1))


if __name__ == "__main__":
    main()
