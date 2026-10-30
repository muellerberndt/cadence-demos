"""The live reward refinement (stage 2b, d): an imitation checkpoint goes on as a living brain
under reward alone.

    python -m arm2.live --from runs/stage2-20261030/D3b_s1/brain.npz --out runs/stage2b/L_D3b_s1 --seed 1

Every decision ``Brain.live(x, reward=, done=)``: the reward of the preceding action (+1 a
release in the right bin, -0.25 the wrong bin, -0.1 a drop or a slip, else 0), ``done`` at a
placement; the actor's step ``--actor-eta`` (0.001), arousal on (a calm moment is a greedy
settle that learns nothing; surprise, pain and reward raise the arousal and the brain learns
from every outcome), no teacher labels and no lessons. The cells restart on placement or at the
cap with no warm start. Readings as in ``arm2.train`` (``arm2.inspect`` on the frozen
checkpoint, in a separate process); the imitation checkpoint itself is the control, read on the
same fresh seeds in the readings' ``newborn`` slot (``imitation.npz``).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import time
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import cadence
import mujoco
import numpy as np
from cadence import Brain

from .actions import slots_of
from .pool import CellPool, LocalPool
from .scene import PHYSICS
from .senses import inputs, layout
from .train import reading, render

REWARD = {"right": 1.0, "wrong": -0.25, "dropped": -0.1, "slipped": -0.1}


def reward_of(event: str) -> float:
    if event.startswith("placed"):
        return REWARD["right"] if event.endswith("right") else REWARD["wrong"]
    return REWARD.get(event, 0.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--from", dest="source", required=True, help="the imitation checkpoint (brain.npz)")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cells", type=int, default=64)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--episodes", type=int, default=100)
    p.add_argument("--decisions", type=int, default=80)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--actor-eta", dest="actor_eta", type=float, default=0.001)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--no-velocity", dest="no_velocity", action="store_true")
    p.add_argument("--physics", choices=("nominal", "wide"), default="nominal")
    p.add_argument("--heldout-set", dest="heldout_set", choices=("heldout", "heldout2"), default=None)
    p.add_argument("--senses", choices=("basic", "slip"), default="basic")
    p.add_argument("--inspect-every", dest="inspect_every", type=int, default=10)
    p.add_argument("--inspect-trials", dest="inspect_trials", type=int, default=40)
    p.add_argument("--fresh-every", dest="fresh_every", type=int, default=50)
    p.add_argument("--fresh-trials", dest="fresh_trials", type=int, default=200)
    p.add_argument("--no-render", dest="no_render", action="store_true")
    p.add_argument("--mlp-control", dest="mlp_control", default=None)
    p.add_argument("--reading-timeout", dest="reading_timeout", type=int, default=10_800)
    p.add_argument("--report-every", dest="report_every", type=int, default=5)
    p.add_argument("--backend", default="cpu")
    p.add_argument("--device", default=None)
    a = p.parse_args()
    a.heldout_set = a.heldout_set or ("heldout" if a.physics == "nominal" else "heldout2")
    velocity, slip = not a.no_velocity, a.senses == "slip"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = slots_of(a.pools)
    pool = (CellPool(a.cells, a.workers, a.seed, a.physics, a.pools, velocity, a.cap, slip) if a.workers > 0
            else LocalPool(a.cells, a.seed, a.physics, a.pools, velocity, a.cap, slip))
    brain = Brain.load(a.source, backend=a.backend, device=a.device)
    if len(brain.sensory_index) != inputs(a.pools, slip):
        raise SystemExit(f"the checkpoint reads {len(brain.sensory_index)} inputs; --senses {a.senses} gives {inputs(a.pools, slip)}")
    brain.retune(actor_eta=a.actor_eta)
    # arousal is composed at construction (retune cannot switch it on): a checkpoint composed with
    # --arousal runs Brain.live (calm moments learn nothing); one without runs Brain.step, the
    # reward-driven loop without the gate
    gated = brain.arousal is not None
    moment = brain.live if gated else brain.step
    if gated and a.cells != 1:
        raise SystemExit("a brain with arousal lives one continuing stream (Brain.live takes one row): use --cells 1 --workers 0; "
                         "a checkpoint without arousal runs the batched Brain.step instead")
    checkpoint, best_path, imitation = out / "brain.npz", out / "brain_best.npz", out / "imitation.npz"
    shutil.copy(a.source, imitation)
    brain.save(checkpoint)
    a.newborn = str(imitation)  # the control the readings carry (a string: the receipt is JSON)
    meta = {"stage": "live", "source": str(a.source), "pools": a.pools, "slots": list(slots), "settings": vars(a),
            "layout": layout(a.pools, slip), "velocity": velocity, "workers": pool.workers, "physics": PHYSICS,
            "reward": REWARD, "arousal_gated": gated, "cadence": cadence.__version__, "mujoco": mujoco.__version__, "numpy": np.__version__,
            "python": platform.python_version(), "machine": platform.machine(), "threads": os.environ.get("NUMBA_NUM_THREADS"),
            "notes": ["Brain.live with the preceding action's reward; no lessons; the imitation checkpoint is the readings' newborn slot"]}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    receipt: dict = {"settings": vars(a), "curve": [], "steps": [{"actor_eta": a.actor_eta}]}
    fresh_count = 0

    def fresh_seed(k: int) -> int:
        return 80_000 + 1000 * a.seed + 10 * k

    def selection(episode: int) -> dict:
        return reading("selection", checkpoint, a, episode, 30_000 + a.seed, a.inspect_trials, False, None, out)

    def fresh(episode: int) -> dict:
        nonlocal fresh_count
        fresh_count += 1
        r = reading("fresh", checkpoint, a, episode, fresh_seed(fresh_count), a.fresh_trials, True, imitation, out)
        if not a.no_render:
            render(checkpoint, a, episode, out)
        return r

    def score(r: dict) -> tuple:
        b = r.get("brain") or {}
        return (b.get("right") or 0.0, b.get("grasped") or 0.0, b.get("reached") or 0.0)

    best = score(selection(0))
    brain.save(best_path)
    t0 = time.time()
    window: list[dict] = []
    for episode in range(1, a.episodes + 1):
        pool.warm(0.0, 0)
        brain.reset()
        reward = np.zeros(a.cells)
        done = np.zeros(a.cells, dtype=bool)
        jobs = rights = wrongs = grasps = drops = 0
        total_reward = 0.0
        ms = {"live": 0.0, "world": 0.0, "labels": 0.0}
        aroused = 0.0
        for d in range(a.decisions):
            t = time.perf_counter()
            x, _labels = pool.sense()
            ms["labels"] += time.perf_counter() - t
            t = time.perf_counter()
            # the stream's first decision has no preceding action to credit: no feedback with it
            answer = np.asarray(moment(x) if d == 0 else moment(x, reward=reward, done=done), dtype=np.int64)
            ms["live"] += time.perf_counter() - t
            state = getattr(brain, "last_arousal", None)
            if isinstance(state, dict) and "aroused" in state:
                aroused += float(np.mean(state["aroused"]))
            t = time.perf_counter()
            counts = pool.act(answer, 0.0, 0)
            ms["world"] += time.perf_counter() - t
            events = counts["events"]
            reward = np.array([reward_of(e) for e in events])
            done = np.array([e.startswith("placed") for e in events])
            total_reward += float(reward.sum())
            jobs, rights, wrongs = jobs + counts["jobs"], rights + counts["rights"], wrongs + counts["wrongs"]
            grasps, drops = grasps + counts["grasps"], drops + counts["drops"]
        n = a.decisions
        window.append({"jobs": jobs, "right": rights / max(jobs, 1), "wrong": wrongs / max(jobs, 1), "grasps_per_cell": grasps / a.cells,
                       "drops_per_cell": drops / a.cells, "reward_per_cell": total_reward / a.cells, "aroused": aroused / n,
                       "ms_live": ms["live"] * 1000 / n, "ms_world": ms["world"] * 1000 / n, "ms_labels": ms["labels"] * 1000 / n,
                       "ms_decision": sum(ms.values()) * 1000 / n})
        if episode % a.report_every == 0 or episode == a.episodes:
            mean = {k: round(float(np.mean([r[k] for r in window])), 3) for k in window[0]}
            mean.update(episode=episode, decisions=episode * n * a.cells, seconds=round(time.time() - t0, 1))
            receipt["curve"].append(mean)
            print(json.dumps(mean), flush=True)
            window.clear()
        last = episode == a.episodes
        if episode % a.inspect_every == 0 or last:
            brain.save(checkpoint)
            s = score(selection(episode))
            if s > best:
                best = s
                brain.save(best_path)
        if (a.fresh_every and episode % a.fresh_every == 0) or last:
            if not (episode % a.inspect_every == 0 or last):
                brain.save(checkpoint)
            fresh(episode)
        receipt["best"] = {"right": best[0], "grasped": best[1], "reached": best[2]}
        receipt["seconds"] = round(time.time() - t0, 1)
        (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    receipt["final_best"] = reading("fresh_best", best_path, a, a.episodes, fresh_seed(fresh_count + 1), a.fresh_trials, True,
                                    imitation, out)
    receipt["seconds"] = round(time.time() - t0, 1)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    pool.close()


if __name__ == "__main__":
    main()
