"""Closed-loop teaching in many worlds at once, on Cadence 0.91.

    python -m arm091.dagger --init runs/n10-xent/brain.npz --out runs/d1 --worlds 32 --episodes 4000

``--worlds`` cells run side by side, one row each of the brain's batch, through synchronous
episodes of ``--limit`` decisions from random postures. At every decision the brain acts on all
rows, the caregiver labels every row's state (the eye's readouts from the world, the joints from
``--teacher``: ``gradient`` names a direction for every joint, ``joint`` is the 0.83 caregiver
with its dead zone), and one lesson teaches the batch, warm from the act's own state. With
``--surprise`` only the rows whose joint commands disagreed with the labels are taught. The executed step is
the brain's own, or the caregiver's with a share that fades from ``--mixture`` to
``--mixture-end``. A row that reached keeps acting (the caregiver labels holding there), or with
``--respawn`` starts a new reach from a fresh random scene at once.

Every ``--assay-every`` episodes the brain alone reaches on held-out postures and blocks (the
nursery's assay, no lessons, one row): the only reading of the policy. The receipt holds the curve,
the assays, the settings and the library version.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import time
from dataclasses import replace
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import cadence  # noqa: E402
import numpy as np  # noqa: E402
from cadence import Brain  # noqa: E402

from arm import caregiver  # noqa: E402
from arm.anatomy import EYE_SLOTS  # noqa: E402
from arm.eyes import Eyes  # noqa: E402
from arm.nursery import head_of, reach  # noqa: E402
from arm.world import ArmSpec, World, steps_of  # noqa: E402

from . import teacher  # noqa: E402
from .job import GRIP, job_assay, job_labels  # noqa: E402

POOLS = slice(len(EYE_SLOTS), len(EYE_SLOTS) + 4)


def warm_start(world: World, eyes: Eyes, rng: np.random.Generator, chance: float, most: int,
               plan: str = "steps") -> None:
    """A fresh job, then with probability ``chance`` the caregiver drives the world alone (no
    brain, no lessons) for up to ``most`` decisions, so the brain takes over in any phase of the
    job: over the block, holding it, on the way to the bin."""
    world.randomize(holding_rate=0.0)
    world.closed = False
    eyes.reset()
    if chance and rng.random() < chance:
        for _ in range(int(rng.integers(0, most + 1))):
            want = job_labels(world, eyes, plan=plan)
            event = world.decide(steps_of(want[POOLS]), want[GRIP])["event"] or ""
            if event.startswith("placed"):  # the caregiver finished it: start the brain on a fresh one
                world.randomize(holding_rate=0.0)
                world.closed = False
                break
        eyes.reset()


def labels_of(world: World, eyes: Eyes, rule: str) -> list[int]:
    target = caregiver.hover_point(world)
    joints = teacher.reach_labels(world, target) if rule == "gradient" else caregiver.reach_labels(world, target)
    return eyes.labels(world) + joints


_RENDER: dict = {}


def _render_init(head) -> None:
    _RENDER["world"], _RENDER["eyes"] = World(ArmSpec(), 0), Eyes(head)


def _render(snapshot: dict) -> np.ndarray:
    """A worker's view of one cell: its own world restored to the snapshot, seen by its own eyes
    (no change channel, so the eyes keep no state between moments)."""
    world, eyes = _RENDER["world"], _RENDER["eyes"]
    world.restore(snapshot)
    return eyes.inputs(world)


def assay(brain: Brain, head, seed: int, trials: int, dark: bool = False) -> dict:
    world, eyes = World(ArmSpec(), seed), Eyes(head)
    return reach(brain, world, eyes, trials, 10_000 + seed + 1, dark=dark)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--init", required=True, help="a raised brain (its run.json beside it names the head)")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--worlds", type=int, default=32)
    p.add_argument("--episodes", type=int, default=2000, help="episodes per world")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--teacher", choices=("gradient", "joint"), default="gradient")
    p.add_argument("--task", choices=("reach", "job"), default="reach",
                   help="job: every joint and the gripper through hover, lower, grasp, lift, carry, release; "
                        "a cell starts a new job when its block lands in a bin or after --limit decisions")
    p.add_argument("--eta", type=float, default=None, help="the teaching step (default: the loaded brain's)")
    p.add_argument("--eta-scale", dest="eta_scale", type=float, default=1.0,
                   help="multiply the step and the bias step by this at the start")
    p.add_argument("--anneal-patience", dest="anneal_patience", type=int, default=0,
                   help="assays without a new best before the steps are scaled by --anneal-factor (0: never)")
    p.add_argument("--anneal-factor", dest="anneal_factor", type=float, default=0.5)
    p.add_argument("--fresh-trials", dest="fresh_trials", type=int, default=100,
                   help="trials of the final assay on postures and blocks no assay chose by")
    p.add_argument("--eta-end", dest="eta_end", type=float, default=None, help="eta at the last episode (linear)")
    p.add_argument("--surprise", action="store_true", help="teach only the rows whose act disagreed")
    p.add_argument("--mixture", type=float, default=0.5)
    p.add_argument("--mixture-end", dest="mixture_end", type=float, default=0.0)
    p.add_argument("--fade", type=float, default=0.5, help="share of the episodes over which the mixture fades")
    p.add_argument("--trace", type=float, default=None, help="working trace amplitude (default: as saved)")
    p.add_argument("--assay-every", dest="assay_every", type=int, default=100)
    p.add_argument("--assay-trials", dest="assay_trials", type=int, default=40)
    p.add_argument("--report-every", dest="report_every", type=int, default=10)
    p.add_argument("--backend", default="cpu")
    p.add_argument("--device", default=None)
    p.add_argument("--precision", default=None)
    p.add_argument("--respawn", action="store_true",
                   help="a cell that reached starts a new reach at once (no lessons parked at the goal)")
    p.add_argument("--plan", choices=("steps", "smooth"), default="steps",
                   help="job: the caregiver's plan (steps: arm.caregiver.plan; smooth: job.smooth_plan)")
    p.add_argument("--warm-start", dest="warm_start", type=float, default=0.0,
                   help="job: the share of fresh jobs the caregiver drives alone for a while before the brain takes over")
    p.add_argument("--warm-max", dest="warm_max", type=int, default=40, help="job: the most decisions it drives")
    p.add_argument("--render-workers", dest="render_workers", type=int, default=0,
                   help="processes that paint the retinas of the cells (0: in this process)")
    a = p.parse_args()
    placed = {"backend": a.backend, "device": a.device, "precision": a.precision}

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run = json.loads((Path(a.init).parent / "run.json").read_text())
    head = head_of(run)
    if head.change:
        a.render_workers = 0  # the change channel keeps each eye's previous frame
    pool = None
    if a.render_workers:  # forked before the brain reaches a device
        pool = multiprocessing.get_context("fork").Pool(a.render_workers, _render_init, (head,))
    brain = Brain.load(a.init, **placed)
    if a.trace is not None and brain.working_memory is not None:
        brain.working_memory.amplitude = a.trace
    def set_steps(scale: float, eta: float | None = None) -> None:
        """The learner's steps, through retune: the step and the bias step together."""
        c = brain.learner.config
        new_eta = (c.eta if eta is None else eta) * scale
        bias = None if c.eta_bias is None else c.eta_bias * (new_eta / c.eta)
        brain.retune(learning=replace(c, eta=new_eta, eta_bias=bias, surprise=bool(a.surprise)))

    set_steps(a.eta_scale, a.eta)
    worlds = [World(ArmSpec(), a.seed * 1000 + k) for k in range(a.worlds)]
    eyes = [Eyes(head) for _ in range(a.worlds)]
    rng = np.random.default_rng(a.seed + 77)
    meta = {**run, "continued_from": str(a.init), "dagger": vars(a), "cadence": cadence.__version__,
            "numpy": np.__version__, "python": platform.python_version(), "machine": platform.machine(),
            "threads": os.environ.get("NUMBA_NUM_THREADS")}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    receipt = {"settings": vars(a), "cadence": cadence.__version__, "curve": [], "assays": [],
               "learning": {"eta": brain.learner.config.eta, "eta_bias": brain.learner.config.eta_bias}}

    def reading(episode: int) -> dict:
        t = time.time()
        if a.task == "job":
            r = job_assay(brain, head, a.assay_trials, 30_000 + a.seed, a.limit)
        else:
            r = assay(brain, head, a.seed, a.assay_trials)
        r.update(episode=episode, seconds=round(time.time() - t, 1))
        receipt["assays"].append(r)
        print(json.dumps({"assay": r}), flush=True)
        return r

    best = reading(0)["success"]
    brain.save(out / "brain_best.npz")
    stale = 0
    t0 = time.time()
    window: list[dict] = []
    for episode in range(1, a.episodes + 1):
        progress = min(1.0, (episode - 1) / max(a.fade * a.episodes, 1))
        share = a.mixture + (a.mixture_end - a.mixture) * progress
        if a.eta_end is not None and a.eta is not None:
            set_steps(1.0, a.eta + (a.eta_end - a.eta) * (episode - 1) / max(a.episodes - 1, 1))
        for w, e in zip(worlds, eyes, strict=True):
            if a.task == "job":
                warm_start(w, e, rng, a.warm_start, a.warm_max, a.plan)
            else:
                w.randomize(holding_rate=0.0)
                w.closed = False
                e.reset()
        brain.reset()
        reached = np.full(a.worlds, -1)
        spawned = np.zeros(a.worlds, dtype=int)  # the decision at which each cell's current reach began
        reaches = successes = grasps = 0
        taught = disagreed = 0
        holds = matches = label_holds = 0.0
        start = time.perf_counter()
        for d in range(a.limit):
            for k, w in enumerate(worlds):
                if np.linalg.norm(w.tip() - caregiver.hover_point(w)) <= 0.025:
                    if reached[k] < 0:
                        reached[k] = d
                    if a.respawn and a.task == "reach":  # a fresh reach at once: no lessons on states parked at the goal
                        reaches += 1
                        successes += 1
                        w.randomize(holding_rate=0.0)
                        w.closed = False
                        eyes[k].reset()
                        spawned[k] = d
            if pool is not None:
                x = np.stack(pool.map(_render, [w.snapshot() for w in worlds],
                                      chunksize=max(1, a.worlds // (2 * a.render_workers))))
            else:
                x = np.stack([e.inputs(w) for w, e in zip(worlds, eyes, strict=True)])
            if a.task == "job":
                labels = np.array([job_labels(w, e, a.teacher, a.plan) for w, e in zip(worlds, eyes, strict=True)],
                                  dtype=np.int64)
            else:
                labels = np.array([labels_of(w, e, a.teacher) for w, e in zip(worlds, eyes, strict=True)], dtype=np.int64)
            drive = brain.stimulus(x)
            answer = np.asarray(brain.act(x, greedy=True))
            warm = brain.basal_ganglia.state
            judged = None
            if a.surprise:  # a row disagrees when a joint's command differs; the eye's bins do not count
                judged = labels.copy()
                judged[:, POOLS] = answer[:, POOLS]
                if a.task == "job":  # and in the job the gripper's
                    judged[:, GRIP] = answer[:, GRIP]
            _, report = brain.learner.step(drive, labels, warm=warm, answer=judged)
            taught += int(report.get("accepted_presentations", a.worlds))
            disagreed += int(np.any(answer != labels, axis=1).sum())
            holds += float(np.mean(answer[:, POOLS] == 2))
            label_holds += float(np.mean(labels[:, POOLS] == 2))
            matches += float(np.mean(answer[:, POOLS] == labels[:, POOLS]))
            for k, w in enumerate(worlds):
                source = labels if rng.random() < share else answer
                steps = steps_of(source[k, POOLS])
                close = int(source[k, GRIP]) if a.task == "job" else 0
                event = w.decide(steps, close)["event"] or ""
                if a.task == "job":
                    grasps += event == "grasped"
                    if event.startswith("placed") or d - spawned[k] >= a.limit - 1:
                        reaches += 1
                        successes += event.endswith("right")
                        warm_start(w, eyes[k], rng, a.warm_start, a.warm_max, a.plan)
                        spawned[k] = d + 1
        if a.task == "reach" and a.respawn:
            reaches += a.worlds  # the reaches still open at the episode's end count as missed
        # a job is counted when its block lands or its cell reaches --limit; one still open at the
        # episode's end is not
        window.append({"reached": float(successes / max(reaches, 1)) if (a.respawn or a.task == "job") else float(np.mean(reached >= 0)),
                       "grasps_per_cell": grasps / a.worlds,
                       "taught": taught / (a.limit * a.worlds),
                       "disagreed": disagreed / (a.limit * a.worlds), "holds": holds / a.limit,
                       "label_holds": label_holds / a.limit,
                       "joint_match": matches / a.limit, "share": share,
                       "ms_per_decision": (time.perf_counter() - start) * 1000 / a.limit})
        if episode % a.report_every == 0:
            mean = {k: round(float(np.mean([r[k] for r in window])), 3) for k in window[0]}
            mean.update(episode=episode, decisions=episode * a.limit * a.worlds, seconds=round(time.time() - t0, 1),
                        eta=round(float(brain.learner.config.eta), 4))
            receipt["curve"].append(mean)
            print(json.dumps(mean), flush=True)
            window.clear()
        if episode % a.assay_every == 0 or episode == a.episodes:
            r = reading(episode)
            brain.save(out / "brain.npz")
            if r["success"] > best:
                stale = 0
            else:
                stale += 1
            if r["success"] >= best:
                best = r["success"]
                brain.save(out / "brain_best.npz")
            if a.anneal_patience and stale >= a.anneal_patience:
                set_steps(a.anneal_factor)
                stale = 0
                receipt.setdefault("anneals", []).append({"episode": episode, "eta": brain.learner.config.eta,
                                                          "eta_bias": brain.learner.config.eta_bias})
                print(json.dumps({"anneal": receipt["anneals"][-1]}), flush=True)
            (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    final = Brain.load(out / "brain_best.npz", **placed)
    if a.task == "job":
        world0, eyes0 = World(ArmSpec(), a.seed), Eyes(head)
        receipt["final"] = {
            "best_success": best,
            "job": job_assay(final, head, a.assay_trials, 30_000 + a.seed, a.limit),
            "job_fresh": job_assay(final, head, a.fresh_trials, 80_000 + a.seed, a.limit),
            "job_fresh_dark": job_assay(final, head, a.fresh_trials, 80_000 + a.seed, a.limit, dark=True),
            "job_random": job_assay(None, head, a.fresh_trials, 80_000 + a.seed, a.limit, policy="random"),
            "job_caregiver": job_assay(None, head, a.fresh_trials, 80_000 + a.seed, a.limit, policy="caregiver",
                                       plan=a.plan),
            "reach_fresh": reach(final, world0, eyes0, a.fresh_trials, 50_000 + a.seed),
        }
        receipt["seconds"] = round(time.time() - t0, 1)
        (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
        print(json.dumps({"final": receipt["final"]}), flush=True)
        return
    receipt["final"] = {
        "best_success": best,
        "reach": assay(final, head, a.seed, a.assay_trials),
        "reach_dark": assay(final, head, a.seed, a.assay_trials, dark=True),
        "reach_fresh": reach(final, World(ArmSpec(), a.seed), Eyes(head), a.fresh_trials, 50_000 + a.seed),
        "reach_fresh_dark": reach(final, World(ArmSpec(), a.seed), Eyes(head), a.fresh_trials, 50_000 + a.seed,
                                  dark=True),
        "reach_random": reach(None, World(ArmSpec(), a.seed), Eyes(head), a.assay_trials, 10_000 + a.seed + 1,
                              policy="random"),
        "reach_caregiver": reach(None, World(ArmSpec(), a.seed), Eyes(head), a.assay_trials, 10_000 + a.seed + 1,
                                 policy="caregiver"),
    }
    receipt["seconds"] = round(time.time() - t0, 1)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    print(json.dumps({"final": receipt["final"]}), flush=True)


if __name__ == "__main__":
    main()
