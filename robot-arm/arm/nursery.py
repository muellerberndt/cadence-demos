"""Raise the eye-arm brain, then assay it.

    python -m arm.nursery raise --out runs/n1-s1 --seed 1 --lessons 12000
    python -m arm.nursery assay --brain runs/n1-s1/brain.npz --scenes 300
    python -m arm.nursery reach --brain runs/n1-s1/brain.npz --trials 40

Raising is a nursery of random scenes: the arm in a random posture over the table, a block
somewhere, an order lamp on, sometimes the block already in the hand. Every scene is one
lesson on all the slots at once: what the eyes should read (where the block and the hand are,
whether the block is held, which lamp is on) and what the caregiver would do next (a step per
joint, the gripper). The lesson is the library's local contrast step on the drive the answer
used, warm from the answer's own free state, as the Eyes demo raises its eye.

The assays score free answers on held-out scenes before any lesson: first glance from rest,
the same scenes with the retinas dark (what the eyes add), and a closed-loop reach where the
brain alone brings the hand above the block.
"""

from __future__ import annotations

import argparse
import json
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

from . import caregiver  # noqa: E402
from .anatomy import EYE_SLOTS, MOTOR_SLOTS, Anatomy, Stage, build, describe, eye_learner, pool_phase, raising_config, share_graph  # noqa: E402
from .eyes import Eyes, HeadSpec  # noqa: E402
from .world import ArmSpec, World, steps_of  # noqa: E402

SLOT_NAMES = ("block_x", "block_y", "hand_x", "hand_y", "held", "order", "yaw", "shoulder", "elbow", "wrist", "gripper")
POSITION_SLOTS = {0, 1, 2, 3}


def make_brain(seed: int, size: int, eyes: int, change: bool, hidden: int, features: int, sheet: int,
               trace: bool = True, memory: bool = True, sheets: int = 1, readout: str = "dense",
               map_reciprocal: bool = True, map_density: float = 1.0, colour: bool = False,
               tie_rate: str = "sum", eye_streams: bool = False, priors: bool = False,
               readout_reciprocal: bool = True, map_input_reciprocal: bool = True, depth_map: bool = False,
               field: int = 5, deep: tuple[int, ...] = (), apical: float = 0.0) -> tuple[Brain, Anatomy, HeadSpec]:
    head = HeadSpec(size=size, eyes=eyes, change=change, colour=colour)
    anatomy = Anatomy(size=size, channels=head.channels, eyes=eyes, eye_streams=eye_streams, hidden=hidden,
                      stages=(Stage(features, field, 2),), sheet=sheet, sheets=sheets, readout=readout,
                      map_reciprocal=map_reciprocal, map_density=map_density, priors=priors,
                      readout_reciprocal=readout_reciprocal, map_input_reciprocal=map_input_reciprocal, depth_map=depth_map,
                      deep=tuple(deep))
    options = dict(arousal=True)
    if apical:  # the 0.90 compartment: top-down halves of the reciprocal pairs between regions
        options["apical"] = apical
    if memory:
        options.update(memory_choice=True, memory_context=0.5, memory_rate=0.5, memory_replay=8,
                       memory_demonstrations=1.0, memory_expansion=1024, memory_winners=24)
    brain = build(anatomy, seed=seed, trace=(3.0, 0.0) if trace else None, tie_rate=tie_rate, **options)
    return brain, anatomy, head


def scene_labels(world: World, eyes: Eyes) -> np.ndarray:
    return np.array([eyes.labels(world) + caregiver.labels(world)], dtype=np.int64)


def chance(world: World, eyes: Eyes, scenes: int = 500, seed: int = 999) -> dict[str, float]:
    """The best constant guess per slot over random scenes: within one bin for positions."""
    rng_state = world.rng
    world.rng = np.random.default_rng(seed)
    rows = []
    for _ in range(scenes):
        world.randomize()
        rows.append(eyes.labels(world))
    world.rng = rng_state
    L = np.array(rows)
    out = {}
    for k, name in enumerate(SLOT_NAMES[:6]):
        v = L[:, k]
        if k in POSITION_SLOTS:
            out[name] = round(max(float(np.mean(np.abs(v - g) <= 1)) for g in range(12)), 3)
        else:
            out[name] = round(max(float(np.mean(v == g)) for g in range(3)), 3)
    return out


def score(answer: np.ndarray | None, labels: np.ndarray) -> dict[str, float]:
    """Per-slot correctness of one answer: within one bin for positions, exact otherwise;
    ``err_block``/``err_hand`` are the mean absolute bin errors of the position readouts."""
    out = {}
    for k, name in enumerate(SLOT_NAMES):
        if answer is None:
            out[name] = 0.0
        elif k in POSITION_SLOTS:
            out[name] = float(abs(int(answer[k]) - int(labels[0, k])) <= 1)
        else:
            out[name] = float(int(answer[k]) == int(labels[0, k]))
    if answer is None:
        out["err_block"] = out["err_hand"] = 6.0
    else:
        out["err_block"] = float(np.mean([abs(int(answer[k]) - int(labels[0, k])) for k in (0, 1)]))
        out["err_hand"] = float(np.mean([abs(int(answer[k]) - int(labels[0, k])) for k in (2, 3)]))
    out["joints"] = float(answer is not None and all(int(answer[k]) == int(labels[0, k]) for k in range(6, 10)))
    return out


def answer_of(brain: Brain, x: np.ndarray) -> np.ndarray | None:
    try:
        return brain.act(x, greedy=True)[0]
    except RuntimeError:
        return None


def glance(brain: Brain, world: World, eyes: Eyes, scenes: int, seed: int, dark: bool = False) -> dict:
    """First glance from rest on held-out scenes; ``dark`` zeroes the retinas."""
    world.rng = np.random.default_rng(seed)
    totals: dict[str, float] = {}
    refused = 0
    sweeps = []
    for _ in range(scenes):
        world.randomize()
        eyes.reset()
        x = eyes.inputs(world)[None]
        if dark:
            x = x.copy()
            x[:, : eyes.spec.retina] = 0.0
        labels = scene_labels(world, eyes)
        visible = eyes.block_visible(world)
        brain.reset()
        answer = answer_of(brain, x)
        refused += answer is None
        sweeps.append(int((brain.last_settlement or {}).get("steps", 0)))
        for k, v in score(answer, labels).items():
            totals[k] = totals.get(k, 0.0) + v
            if visible and k in ("block_x", "block_y"):
                totals[k + "_visible"] = totals.get(k + "_visible", 0.0) + v
        totals["visible"] = totals.get("visible", 0.0) + float(visible)
    out = {k: round(v / scenes, 3) for k, v in totals.items() if not k.endswith("_visible")}
    seen = max(totals.get("visible", 0.0), 1.0)
    out.update({k: round(v / seen, 3) for k, v in totals.items() if k.endswith("_visible")})
    out.update(scenes=scenes, refused=refused, sweeps=round(float(np.mean(sweeps)), 1))
    return out


def reach(brain: Brain | None, world: World, eyes: Eyes, trials: int, seed: int, limit: int = 30,
          dark: bool = False, policy: str = "brain") -> dict:
    """Closed loop from a random posture: bring the fingertip above the block within ``limit``
    decisions. ``policy`` is ``brain``, ``caregiver`` (the ceiling) or ``random``."""
    world.rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed + 1)
    successes, decisions, final = 0, [], []
    for _ in range(trials):
        world.randomize(holding_rate=0.0)
        world.closed = False
        eyes.reset()
        if brain is not None:
            brain.reset()
        done_at = None
        for d in range(limit):
            target = caregiver.hover_point(world)
            if np.linalg.norm(world.tip() - target) <= 0.025:
                done_at = d
                break
            if policy == "caregiver":
                steps = caregiver.ideal_steps(world, target)
                close = 0
            elif policy == "random":
                steps = rng.integers(-1, 2, size=4)
                close = 0
            else:
                x = eyes.inputs(world)[None]
                if dark:
                    x = x.copy()
                    x[:, : eyes.spec.retina] = 0.0
                answer = answer_of(brain, x)
                if answer is None:
                    steps, close = np.zeros(4), int(world.closed)
                else:
                    steps = steps_of(answer[6:10])
                    close = 0  # the reach assay keeps the gripper open
            world.decide(steps, close)
        target = caregiver.hover_point(world)
        final.append(float(np.linalg.norm(world.tip() - target)))
        if done_at is not None:
            successes += 1
            decisions.append(done_at)
    return {"trials": trials, "success": round(successes / trials, 3),
            "decisions_median": None if not decisions else float(np.median(decisions)),
            "final_distance_median": round(float(np.median(final)), 4)}


def cmd_raise(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    brain, anatomy, head = make_brain(a.seed, a.size, a.eyes, a.change, a.hidden, a.features, a.sheet,
                                      sheets=a.sheets, readout=a.readout, map_reciprocal=not a.map_forward,
                                      map_density=a.map_density, colour=a.colour, tie_rate=a.tie_rate,
                                      eye_streams=a.eye_streams, priors=a.priors,
                                      readout_reciprocal=not a.readout_forward,
                                      map_input_reciprocal=not a.map_input_forward, depth_map=a.depth_map,
                                      memory=not a.no_memory, field=a.field, deep=tuple(a.deep), apical=a.apical)
    raising_config(brain, a.eta, a.decay, a.scale_cap)
    amplitude = brain.working_memory.amplitude if brain.working_memory is not None else None
    if brain.working_memory is not None and not a.trace_while_raising:
        brain.working_memory.amplitude = 0.0
    world, eyes = World(ArmSpec(), a.seed), Eyes(head)
    baseline = chance(world, eyes)
    meta = {"anatomy": {**anatomy.to_dict(), **describe(brain)}, "head": {**head.__dict__, "bright": dict(head.bright)},
            "chance": baseline, "tie_rate": a.tie_rate, "teach_maps": a.teach_maps,
            "pool_eta": a.pool_eta, "pool_nudge": a.pool_nudge,
            "learning": {k: getattr(brain.learner.config, k, None) for k in ("eta", "eta_bias", "momentum", "nudge", "tolerance", "free_steps", "decay", "scale_cap")},
            "labels": "eye coordinates (first eye's column and row bins)",
            "seed": a.seed, "lessons": a.lessons, "eye_lessons": a.eye_lessons, "trace_while_raising": a.trace_while_raising,
            "cadence": cadence.__version__, "numpy": np.__version__, "python": platform.python_version()}
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"brain {brain.connectome.n} neurons, {brain.connectome.synapses} synapses; "
          f"retina {head.channels}x{head.size}x{head.size}, association {anatomy.hidden}", flush=True)
    print("constant-guess baseline: " + " ".join(f"{k} {v}" for k, v in baseline.items()), flush=True)
    t0 = time.time()
    curve = []
    phases = [("eye", a.eye_lessons, eye_learner(brain, teach_maps=a.teach_maps)), ("pools", a.lessons, None)]
    for phase, lessons, learner in phases:
        if lessons <= 0:
            continue
        if phase == "pools":
            brain.learner.config = replace(brain.learner.config, eta=a.pool_eta, nudge=a.pool_nudge)
            if a.apical:  # the deep-brain teaching of 0.90: normalized, a relative floor, whole nudged phases
                brain.learner.config = replace(brain.learner.config, normalize=0.99, normalize_relative=0.1,
                                               nudged_steps=32, nudged_fixed=True)
            if a.eye_lessons > 0:
                pool_phase(brain)  # the visual pathway is fixed from here on
        if learner is None:
            learner = brain.learner
        print(f"phase {phase}: {lessons} lessons, {int(learner.plastic_synapses.sum()) if learner.plastic_synapses is not None else brain.connectome.synapses} plastic synapses", flush=True)
        window: list[dict] = []
        for lesson in range(lessons):
            world.randomize()
            eyes.reset()
            x = eyes.inputs(world)[None]
            labels = scene_labels(world, eyes)
            drive = brain.stimulus(x)
            start = time.perf_counter()
            answer = answer_of(brain, x)
            row = score(answer, labels)
            row["refused"] = float(answer is None)
            row["sweeps"] = float((brain.last_settlement or {}).get("steps", 0))
            warm = brain.basal_ganglia.state if answer is not None else None
            if phase == "eye":
                taught = labels[:, : len(EYE_SLOTS)]
                if a.teach_maps:
                    cells = eyes.map_labels(world, anatomy.sheet)[: anatomy.sheets]
                    taught = np.concatenate([np.array([cells], dtype=np.int64), taught], axis=1)
            else:
                taught = labels
            _, report = learner.step(drive, taught, warm=warm)
            if phase == "eye":
                share_graph(brain, learner)
            row["lesson_sweeps"] = float(report.get("total_steps", 0))
            row["ms"] = (time.perf_counter() - start) * 1000
            window.append(row)
            if len(window) == a.report_every or lesson == lessons - 1:
                mean = {k: round(float(np.mean([r[k] for r in window])), 3) for k in window[0]}
                mean["lesson"] = lesson + 1
                mean["phase"] = phase
                curve.append(mean)
                print(f"{phase} {lesson + 1:6d}  block {mean['block_x']:.2f}/{mean['block_y']:.2f}  hand {mean['hand_x']:.2f}/{mean['hand_y']:.2f}  "
                      f"held {mean['held']:.2f} order {mean['order']:.2f}  joints {mean['joints']:.2f} grip {mean['gripper']:.2f}  "
                      f"err {mean['err_block']:.2f}/{mean['err_hand']:.2f}  sweeps {mean['sweeps']:4.0f}+{mean['lesson_sweeps']:4.0f}  ms {mean['ms']:5.1f}", flush=True)
                window.clear()
    if brain.working_memory is not None and amplitude is not None:
        brain.working_memory.amplitude = amplitude
    if a.episodes > 0:
        brain.learner.config = replace(brain.learner.config, eta=a.pool_eta, nudge=a.pool_nudge)
        if a.eye_lessons > 0 and a.lessons <= 0:
            pool_phase(brain)
        rng = np.random.default_rng(a.seed + 77)
        print(f"phase episodes: {a.episodes} closed-loop corrected reaches, caregiver share {a.mixture} -> {a.mixture_end}", flush=True)
        curve += episodes_phase(brain, world, eyes, a.episodes, a.limit, a.report_every_episodes, a.mixture, rng,
                                mixture_end=a.mixture_end)
    path = brain.save(out / "brain.npz")
    summary = {"eye_lessons": a.eye_lessons, "lessons": a.lessons, "episodes": a.episodes,
               "seconds": round(time.time() - t0, 1), "curve": curve}
    (out / "curve.json").write_text(json.dumps(summary, indent=1))
    if a.assay:
        summary["assays"] = run_assays(path, head, a.seed, a.assay_scenes, a.assay_trials)
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary["assays"], indent=1), flush=True)


def run_assays(path, head: HeadSpec, seed: int, scenes: int, trials: int) -> dict:
    world, eyes = World(ArmSpec(), seed), Eyes(head)
    brain = Brain.load(path)
    held = 10_000 + seed
    out = {
        "glance": glance(brain, world, eyes, scenes, held),
        "glance_dark": glance(brain, world, eyes, scenes, held, dark=True),
        "reach": reach(brain, world, eyes, trials, held + 1),
        "reach_dark": reach(brain, world, eyes, trials, held + 1, dark=True),
        "reach_caregiver": reach(None, world, eyes, trials, held + 1, policy="caregiver"),
        "reach_random": reach(None, world, eyes, trials, held + 1, policy="random"),
    }
    return out


def episodes_phase(brain: Brain, world: World, eyes: Eyes, episodes: int, limit: int, report_every: int,
                   mixture: float, rng: np.random.Generator, mixture_end: float | None = None) -> list[dict]:
    """Closed-loop corrected reaching: from a random posture the arm drives toward the block, the
    caregiver labels every state it visits and the lesson is taken there, so the pools learn on
    the states they will meet, the last centimetres included. With probability ``mixture`` the
    caregiver's own step is executed instead of the brain's, which keeps the early episodes on
    useful states."""
    curve, window, successes, lengths = [], [], 0, []
    end = mixture if mixture_end is None else mixture_end
    for episode in range(episodes):
        share = mixture + (end - mixture) * episode / max(episodes - 1, 1)  # the caregiver's share fades
        world.randomize(holding_rate=0.0)
        world.closed = False
        eyes.reset()
        reached = None
        for d in range(limit):
            target = caregiver.hover_point(world)
            if np.linalg.norm(world.tip() - target) <= 0.025:
                reached = d
                break
            x = eyes.inputs(world)[None]
            want = caregiver.reach_labels(world, target)
            labels = np.array([eyes.labels(world) + want], dtype=np.int64)
            drive = brain.stimulus(x)
            start = time.perf_counter()
            answer = answer_of(brain, x)
            row = score(answer, labels)
            row["sweeps"] = float((brain.last_settlement or {}).get("steps", 0))
            warm = brain.basal_ganglia.state if answer is not None else None
            _, report = brain.learner.step(drive, labels, warm=warm)
            row["lesson_sweeps"] = float(report.get("total_steps", 0))
            row["ms"] = (time.perf_counter() - start) * 1000
            row["refused"] = float(answer is None)
            window.append(row)
            if answer is None or rng.random() < share:
                steps = steps_of(want[:4])
            else:
                steps = steps_of(answer[len(EYE_SLOTS):len(EYE_SLOTS) + 4])
            world.decide(steps, 0)
        successes += reached is not None
        lengths.append(limit if reached is None else reached)
        if (episode + 1) % report_every == 0 or episode == episodes - 1:
            mean = {k: round(float(np.mean([r[k] for r in window])), 3) for k in window[0]} if window else {}
            mean.update(episode=episode + 1, phase="episodes", reached=round(successes / report_every, 3),
                        decisions=round(float(np.mean(lengths)), 1))
            curve.append(mean)
            print(f"episodes {episode + 1:5d}  reached {mean['reached']:.2f} in {mean['decisions']:.1f}  "
                  f"joints {mean.get('joints', 0):.2f}  yaw {mean.get('yaw', 0):.2f} sh {mean.get('shoulder', 0):.2f} "
                  f"el {mean.get('elbow', 0):.2f} wr {mean.get('wrist', 0):.2f}  sweeps {mean.get('sweeps', 0):4.0f}  ms {mean.get('ms', 0):5.1f}", flush=True)
            window, successes, lengths = [], 0, []
    return curve


def cmd_continue(a: argparse.Namespace) -> None:
    """Continue a saved brain with closed-loop corrected reaching, then the assays."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run = json.loads((Path(a.brain).parent / "run.json").read_text())
    head = head_of(run)
    brain = Brain.load(a.brain)
    brain.reset()
    if brain.working_memory is not None:
        brain.working_memory.amplitude = a.trace_amplitude
    world, eyes = World(ArmSpec(), a.seed), Eyes(head)
    rng = np.random.default_rng(a.seed + 77)
    t0 = time.time()
    curve = episodes_phase(brain, world, eyes, a.episodes, a.limit, a.report_every, a.mixture, rng)
    path = brain.save(out / "brain.npz")
    run.update(continued_from=str(a.brain), episodes=a.episodes, mixture=a.mixture, trace_amplitude=a.trace_amplitude)
    (out / "run.json").write_text(json.dumps(run, indent=1, default=str))
    summary = {"episodes": a.episodes, "seconds": round(time.time() - t0, 1), "curve": curve}
    (out / "curve.json").write_text(json.dumps(summary, indent=1))
    if a.assay:
        summary["assays"] = run_assays(path, head, run["seed"], a.assay_scenes, a.assay_trials)
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary["assays"], indent=1), flush=True)


def head_of(run: dict) -> HeadSpec:
    h = run["head"]
    return HeadSpec(size=h["size"], eyes=h["eyes"], baseline=h["baseline"], position=tuple(h["position"]),
                    target=tuple(h["target"]), fov=h["fov"], change=h["change"], colour=h.get("colour", False))


def cmd_assay(a: argparse.Namespace) -> None:
    run = json.loads((Path(a.brain).parent / "run.json").read_text())
    h = run["head"]
    head = HeadSpec(size=h["size"], eyes=h["eyes"], baseline=h["baseline"], position=tuple(h["position"]),
                    target=tuple(h["target"]), fov=h["fov"], change=h["change"], colour=h.get("colour", False))
    result = run_assays(a.brain, head, run["seed"], a.scenes, a.trials)
    print(json.dumps(result, indent=1))
    (Path(a.brain).parent / "assay.json").write_text(json.dumps(result, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("raise")
    r.add_argument("--out", required=True)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--lessons", type=int, default=12000, help="lessons of the pools phase")
    r.add_argument("--eye-lessons", dest="eye_lessons", type=int, default=0, help="lessons of the eye phase first")
    r.add_argument("--teach-maps", dest="teach_maps", action="store_true", help="teach each map the cell under its object")
    r.add_argument("--episodes", type=int, default=0, help="closed-loop corrected reaches after the pools phase")
    r.add_argument("--limit", type=int, default=30)
    r.add_argument("--mixture", type=float, default=0.5, help="the caregiver's share of executed steps at first")
    r.add_argument("--mixture-end", dest="mixture_end", type=float, default=0.0, help="and at the last episode")
    r.add_argument("--report-every-episodes", dest="report_every_episodes", type=int, default=50)
    r.add_argument("--size", type=int, default=40)
    r.add_argument("--eyes", type=int, default=2)
    r.add_argument("--change", action="store_true")
    r.add_argument("--colour", action="store_true", help="a second cone channel per eye: redness")
    r.add_argument("--hidden", type=int, default=256)
    r.add_argument("--deep", type=int, nargs="*", default=[], help="widths of further association regions (0.91)")
    r.add_argument("--apical", type=float, default=0.0, help="the apical compartment's fraction (0.91)")
    r.add_argument("--features", type=int, default=8)
    r.add_argument("--field", type=int, default=5, help="side of a V1 cell's window in pixels")
    r.add_argument("--sheet", type=int, default=18)
    r.add_argument("--sheets", type=int, default=1)
    r.add_argument("--readout", default="dense", choices=("dense", "topographic"))
    r.add_argument("--map-forward", dest="map_forward", action="store_true", help="maps drive the association one way")
    r.add_argument("--map-density", dest="map_density", type=float, default=1.0)
    r.add_argument("--tie-rate", dest="tie_rate", default="sum", choices=("sum", "sqrt", "mean"))
    r.add_argument("--eye-streams", dest="eye_streams", action="store_true", help="one V1 per eye; maps read the first")
    r.add_argument("--priors", action="store_true", help="innate colour wiring of V1 features and maps")
    r.add_argument("--readout-forward", dest="readout_forward", action="store_true", help="readouts read the maps one way")
    r.add_argument("--map-input-forward", dest="map_input_forward", action="store_true", help="maps read V1 one way")
    r.add_argument("--depth-map", dest="depth_map", action="store_true", help="the second eye feeds a map, not a dense projection")
    r.add_argument("--no-memory", dest="no_memory", action="store_true", help="no episodic memory stores (a lean page brain)")
    r.add_argument("--eta", type=float, default=0.1, help="the eye phase's teaching step")
    r.add_argument("--pool-eta", dest="pool_eta", type=float, default=0.1, help="the pools' and episodes' teaching step")
    r.add_argument("--pool-nudge", dest="pool_nudge", default="quadratic", choices=("quadratic", "cross_entropy"))
    r.add_argument("--decay", type=float, default=0.0)
    r.add_argument("--scale-cap", dest="scale_cap", type=float, default=None)
    r.add_argument("--trace-while-raising", dest="trace_while_raising", action="store_true")
    r.add_argument("--report-every", dest="report_every", type=int, default=500)
    r.add_argument("--no-assay", dest="assay", action="store_false")
    r.add_argument("--assay-scenes", dest="assay_scenes", type=int, default=300)
    r.add_argument("--assay-trials", dest="assay_trials", type=int, default=40)
    r.set_defaults(func=cmd_raise)
    c = sub.add_parser("continue")
    c.add_argument("--brain", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--episodes", type=int, default=400)
    c.add_argument("--limit", type=int, default=30)
    c.add_argument("--mixture", type=float, default=0.3, help="share of decisions the caregiver executes")
    c.add_argument("--trace-amplitude", dest="trace_amplitude", type=float, default=3.0)
    c.add_argument("--report-every", dest="report_every", type=int, default=25)
    c.add_argument("--no-assay", dest="assay", action="store_false")
    c.add_argument("--assay-scenes", dest="assay_scenes", type=int, default=300)
    c.add_argument("--assay-trials", dest="assay_trials", type=int, default=40)
    c.set_defaults(func=cmd_continue)
    s = sub.add_parser("assay")
    s.add_argument("--brain", required=True)
    s.add_argument("--scenes", type=int, default=300)
    s.add_argument("--trials", type=int, default=40)
    s.set_defaults(func=cmd_assay)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
