"""The promise of the Tron page, run on the real page in headless Chromium: Cadence brains play
strong games. The deep brain sees the whole arena, settles on every move in the browser in real
time, and beats a bot that looks one move ahead; the page draws every settle.

    python tools/promise_test.py --out evidence/promise-<date>.json [--games 32] [--parity 4]

Serves web/ on a free port and opens the page with the deep brain. On the arena seeds the
readings use (2,200,000 and up), the page's brain plays the `voronoi` bot (one move ahead for
both riders, `tron/bots.py`), the bot's moves sent in from here:

  1. BRAIN ALONE (`?player=alone`): every move is one settle of the brain in the page's worker.
     The first --parity games are replayed natively on cadence-net 0.95.2 (`tests/play_check.py`'s
     reference): the page's brain must play the same moves and reach the same result.
  2. BRAIN + SEARCH (the page's default): the brain proposes, the page's own look-ahead decides.

Checks: the page plays the native brain's moves; every move the page receives carries its settle
(sweeps and the largest repair per sweep, which the brain view draws); the brain's median time per
move fits the page's 120 ms tick; the brain alone scores at least 0.70 and the brain + look-ahead
at least 0.85 against `voronoi` (draws count half; the readings over 128 games: 0.80 and 0.93); no
page error. The games are deterministic, so a rerun gives the same results. Exit 1 on a failure.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from playwright.sync_api import sync_playwright  # noqa: E402

from play_check import reference, serve, wait_phase  # noqa: E402
from tron import bots  # noqa: E402
from tron.world import Arena  # noqa: E402

TICK_MS = 120  # web/js/main.js
SLIM = """(s) => ({moved: s.moved, heads: s.heads, headings: s.headings, grid: s.grid, over: s.over, result: s.result,
  tick: s.tick, brain: s.brain ? {choice: s.brain.choice, sweeps: s.brain.sweeps, act_ms: s.brain.act_ms, refused: s.brain.refused} : null,
  repair: s.repair ? s.repair.length : 0})"""
BEGIN_JS = """async (seed) => (""" + SLIM + """)(await window.__tron.call("begin", {seed}))"""
TICK_JS = """async ([move, decided]) => { const p = {move}; if (decided !== null) p.decided = decided;
  return (""" + SLIM + """)(await window.__tron.call("tick", p)); }"""
DECIDE_JS = """async (st) => await window.__tron.decide(st)"""


def play(page, seed: int, search: bool) -> dict:
    s = page.evaluate(BEGIN_JS, seed)
    arena = Arena(24, seed=seed)
    moves, settles, act_ms, overruled = [], [], [], 0
    while True:
        decided = None
        if search:
            d = page.evaluate(DECIDE_JS, s)
            decided = d["move"]
            overruled += int(d["move"] != d["prior"])
        t = bots.voronoi(arena, 1)
        s = page.evaluate(TICK_JS, [t, decided])
        arena.step((s["moved"][0], t))
        moves.append(s["moved"][0])
        if s["brain"] and not s["over"]:  # the last tick of a round ends it: no move is settled
            settles.append(bool(s["brain"]["sweeps"]) and s["repair"] > 0)
            act_ms.append(s["brain"]["act_ms"])
        if s["over"]:
            break
    return {"seed": seed, "result": s["result"], "ticks": s["tick"], "brain": "".join(map(str, moves)),
            "replica_winner": arena.winner, "settles_shown": all(settles), "act_ms": act_ms, "overruled": overruled}


def score(games: list[dict]) -> dict:
    w = sum(g["result"] == "win" for g in games)
    lo = sum(g["result"] == "loss" for g in games)
    d = len(games) - w - lo
    return {"wins": w, "losses": lo, "draws": d, "score": round((w + 0.5 * d) / max(1, len(games)), 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=32)
    ap.add_argument("--parity", type=int, default=4, help="games replayed natively (needs cadence-net 0.95.2)")
    ap.add_argument("--slot", default="deep", choices=["deep", "flat"])
    ap.add_argument("--first-seed", type=int, default=2_200_000)
    ap.add_argument("--out")
    ap.add_argument("--shots", help="a folder for a screenshot of each player's page")
    a = ap.parse_args()
    seeds = [a.first_seed + k for k in range(a.games)]
    # the native games first, on cadence-net 0.95.2, so a missing library fails before the browser runs
    import cadence

    if a.parity and cadence.__version__ != "0.95.2":
        raise SystemExit(f"the parity games need cadence-net 0.95.2 (found {cadence.__version__})")
    ref = reference(a.slot, seeds[: a.parity]) if a.parity else []
    server, port = serve(ROOT / "web")
    url = f"http://127.0.0.1:{port}/index.html"
    errors: list[str] = []
    load = [os.getloadavg()]
    began = time.time()
    out: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        for player in ("alone", "search"):
            page.goto(f"{url}?brain={a.slot}" + ("&player=alone" if player == "alone" else ""))
            wait_phase(page, ("ready",))
            view = page.evaluate("window.__tron.view()")
            games = [play(page, s, player == "search") for s in seeds]
            out[player] = {"brain": view["brain"], "player": view["player"], "games": games, **score(games)}
            if a.shots:
                Path(a.shots).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(a.shots) / f"promise-{player}.png"))
            load.append(os.getloadavg())
        browser.close()
    server.shutdown()

    alone = out["alone"]["games"]
    parity = [{"seed": r["seed"], "moves_identical": g["brain"] == r["brain"], "winner_identical": g["replica_winner"] == r["winner"]}
              for g, r in zip(alone, ref)]
    act = [x for g in alone for x in g["act_ms"]]
    checks = {
        "page_plays_the_native_brain": bool(parity) and all(x["moves_identical"] and x["winner_identical"] for x in parity),
        "every_move_carries_its_settle": all(g["settles_shown"] for k in out for g in out[k]["games"]),
        "brain_fits_the_tick": bool(act) and statistics.median(act) < TICK_MS,
        "brain_alone_beats_voronoi": out["alone"]["score"] >= 0.70,
        "brain_and_look_ahead_beat_voronoi": out["search"]["score"] >= 0.85,
        "no_page_errors": not errors,
    }
    checks["PASS"] = all(checks.values())
    for k in out:
        for g in out[k]["games"]:
            g["act_ms_median"] = round(statistics.median(g.pop("act_ms")), 2) if g.get("act_ms") else None
    result = {
        "what": "tools/promise_test.py: the Tron page in headless Chromium against the voronoi bot, the brain in the page's seat, "
                f"seeds {seeds[0]} to {seeds[-1]}",
        "checks": checks,
        "brain_alone": {k: v for k, v in out["alone"].items() if k != "games"},
        "brain_and_look_ahead": {k: v for k, v in out["search"].items() if k != "games"},
        "overruled_moves": sum(g["overruled"] for g in out["search"]["games"]),
        "moves_with_look_ahead": sum(g["ticks"] for g in out["search"]["games"]),
        "brain_ms_per_move": {"median": round(statistics.median(act), 2), "max": round(max(act), 2)} if act else None,
        "parity": parity, "native_cadence": cadence.__version__,
        "games": {k: out[k]["games"] for k in out},
        "seconds": round(time.time() - began, 1), "load_average": [[round(x, 1) for x in t] for t in load],
        "page_errors": errors[:10], "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("checks", "brain_alone", "brain_and_look_ahead", "overruled_moves", "brain_ms_per_move", "parity", "seconds")}, indent=1))
    print("PASS" if checks["PASS"] else "FAIL")
    return 0 if checks["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
