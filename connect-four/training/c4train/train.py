"""Teach a Connect Four policy from the perfect solver, on its own positions too.

    python -m c4train.train --arm cadence --modules 512 --lessons 20000 --out runs/c512_sur_s0

A pool of positions from games of the solver against itself (strength .5 to 1.0, short random
openings; each position also mirrored) is labelled with the centre-most optimal column. Lessons
draw batches from the pool. Every ``--own-every`` lessons the policy plays ``--own-games`` games
against the solver and the positions it faced join the pool, labelled the same way (the
own-path recipe: lessons where the policy actually goes). Every ``--eval-every`` lessons the
held-out positions are read, and every ``--games-every`` games against the perfect solver.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .evaluate import Heldout, games
from .imagine import finished, imagined
from .positions import arrays, noisy_game, own_game
from .solver import INVALID, Solver, label
from .tactics import tactics


def build_pool(solver, rng, count):
    items = []
    while len(items) < count:
        items += noisy_game(solver, rng, strength=float(rng.uniform(0.5, 1.0)))
    return items


def first_choosers(policy, verdict: bool = False):
    """The brain alone, and with a verdict slot the brain imagining each move and judging the
    board it pictures: no rule judges its moves."""
    out = [("brain", policy.choose)]
    if verdict:
        out.append(("imagined", imagined(policy)))
    return out


def keeps_best(scores: np.ndarray, chosen: np.ndarray) -> np.ndarray:
    """Whether each chosen column is score-maximal (the solver's optimal set)."""
    best = np.where(scores == INVALID, -10_000, scores).max(axis=1)
    return scores[np.arange(len(chosen)), chosen] == best


def keeps(scores: np.ndarray, chosen: np.ndarray) -> np.ndarray:
    """Whether each chosen column keeps the position's theoretical result."""
    best = np.where(scores == INVALID, -10_000, scores).max(axis=1)
    got = scores[np.arange(len(chosen)), chosen]
    return (got != INVALID) & (np.sign(got) == np.sign(best))


def keep_columns(scores: np.ndarray) -> np.ndarray:
    """``(n, 7)``: the playable columns that keep each position's theoretical result."""
    best = np.where(scores == INVALID, -10_000, scores).max(axis=1, keepdims=True)
    keep = (scores != INVALID) & (np.sign(scores) == np.sign(best))
    # a lost position: every column keeps the loss; the ones that delay it longest are taught
    return np.where(best < 0, scores == best, keep)


def first_games(choose, solver, count: int, seed: int, policy_first: bool = True,
                strength: float = 1.0) -> dict:
    """``count`` games from the empty board against the solver at ``strength`` (its optimal
    replies, ties at random; below 1 a share of random moves), the policy first or second:
    wins, draws, losses and blunder-free games."""
    rng = np.random.default_rng(seed)
    results = {"win": 0, "draw": 0, "loss": 0}
    clean = 0
    for _ in range(count):
        game = own_game(choose, solver, rng, strength, policy_first=policy_first, opening=0)
        results[game["result"]] += 1
        clean += int(game["qualities"].count("blunder") == 0)
    return {"games": count, **results, "blunder_free_games": clean / max(count, 1)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=("cadence", "mlp"), default="cadence")
    p.add_argument("--modules", type=int, nargs="+", default=[512])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--every-row", action="store_true", help="teach every row (default: only wrong rows)")
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--pool", type=int, default=50_000, help="initial positions before mirroring")
    p.add_argument("--lessons", type=int, default=20_000)
    p.add_argument("--own-every", type=int, default=500)
    p.add_argument("--own-games", type=int, default=64)
    p.add_argument("--eval-every", type=int, default=1000)
    p.add_argument("--games-every", type=int, default=5000)
    p.add_argument("--rate", type=float, default=1e-3, help="MLP Adam rate")
    p.add_argument("--retune", type=json.loads, default={},
                   help="Brain.retune settings applied after composing or loading, as JSON "
                        "(e.g. {\"eta_scale\": 0.33}: both learning rates scaled)")
    p.add_argument("--eta-scale", type=float, default=None,
                   help="scale both learning rates of the composed or loaded brain (as --retune eta_scale)")
    p.add_argument("--pool-file", type=Path, nargs="+", default=None,
                   help="a shared pool from gen_pool (packed inputs and scores; mirrored here)")
    p.add_argument("--games", type=int, default=40, help="games per strength at each games reading")
    p.add_argument("--genes", type=json.loads, default={},
                   help="extra Brain.compose options for the Cadence arm, as JSON")
    p.add_argument("--apical", type=float, default=0.0, help="Brain.compose(apical=F)")
    p.add_argument("--relative", type=float, default=0.0, help="learning_normalize_relative")
    p.add_argument("--tolerance", type=float, default=0.0, help="learning_tolerance (0: the founder)")
    p.add_argument("--nudged-steps", type=int, default=0, help="learning_nudged_steps (0: the founder)")
    p.add_argument("--free-steps", type=int, default=0, help="learning_free_steps (0: the founder)")
    p.add_argument("--backend", default="cpu", help="cpu or torch")
    p.add_argument("--device", default=None, help="torch device, e.g. cuda:0")
    p.add_argument("--precision", default=None, help="float32: the torch state in float32 (set at load)")
    p.add_argument("--apical-readout", type=int, default=1,
                   help="0: the readout pair stays tied; only pairs between processing regions are apical")
    p.add_argument("--nudged-fixed", action="store_true", help="nudged phases run their whole budget")
    p.add_argument("--chain-scale", type=float, default=1.0, help="multiply every chain projection at birth")
    p.add_argument("--skip", action="store_true", help="sensory -> every module above the first, one way")
    p.add_argument("--frozen-gain", action="store_true", help="nudged phases keep the free phase's apical gain")
    p.add_argument("--init", type=Path, default=None, help="start from a saved brain (policy.npz)")
    p.add_argument("--first-games", type=int, default=0,
                   help="games the policy plays first from the empty board at each own round")
    p.add_argument("--first-weight", type=int, default=1,
                   help="copies of each first-game position added to the pool")
    p.add_argument("--first-eval", type=int, default=0,
                   help="first-move games from the empty board against the perfect solver per reading")
    p.add_argument("--patience", type=int, default=0,
                   help="stop after this many readings without a new best optimal share (0: never)")
    p.add_argument("--anneal", type=int, default=0,
                   help="at a plateau (--patience readings without a gain) scale both learning "
                        "rates by --anneal-factor and go on, this many times, before stopping")
    p.add_argument("--anneal-factor", type=float, default=0.33)
    p.add_argument("--min-delta", type=float, default=0.002,
                   help="the gain over the best reading that counts as an improvement")
    p.add_argument("--verdict", action="store_true",
                   help="a second motor slot taught the solver's verdict for the mover (loss, draw, win)")
    p.add_argument("--planes", type=int, default=2, choices=(2, 3),
                   help="3: a third input plane of the playable cells (Cadence arm)")
    p.add_argument("--target", choices=("best", "keep", "keepwin"), default="best",
                   help="keep: where the brain's own choice keeps the result it is the label, "
                        "elsewhere the centre-most optimal column; keepwin: as keep, but a position "
                        "with a win now is labelled with the winning column (a slower win keeps the "
                        "result too, so keep never teaches taking it)")
    p.add_argument("--soft", type=float, default=0.0,
                   help="teach targets= (0.95.1): this share of each move row spread evenly over the "
                        "columns that keep the result (the winning columns where one wins now), the "
                        "rest on the label; the verdict slot one-hot")
    p.add_argument("--tactics-weight", type=float, default=1.0,
                   help="lesson weights= (0.95.1): rows with a win now or a forced block weigh this much")
    p.add_argument("--slip-weight", type=int, default=0,
                   help="extra copies of each own-game position where the brain's choice slipped")
    p.add_argument("--patience-on", choices=("optimal", "keep", "score"), default="optimal",
                   help="the reading that patience and policy_best.npz follow (keep: the share of "
                        "moves keeping the result where the mover is not already lost; score: keep "
                        "+ 0.25 x (wins_now + blocks))")
    p.add_argument("--terminal-share", type=float, default=0.0,
                   help="with --verdict: share of each batch replaced by boards just won, seen by "
                        "the loser (verdict: loss; move label: the brain's own choice)")
    p.add_argument("--tactics-share", type=float, default=0.0,
                   help="share of each batch drawn from positions with a win now or a forced block")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.genes = dict(a.genes)
    for flag, gene in (("apical", "apical"), ("relative", "learning_normalize_relative"),
                       ("tolerance", "learning_tolerance"), ("nudged_steps", "learning_nudged_steps"),
                       ("free_steps", "learning_free_steps")):
        if getattr(a, flag):
            a.genes[gene] = getattr(a, flag)
    if a.backend != "cpu":
        a.genes["backend"] = "torch" if a.backend == "torch" else a.backend
        if a.device:
            a.genes["device"] = a.device
    a.out.mkdir(parents=True, exist_ok=True)
    import os
    cache = Path(os.environ.get("C4_CACHE", Path(__file__).resolve().parents[1] / "runs" / "solver_cache.pkl"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    solver = Solver(cache=cache)
    rng = np.random.default_rng(a.seed)
    t0 = time.time()
    heldout = Heldout(solver)
    if a.pool_file:
        parts = [np.load(f) for f in a.pool_file]
        x = np.concatenate([np.unpackbits(d["bits"], axis=1)[:, :84] for d in parts]).astype(np.uint8)  # 0/1; float per batch
        scores = np.concatenate([d["scores"] for d in parts]).astype(np.int64)
        mirror = x.reshape(-1, 2, 6, 7)[:, :, :, ::-1].reshape(-1, 84)
        x, scores = np.concatenate([x, mirror]), np.concatenate([scores, scores[:, ::-1]])
        occupied = x.reshape(-1, 2, 6, 7).any(axis=1)
        legal = ~occupied[:, 5, :]
        stones = x.sum(axis=1).astype(int)
    else:
        items = build_pool(solver, rng, a.pool)
        x, scores, legal, stones = arrays(items)
    def labels(rows):
        moves = np.array([label(r) for r in rows])
        if not a.verdict:
            return moves
        best = np.array([int(r[r != INVALID].max()) for r in rows])
        return np.stack([moves, np.sign(best) + 1], axis=1)  # 0 loss, 1 draw, 2 win

    y = labels(scores)
    solver.save()
    if a.arm == "cadence":
        from .policy import CadencePolicy
        policy = CadencePolicy(modules=a.modules, seed=a.seed, surprise=not a.every_row,
                               apical_readout=bool(a.apical_readout), nudged_fixed=a.nudged_fixed,
                               chain_scale=a.chain_scale, skip=a.skip, frozen_gain=a.frozen_gain,
                               inputs=84 if a.planes == 2 else 126, verdict=a.verdict, **a.genes)
    else:
        from .policy import MLPPolicy
        policy = MLPPolicy(hidden=tuple(a.modules), seed=a.seed, rate=a.rate)
    if a.init is not None:
        # the saved brain replaces the composed one: its weights, compartment and learner settings
        from cadence import Brain
        placed = {k: a.genes[k] for k in ("backend", "device") if k in a.genes}
        policy.brain = Brain.load(a.init, precision=a.precision, **placed)
    elif a.precision and a.arm == "cadence":
        # precision is chosen at load: the composed brain is saved and loaded at it
        from cadence import Brain
        placed = {k: a.genes[k] for k in ("backend", "device") if k in a.genes}
        policy.brain.save(a.out / "policy_composed.npz")
        policy.brain = Brain.load(a.out / "policy_composed.npz", precision=a.precision, **placed)
    if a.eta_scale is not None:
        a.retune = {**a.retune, "eta_scale": a.eta_scale}
    if a.retune and a.arm == "cadence":
        settings = dict(a.retune)
        scale = settings.pop("eta_scale", None)
        if scale is not None:
            # normalized teaching owns eta: the whole learner config is replaced by a copy with
            # both rates scaled, the optimizer history kept
            from dataclasses import replace
            config = policy.brain.learner.config
            settings["learning"] = replace(config, eta=config.eta * scale, eta_bias=config.eta_bias * scale)
        policy.brain.retune(**settings)
    if a.planes == 3:
        from .policy import Planes
        policy = Planes(policy)
    def plain(v):
        return [plain(u) for u in v] if isinstance(v, list) else (str(v) if isinstance(v, Path) else v)

    receipt = {"args": {k: plain(v) for k, v in vars(a).items()},
               "size": policy.size(), "pool_start": int(len(x)), "curve": [], "games": []}
    print(json.dumps({"start": receipt["size"], "pool": len(x), "setup_s": round(time.time() - t0, 1)}), flush=True)
    taught = offered = 0
    best_optimal, stale, slips_added = -1.0, 0, 0
    tactical = np.flatnonzero(np.concatenate(tactics(x), axis=1).any(axis=1))
    held_win, held_block = tactics(heldout.x)
    not_lost = np.where(heldout.scores == INVALID, -10_000, heldout.scores).max(axis=1) >= 0
    for lesson in range(1, a.lessons + 1):
        idx = rng.integers(0, len(x), a.batch)
        if a.tactics_share > 0 and len(tactical):
            k = int(round(a.tactics_share * a.batch))
            idx[:k] = tactical[rng.integers(0, len(tactical), k)]
        labels_now = y[idx]
        win_now, block_now = tactics(x[idx])
        if a.target in ("keep", "keepwin"):
            # a column that keeps the result is as right as the solver's fastest one
            own = policy.choose_x(x[idx], legal[idx])
            ok = keeps(scores[idx], own)
            if a.target == "keepwin":  # but a win now is taken now
                ok &= ~win_now.any(axis=1)
            labels_now = labels_now.copy()
            if labels_now.ndim == 2:
                labels_now[:, 0] = np.where(ok, own, labels_now[:, 0])
            else:
                labels_now = np.where(ok, own, labels_now)
        weights_now = np.where((win_now | block_now).any(axis=1), a.tactics_weight, 1.0)
        x_now = x[idx].astype(float)
        n_done = 0
        if a.verdict and a.terminal_share > 0:
            k = int(round(a.terminal_share * a.batch))
            done = finished(x[tactical[rng.integers(0, len(tactical), 2 * k)]], rng)[:k]
            n_done = len(done)
            if len(done):
                legal_done = ~(done.reshape(-1, 2, 6, 7).any(axis=1)[:, 5, :])
                legal_done[~legal_done.any(axis=1), 3] = True  # a full board: any slot will do
                own_done = policy.choose_x(done, legal_done)
                # the finished boards take the batch's last rows; the tactical rows lead it
                x_now = np.concatenate([x_now[:-len(done)], done])
                labels_now = np.concatenate([labels_now[:-len(done)],
                                             np.stack([own_done, np.zeros(len(done), dtype=own_done.dtype)], axis=1)])
                weights_now = np.concatenate([weights_now[:-len(done)], np.ones(len(done))])
        targets_now = None
        if a.soft > 0:
            n = len(labels_now)
            move = labels_now[:, 0] if labels_now.ndim == 2 else labels_now
            sc = scores[idx][:n]
            wins = win_now[:n]
            spread = np.where(wins.any(axis=1, keepdims=True), wins, keep_columns(sc)).astype(float)
            if n_done:  # the finished boards in the batch's last rows: their label alone
                spread[-n_done:] = 0.0
            hard = np.eye(7)[move]
            has = spread.sum(axis=1, keepdims=True) > 0
            spread = np.where(has, spread / np.maximum(spread.sum(axis=1, keepdims=True), 1), hard)
            dist = (1 - a.soft) * hard + a.soft * spread
            if labels_now.ndim == 2:
                dist = np.concatenate([dist, np.eye(3)[labels_now[:, 1]]], axis=1)
            targets_now = dist
        report = policy.teach(x_now, labels_now, targets=targets_now,
                              weights=weights_now if a.tactics_weight != 1.0 else None)
        offered += a.batch
        taught += int(round(report.get("accepted_presentations", a.batch)))
        if a.own_every and lesson % a.own_every == 0:
            faced = []
            for g in range(a.own_games):
                game = own_game(policy.choose, solver, rng, float(rng.uniform(0.7, 1.0)),
                                policy_first=bool(g % 2 == 0))
                faced += game["faced"]
            for g in range(a.first_games):
                # the policy first from the empty board, the solver answering at its best (ties at
                # random) or nearly: the positions a winning first player has to get right
                strength = 1.0 if rng.random() < 0.7 else float(rng.uniform(0.9, 1.0))
                game = own_game(policy.choose, solver, rng, strength, policy_first=True, opening=0)
                faced += game["faced"] * max(1, a.first_weight)
            if faced:
                fx, fs, fl, fst = arrays(faced)
                if a.slip_weight and hasattr(policy, "choose_x"):
                    slipped = ~keeps(fs, policy.choose_x(fx, fl))
                    rows = np.r_[np.arange(len(fx)), np.repeat(np.flatnonzero(slipped), a.slip_weight)]
                    fx, fs, fl, fst = fx[rows], fs[rows], fl[rows], fst[rows]
                    slips_added += int(slipped.sum())
                start = len(x)
                x, scores, legal, stones = (np.concatenate([x, fx.astype(x.dtype)]), np.concatenate([scores, fs]),
                                            np.concatenate([legal, fl]), np.concatenate([stones, fst]))
                new = np.flatnonzero(np.concatenate(tactics(fx), axis=1).any(axis=1)) + start
                tactical = np.concatenate([tactical, new])
                y = np.concatenate([y, labels(fs)])
        if lesson % a.eval_every == 0:
            reading = heldout.read(policy)
            if a.verdict:
                truth = np.array([int(np.sign(r[r != INVALID].max())) + 1 for r in heldout.scores])
                judged = np.concatenate([policy.verdict(heldout.x[i:i + 512]).argmax(axis=1)
                                         for i in range(0, len(heldout.x), 512)])
                reading["verdict"] = round(float(np.mean(judged == truth)), 4)
                seen = imagined(policy).choose_x(heldout.x, heldout.legal)
                rows_i = np.arange(len(seen))
                imag = {"optimal": round(float(np.mean(keeps_best(heldout.scores, seen))), 4),
                        "keep_not_lost": round(float(keeps(heldout.scores, seen)[not_lost].mean()), 4)}
                for name, mask in (("wins_now", held_win), ("blocks", held_block)):
                    need = mask.any(axis=1)
                    imag[name] = round(float(mask[rows_i, seen][need].mean()), 4)
                reading["imagined"] = imag
            if hasattr(policy, "choose_x"):
                chosen = policy.choose_x(heldout.x, heldout.legal)
                rows = np.arange(len(chosen))
                for name, mask in (("wins_now", held_win), ("blocks", held_block)):
                    need = mask.any(axis=1)
                    reading[name] = round(float(mask[rows, chosen][need].mean()), 4)
            reading["keep_not_lost"] = round(1.0 - float(reading["blunder_not_lost"]), 4)
            row = {"lesson": lesson, "pool": int(len(x)), "taught_share": round(taught / max(offered, 1), 3),
                   "slips_added": slips_added, "seconds": round(time.time() - t0, 1), **reading,
                   **(policy.drain_work() if hasattr(policy, "drain_work") else {})}
            receipt["curve"].append(row)
            taught = offered = 0
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()
                              if not isinstance(v, dict)}), flush=True)
            if a.games_every and lesson % a.games_every == 0:
                for strength in (1.0, 0.9):
                    r = games(policy, solver, a.games, strength, seed=777 + lesson)
                    receipt["games"].append({"lesson": lesson, **r})
                    print(json.dumps({"lesson": lesson, **r}), flush=True)
                if a.first_eval:
                    for name, choose in first_choosers(policy, a.verdict):
                        # first against the perfect solver; second against it at 0.9, where
                        # its mistakes give the policy wins to convert
                        for first, strength in ((True, 1.0), (False, 0.9)):
                            r = first_games(choose, solver, a.first_eval, seed=991 + lesson,
                                            policy_first=first, strength=strength)
                            first_row = {"lesson": lesson, "chooser": name, "policy_first": first, **r,
                                         "strength": strength}
                            receipt.setdefault("first", []).append(first_row)
                            print(json.dumps(first_row), flush=True)
            solver.save()
            (a.out / "receipt.json").write_text(json.dumps(receipt, indent=1))
            policy.save(a.out / "policy.npz")
            # keep the best brain so far; stop once readings stop improving
            followed = (row["optimal"] if a.patience_on == "optimal" else row["keep_not_lost"]
                        if a.patience_on == "keep" else
                        row["keep_not_lost"] + 0.25 * (row.get("wins_now", 0) + row.get("blocks", 0)))
            if followed > best_optimal + a.min_delta:
                best_optimal, stale = followed, 0
                policy.save(a.out / "policy_best.npz")
                receipt["best"] = {"lesson": lesson, "optimal": row["optimal"],
                                   "keep_not_lost": row["keep_not_lost"], "wins_now": row.get("wins_now"),
                                   "blocks": row.get("blocks"), "verdict": row.get("verdict"), "followed": followed}
            else:
                stale += 1
            if a.patience and stale >= a.patience and a.anneal > len(receipt.get("anneals", [])):
                from dataclasses import replace
                config = policy.brain.learner.config
                policy.brain.retune(learning=replace(config, eta=config.eta * a.anneal_factor,
                                                     eta_bias=config.eta_bias * a.anneal_factor))
                receipt.setdefault("anneals", []).append(
                    {"lesson": lesson, "eta": policy.brain.learner.config.eta})
                print(json.dumps({"annealed": receipt["anneals"][-1]}), flush=True)
                stale = 0
            elif a.patience and stale >= a.patience:
                receipt["stopped"] = {"lesson": lesson, "reason": f"{stale} readings without a gain of {a.min_delta}"}
                print(json.dumps(receipt["stopped"]), flush=True)
                break
    receipt["refused"] = getattr(policy, "refused", 0)
    receipt["seconds"] = round(time.time() - t0, 1)
    (a.out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    policy.save(a.out / "policy.npz")
    solver.close()


if __name__ == "__main__":
    main()
