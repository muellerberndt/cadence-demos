"""The league: robots with one life each, their brains, their record and their fights.

A league is a folder: ``league.json`` (every robot's blueprint, rating and record, every
fight's result), ``brains/<name>.npz`` (the one continuing brain of each robot), ``reports/``
(nursery reports) and ``fights/`` (replays and viewer pages). ``python -m arena`` drives it.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import cadence

from .brain import FOUNDER, RobotBrain
from .nursery import run_nursery, save_report
from .parts import Blueprint, blueprint_from_dict, stock_designs
from .replay import render_html, save_replay
from .royale import Fighter, elo_update, run_royale

FORMAT = "cadence-robot-arena/league/1"
START_ELO = 1000.0


class League:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.path = self.root / "league.json"
        self.data: dict[str, Any] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get("format") != FORMAT:
                raise ValueError(f"{self.path} is not a {FORMAT} league")

    # -- storage

    @property
    def brains(self) -> Path:
        return self.root / "brains"

    def brain_path(self, name: str) -> Path:
        return self.brains / f"{name}.npz"

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1) + "\n")

    def create(self, designs: list[Blueprint]) -> None:
        if self.path.exists():
            raise FileExistsError(f"{self.path} exists")
        self.data = {
            "format": FORMAT,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cadence": cadence.__version__,
            "founder_genes": FOUNDER,
            "robots": {},
            "fights": [],
        }
        for bp in designs:
            self.add(bp)
        self.save()

    def add(self, blueprint: Blueprint) -> dict[str, Any]:
        if blueprint.name in self.data["robots"]:
            raise ValueError(f"{blueprint.name} is already in the league")
        entry = {
            "blueprint": blueprint.to_dict(),
            "policy": blueprint.policy,
            "elo": START_ELO,
            "fights": 0,
            "wins": 0,
            "places": [],
            "dealt": 0.0,
            "taken": 0.0,
            "moments": 0,
            "born": time.strftime("%Y-%m-%d %H:%M:%S"),
            "nursery": None,
            "owed": None,
            "history": [],
        }
        if blueprint.policy == "brain":
            self.brains.mkdir(parents=True, exist_ok=True)
            RobotBrain.newborn(blueprint).save(self.brain_path(blueprint.name))
        self.data["robots"][blueprint.name] = entry
        return entry

    def blueprint(self, name: str) -> Blueprint:
        return blueprint_from_dict(self.data["robots"][name]["blueprint"])

    def names(self, policy: str | None = None) -> list[str]:
        return [
            n for n, e in self.data["robots"].items() if policy is None or e["policy"] == policy
        ]

    # -- the nursery

    def nursery(
        self,
        names: list[str] | None = None,
        *,
        moments: int = 6000,
        workers: int = 1,
        seed: int = 0,
        controls: bool = False,
        verbose: bool = False,
    ) -> list[dict[str, Any]]:
        names = names or self.names("brain")
        jobs = []
        for name in names:
            entry = self.data["robots"][name]
            if entry["policy"] != "brain":
                continue
            bp = self.blueprint(name)
            jobs.append((
                bp.to_dict(), moments, seed, "brain", str(self.brain_path(name)),
                entry.get("owed"), verbose,
            ))
            if controls:
                # A repeated nursery loads the pupil's acquired brain; its controls
                # remain genuine newborns of the same body and founder seed.
                jobs.append((bp.to_dict(), moments, seed, "random", None, None, verbose))
                jobs.append((bp.to_dict(), moments, seed, "frozen", None, None, verbose))
        reports: list[dict[str, Any]] = []
        if workers > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                reports = list(pool.map(_nursery_job, jobs))
        else:
            reports = [_nursery_job(job) for job in jobs]
        (self.root / "reports").mkdir(parents=True, exist_ok=True)
        for report in reports:
            name = report["robot"]
            save_report(report, self.root / "reports" / f"nursery-{name}-{report['policy']}.json")
            if report["policy"] == "brain":
                entry = self.data["robots"][name]
                entry["nursery"] = {
                    "moments": report["moments"],
                    "seed": report["seed"],
                    "total": report["total"],
                    "first_half": report["first_half"],
                    "second_half": report["second_half"],
                    "moments_per_second": round(report["moments_per_second"], 1),
                    "acceleration": round(report["acceleration"], 1),
                }
                entry["moments"] += report["moments"]
                entry["owed"] = report["owed"]
        self.save()
        return reports

    # -- fights

    def pick(self, size: int, rng: random.Random) -> list[str]:
        """The fighters of the next royale: everyone when the league is small, otherwise the
        robots with the fewest fights first, ties broken at random."""
        names = list(self.data["robots"])
        if len(names) <= size:
            return names
        rng.shuffle(names)
        names.sort(key=lambda n: self.data["robots"][n]["fights"])
        return names[:size]

    def royale(
        self,
        names: list[str] | None = None,
        *,
        size: int = 6,
        seed: int | None = None,
        duration: int = 1200,
        zone_moments: int = 1000,
        workers: int | None = None,
        record: bool = True,
        verbose: bool = False,
        need: float | None = None,
        reset: bool = False,
        stage: dict | None = None,
        zone_end: float = 2.5,
    ) -> dict[str, Any]:
        fight_id = len(self.data["fights"]) + 1
        rng = random.Random(fight_id if seed is None else seed)
        seed = rng.randrange(1_000_000) if seed is None else seed
        names = names or self.pick(size, rng)
        fighters = []
        for name in names:
            entry = self.data["robots"][name]
            owed = entry.get("owed")
            fighters.append(
                Fighter(
                    name=name,
                    blueprint=self.blueprint(name),
                    policy=entry["policy"],
                    brain_path=self.brain_path(name) if entry["policy"] == "brain" else None,
                    owed=None if owed is None else (float(owed[0]), bool(owed[1])),
                    need=need,
                    reset=reset,
                    stage=stage,
                )
            )
        if workers is None:
            workers = len(fighters) if len(fighters) > 2 else 0
        began = time.perf_counter()
        outcome = run_royale(
            fighters,
            seed=seed,
            duration=duration,
            zone_moments=zone_moments,
            zone_end=zone_end,
            workers=workers,
            record=record,
            verbose=verbose,
        )
        elapsed = time.perf_counter() - began
        stats = {f.name: f.stats for f in fighters}
        owed = {f.name: f.owed for f in fighters}
        record_row = self._record_fight(
            [(f.name, f.policy) for f in fighters], stats, owed, seed, elapsed,
            outcome["moments"], outcome["replay"] if record else None,
        )
        self.save()
        return record_row

    def _record_fight(
        self,
        who: list[tuple[str, str]],
        stats: dict[str, dict[str, Any]],
        owed: dict[str, tuple[float, bool] | None],
        seed: int,
        elapsed: float,
        moments: int,
        replay: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Elo, records, histories and the replay files of one finished fight."""
        fight_id = len(self.data["fights"]) + 1
        ratings = {name: float(self.data["robots"][name]["elo"]) for name, _ in who}
        places = {name: int(stats[name]["place"]) for name, _ in who}
        deltas = elo_update(ratings, places)
        record_row: dict[str, Any] = {
            "id": fight_id,
            "seed": seed,
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
            "moments": moments,
            "seconds": round(elapsed, 1),
            "results": [],
        }
        for name, policy in who:
            entry = self.data["robots"][name]
            st = stats[name]
            entry["elo"] = round(ratings[name] + deltas[name], 1)
            entry["fights"] += 1
            entry["wins"] += int(st["place"] == 1)
            entry["places"].append(int(st["place"]))
            entry["dealt"] += st["dealt"]
            entry["taken"] += st["taken"]
            entry["moments"] += st["moments"]
            o = owed.get(name)
            entry["owed"] = None if o is None else [float(o[0]), bool(o[1])]
            row = {
                **st,
                "name": name,
                "policy": policy,
                "elo_before": round(ratings[name], 1),
                "elo_after": entry["elo"],
            }
            entry["history"].append({"fight": fight_id, **row})
            record_row["results"].append(row)
        record_row["results"].sort(key=lambda r: r["place"])
        if replay is not None:
            fights = self.root / "fights"
            fights.mkdir(parents=True, exist_ok=True)
            replay_path = save_replay(replay, fights / f"fight-{fight_id:04d}.json")
            page = fights / f"fight-{fight_id:04d}.html"
            page.write_text(render_html(replay))
            record_row["replay"] = str(replay_path.relative_to(self.root))
            record_row["page"] = str(page.relative_to(self.root))
        self.data["fights"].append(record_row)
        return record_row

    # -- a round of fights in parallel

    def groups(self, size: int, rng: random.Random) -> list[list[str]]:
        """Disjoint groups of ``size`` for one round: every raised robot, least-fought first,
        ties at random; a remainder smaller than two sits the round out."""
        names = [
            n for n, e in self.data["robots"].items()
            if e["policy"] != "brain" or e.get("nursery") is not None
        ]
        rng.shuffle(names)
        names.sort(key=lambda n: self.data["robots"][n]["fights"])
        out = [names[i : i + size] for i in range(0, len(names), size)]
        return [g for g in out if len(g) >= 2]

    def round(
        self,
        *,
        size: int = 6,
        parallel: int = 4,
        inner_workers: int = 0,
        seed: int = 0,
        duration: int = 1200,
        zone_moments: int = 1000,
        record: bool = False,
        rng: random.Random | None = None,
        zone_end: float = 2.5,
    ) -> list[dict[str, Any]]:
        """One round: the league split into disjoint groups that fight at the same time, one
        process per fight (and, with ``inner_workers``, one worker per brain inside it).
        Brains are saved by the fight processes; this process keeps the books."""
        rng = rng or random.Random(seed)
        jobs = []
        for k, group in enumerate(self.groups(size, rng)):
            fighters = []
            for name in group:
                entry = self.data["robots"][name]
                fighters.append(
                    {
                        "name": name,
                        "blueprint": entry["blueprint"],
                        "policy": entry["policy"],
                        "brain_path": str(self.brain_path(name)) if entry["policy"] == "brain" else None,
                        "owed": entry.get("owed"),
                    }
                )
            jobs.append((fighters, seed * 1000 + k, duration, zone_moments, inner_workers, record, zone_end))
        if not jobs:
            return []
        began = time.perf_counter()
        if parallel > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(
                max_workers=min(parallel, len(jobs)), mp_context=multiprocessing.get_context("spawn")
            ) as pool:
                outcomes = list(pool.map(_fight_job, jobs))
        else:
            outcomes = [_fight_job(job) for job in jobs]
        elapsed = time.perf_counter() - began
        rows = []
        for (fighters, fight_seed, *_), outcome in zip(jobs, outcomes, strict=True):
            who = [(f["name"], f["policy"]) for f in fighters]
            owed = {n: (None if o is None else (float(o[0]), bool(o[1]))) for n, o in outcome["owed"].items()}
            rows.append(
                self._record_fight(
                    who, outcome["stats"], owed, fight_seed, outcome["seconds"], outcome["moments"],
                    outcome.get("replay"),
                )
            )
        self.data.setdefault("rounds", []).append(
            {"fights": [r["id"] for r in rows], "seconds": round(elapsed, 1), "when": time.strftime("%Y-%m-%d %H:%M:%S")}
        )
        self.save()
        return rows

    def retire(self, names: list[str], *, reason: str = "retired", delete_brains: bool = False) -> list[str]:
        """Move robots out of the league into ``retired`` (their records stay)."""
        gone = []
        self.data.setdefault("retired", {})
        for name in names:
            entry = self.data["robots"].pop(name, None)
            if entry is None:
                continue
            entry["retired_reason"] = reason
            entry["retired_when"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.data["retired"][name] = {k: v for k, v in entry.items() if k != "history"}
            if delete_brains:
                path = self.brain_path(name)
                if path.exists():
                    path.unlink()
            gone.append(name)
        self.save()
        return gone

    # -- tables

    def ladder(self) -> list[dict[str, Any]]:
        rows = []
        for name, e in self.data["robots"].items():
            places = e["places"]
            recent = e["history"][-5:]
            rows.append(
                {
                    "name": name,
                    "policy": e["policy"],
                    "chassis": e["blueprint"]["chassis"],
                    "parts": len(e["blueprint"]["parts"]),
                    "elo": e["elo"],
                    "fights": e["fights"],
                    "wins": e["wins"],
                    "mean_place": round(sum(places) / len(places), 2) if places else None,
                    "dealt": round(e["dealt"], 0),
                    "taken": round(e["taken"], 0),
                    "moments": e["moments"],
                    "recent_aroused": round(
                        sum(r["aroused_share"] for r in recent) / len(recent), 2
                    ) if recent else None,
                    "recent_learning_sweeps": sum(r["learning_sweeps"] for r in recent),
                }
            )
        rows.sort(key=lambda r: (-r["elo"], r["name"]))
        return rows


def _fight_job(job: tuple) -> dict[str, Any]:
    """One royale in its own process; returns plain data (the brains are saved in place)."""
    fighters_data, seed, duration, zone_moments, inner_workers, record, zone_end = job
    fighters = [
        Fighter(
            name=f["name"],
            blueprint=blueprint_from_dict(f["blueprint"]),
            policy=f["policy"],
            brain_path=None if f["brain_path"] is None else Path(f["brain_path"]),
            owed=None if f["owed"] is None else (float(f["owed"][0]), bool(f["owed"][1])),
        )
        for f in fighters_data
    ]
    began = time.perf_counter()
    outcome = run_royale(
        fighters, seed=seed, duration=duration, zone_moments=zone_moments, zone_end=zone_end,
        workers=inner_workers if len(fighters) > 2 else 0, record=record, save=True,
    )
    return {
        "stats": {f.name: f.stats for f in fighters},
        "owed": {f.name: f.owed for f in fighters},
        "moments": outcome["moments"],
        "seconds": round(time.perf_counter() - began, 1),
        "replay": outcome["replay"] if record else None,
    }


def _nursery_job(job: tuple) -> dict[str, Any]:
    bp_dict, moments, seed, policy, brain_path, owed, verbose = job
    bp = blueprint_from_dict(bp_dict)
    return run_nursery(
        bp,
        moments=moments,
        seed=seed,
        policy=policy,
        brain_path=brain_path,
        owed=None if owed is None else (float(owed[0]), bool(owed[1])),
        save_to=brain_path if policy == "brain" else None,
        verbose=verbose,
    )


def ladder_text(rows: list[dict[str, Any]]) -> str:
    head = (
        f"{'#':>2} {'robot':12} {'policy':7} {'chassis':7} {'elo':>7} {'fights':>6} {'wins':>4} "
        f"{'place':>5} {'dealt':>6} {'taken':>6} {'aroused':>7} {'learn':>7}"
    )
    lines = [head, "-" * len(head)]
    for k, r in enumerate(rows, 1):
        lines.append(
            f"{k:>2} {r['name']:12} {r['policy']:7} {r['chassis']:7} {r['elo']:7.1f} {r['fights']:6} "
            f"{r['wins']:4} {('-' if r['mean_place'] is None else f'{r['mean_place']:.2f}'):>5} "
            f"{r['dealt']:6.0f} {r['taken']:6.0f} "
            f"{('-' if r['recent_aroused'] is None else f'{r['recent_aroused']:.2f}'):>7} "
            f"{r['recent_learning_sweeps']:7}"
        )
    return "\n".join(lines)


def baseline_bots(designs: list[Blueprint], names: tuple[str, ...] = ("Tumbler", "Mantis")) -> list[Blueprint]:
    """Uniform-random twins of two stock bodies: the baseline that fights in the same ring."""
    by_name = {b.name: b for b in designs}
    return [replace(by_name[n], name=f"Random-{n}", policy="random", seed=by_name[n].seed + 100) for n in names]
