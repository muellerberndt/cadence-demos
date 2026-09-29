"""Collect teacher witnesses in parallel: (periphery, fovea) -> buttons.

Each worker owns one DoomLab and plays whole episodes with the scripted
privileged teacher. Stored witnesses contain only what the student may see
(the two grayscale retinas) plus the teacher's chosen buttons. Episode
receipts retain the privileged run statistics separately.

Usage: python collect.py --episodes 30 --checks 6 --workers 8 --out data/run1
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import random

import numpy as np

from doomlab import DoomLab, Teacher, FRAME_SKIP, brain_view
from wadmap import build_route_v3


def run_episode(job):
    seed, doom_map = job
    route = build_route_v3(doom_map, rng=random.Random(seed))
    lab = DoomLab(doom_map=doom_map)
    try:
        lab.game.set_seed(seed)
        lab.new_episode()
        teacher = Teacher(route=route)
        periphery, fovea, buttons, efference = [], [], [], []
        health, ammo, kills = [], [], []
        previous = np.zeros(8, np.int8)
        while not lab.finished:
            state = lab.state()
            if state is None:
                break
            v = state.game_variables
            per, fov = brain_view(state.screen_buffer)
            act = teacher.act(state, (v[3], v[4]), angle=v[5])
            periphery.append(per.astype(np.float32).ravel())
            fovea.append(fov.astype(np.float32).ravel())
            buttons.append(np.asarray(act, np.int8))
            efference.append(previous.copy())
            health.append(v[0]); ammo.append(v[2]); kills.append(v[1])
            previous = np.asarray(act, np.int8)
            lab.act(act, FRAME_SKIP)
        import vizdoom as vzd
        gv = lab.game.get_game_variable
        stats = {
            "seed": seed,
            "map": doom_map,
            "decisions": len(buttons),
            "kills": gv(vzd.GameVariable.KILLCOUNT),
            "health": gv(vzd.GameVariable.HEALTH),
            "ammo": gv(vzd.GameVariable.AMMO2),
        }
        return (np.stack(periphery), np.stack(fovea), np.stack(buttons),
                np.stack(efference),
                np.asarray(health, np.float32), np.asarray(ammo, np.float32),
                np.asarray(kills, np.float32), stats)
    finally:
        lab.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--checks", type=int, default=6,
                        help="episodes reserved for readiness checks")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--maps", default="E1M1")
    parser.add_argument("--out", default="data/run1")
    args = parser.parse_args()
    maps = args.maps.split(",")
    total = args.episodes + args.checks
    jobs = [(args.seed + i, maps[i % len(maps)]) for i in range(total)]
    started = time.perf_counter()
    if args.workers == 1:
        results = [run_episode(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=min(args.workers, total),
                                 mp_context=get_context("spawn")) as pool:
            results = list(pool.map(run_episode, jobs))
    os.makedirs(args.out, exist_ok=True)
    stats = [r[-1] for r in results]
    episode_ids = np.concatenate([
        np.full(len(r[2]), i, np.int32) for i, r in enumerate(results)])
    np.savez_compressed(
        os.path.join(args.out, "witnesses.npz"),
        periphery=np.concatenate([r[0] for r in results]),
        fovea=np.concatenate([r[1] for r in results]),
        buttons=np.concatenate([r[2] for r in results]),
        efference=np.concatenate([r[3] for r in results]),
        health=np.concatenate([r[4] for r in results]),
        ammo=np.concatenate([r[5] for r in results]),
        kills=np.concatenate([r[6] for r in results]),
        episode=episode_ids,
        episode_map=np.array([s["map"] for s in stats]),
        check_episodes=np.arange(args.episodes, total, dtype=np.int32),
    )
    receipt = {
        "elapsed_seconds": time.perf_counter() - started,
        "frame_skip": FRAME_SKIP,
        "episodes": stats,
        "teacher": "scripted privileged v2 (labels+depth+auto-shuffled routes)",
        "maps": maps,
        "decisions": int(len(episode_ids)),
        "mean_kills": float(np.mean([s["kills"] for s in stats])),
        "deaths": int(sum(1 for s in stats if s["health"] <= 0)),
    }
    with open(os.path.join(args.out, "collect_receipt.json"), "w") as f:
        json.dump(receipt, f, indent=2)
    print(json.dumps({k: receipt[k] for k in
                      ("elapsed_seconds", "decisions", "mean_kills", "deaths")}))


if __name__ == "__main__":
    main()
