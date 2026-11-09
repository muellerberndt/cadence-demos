"""Raise a Castlevania brain on cadence-net 0.95.2: imitation of the RAM-reading teacher in
several streams at once, then (optionally) expert iteration with a search over emulator
savestates, the AlphaZero recipe at one ply.

The brain is ``Brain.compose(827, 10, modules=..., slots=(3, 3, 2, 2), arousal=True, **genes)``:
the composition of cadence-net 0.95 (the recall memory at ``teaching="deep"``, lessons by surprise) with the
genes of the config (by default ``memory_choice``, two recall heads, the executed command and
the boundary in the recall memory). Its eye is eye v2 (``eye.py``, 827 inputs).

Imitation (every decision until ``search_at``): ``streams`` practice segments run side by side
in the process's one emulator (each stream's savestate is restored before its step). Every
moment the teacher labels each stream's state, the brain takes one lesson on all rows
(``Brain.lesson(x, labels, weights=w)``; a row at a critical place of the route, or one whose
label whips, jumps or presses up, weighs ``critical_weight``), then acts greedily on all rows;
the teacher's action is executed.

Expert iteration (from ``search_at`` decisions on): the segments start at the same practice
states, and the brain drives. On a share ``search_share`` of the rows a search labels the
state: the brain's memory-free settle gives priors over the 36 pad actions (the product of its
four slots' softmax at the learner's temperature); the ``search_k`` most likely actions and the
teacher's are each executed from the savestate and rolled out ``search_horizon`` decisions by
the teacher's heuristic (no lookahead); a rollout's value is the progress gained (world x, a
new block of the stage counted as 300 px, a stage clear as 600 px) less 1,500 px per life lost and 30 px per health point lost;
``search_sims`` PUCT visits (``c_puct``, Dirichlet noise 0.25/0.3 at the root) over those
values give the visit shares, and the row is taught their marginals per slot
(``Brain.lesson(x, targets=p)``; a row whose values spread by a life or more weighs
``critical_weight``). The most visited action is executed. The other rows are labelled by the
teacher (with its bat lookahead) and the brain's own greedy action is executed (DAgger). Every
row of a moment is taught in one lesson of targets (a label as its one-hot row).

Evaluations every ``eval_every`` decisions at a segment boundary: a deep copy plays greedily
from power-on (``eval_starts``, ``eval_decisions`` each); a checkpoint ``d<N>.brain.npz``;
``readings.jsonl`` and ``result.json``. ``--resume`` continues from the
newest checkpoint.

    python training/train.py --config '{"name": "a", "seed": 0}' --out runs/a
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from common import (ACTIONS, EYES, SLOTS, Body, from_parts, frozen_evaluation, library,
                    load_practice, load_validation, note_executed, place, predict_reading,
                    readings, sensor_from, summarize, tags_of, teacher_action, to_parts, world_x)

DRAW = {"all": 0.2, "start": 0.08, "stage1_start": 0.04, "stairs1": 0.15, "stage2_start": 0.04,
        "stage2_left": 0.06, "water_jumps": 0.05, "under_stairs": 0.05, "stage2_exit": 0.06,
        "whip": 0.07, "stage3": 0.06, "bat": 0.08, "stage4": 0.06}
DEFAULTS = {
    "name": "arm", "seed": 0, "modules": [256, 128], "eye": "v2",
    "genes": {"memory_choice": True, "recall_heads": 2, "recall_action": True, "recall_boundary": True},
    "streams": 8, "segment": 40, "budget": 300000, "draw": DRAW, "critical_weight": 3.0,
    "eval_every": 25000, "eval_starts": [0, 7, 14], "eval_decisions": 1500,
    "search_at": 0, "search_share": 0.5, "search_k": 5, "search_horizon": 16, "search_sims": 48,
    "c_puct": 1.5, "search_min_spread": 16.0, "noise": 0.25, "noise_alpha": 0.3, "wall_hours": 0,
    "practice": "runs/pool/practice.pkl", "validation": "runs/pool/validation.npz",
    "load": None, "backend": None,
}
CRITICAL = {"stairs1", "stage2_left", "water_jumps", "under_stairs", "stage2_exit", "stage3", "bat",
            "stage4", "whip", "jump"}
PARTS = np.array([[h + 1, v + 1, w, j] for h, v, w, j in ACTIONS])  # 36 x 4 slot choices
OFFSETS = np.cumsum((0,) + SLOTS[:-1])  # the slots' first motor columns: 0, 3, 6, 8


def compose(cfg: dict):
    """The 0.95 composition with the config's genes; ``teach_eta`` (not a library gene) names the
    raw learner instead of the teaching point: a raw step ``teach_eta`` (bias a tenth),
    unqualified, every row taught, 32 nudged sweeps run whole (``LearnerConfig``)."""
    from cadence import Brain
    genes = dict(cfg["genes"])
    eta = genes.pop("teach_eta", None)
    if eta is not None:
        from cadence.learning import LearnerConfig
        genes["learning"] = LearnerConfig(
            beta=0.1, eta=float(eta), eta_bias=float(eta) / 10, temperature=0.2, tolerance=3e-3,
            free_steps=1024, nudged_steps=32, momentum=0.9, qualified=False, nudged_fixed=True,
            surprise=False)
    return Brain.compose(EYES[cfg["eye"]], sum(SLOTS), modules=tuple(cfg["modules"]), slots=SLOTS,
                         seed=cfg["seed"], arousal=True, **({"backend": cfg["backend"]} if cfg.get("backend") else {}), **genes)


def one_hot_targets(labels) -> np.ndarray:
    out = np.zeros((len(labels), sum(SLOTS)))
    for r, label in enumerate(labels):
        for k, choice in enumerate(PARTS[int(label)]):
            out[r, OFFSETS[k] + choice] = 1.0
    return out


def marginals(dist: dict[int, float]) -> np.ndarray:
    out = np.zeros(sum(SLOTS))
    for action, share in dist.items():
        for k, choice in enumerate(PARTS[action]):
            out[OFFSETS[k] + choice] += share
    return out


def priors(brain, x: np.ndarray) -> np.ndarray:
    """(rows, 36) action probabilities of the memory-free settle: the product of the slots'
    softmax over the settled motor activations at the learner's temperature."""
    state = brain.learner.free(brain.stimulus(x, memory=False))
    act = np.asarray(state.activation)[:, brain.learner.output_index]
    temp = float(brain.learner.config.temperature)
    probs = np.ones((len(x), len(ACTIONS)))
    for k, size in enumerate(SLOTS):
        z = act[:, OFFSETS[k]:OFFSETS[k] + size] / temp
        z = np.exp(z - z.max(axis=1, keepdims=True))
        z /= z.sum(axis=1, keepdims=True)
        probs *= z[:, PARTS[:, k]]
    return probs


def progress(ram) -> tuple[int, int]:
    r = readings(ram)
    return r["stage"], world_x(ram)


def rollout(body, root: bytes, memory: dict, first: int, horizon: int) -> float:
    """Execute ``first`` from the savestate, then the teacher's heuristic for ``horizon``
    decisions; the value in pixels of progress."""
    ram = body.restore(root)
    start = readings(ram)
    stage0, wx0 = start["stage"], world_x(ram)
    best, lives_lost, health_lost = 0.0, 0, 0
    mem = copy.deepcopy(memory)
    mem.pop("plan", None)
    stage_seen = stage0
    block0, blocks = int(ram[0x46]), 0
    action = first
    previous = start
    for t in range(horizon + 1):
        if t > 0:
            label = int(teacher_action(ram, mem, None))
            note_executed(mem, label, label)
            action = label
        frame, ram, done = body.step(action)
        now = readings(ram)
        if now["lives"] < previous["lives"]:
            lives_lost += 1
        health_lost += max(previous["health"] - now["health"], 0) if now["lives"] == previous["lives"] else 0
        previous = now
        if now["stage"] != 20 and now["stage"] != stage_seen and now["stage"] > stage_seen:
            stage_seen = now["stage"]
        if now["stage"] == stage0 and int(ram[0x46]) != block0 and now["health"] > 0:
            blocks = 1  # a new block of the stage (the stairs down into the underground, and out)
        if now["stage"] != 20:
            gain = 600.0 * (stage_seen - stage0) + 300.0 * blocks \
                + (world_x(ram) - wx0 if now["stage"] == stage0 and not blocks else 0)
            best = max(best, float(gain))
        if done or lives_lost:
            break
    return best - 1500.0 * lives_lost - 30.0 * health_lost


def search(body, root: bytes, memory: dict, prior: np.ndarray, label: int, cfg: dict, rng) -> dict:
    """One-ply PUCT over rollouts: visit shares over the candidates, their values, the most
    visited action."""
    order = list(np.argsort(-prior)[:cfg["search_k"]])
    if label not in order:
        order.append(int(label))
    cand = [int(a) for a in order]
    p = prior[cand] / max(prior[cand].sum(), 1e-12)
    if cfg["noise"] > 0:
        p = (1 - cfg["noise"]) * p + cfg["noise"] * rng.dirichlet([cfg["noise_alpha"]] * len(cand))
    values = np.array([rollout(body, root, memory, a, cfg["search_horizon"]) for a in cand])
    body.restore(root)
    spread = float(values.max() - values.min())
    if spread < cfg["search_min_spread"]:  # the rollouts tell the candidates apart by too little
        return {"dist": {int(label): 1.0}, "values": values.tolist(), "candidates": cand,
                "chosen": int(label), "spread": spread, "informative": False}
    q = (values - values.min()) / spread if spread > 1e-9 else np.full(len(cand), 0.5)
    n = np.zeros(len(cand))
    for _ in range(cfg["search_sims"]):
        u = q + cfg["c_puct"] * p * math.sqrt(1 + n.sum()) / (1 + n)
        n[int(np.argmax(u))] += 1
    shares = n / n.sum()
    return {"dist": {a: float(s) for a, s in zip(cand, shares) if s > 0}, "values": values.tolist(),
            "candidates": cand, "chosen": cand[int(np.argmax(n))], "spread": spread, "informative": True}


class Stream:
    """One practice segment's custody: the savestate, the eye's carried state, the teacher's
    memory, the observation to answer and the harvest's label script."""

    def __init__(self, state: dict, eye: str) -> None:
        self.emu = state["emu"]
        self.sensor = sensor_from(state["sensor"])
        self.memory = copy.deepcopy(state["memory"])
        self.memory.pop("plan", None)
        self.x = state["obs"].astype(float)
        self.script = list(state.get("labels", ()))
        self.k = 0
        self.eye = eye


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    given = json.loads(Path(a.config).read_text()) if a.config.endswith(".json") else json.loads(a.config)
    cfg = {**DEFAULTS, **given}
    t0 = time.time()
    rng = np.random.default_rng(10_000 + cfg["seed"])
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    result_path, readings_path = out / "result.json", out / "readings.jsonl"
    states = load_practice(Path(cfg["practice"]))
    for extra in cfg.get("extra_pools", []):  # e.g. a frozen brain's stall and death points (harvest.py --failures)
        states = states + load_practice(Path(extra))
    validation = load_validation(Path(cfg["validation"]))
    inputs = EYES[cfg["eye"]]
    if len(states[0]["obs"]) != inputs:
        raise ValueError("the practice states carry another eye's observations")
    groups: dict[str, list] = {"all": list(range(len(states)))}
    for i, s in enumerate(states):
        for tag in s["tags"] + ([s["failure"]] if s.get("failure") else []):
            groups.setdefault(tag, []).append(i)
        if s["stage"] == 0 and s["wx"] < 200:
            groups.setdefault("start", []).append(i)
        if s["stage"] == 1 and s["wx"] < 300:
            groups.setdefault("stage1_start", []).append(i)
        if s["stage"] == 2 and s["block"] == 1 and s["y"] < 150 and s["wx"] < 200:
            groups.setdefault("stage2_start", []).append(i)
    names = [k for k, w in cfg["draw"].items() if w > 0 and groups.get(k)]
    weights_draw = np.array([cfg["draw"][k] for k in names], float)
    weights_draw /= weights_draw.sum()

    from cadence import Brain
    checkpoints = sorted(((int(f.name[1:-10]), f) for f in out.glob("d*.brain.npz")), key=lambda t: t[0])
    result = {"config": cfg, "library": library(), "inputs": inputs, "evaluations": [],
              "draw_groups": {k: len(groups[k]) for k in names}}
    counters = {"decisions": 0, "lessons": 0, "lesson_refused": 0, "act_refused": 0, "searched": 0,
                "search_changed": 0, "search_informative": 0, "own_ran": 0, "teacher_ran": 0, "segments": 0, "weighted_rows": 0}
    if a.resume and checkpoints:
        at, newest = checkpoints[-1]
        brain = Brain.load(newest, backend=cfg["backend"]) if cfg["backend"] else Brain.load(newest)
        saved = json.loads(result_path.read_text()) if result_path.exists() else {}
        result["evaluations"] = [e for e in saved.get("evaluations", []) if e["decision"] <= at]
        counters.update(saved.get("counters", {}))
        counters["decisions"] = at
        result["resumed"] = saved.get("resumed", []) + [at]
        if readings_path.exists():
            keep = [l for l in readings_path.read_text().splitlines() if l.strip() and json.loads(l)["decisions"] <= at]
            readings_path.write_text("".join(l + "\n" for l in keep))
    elif cfg["load"]:
        brain = Brain.load(cfg["load"], backend=cfg["backend"]) if cfg["backend"] else Brain.load(cfg["load"])
        counters["decisions"] = int(cfg.get("load_decisions", 0))
        result["loaded"] = {"from": cfg["load"], "decisions": counters["decisions"]}
    else:
        brain = compose(cfg)
    if len(brain.sensory_index) != inputs:
        raise ValueError("the brain's inputs do not match the eye")
    result["describe"] = {k: v for k, v in brain.describe().items() if k in ("layout", "recall", "learning", "parameters")}
    body = Body()

    def save() -> None:
        result.update(counters=counters, seconds=round(time.time() - t0, 1))
        tmp = result_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=1, default=float) + "\n")
        os.replace(tmp, result_path)

    def evaluate(label: str) -> None:
        te = time.time()
        ev = frozen_evaluation(brain, body, cfg["eval_starts"], cfg["eval_decisions"], eye=cfg["eye"])
        reading = predict_reading(brain, validation)
        entry = {"label": label, "decision": counters["decisions"], **summarize(ev),
                 "predict": reading, "seconds": round(time.time() - te, 1)}
        result["evaluations"].append(entry)
        with open(readings_path, "a") as handle:
            for g in ev["greedy"]:
                handle.write(json.dumps({"decisions": counters["decisions"], "start": g["noops"],
                                         "stage": g["furthest_stage"], "world_x": g["world_x"],
                                         "deaths_by_stage": g["deaths_by_stage"],
                                         "bat_hp_dealt": g["bat_hp_dealt"],
                                         "passed_stairs": bool(g["passed_stairs"]),
                                         "progress": g["progress"], "lives_lost": g["lives_lost"],
                                         "arm": cfg["name"], "seed": cfg["seed"], "label": label}) + "\n")
        brain.save(out / f"d{counters['decisions']}.brain")
        print(json.dumps({"label": label, "decision": counters["decisions"], "stage": entry["stage"],
                          "progress": entry["progress"], "past_stairs": entry["past_stairs"],
                          "lives_lost": entry["lives_lost"], "predict": round(reading["agreement"], 3),
                          "searched": counters["searched"], "t": round(time.time() - t0)}), flush=True)
        save()

    next_eval = (counters["decisions"] // cfg["eval_every"] + 1) * cfg["eval_every"]
    S, K = cfg["streams"], cfg["segment"]
    deadline = t0 + 3600 * cfg["wall_hours"] if cfg["wall_hours"] else None
    while counters["decisions"] < cfg["budget"]:
        if deadline and time.time() > deadline:
            result["stopped"] = "wall_hours"
            break
        searching = bool(cfg["search_at"]) and counters["decisions"] >= cfg["search_at"]
        streams = []
        for _ in range(S):
            name = names[int(rng.choice(len(names), p=weights_draw))]
            streams.append(Stream(states[int(rng.choice(groups[name]))], cfg["eye"]))
        counters["segments"] += S
        brain.reset()
        for k in range(K):
            x = np.stack([s.x for s in streams])
            labels, rams, search_rows = [], [], {}
            prior = priors(brain, x) if searching and cfg["search_share"] > 0 else None
            for i, s in enumerate(streams):
                ram = body.restore(s.emu)
                rams.append(ram)
                if s.k < len(s.script):
                    label = int(s.script[s.k])
                else:
                    label = int(teacher_action(ram, s.memory, body))
                    body.restore(s.emu)
                labels.append(label)
                if searching and rng.random() < cfg["search_share"]:
                    search_rows[i] = search(body, s.emu, s.memory, prior[i], label, cfg, rng)
                    counters["searched"] += 1
                    counters["search_changed"] += search_rows[i]["chosen"] != label
                    counters["search_informative"] += bool(search_rows[i]["informative"])
            w = np.ones(S)
            for i, (ram, label) in enumerate(zip(rams, labels)):
                critical = bool(CRITICAL.intersection(tags_of(place(ram), label))) or ACTIONS[label][1] < 0
                if i in search_rows:
                    critical = search_rows[i]["spread"] >= 1500.0 or critical
                w[i] = cfg["critical_weight"] if critical else 1.0
            counters["weighted_rows"] += int((w > 1).sum())
            try:
                if searching:
                    targets = one_hot_targets(labels)
                    for i, found in search_rows.items():
                        targets[i] = marginals(found["dist"])
                    brain.lesson(x, targets=targets, weights=w)
                else:
                    brain.lesson(x, to_parts(labels), weights=w)
                counters["lessons"] += S
            except RuntimeError:
                counters["lesson_refused"] += S
            try:
                own = from_parts(brain.act(x, greedy=True))
            except RuntimeError:
                counters["act_refused"] += S
                own = np.full(S, -1)
            for i, s in enumerate(streams):
                label = labels[i]
                if i in search_rows:
                    executed = search_rows[i]["chosen"]
                elif searching and own[i] >= 0:
                    executed = int(own[i])
                    counters["own_ran"] += 1
                else:
                    executed = label
                    counters["teacher_ran"] += 1
                ram = body.restore(s.emu)
                note_executed(s.memory, label, executed)
                if executed != label:
                    s.script = []
                s.sensor.executed(executed)
                frame, ram, done = body.step(executed)
                s.k += 1
                if done:  # a game over inside a segment: this stream starts again at a new place
                    name = names[int(rng.choice(len(names), p=weights_draw))]
                    streams[i] = Stream(states[int(rng.choice(groups[name]))], cfg["eye"])
                    continue
                s.x = s.sensor.observe(frame, ram)
                s.emu = body.snapshot()
            counters["decisions"] += S
            if counters["decisions"] >= cfg["budget"]:
                break
        if counters["decisions"] >= next_eval:
            next_eval += cfg["eval_every"]
            evaluate("periodic")
    if not result["evaluations"] or result["evaluations"][-1]["decision"] != counters["decisions"]:
        evaluate("end")
    brain.save(out / "end.brain")
    save()
    (out / "DONE").write_text(json.dumps({"seconds": round(time.time() - t0, 1), "counters": counters}) + "\n")
    print(json.dumps({"done": cfg["name"], "seconds": round(time.time() - t0, 1), "counters": counters}), flush=True)
    body.close()


if __name__ == "__main__":
    main()
