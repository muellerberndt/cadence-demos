"""Headless guarantee runs for the arcade pipeline.

For each game, two runners with identical seeds share one process:
one learns during life, one is frozen at takeover. The report checks
takeover within bounds, zero brain faults, no score collapse against
the teacher, and the living arm holding or beating the frozen arm.

    python headless_control.py --seed 0 --out report_s0.json
"""

from __future__ import annotations

import argparse
import json
import time

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
            "witnesses": r.witnesses,
            "agreement": (round(float(np.mean(r.agreement)), 3)
                          if r.agreement else None),
            "teacher_mean": (round(float(np.mean(r.teacher_returns)), 1)
                             if r.teacher_returns else None),
            "episodes_lived": len(rets),
            "returns": rets,
            "late_mean": (round(float(np.mean(rets[-5:])), 1)
                          if len(rets) >= 3 else None),
            "faults": r.faults,
            "last_error": r.last_error,
            "understanding": r.coherence,
            "transitions": r.transitions,
            "life_admissions": r.life_admissions,
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
            "no_collapse": (lm is not None and teacher
                            and lm >= 0.25 * teacher),
            "expert_via_selfplay": (lm is not None and teacher
                                    and lm >= 0.8 * teacher),
            "living_holds_or_beats_frozen": (
                lm is not None and fm is not None
                and lm >= fm * 0.9 - 1e-9),
        }
        checks["PASS"] = all(checks.values())
        out[game] = checks
    return out


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
    result = {"seed": args.seed, "report": report,
              "verdicts": verdicts(report, games)}
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps(result["verdicts"], indent=1))
    print("HEADLESS-PASS-DONE", flush=True)


if __name__ == "__main__":
    main()
