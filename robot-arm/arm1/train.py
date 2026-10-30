"""DAgger-style warm lessons on true state, many cells at once, on Cadence 0.91.1.

    python -m arm1.train --arm D1 --out runs/arm1/D1_s1 --seed 1 --cells 128 --episodes 400

``--cells`` worlds run side by side, one row each of the brain's batch, through synchronous
episodes of ``--decisions`` decisions. Every decision, in this order: the teacher labels every
cell's state from the smooth plan (``arm1.teacher``); ``Brain.lesson`` teaches the batch
without acting (by surprise: only the rows whose greedy answer disagrees are taught, from the
first lesson on); ``Brain.act`` settles afresh and answers; each cell executes the brain's answer
or, with a share fading from ``--mixture`` to ``--mixture-end`` over ``--fade`` of the run, the
teacher's label. ``Brain.step`` is never called, so no unexecuted action is ever credited; with a
recall memory (D4) the executed command replaces the brain's in ``recall.acted`` for the rows the
teacher moved. A cell restarts on placement or after ``--cap`` decisions of one job; a fresh job
begins, with probability ``--warm-start``, with the teacher driving alone for up to
``--warm-max`` decisions, so the lessons cover every phase. The step starts at ``--eta``, falls
to a third at the first plateau (``--anneal-patience`` selection readings without a new best) and
halves at every later one.

Readings (``readings.jsonl``, one JSON line each; ``arm1.inspect`` in a separate process on the
saved checkpoint): every ``--inspect-every`` episodes 40 selection trials on a fixed seed; every
``--fresh-every`` episodes and at the end 200 fresh trials on a seed never used for selection,
with the controls (teacher, random, blind twin, frozen newborn, the MLP control where given); the
four fixed trials rendered into ``frames/ep<N>/`` with every fresh reading. ``--arm mlp`` runs the
torch control through the same loop.
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
import numpy as np
from cadence import Brain
from cadence.learning import LearningPhaseError
from cadence.memories import command as one_hot

from arm.world import ArmSpec, World

from . import brains, teacher
from .actions import HOLD, execute, hold_answer, motion, slots_of
from .senses import INPUTS, layout, observe_batch

LANE = Path(__file__).resolve().parent.parent


def warm_start(world: World, rng: np.random.Generator, chance: float, most: int, pools: str) -> int:
    """A fresh job, then with probability ``chance`` the teacher drives alone for up to ``most``
    decisions (no brain, no lessons). Returns the decisions it drove."""
    world.randomize(holding_rate=0.0)
    world.closed = False
    driven = 0
    if chance and rng.random() < chance:
        for _ in range(int(rng.integers(0, most + 1))):
            event = execute(world, teacher.labels(world, pools), pools)["event"] or ""
            driven += 1
            if event.startswith("placed"):
                world.randomize(holding_rate=0.0)
                world.closed = False
                break
    return driven


def reading(kind: str, checkpoint: Path, a, episode: int, seed: int, trials: int, controls: bool, newborn: Path | None,
            out: Path) -> dict:
    """``arm1.inspect`` in a separate process on the frozen checkpoint; one line appended."""
    cmd = [sys.executable, "-m", "arm1.inspect", "--checkpoint", str(checkpoint), "--pools", a.pools, "--trials", str(trials),
           "--seed", str(seed), "--cap", str(a.cap), "--starts", "40", "--starts-seed", str(90_000 + a.seed), "--json"]
    if controls:
        cmd.append("--controls")
        if newborn is not None:
            cmd += ["--newborn", str(newborn)]
        if a.mlp_control:
            cmd += ["--mlp", a.mlp_control]
    t = time.time()
    proc = subprocess.run(cmd, check=False, cwd=LANE, capture_output=True, text=True, timeout=a.reading_timeout)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
    if proc.returncode != 0 or not lines:
        r = {"error": (proc.stderr or proc.stdout)[-2000:], "returncode": proc.returncode}
    else:
        r = json.loads(lines[-1])
    r.update(kind=kind, episode=episode, checkpoint=str(checkpoint), wall_seconds=round(time.time() - t, 1))
    with (out / "readings.jsonl").open("a") as f:
        f.write(json.dumps(r) + "\n")
    brief = {k: r.get(k) for k in ("kind", "episode", "wall_seconds", "error")}
    if "brain" in r:
        brief.update({k: r["brain"].get(k) for k in ("reached", "grasped", "lifted", "carried", "right", "wrong", "dropped",
                                                     "decisions_median", "holds", "sweeps")},
                     distinct=r["starts"].get("distinct"), activation_max=r["starts"].get("activation_max"),
                     gates_vs_teacher=r.get("gates_vs_teacher"))
        for ctl in ("random", "blind", "newborn", "mlp", "teacher"):
            if ctl in r:
                brief[ctl] = r[ctl].get("right")
    print(json.dumps({"reading": brief}), flush=True)
    return r


def render(checkpoint: Path, a, episode: int, out: Path) -> None:
    cmd = [sys.executable, "-m", "arm1.render", "--checkpoint", str(checkpoint), "--out", str(out / "frames" / f"ep{episode}"),
           "--pools", a.pools, "--trials", "4", "--seed", str(70_000 + a.seed), "--cap", str(a.cap)]
    proc = subprocess.run(cmd, check=False, cwd=LANE, capture_output=True, text=True, timeout=a.reading_timeout)
    if proc.returncode != 0:
        print(json.dumps({"render_error": proc.stderr[-1000:]}), flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--arm", choices=brains.ARMS + ("mlp",), required=True)
    p.add_argument("--resume", action="store_true",
                   help="continue the run in --out: load its brain.npz, the episode of its last selection reading, the step "
                        "and the plateau state from its receipt; readings append to its readings.jsonl")
    p.add_argument("--pools", choices=("cartesian", "joint"), default=None, help="default: joint for D2, else cartesian")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cells", type=int, default=128)
    p.add_argument("--episodes", type=int, default=400)
    p.add_argument("--decisions", type=int, default=80,
                   help="synchronous decisions per episode (the cap, so a job that never places still closes once per episode)")
    p.add_argument("--cap", type=int, default=80, help="decisions one job may take before the cell restarts")
    p.add_argument("--eta", type=float, default=None, help="the teaching step (default per arm: 0.03; D3 keeps its normalized point)")
    p.add_argument("--anneal-patience", dest="anneal_patience", type=int, default=6,
                   help="selection readings without a new best before the step falls (a third, then halves); 0 never")
    p.add_argument("--all-rows", dest="all_rows", action="store_true", help="teach every row (the surprise rule off)")
    p.add_argument("--mixture", type=float, default=0.5)
    p.add_argument("--mixture-end", dest="mixture_end", type=float, default=0.0)
    p.add_argument("--fade", type=float, default=1.0, help="share of the episodes over which the teacher's share fades")
    p.add_argument("--warm-start", dest="warm_start", type=float, default=0.7)
    p.add_argument("--warm-max", dest="warm_max", type=int, default=40)
    p.add_argument("--inspect-every", dest="inspect_every", type=int, default=20)
    p.add_argument("--inspect-trials", dest="inspect_trials", type=int, default=40)
    p.add_argument("--fresh-every", dest="fresh_every", type=int, default=100, help="0: fresh readings at the end only")
    p.add_argument("--fresh-trials", dest="fresh_trials", type=int, default=200)
    p.add_argument("--no-render", dest="no_render", action="store_true")
    p.add_argument("--mlp-control", dest="mlp_control", default=None, help="an MLP checkpoint read as a control in fresh readings")
    p.add_argument("--reading-timeout", dest="reading_timeout", type=int, default=7200)
    p.add_argument("--report-every", dest="report_every", type=int, default=5)
    p.add_argument("--backend", default="cpu")
    p.add_argument("--device", default=None)
    a = p.parse_args()
    a.pools = a.pools or brains.DEFAULT_POOLS[a.arm]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = slots_of(a.pools)
    move = motion(a.pools)
    rng = np.random.default_rng(a.seed + 77)
    worlds = [World(ArmSpec(), a.seed * 1000 + k) for k in range(a.cells)]

    trainer = None
    brain = None
    resuming = False
    if a.arm == "mlp":
        from . import mlp

        trainer = mlp.Trainer(INPUTS, slots, a.seed, lr=a.eta or 1e-3)
        checkpoint, best_path, newborn = out / "mlp.pt", out / "mlp_best.pt", out / "mlp_newborn.pt"
        trainer.save(newborn)
        trainer.save(checkpoint)
        step_now = {"lr": trainer.lr}
        described = {"parameters": int(sum(p.numel() for p in trainer.model.parameters()))}
    else:
        checkpoint, best_path, newborn = out / "brain.npz", out / "brain_best.npz", out / "brain_newborn.npz"
        resuming = a.resume and checkpoint.exists()
        if resuming:
            brain = Brain.load(checkpoint, backend=a.backend, device=a.device)
            old = json.loads((out / "receipt.json").read_text()) if (out / "receipt.json").exists() else {}
            eta = (old.get("anneals") or [{}])[-1].get("eta") or brain.learner.config.eta  # the step after the last plateau
            step_now = brains.set_steps(brain, eta)
            if not newborn.exists():  # the frozen newborn is deterministic in the arm, pools and seed
                brains.compose(a.arm, a.pools, a.seed, surprise=not a.all_rows).save(newborn)
        else:
            brain = brains.compose(a.arm, a.pools, a.seed, surprise=not a.all_rows, backend=a.backend, device=a.device)
            eta = a.eta if a.eta is not None else brains.DEFAULT_ETA[a.arm]
            step_now = brains.set_steps(brain, eta)
            brain.save(newborn)
            brain.save(checkpoint)
        described = brains.describe(brain)
    meta = {"arm": a.arm, "pools": a.pools, "slots": list(slots), "settings": vars(a), "layout": layout(),
            "recipe": brains.RECIPES.get(a.arm), "brain": described, "steps": step_now,
            "cadence": cadence.__version__, "numpy": np.__version__, "python": platform.python_version(),
            "machine": platform.machine(), "threads": os.environ.get("NUMBA_NUM_THREADS"),
            "selection_seed": 30_000 + a.seed, "starts_seed": 90_000 + a.seed, "render_seed": 70_000 + a.seed,
            "notes": ["Brain.lesson before Brain.act; Brain.step never called",
                      "D4 keys its recall on all inputs plus the command (recall_heard is one number in 0.91.1)"]}
    (out / ("run_resume.json" if resuming else "run.json")).write_text(json.dumps(meta, indent=1, default=str))
    receipt: dict = {"settings": vars(a), "cadence": cadence.__version__, "curve": [], "anneals": [], "steps": [step_now]}
    if resuming and (out / "receipt.json").exists():
        receipt = json.loads((out / "receipt.json").read_text())
        receipt.setdefault("resumed", []).append({"settings": vars(a), "steps": step_now, "cadence": cadence.__version__})

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

    start = 1
    if resuming and (out / "readings.jsonl").exists():
        # the episode of the checkpoint is its last selection reading's; the plateau state is read
        # back from the readings (the best so far, readings since it) and the receipt (anneals)
        rows = [json.loads(line) for line in (out / "readings.jsonl").read_text().splitlines() if line.strip()]
        selections = [r for r in rows if r.get("kind") == "selection" and "brain" in r]
        scores = [score(r) for r in selections]
        best = max(scores) if scores else score({})
        stale = (len(scores) - 1 - max(i for i, s in enumerate(scores) if s == best)) if scores else 0
        anneals = len(receipt.get("anneals") or [])
        fresh_count = sum(r.get("kind") == "fresh" for r in rows)
        start = (selections[-1]["episode"] if selections else 0) + 1
        print(json.dumps({"resume": {"from_episode": start - 1, "best": best, "stale": stale, "anneals": anneals,
                                     "fresh_readings": fresh_count, "step": step_now}}), flush=True)
    else:
        best = score(selection(0))
        (trainer.save if trainer else brain.save)(best_path)
        stale = anneals = 0
    t0 = time.time()
    window: list[dict] = []
    motor = int(sum(slots))
    for episode in range(start, a.episodes + 1):
        progress = min(1.0, (episode - 1) / max(a.fade * a.episodes, 1))
        share = a.mixture + (a.mixture_end - a.mixture) * progress
        driven = sum(warm_start(w, rng, a.warm_start, a.warm_max, a.pools) for w in worlds)
        if brain is not None:
            brain.reset()
        spawned = np.zeros(a.cells, dtype=int)
        jobs = rights = grasps = wrongs = drops = 0
        taught = agreed = refused_lessons = refused_acts = 0
        match = holds = label_holds = 0.0
        ms = {"lesson": 0.0, "act": 0.0, "world": 0.0, "labels": 0.0}
        for d in range(a.decisions):
            t = time.perf_counter()
            x = observe_batch(worlds)
            labels = np.array([teacher.labels(w, a.pools) for w in worlds], dtype=np.int64)
            ms["labels"] += time.perf_counter() - t
            t = time.perf_counter()
            if trainer is not None:
                report = trainer.lesson(x, labels)
                taught += a.cells
            else:
                try:
                    report = brain.lesson(x, labels)
                    taught += int(report.get("accepted_presentations", 0))
                    agreed += int(report.get("agreed_presentations", 0))
                except (LearningPhaseError, RuntimeError) as error:  # a refused phase leaves the parameters as they were
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
                    answer = np.stack([hold_answer(a.pools, w.closed) for w in worlds])
            ms["act"] += time.perf_counter() - t
            match += float(np.mean(answer == labels))
            holds += float(np.mean(np.all(answer[:, move] == HOLD, axis=1)))
            label_holds += float(np.mean(np.all(labels[:, move] == HOLD, axis=1)))
            use_teacher = rng.random(a.cells) < share
            chosen = np.where(use_teacher[:, None], labels, answer)
            if brain is not None and brain.recall is not None and use_teacher.any():
                # the recall memory read the brain's own command as the one executed; correct the rows the teacher moved
                brain.recall.acted[use_teacher] = one_hot(chosen[use_teacher], motor, brain.learner.slot_offsets)
            t = time.perf_counter()
            for k, w in enumerate(worlds):
                event = execute(w, chosen[k], a.pools)["event"] or ""
                grasps += event == "grasped"
                drops += event == "dropped"
                if event.startswith("placed") or d - spawned[k] >= a.cap - 1:
                    jobs += 1
                    rights += event.endswith("right")
                    wrongs += event.endswith("wrong")
                    warm_start(w, rng, a.warm_start, a.warm_max, a.pools)
                    spawned[k] = d + 1
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
            (trainer.save if trainer else brain.save)(checkpoint)
            r = selection(episode)
            s = score(r)
            if s > best:
                best, stale = s, 0
                (trainer.save if trainer else brain.save)(best_path)
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
                (trainer.save if trainer else brain.save)(checkpoint)
            fresh(episode)
        receipt["best"] = {"right": best[0], "grasped": best[1], "reached": best[2]}
        receipt["seconds"] = round(time.time() - t0, 1)
        (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    receipt["final_best"] = reading("fresh_best", best_path if best_path.exists() else checkpoint, a, a.episodes,
                                    fresh_seed(fresh_count + 1), a.fresh_trials, True, newborn, out)
    receipt["seconds"] = round(time.time() - t0, 1)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1))


if __name__ == "__main__":
    main()
