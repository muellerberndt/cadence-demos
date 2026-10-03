"""Headless guarantee runs for the arcade pipeline.

For each game, two runners with identical seeds share one process:
one learns during life, one is frozen at takeover. The report checks
takeover within bounds, zero brain faults, no score collapse against
the teacher, and the living arm holding or beating the frozen arm.

    python headless_control.py --seed 0 --out report_s0.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from importlib import metadata
from pathlib import Path

import numpy as np

import server


def run_pass(seed: int, games, minutes: float, episodes_target: int):
    runners = {}
    for game in games:
        for arm in ("living", "frozen"):
            runners[f"{game}:{arm}"] = server.Runner(
                game, seed=seed, life_learn=(arm == "living"))
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        done = all(len(r.returns) >= episodes_target
                   for r in runners.values())
        if done:
            break
        time.sleep(15)
    report = {}
    for key, r in runners.items():
        rets = list(r.returns)
        report[key] = {
            "phase": r.phase,
            "lessons": r.lessons,
            "takeover": r.takeover,
            "agreement_with_teacher_now": (
                round(float(np.mean(r.agreement)), 3)
                if r.agreement else None),
            "teacher_returns": list(r.teacher_returns),
            "teacher_mean": (round(float(np.mean(r.teacher_returns)), 1)
                             if r.teacher_returns else None),
            "episodes_lived": len(rets),
            "returns": rets,
            "late_mean": (round(float(np.mean(rets[-5:])), 1)
                          if len(rets) >= 3 else None),
            "best": r.best_score,
            "faults": r.faults,
            "refused": r.refused,
            "last_error": r.last_error,
            "decisions": r.decisions,
            "env_steps": r.tick,
            "outcomes_learned": r.outcomes,
            "seconds": round(time.time() - r.born, 1),
            "think_seconds": {
                name: round(float(value), 4) for name, value in zip(
                    ("p50", "p95", "p99", "max"),
                    (*np.percentile(r.think_seconds, [50, 95, 99]),
                     max(r.think_seconds)), strict=True)
            } if r.think_seconds else None,
            "think_seconds_scope": (
                "last 20000 whole brain handlers; watching and play, "
                "including refusals/fault backoff; "
                "excludes emulator, retina, waiting and rendering"),
        }
        r.stop()
    time.sleep(2)
    return report


def verdicts(report, games):
    out = {}
    for game in games:
        living = report.get(f"{game}:living", {})
        frozen = report.get(f"{game}:frozen", {})
        teacher = living.get("teacher_mean") or 0
        lm, fm = living.get("late_mean"), frozen.get("late_mean")
        checks = {
            "takeover_living": living.get("phase") == "playing",
            "takeover_frozen": frozen.get("phase") == "playing",
            "no_faults": (living.get("faults", 1) == 0
                          and frozen.get("faults", 1) == 0),
            "lived_episodes": (living.get("episodes_lived", 0) >= 3
                               and frozen.get("episodes_lived", 0) >= 3),
            "no_collapse": bool(lm is not None and teacher
                                and lm >= 0.25 * teacher),
            "expert_via_selfplay": bool(lm is not None and teacher
                                        and lm >= 0.8 * teacher),
            "living_holds_or_beats_frozen": bool(
                lm is not None and fm is not None
                and lm >= fm * 0.9 - 1e-9),
        }
        checks["PASS"] = all(checks.values())
        out[game] = checks
    return out


def identity():
    """What ran: the library release and the hashes of this demo's sources."""
    here = Path(__file__).parent
    return {
        "cadence_net": metadata.version("cadence-net"),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "machine": platform.machine(),
        "sources_sha256": {
            name: hashlib.sha256((here / name).read_bytes()).hexdigest()
            for name in ("server.py", "headless_control.py")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--games", default="Freeway,Carnival,SpaceInvaders,Atlantis")
    parser.add_argument("--minutes", type=float, default=45)
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    games = args.games.split(",")
    report = run_pass(args.seed, games, args.minutes, args.episodes)
    result = {"seed": args.seed, "identity": identity(), "report": report,
              "verdicts": verdicts(report, games)}
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps(result["verdicts"], indent=1))
    print("HEADLESS-PASS-DONE", flush=True)


if __name__ == "__main__":
    main()
