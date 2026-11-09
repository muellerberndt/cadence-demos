"""Teacher games for practice: practice states, a held-out validation set.

Each teacher game starts at power-on after ``noops`` idle decisions; with ``epsilon`` > 0 a
random action replaces the teacher's with that probability (the label stays the teacher's), so
the states also cover places just off the route. A game stops at game over, at ``--max``
decisions, or after a long stretch without new ground. Every ``--every`` decisions a practice
state is kept: the emulator state, the eye's observation and carried state, the teacher's
memory, the place tags and the teacher's next labels (the trainer replays them while the
teacher drives). The validation set keeps the observation, the label and the tags of every
``--val-every`` decision. ``--failures BRAIN`` keeps the states where a frozen brain stalled or
died, for practice from there.

    python training/harvest.py --out runs/pool --part train --train-noops 0 2 4 --epsilons 0 0.1
    python training/harvest.py --out runs/pool --part val
"""

from __future__ import annotations

import argparse
import copy
import json
import pickle
import time
from pathlib import Path

import numpy as np

from common import (ACTIONS, Body, choice, eye_of_inputs, make_sensor, note_executed, place,
                    readings, sensor_state, tags_of, teacher_action)


def game(body: Body, noops: int, epsilon: float, seed: int, maximum: int, every: int,
         keep_states: bool, eye: str):
    rng = np.random.default_rng(seed)
    frame, ram = body.power_on(noops)
    sensor, memory = make_sensor(eye), {}
    states, rows = [], []
    reach: dict = {}  # (stage, block) -> [min wx, max wx]; a game without progress for STALL decisions ends
    since = 0
    for t in range(maximum):
        x = sensor.observe(frame, ram).astype(np.float32)
        before_memory = copy.deepcopy(memory)
        label = teacher_action(ram, memory, body)
        p = place(ram)
        tags = tags_of(p, label)
        if p["stage"] == 1 and 1285 <= p["wx"] <= 1305 and p["y"] >= 184:
            tags.append("stairs1_window")
        row = {"game": f"n{noops}_e{epsilon}_s{seed}", "t": t, "label": int(label), "tags": tags, **p}
        rows.append((x, row))
        if keep_states and t % every == 0:
            states.append({**row, "emu": body.snapshot(), "obs": x,
                           "sensor": copy.deepcopy(sensor_state(sensor, eye)),
                           "memory": before_memory})
        executed = label
        if epsilon > 0 and rng.random() < epsilon:
            executed = int(rng.integers(len(ACTIONS)))
        note_executed(memory, label, executed)
        sensor.executed(executed)
        frame, ram, done = body.step(executed)
        q = place(ram)
        span = reach.setdefault((q["stage"], q["block"]), [q["wx"], q["wx"]])
        since = 0 if (q["wx"] < span[0] - 8 or q["wx"] > span[1] + 8 or span == [q["wx"], q["wx"]]) else since + 1
        span[0], span[1] = min(span[0], q["wx"]), max(span[1], q["wx"])
        if done or since >= STALL:
            break
    # the teacher's next labels from each kept state: with the teacher driving, the segment
    # from a restored state is deterministic, so train.py replays these instead of planning
    # the bat fight again (it plans live as soon as something else is executed)
    labels = [row["label"] for _, row in rows]
    for s in states:
        s["labels"] = labels[s["t"]:s["t"] + SCRIPT]
    return states, rows


SCRIPT = 96  # labels kept per practice state (longer than any practice segment)
STALL = 200  # a teacher game ends after this many decisions without reaching new ground


def failure_points(body: Body, brain, noops: int, maximum: int, stall: int, eye: str) -> tuple[list, dict]:
    """The frozen brain's stalls and deaths from one start, as practice-like states."""
    brain_eye = eye_of_inputs(len(brain.sensory_index))
    brain.reset()
    frame, ram = body.power_on(noops)
    own, mine, memory = make_sensor(brain_eye), make_sensor(eye), {}
    ring: list[dict] = []  # the last ``stall`` decisions' states
    kept = []
    best, since_best, stalled_at = None, 0, None
    stage_of = {"deaths": 0, "stalls": 0, "decisions": 0, "furthest": 0}
    for t in range(maximum):
        x_own = own.observe(frame, ram)
        x_mine = x_own if brain_eye == eye else mine.observe(frame, ram)
        before_memory = copy.deepcopy(memory)
        label = int(teacher_action(ram, memory))
        p = place(ram)
        ring.append({**{k: p[k] for k in p}, "t": t, "label": label, "tags": tags_of(p, label),
                     "emu": body.snapshot(), "obs": x_mine.astype(np.float32),
                     "sensor": copy.deepcopy(sensor_state(mine if brain_eye != eye else own, eye)),
                     "memory": before_memory, "game": f"fail_n{noops}"})
        ring = ring[-(stall + 1):]
        try:
            action = choice(brain.act(x_own[None, :], greedy=True))
        except RuntimeError:
            break
        note_executed(memory, label, action)
        own.executed(action)
        if brain_eye != eye:
            mine.executed(action)
        before = readings(ram)
        frame, ram, done = body.step(action)
        after = readings(ram)
        stage_of["decisions"] = t + 1
        if after["stage"] != 20:
            stage_of["furthest"] = max(stage_of["furthest"], after["stage"])
        q = place(ram)
        # world progress: stage, then block-independent world x (left is progress on the
        # stage-2 ground floor; count any 8-px move of the furthest point as progress)
        where = (q["stage"] if q["stage"] != 20 else 0, q["block"], q["wx"])
        if best is None or where[0] > best[0] or where[1] != best[1] or abs(where[2] - best[2]) >= 8:
            if best is None or where[0] > best[0] or where[1] != best[1] or where[2] > best[2] \
                    or (q["stage"] == 2 and q["block"] == 1 and q["y"] >= 150 and where[2] < best[2]):
                best, since_best, stalled_at = where, 0, None
        since_best += 1
        if after["health"] == 0 and before["health"] > 0:
            stage_of["deaths"] += 1
            for back in (stall // 2, stall):
                if len(ring) > back:
                    s = ring[-1 - back]
                    kept.append({**s, "tags": s["tags"] + ["failure", "death", f"stage{s['stage']}"],
                                 "failure": "death", "back": back})
            ring = []
            since_best = 0
        elif since_best == stall and stalled_at is None and len(ring) >= stall:
            s = ring[0]
            kept.append({**s, "tags": s["tags"] + ["failure", "stall", f"stage{s['stage']}"],
                         "failure": "stall", "back": stall})
            stage_of["stalls"] += 1
            stalled_at = t
        if done:
            break  # a stalled brain plays on: a pause at the hall entrance is not the end
    return kept, stage_of


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--eye", type=str, default="v2", help="the eye (v2)")
    p.add_argument("--train-noops", type=int, nargs="+", default=list(range(0, 24, 2)))
    p.add_argument("--val-noops", type=int, nargs="+", default=[1, 5, 11, 17])
    p.add_argument("--epsilons", type=float, nargs="+", default=[0.0, 0.1])
    p.add_argument("--every", type=int, default=2)
    p.add_argument("--val-every", type=int, default=2)
    p.add_argument("--max", type=int, default=2500)
    p.add_argument("--part", type=str, default="all",
                   help="train (practice states and trajectories), traj (trajectories only), val or all")
    p.add_argument("--failures", type=Path, default=None, help="a saved brain: write failures.pkl")
    p.add_argument("--failure-noops", type=int, nargs="+", default=[0, 3, 7, 10, 14, 21])
    p.add_argument("--stall", type=int, default=30)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    body = Body()
    t0 = time.time()
    summary = {"args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()},
               "games": []}
    if a.failures is not None:
        from cadence import Brain
        brain = Brain.load(a.failures)
        kept, per_start = [], []
        for noops in a.failure_noops:
            states, info = failure_points(body, brain, noops, a.max, a.stall, a.eye)
            kept += states
            per_start.append({"noops": noops, **info, "kept": len(states)})
            print(json.dumps(per_start[-1]), flush=True)
        with open(a.out / "failures.pkl", "wb") as handle:
            pickle.dump(kept, handle, protocol=pickle.HIGHEST_PROTOCOL)
        counts: dict[str, int] = {}
        for s in kept:
            for tag in s["tags"]:
                counts[tag] = counts.get(tag, 0) + 1
        summary["failures"] = {"brain": str(a.failures), "states": len(kept), "starts": per_start,
                               "tags": counts, "seconds": round(time.time() - t0, 1)}
        (a.out / "harvest_failures.json").write_text(json.dumps(summary, indent=1) + "\n")
        print(json.dumps(summary["failures"]))
        body.close()
        return
    if a.part in ("train", "all", "traj"):
        practice = []
        traj_x, traj_y, traj_rows = [], [], []
        for noops in a.train_noops:
            for epsilon in a.epsilons:
                states, rows = game(body, noops, epsilon, 1000 + noops, a.max, a.every,
                                    a.part != "traj", a.eye)
                practice += states
                for x, row in rows:  # every decision, in order: a teacher trajectory
                    traj_x.append(x)
                    traj_y.append(row["label"])
                    traj_rows.append(row)
                last = rows[-1][1]
                furthest = max(r["stage"] for _, r in rows if r["stage"] != 20)
                summary["games"].append({"part": "train", "noops": noops, "epsilon": epsilon,
                                         "decisions": len(rows), "states": len(states),
                                         "end_stage": last["stage"], "furthest_stage": furthest,
                                         "end_wx": last["wx"], "seconds": round(time.time() - t0, 1)})
                print(json.dumps(summary["games"][-1]), flush=True)
        if a.part != "traj":
            with open(a.out / "practice.pkl", "wb") as handle:
                pickle.dump(practice, handle, protocol=pickle.HIGHEST_PROTOCOL)
        names = sorted({t for r in traj_rows for t in r["tags"]})
        games = sorted({r["game"] for r in traj_rows})
        game_index = np.array([games.index(r["game"]) for r in traj_rows])
        np.savez_compressed(
            a.out / "trajectories.npz", x=np.array(traj_x, np.float32), y=np.array(traj_y),
            game=game_index, t=np.array([r["t"] for r in traj_rows]),
            stage=np.array([r["stage"] for r in traj_rows]),
            **{"tag_" + n: np.array([n in r["tags"] for r in traj_rows]) for n in names})
        counts = {}
        for s in practice:
            for tag in s["tags"] + [f'stage{s["stage"]}']:
                counts[tag] = counts.get(tag, 0) + 1
        summary["practice"] = {"states": len(practice), "tags": counts, "eye": a.eye}
    if a.part in ("val", "all"):
        xs, ys, rows_all = [], [], []
        for noops in a.val_noops:
            for epsilon in a.epsilons:
                _, rows = game(body, noops, epsilon, 2000 + noops, a.max, a.every, False, a.eye)
                for x, row in rows[::a.val_every]:
                    xs.append(x)
                    ys.append(row["label"])
                    rows_all.append(row)
                summary["games"].append({"part": "val", "noops": noops, "epsilon": epsilon,
                                         "decisions": len(rows), "end_stage": rows[-1][1]["stage"]})
                print(json.dumps(summary["games"][-1]), flush=True)
        names = sorted({t for r in rows_all for t in r["tags"]} | {"stage0", "stage1", "stage2", "stage3"})
        tags = {}
        for name in names:
            if name.startswith("stage") and name[5:].isdigit():
                tags["tag_" + name] = np.array([r["stage"] == int(name[5:]) for r in rows_all])
            else:
                tags["tag_" + name] = np.array([name in r["tags"] for r in rows_all])
        np.savez_compressed(a.out / "validation.npz", x=np.array(xs, np.float32), y=np.array(ys), **tags)
        summary["validation"] = {"rows": len(ys), "tags": {k[4:]: int(v.sum()) for k, v in tags.items()},
                                 "eye": a.eye}
    summary["seconds"] = round(time.time() - t0, 1)
    (a.out / f"harvest_{a.part}.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: summary[k] for k in summary if k in ("practice", "validation", "seconds")}))
    body.close()


if __name__ == "__main__":
    main()
