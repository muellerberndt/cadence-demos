"""Command line: ``python -m arena <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .league import League, baseline_bots, ladder_text
from .parts import Blueprint, Part, stock_designs
from .probe import fingerprint, fingerprint_text
from .replay import render_file


def _parse_part(text: str) -> Part:
    """``wheel@90``, ``leg@-130`` or ``arm@0=hammer``."""
    kind, _, rest = text.partition("@")
    mount, _, weapon = rest.partition("=")
    return Part(kind=kind.strip(), mount=float(mount), weapon=weapon.strip() or None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena", description=__doc__)
    parser.add_argument("--league", default="league", help="the league folder (default: league)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a league with the stock robots and two random baselines")
    p.add_argument("--no-baselines", action="store_true")

    p = sub.add_parser("design", help="assemble a robot and add it to the league (a newborn brain)")
    p.add_argument("--name", required=True)
    p.add_argument("--chassis", default="medium", choices=("light", "medium", "heavy"))
    p.add_argument("--part", action="append", required=True, help="wheel@90, leg@-130, arm@0=spike|hammer|spinner")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--gene", action="append", default=[], help="name=value overrides of the founder genes")
    p.add_argument("--policy", default="brain", choices=("brain", "random"))

    p = sub.add_parser("nursery", help="bootstrap robots against the dummy, accelerated")
    p.add_argument("--only", action="append", help="robot name (repeatable)")
    p.add_argument("--moments", type=int, default=6000)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--controls", action="store_true", help="also run the random and frozen controls")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("royale", help="run ranked battle royales")
    p.add_argument("--fights", type=int, default=1)
    p.add_argument("--size", type=int, default=6)
    p.add_argument("--duration", type=int, default=1200)
    p.add_argument("--zone-moments", type=int, default=1000, help="moments over which the ring closes")
    p.add_argument("--zone-end", type=float, default=2.5, help="the ring's final radius in metres")
    p.add_argument("--seed", type=int)
    p.add_argument("--workers", type=int, help="brain workers (default: one per fighter)")
    p.add_argument("--fighter", action="append", help="robot name (repeatable); default: picked")
    p.add_argument("--no-replay", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--need", type=float, help="the ring stage's arousal need (default: the brain's gene)")
    p.add_argument("--ring-reset", action="store_true", help="forget what life used to pay on entering the ring (Arousal.reset)")
    p.add_argument("--stage", help='ring-stage genes as JSON, e.g. {"need":0,"heat":0,"temperature":0.2,"reset":true}')

    sub.add_parser("ladder", help="print the ranking")
    sub.add_parser("dashboard", help="render the league page (league/index.html)")

    p = sub.add_parser("evolve", help="generations of nursery, fights, selection and mutation")
    p.add_argument("--generations", type=int, default=5)
    p.add_argument("--population", type=int, default=8, help="brains in the league (baselines extra)")
    p.add_argument("--elite", type=int, default=4, help="brains that survive a generation")
    p.add_argument("--nursery-moments", type=int, default=8000)
    p.add_argument("--fights", type=int, default=6)
    p.add_argument("--size", type=int, default=4)
    p.add_argument("--duration", type=int, default=1200)
    p.add_argument("--zone-moments", type=int, default=1000)
    p.add_argument("--zone-end", type=float, default=2.5, help="the ring's final radius in metres")
    p.add_argument("--workers", type=int, default=4, help="nursery processes")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--founders", help="comma-separated robots whose mutants fill the population")
    p.add_argument("--rounds", type=int, default=0, help="rounds of parallel fights per generation (instead of --fights)")
    p.add_argument("--parallel", type=int, default=0, help="fights at the same time in a round")
    p.add_argument("--inner-workers", type=int, default=0, help="brain workers inside each fight (0: in process)")
    p.add_argument("--hours", type=float, default=0.0, help="stop starting generations after this many hours")
    p.add_argument("--keep", type=int, default=0, help="after the last generation keep only the best N")
    p.add_argument("--keep-per-lineage", type=int, default=0, help="the final cut keeps the best N of every lineage first")
    p.add_argument("--fitness", default="placement", choices=("placement", "licence"), help="rank a generation by placement score or by the driving test")
    p.add_argument("--niche-min", type=int, default=0, help="the best N of every lineage survive each generation")
    p.add_argument("--refresher-moments", type=int, default=0, help="extra nursery moments for the survivors while newborns are raised")
    p.add_argument("--stage", help='ring-stage genes for the generation fights as JSON, e.g. {"need":0,"heat":0,"temperature":0.2,"reset":true,"threshold":0.5,"eta":0.01}')

    p = sub.add_parser("retire", help="move robots out of the league (records stay)")
    p.add_argument("names", nargs="*")
    p.add_argument("--random", action="store_true", help="retire the uniform-random baselines")

    p = sub.add_parser("render", help="render a replay JSON as the isometric viewer page")
    p.add_argument("replay")
    p.add_argument("-o", "--out")

    p = sub.add_parser("show", help="print a robot's record")
    p.add_argument("name")

    p = sub.add_parser("probe", help="fingerprint a robot's policy in declared situations")
    p.add_argument("name")

    p = sub.add_parser("licence", help="the driving test of a robot's greedy policy: approach, escape, engage, spin")
    p.add_argument("names", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--random", action="store_true", help="also the uniform-random baseline for each body")
    p.add_argument("--scale", type=float, default=1.0, help="shorten the tests (0.2 for a quick look)")
    p.add_argument("--workers", type=int, default=1, help="robots tested at the same time (full-length tests only)")

    args = parser.parse_args(argv)
    league = League(args.league)

    if args.command == "init":
        designs = stock_designs()
        if not args.no_baselines:
            designs += baseline_bots(designs)
        league.create(designs)
        print(f"league at {league.root} with {len(designs)} robots: {', '.join(b.name for b in designs)}")
        return 0

    if args.command == "design":
        genes: dict = {}
        for item in args.gene:
            key, _, value = item.partition("=")
            try:
                genes[key] = json.loads(value)
            except json.JSONDecodeError:
                genes[key] = value
        bp = Blueprint(
            args.name, args.chassis, tuple(_parse_part(t) for t in args.part), seed=args.seed,
            genes=genes, policy=args.policy,
        )
        league.add(bp)
        league.save()
        print(f"{bp.name}: {bp.chassis} chassis, {len(bp.parts)} parts, mass {bp.mass:.0f} kg, "
              f"{bp.motors} motors in slots {bp.slots}")
        return 0

    if args.command == "nursery":
        reports = league.nursery(
            args.only, moments=args.moments, workers=args.workers, seed=args.seed,
            controls=args.controls, verbose=not args.quiet,
        )
        print(f"{'robot':12} {'policy':7} {'progress m':>10} {'2nd half':>8} {'kills':>5} {'dealt':>6} "
              f"{'aroused':>7} {'moments/s':>9} {'x real':>6}")
        for r in reports:
            print(f"{r['robot']:12} {r['policy']:7} {r['total']['progress_m']:10.1f} "
                  f"{r['second_half'].get('progress_m', 0):8.1f} {r['total']['kills']:5} "
                  f"{r['total']['dealt']:6.0f} {r['second_half'].get('aroused_share', 0):7.2f} "
                  f"{r['moments_per_second']:9.0f} {r['acceleration']:6.0f}")
        return 0

    if args.command == "royale":
        for _ in range(args.fights):
            row = league.royale(
                args.fighter, size=args.size, seed=args.seed, duration=args.duration,
                zone_moments=args.zone_moments, zone_end=args.zone_end, workers=args.workers, record=not args.no_replay,
                verbose=not args.quiet, need=args.need, reset=args.ring_reset,
                stage=json.loads(args.stage) if args.stage else None,
            )
            print(f"fight {row['id']} (seed {row['seed']}, {row['moments']} moments, {row['seconds']} s):")
            for r in row["results"]:
                print(f"  {r['place']}. {r['name']:12} {r['policy']:6} hp {r['hp']:6.1f} dealt {r['dealt']:6.1f} "
                      f"taken {r['taken']:6.1f} aroused {r['aroused_share']:.2f} sweeps/moment {r['sweeps_per_moment']:5.1f} "
                      f"closing {r.get('closing_share', 0):.2f} elo {r['elo_before']:.0f} -> {r['elo_after']:.0f}")
            if "page" in row:
                print(f"  replay: {league.root / row['page']}")
        from .dashboard import render_dashboard

        print(f"league page: {render_dashboard(league)}")
        return 0

    if args.command == "ladder":
        print(ladder_text(league.ladder()))
        return 0

    if args.command == "dashboard":
        from .dashboard import render_dashboard

        print(render_dashboard(league))
        return 0

    if args.command == "evolve":
        import random

        from .evolve import generation, seed_population

        import time as _time

        from .evolve import final_cut

        rng = random.Random(args.seed)
        founders = [n.strip() for n in args.founders.split(",")] if args.founders else None
        born = seed_population(league, args.population, rng, founders)
        if born and not args.quiet:
            print(f"seeded {len(born)} newborns: {', '.join(born[:8])}{' ...' if len(born) > 8 else ''}")
        started = _time.time()
        last = 0.0
        for g in range(args.generations):
            elapsed = _time.time() - started
            if args.hours and g and elapsed + last > args.hours * 3600:
                print(f"stopping before generation {g + 1}: {elapsed / 60:.0f} min used, last generation took {last / 60:.0f} min")
                break
            record = generation(
                league, population=args.population, elite=args.elite,
                nursery_moments=args.nursery_moments, fights=args.fights, size=args.size,
                duration=args.duration, zone_moments=args.zone_moments, workers=args.workers,
                rng=rng, verbose=not args.quiet, rounds=args.rounds, parallel=args.parallel,
                inner_workers=args.inner_workers, zone_end=args.zone_end, fitness=args.fitness,
                niche_min=args.niche_min, refresher_moments=args.refresher_moments,
                stage=json.loads(args.stage) if args.stage else None,
            )
            last = record["seconds"]
            print(f"generation {record['generation']} ({record['seconds']} s): " + ", ".join(
                f"{r['rank']}. {r['name']} {r['score']:+.2f}" for r in record["ranking"][:5]), flush=True)
            print("  lineages: " + ", ".join(f"{k} x{v}" for k, v in sorted(record["lineages"].items(), key=lambda kv: -kv[1])), flush=True)
        if args.keep:
            gone = final_cut(league, args.keep, args.keep_per_lineage)
            print(f"final cut: kept {len(league.data['robots'])}, retired {len(gone)}")
        return 0

    if args.command == "retire":
        names = list(args.names)
        if args.random:
            names += league.names("random")
        gone = league.retire(names)
        print(f"retired {', '.join(gone) if gone else 'nobody'}")
        return 0

    if args.command == "render":
        print(render_file(args.replay, args.out))
        return 0

    if args.command == "show":
        entry = league.data["robots"][args.name]
        print(json.dumps({k: v for k, v in entry.items() if k != "history"}, indent=1))
        for h in entry["history"][-10:]:
            print(f"  fight {h['fight']}: place {h['place']}, dealt {h['dealt']}, taken {h['taken']}, "
                  f"aroused {h['aroused_share']}, learning sweeps {h['learning_sweeps']}, elo {h['elo_after']}")
        return 0

    if args.command == "licence":
        from .licence import licence, licence_text

        names = league.names("brain") if args.all else list(args.names)
        names = [n for n in names if league.brain_path(n).exists()]  # a robot without a brain file is not raised yet
        if args.workers > 1 and len(names) > 1 and not args.random and args.scale == 1.0:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor

            from .evolve import _licence_job

            jobs = [(league.blueprint(n).to_dict(), str(league.brain_path(n))) for n in names]
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                for result in pool.map(_licence_job, jobs):
                    print(licence_text(result), flush=True)
            return 0
        for name in names:
            bp = league.blueprint(name)
            print(licence_text(licence(bp, league.brain_path(name), "brain", args.scale)), flush=True)
            if args.random:
                print(licence_text(licence(bp, None, "random", args.scale)), flush=True)
        return 0

    if args.command == "probe":
        entry = league.data["robots"][args.name]
        if entry["policy"] != "brain":
            print(f"{args.name} has no brain to probe ({entry['policy']} policy)")
            return 1
        print(fingerprint_text(fingerprint(league.blueprint(args.name), league.brain_path(args.name))))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
