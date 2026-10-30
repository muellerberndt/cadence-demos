"""DAgger-style warm lessons under contact physics, many cells at once, on Cadence 0.91.1.

    python -m arm2.train --arm D1 --out runs/arm2/D1_s1 --seed 1 --cells 128 --episodes 400

The loop is ``arm1.train``'s on the Panda cell: every decision the teacher (``arm2.teacher``)
labels every cell, ``Brain.lesson`` teaches by surprise without acting, ``Brain.act`` answers,
each cell executes the brain's answer or the teacher's (a share fading from ``--mixture`` to
``--mixture-end``); ``Brain.step`` is never called; with a recall memory the executed command
replaces the brain's in ``recall.acted`` on the teacher's rows. Cells restart on placement or at
``--cap``; fresh jobs begin with the teacher driving alone with probability ``--warm-start``.
Readings in a separate process (``arm2.inspect``): selection every ``--inspect-every`` episodes,
fresh with the controls and the held-out physics every ``--fresh-every``, four rendered trials
each. ``--no-velocity`` (the arm D1nv) zeroes the joint velocities in the senses.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import cadence
import mujoco
import numpy as np
from cadence.learning import LearningPhaseError
from cadence.memories import command as one_hot

from . import brains
from .actions import HOLD, hold_answer, motion, slots_of
from .pool import CellPool, LocalPool
from .scene import PHYSICS
from .senses import FLAGS, inputs, layout

LANE = Path(__file__).resolve().parent.parent


def reading(kind: str, checkpoint: Path, a, episode: int, seed: int, trials: int, controls: bool, newborn: Path | None,
            out: Path) -> dict:
    cmd = [sys.executable, "-m", "arm2.inspect", "--checkpoint", str(checkpoint), "--pools", a.pools, "--trials", str(trials),
           "--seed", str(seed), "--cap", str(a.cap), "--starts", "40", "--starts-seed", str(90_000 + a.seed), "--json",
           "--physics", a.physics, "--heldout-set", a.heldout_set, "--senses", a.senses]
    if a.no_velocity:
        cmd.append("--no-velocity")
    if controls:
        cmd += ["--controls", "--heldout"]
        if newborn is not None:
            cmd += ["--newborn", str(newborn)]
        if a.mlp_control:
            cmd += ["--mlp", a.mlp_control]
    t = time.time()
    proc = subprocess.run(cmd, check=False, cwd=LANE, capture_output=True, text=True, timeout=a.reading_timeout)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
    r = {"error": (proc.stderr or proc.stdout)[-2000:], "returncode": proc.returncode} if proc.returncode or not lines else json.loads(lines[-1])
    r.update(kind=kind, episode=episode, checkpoint=str(checkpoint), wall_seconds=round(time.time() - t, 1))
    with (out / "readings.jsonl").open("a") as f:
        f.write(json.dumps(r) + "\n")
    brief = {k: r.get(k) for k in ("kind", "episode", "wall_seconds", "error")}
    if "brain" in r:
        brief.update({k: r["brain"].get(k) for k in ("reached", "grasped", "lifted", "carried", "right", "wrong", "dropped",
                                                     "decisions_median", "holds", "sweeps")},
                     distinct=r["starts"].get("distinct"), activation_max=r["starts"].get("activation_max"),
                     gates_vs_teacher=(r.get("gates_vs_teacher") or {}).get("ratio"))
        for ctl in ("random", "blind", "newborn", "mlp", "teacher", "heldout", "teacher_heldout"):
            if ctl in r:
                brief[ctl] = r[ctl].get("right")
    print(json.dumps({"reading": brief}), flush=True)
    return r


def render(checkpoint: Path, a, episode: int, out: Path) -> None:
    cmd = [sys.executable, "-m", "arm2.render", "--checkpoint", str(checkpoint), "--out", str(out / "frames" / f"ep{episode}"),
           "--pools", a.pools, "--trials", "4", "--seed", str(70_000 + a.seed), "--cap", str(a.cap), "--senses", a.senses,
           "--physics", a.physics]
    if a.no_velocity:
        cmd.append("--no-velocity")
    proc = subprocess.run(cmd, check=False, cwd=LANE, capture_output=True, text=True, timeout=a.reading_timeout)
    if proc.returncode != 0:
        print(json.dumps({"render_error": proc.stderr[-1000:]}), flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--arm", choices=brains.ARMS + ("mlp",), required=True)
    p.add_argument("--pools", choices=("cartesian", "joint"), default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cells", type=int, default=128)
    p.add_argument("--workers", type=int, default=6, help="processes that own the cells' physics, teacher and senses (0: in this process)")
    p.add_argument("--episodes", type=int, default=400)
    p.add_argument("--decisions", type=int, default=80)
    p.add_argument("--cap", type=int, default=80)
    p.add_argument("--eta", type=float, default=None)
    p.add_argument("--anneal-patience", dest="anneal_patience", type=int, default=6)
    p.add_argument("--all-rows", dest="all_rows", action="store_true")
    p.add_argument("--no-velocity", dest="no_velocity", action="store_true", help="zero the joint velocities in the senses (D1nv sets it)")
    p.add_argument("--physics", choices=("nominal", "wide"), default="nominal", help="the physics set the cells train on")
    p.add_argument("--heldout-set", dest="heldout_set", choices=("heldout", "heldout2"), default=None,
                   help="the held-out physics of the fresh readings (default: heldout for nominal, heldout2 for wide)")
    p.add_argument("--senses", choices=("basic", "slip"), default="basic",
                   help="slip: the block's velocity relative to the fingertips and the finger contact force appended")
    p.add_argument("--teacher", choices=("plan", "recover"), default="plan", help="recover: the gentle release above the bin")
    p.add_argument("--arousal", action="store_true",
                   help="compose the brain with arousal (construction only), so a later live stage can gate its moments by it")
    p.add_argument("--mixture", type=float, default=0.5)
    p.add_argument("--mixture-end", dest="mixture_end", type=float, default=0.0)
    p.add_argument("--fade", type=float, default=1.0)
    p.add_argument("--warm-start", dest="warm_start", type=float, default=0.7)
    p.add_argument("--warm-max", dest="warm_max", type=int, default=40)
    p.add_argument("--inspect-every", dest="inspect_every", type=int, default=20)
    p.add_argument("--inspect-trials", dest="inspect_trials", type=int, default=40)
    p.add_argument("--fresh-every", dest="fresh_every", type=int, default=100)
    p.add_argument("--fresh-trials", dest="fresh_trials", type=int, default=200)
    p.add_argument("--no-render", dest="no_render", action="store_true")
    p.add_argument("--mlp-control", dest="mlp_control", default=None)
    p.add_argument("--reading-timeout", dest="reading_timeout", type=int, default=10_800)
    p.add_argument("--report-every", dest="report_every", type=int, default=5)
    p.add_argument("--backend", default="cpu")
    p.add_argument("--device", default=None)
    a = p.parse_args()
    a.pools = a.pools or brains.DEFAULT_POOLS[a.arm]
    a.no_velocity = a.no_velocity or not brains.VELOCITY.get(a.arm, True)
    velocity = not a.no_velocity
    slip, recover = a.senses == "slip", a.teacher == "recover"
    a.heldout_set = a.heldout_set or ("heldout" if a.physics == "nominal" else "heldout2")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = slots_of(a.pools)
    move = motion(a.pools)
    rng = np.random.default_rng(a.seed + 77)
    # the cells' processes fork before the brain exists, so no numba thread pool is inherited
    pool = (CellPool(a.cells, a.workers, a.seed, a.physics, a.pools, velocity, a.cap, slip, recover) if a.workers > 0
            else LocalPool(a.cells, a.seed, a.physics, a.pools, velocity, a.cap, slip, recover))
    n_inputs = inputs(a.pools, slip)

    trainer = brain = None
    if a.arm == "mlp":
        from arm1 import mlp

        trainer = mlp.Trainer(n_inputs, slots, a.seed, lr=a.eta or 1e-3)
        checkpoint, best_path, newborn = out / "mlp.pt", out / "mlp_best.pt", out / "mlp_newborn.pt"
        trainer.save(newborn)
        trainer.save(checkpoint)
        step_now = {"lr": trainer.lr}
        described = {"parameters": int(sum(p.numel() for p in trainer.model.parameters()))}
    else:
        brain = brains.compose(a.arm, a.pools, a.seed, surprise=not a.all_rows, inputs_count=n_inputs, backend=a.backend,
                               device=a.device, **({"arousal": True} if a.arousal else {}))
        eta = a.eta if a.eta is not None else brains.DEFAULT_ETA[a.arm]
        step_now = brains.set_steps(brain, eta)
        checkpoint, best_path, newborn = out / "brain.npz", out / "brain_best.npz", out / "brain_newborn.npz"
        brain.save(newborn)
        brain.save(checkpoint)
        described = brains.describe(brain)
    meta = {"arm": a.arm, "pools": a.pools, "slots": list(slots), "settings": vars(a), "layout": layout(a.pools, slip), "velocity": velocity,
            "workers": pool.workers, "senses": a.senses, "physics_set": a.physics, "heldout_set": a.heldout_set, "teacher": a.teacher,
            "recipe": brains.RECIPES.get(a.arm), "brain": described, "steps": step_now, "physics": PHYSICS,
            "cadence": cadence.__version__, "mujoco": mujoco.__version__, "numpy": np.__version__,
            "python": platform.python_version(), "machine": platform.machine(), "threads": os.environ.get("NUMBA_NUM_THREADS"),
            "selection_seed": 30_000 + a.seed, "starts_seed": 90_000 + a.seed, "render_seed": 70_000 + a.seed,
            "notes": ["Brain.lesson before Brain.act; Brain.step never called",
                      "D4 keys its recall on all inputs plus the command (recall_heard is one number in 0.91.1)"]}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    receipt: dict = {"settings": vars(a), "cadence": cadence.__version__, "mujoco": mujoco.__version__, "curve": [], "anneals": [],
                     "steps": [step_now]}

    def fresh_seed(k: int) -> int:
        return 80_000 + 1000 * a.seed + 10 * k

    fresh_count = 0

    def selection(episode: int) -> dict:
        return reading("selection", checkpoint, a, episode, 30_000 + a.seed, a.inspect_trials, False, None, out)

    def fresh(episode: int) -> dict:
        nonlocal fresh_count
        fresh_count += 1
        r = reading("fresh", checkpoint, a, episode, fresh_seed(fresh_count), a.fresh_trials, True, newborn, out)
        if not a.no_render:
            render(checkpoint, a, episode, out)
        return r

    def score(r: dict) -> tuple:
        b = r.get("brain") or {}
        return (b.get("right") or 0.0, b.get("grasped") or 0.0, b.get("reached") or 0.0)

    save = trainer.save if trainer else brain.save
    best = score(selection(0))
    save(best_path)
    stale = anneals = 0
    t0 = time.time()
    window: list[dict] = []
    motor = int(sum(slots))
    for episode in range(1, a.episodes + 1):
        progress = min(1.0, (episode - 1) / max(a.fade * a.episodes, 1))
        share = a.mixture + (a.mixture_end - a.mixture) * progress
        driven = pool.warm(a.warm_start, a.warm_max)
        if brain is not None:
            brain.reset()
        jobs = rights = grasps = wrongs = drops = 0
        taught = agreed = refused_lessons = refused_acts = 0
        match = holds = label_holds = 0.0
        ms = {"lesson": 0.0, "act": 0.0, "world": 0.0, "labels": 0.0}
        for d in range(a.decisions):
            t = time.perf_counter()
            x, labels = pool.sense()
            ms["labels"] += time.perf_counter() - t
            t = time.perf_counter()
            if trainer is not None:
                trainer.lesson(x, labels)
                taught += a.cells
            else:
                try:
                    report = brain.lesson(x, labels)
                    taught += int(report.get("accepted_presentations", 0))
                    agreed += int(report.get("agreed_presentations", 0))
                except (LearningPhaseError, RuntimeError) as error:
                    refused_lessons += 1
                    if refused_lessons <= 3:
                        print(json.dumps({"lesson_refused": repr(error)[:300], "episode": episode, "decision": d}), flush=True)
            ms["lesson"] += time.perf_counter() - t
            t = time.perf_counter()
            if trainer is not None:
                answer = trainer.act(x)
            else:
                try:
                    answer = np.asarray(brain.act(x, greedy=True), dtype=np.int64)
                except RuntimeError:
                    refused_acts += 1
                    answer = np.stack([hold_answer(a.pools, bool(x[k, FLAGS.start] > 0.5)) for k in range(a.cells)])
            ms["act"] += time.perf_counter() - t
            match += float(np.mean(answer == labels))
            holds += float(np.mean(np.all(answer[:, move] == HOLD, axis=1)))
            label_holds += float(np.mean(np.all(labels[:, move] == HOLD, axis=1)))
            use_teacher = rng.random(a.cells) < share
            chosen = np.where(use_teacher[:, None], labels, answer)
            if brain is not None and brain.recall is not None and use_teacher.any():
                brain.recall.acted[use_teacher] = one_hot(chosen[use_teacher], motor, brain.learner.slot_offsets)
            t = time.perf_counter()
            counts = pool.act(chosen, a.warm_start, a.warm_max)
            jobs, rights, wrongs = jobs + counts["jobs"], rights + counts["rights"], wrongs + counts["wrongs"]
            grasps, drops = grasps + counts["grasps"], drops + counts["drops"]
            ms["world"] += time.perf_counter() - t
        n = a.decisions
        window.append({"jobs": jobs, "right": rights / max(jobs, 1), "wrong": wrongs / max(jobs, 1), "grasps_per_cell": grasps / a.cells,
                       "drops_per_cell": drops / a.cells, "taught": taught / (n * a.cells), "agreed": agreed / (n * a.cells),
                       "match": match / n, "holds": holds / n, "label_holds": label_holds / n, "share": share,
                       "warm_decisions": driven / a.cells, "refused_lessons": refused_lessons, "refused_acts": refused_acts,
                       "ms_lesson": ms["lesson"] * 1000 / n, "ms_act": ms["act"] * 1000 / n, "ms_world": ms["world"] * 1000 / n,
                       "ms_labels": ms["labels"] * 1000 / n, "ms_decision": sum(ms.values()) * 1000 / n})
        if episode % a.report_every == 0 or episode == a.episodes:
            mean = {k: round(float(np.mean([r[k] for r in window])), 3) for k in window[0]}
            mean.update(episode=episode, decisions=episode * n * a.cells, seconds=round(time.time() - t0, 1),
                        step=round(float(trainer.lr if trainer else brain.learner.config.eta), 5))
            receipt["curve"].append(mean)
            print(json.dumps(mean), flush=True)
            window.clear()
        last = episode == a.episodes
        if episode % a.inspect_every == 0 or last:
            save(checkpoint)
            s = score(selection(episode))
            if s > best:
                best, stale = s, 0
                save(best_path)
            else:
                stale += 1
            if a.anneal_patience and stale >= a.anneal_patience:
                factor = 1.0 / 3.0 if anneals == 0 else 0.5
                anneals += 1
                stale = 0
                step_now = {"lr": trainer.scale_lr(factor)} if trainer else brains.set_steps(brain, scale=factor)
                receipt["anneals"].append({"episode": episode, "factor": factor, **step_now})
                print(json.dumps({"anneal": receipt["anneals"][-1]}), flush=True)
        if (a.fresh_every and episode % a.fresh_every == 0) or last:
            if not (episode % a.inspect_every == 0 or last):
                save(checkpoint)
            fresh(episode)
        receipt["best"] = {"right": best[0], "grasped": best[1], "reached": best[2]}
        receipt["seconds"] = round(time.time() - t0, 1)
        (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    receipt["final_best"] = reading("fresh_best", best_path, a, a.episodes, fresh_seed(fresh_count + 1), a.fresh_trials, True,
                                    newborn, out)
    receipt["seconds"] = round(time.time() - t0, 1)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    pool.close()


if __name__ == "__main__":
    main()
