"""The claim of the Connect Four page, played on the page itself in headless Chromium.

    python connect-four/tools/promise_test.py --out connect-four/evidence/promise_test-<date>.json [--shots DIR]

The claim (site.json): the brain settles on each move and judges the game; a search over the rules
checks the move; teach it a better column and it learns. A scripted visitor plays the real page
(web/, served here) and checks:

  1. brain + search is the page's player: every brain move comes from a finished settle with a
     verdict over loss, draw and win, and the search's report; the brain's own column is its
     strongest motor neuron among the columns with room;
  2. the search checks the move: the visitor builds threats of four, and every immediate win the
     brain has is taken and every single threat the visitor makes is blocked;
  3. brain alone plays the strongest legal motor neuron of one settle, with no search;
  4. teaching: on the brain's first move of a new game, the visitor teaches a neighbouring column;
     each lesson changes synapses, and within four lessons that column becomes the brain's move on
     that board; Reset brain brings back the trained brain's move;
  5. the game numbers the claim quotes (363, 25 and 12 of 400, the brain first against the perfect
     player, with the page's search budget) are the ones in evidence/search_reading.json.

Console errors, page errors and failed requests fail it. Writes one JSON record to --out.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import random
import re
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
ROWS, COLS = 6, 7


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


def four(cells: list[int], who: int) -> bool:
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                if all(0 <= r + k * dr < ROWS and 0 <= c + k * dc < COLS and cells[(r + k * dr) * COLS + c + k * dc] == who for k in range(4)):
                    return True
    return False


def landing(cells: list[int], c: int) -> int | None:
    return next((r * COLS + c for r in range(ROWS) if cells[r * COLS + c] == 0), None)


def wins(cells: list[int], who: int) -> list[int]:
    out = []
    for c in range(COLS):
        k = landing(cells, c)
        if k is None:
            continue
        t = cells[:]
        t[k] = who
        if four(t, who):
            out.append(c)
    return out


def strongest_legal(motor: list[float], legal: list[bool]) -> int:
    return max((c for c in range(COLS) if legal[c]), key=lambda c: motor[c])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--url", help="a running server for web/ (default: serve it here)")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--games", type=int, default=2, help="games of brain + search against the threat-building visitor (more, up to 5, until it has faced two threats)")
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    record: dict = {"schema": "connect-four-promise/1", "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "claim": json.loads((HERE / "site.json").read_text())["feature"], "checks": [], "games": [],
                    "errors": []}

    def check(name: str, ok: bool, detail=None) -> None:
        record["checks"].append({"name": name, "passed": bool(ok), "detail": detail})
        print(("ok   " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:300] if not ok else "", flush=True)

    # 5. the numbers the claim quotes
    reading = json.loads((HERE / "evidence" / "search_reading.json").read_text())
    page = reading["summary"]["brain + search, 120000 nodes (the page)"]["solver100_first"]
    budget = int(re.search(r"export const NODES = (\d+)", (HERE / "web" / "search.js").read_text()).group(1))
    check("claim_numbers_are_the_evidence", (page["games"], page["win"], page["draw"], page["loss"]) == (400, 363, 25, 12) and budget == 120000
          and "363 of 400" in record["claim"], {"evidence": page, "page_search_nodes": budget})

    url, server = (args.url, None) if args.url else serve(HERE / "web")
    began = time.monotonic()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.on("console", lambda m: record["errors"].append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: record["errors"].append(str(e)))
            pg.on("requestfailed", lambda r: record["errors"].append("failed " + r.url))
            pg.goto(url, wait_until="domcontentloaded")
            state = lambda: pg.evaluate("window.c4.state()")  # noqa: E731
            wait = lambda js, t=180000: pg.wait_for_function(js, timeout=t, polling=100)  # noqa: E731
            idle = "() => window.c4 && window.c4.state().ready && ['human', 'over'].includes(window.c4.state().phase)"
            wait(idle, 240000)
            record["startup_ms"] = state()["startup"]
            check("brain_plus_search_is_the_default", state()["player"] == "search", state()["player"])

            def brain_move_record(s, before_cells, brain_val, vis_val):
                f = s["lastFinal"]
                v = f.get("verdict") or []
                return {"column": f["column"], "brain_column": f.get("brain_column"), "sweeps": f["sweeps"], "settled": f["settled"],
                        "verdict": v, "search": ({k: f["search"].get(k) for k in ("reason", "depth", "nodes", "immediate")} if f.get("search") else None),
                        "own_strongest": strongest_legal(f["motor"], f["legal"]),
                        "brain_wins": wins(before_cells, brain_val), "visitor_wins": wins(before_cells, vis_val)}

            # 1 and 2: games of brain + search against a visitor who builds threats
            g = 0
            while g < args.games or (g < 5 and sum(1 for gm in record["games"] for m in gm["moves"]
                                                   if "brain" in m and not m["brain"]["brain_wins"] and len(m["brain"]["visitor_wins"]) == 1) < 2):
                pg.click("[data-first='you']")
                wait(f"() => window.c4.state().moves.length === 0 && window.c4.state().phase === 'human'")
                moves = []
                while state()["phase"] == "human":
                    s = state()
                    cells, legal = s["game"]["cells"], s["game"]["legal"]
                    vis_val, brain_val = 2 - s["brainPlayer"], 1 + s["brainPlayer"]
                    options = [c for c in range(COLS) if legal[c]]
                    def after(c):  # the board after the visitor drops a stone in column c
                        t = cells[:]
                        t[landing(t, c)] = vis_val
                        return t
                    mine = wins(cells, vis_val)
                    if mine:  # the brain left a win open: take it
                        col = mine[0]
                    else:  # make a threat of four if possible, never one that hands the brain a win
                        safe = [c for c in options if not wins(after(c), brain_val)] or options
                        threat = [c for c in safe if wins(after(c), vis_val)]
                        col = rng.choice(threat) if threat else rng.choice(sorted(safe, key=lambda c: abs(c - 3))[:4])
                    n = len(s["moves"])
                    pg.click(f"#col-{col}")
                    wait(f"() => window.c4.state().moves.length > {n + 1} || window.c4.state().phase === 'over'")
                    wait(idle)
                    s2 = state()
                    after_visitor = cells[:]
                    after_visitor[landing(after_visitor, col)] = vis_val
                    entry = {"visitor": col}
                    if len(s2["moves"]) > n + 1:
                        entry["brain"] = brain_move_record(s2, after_visitor, brain_val, vis_val)
                    moves.append(entry)
                    if g == 0 and len(moves) == 3 and args.shots:
                        pg.screenshot(path=str(args.shots / "promise-brain-move.png"))
                s = state()
                record["games"].append({"moves": moves, "winner": s["game"]["winner"], "brain_player": s["brainPlayer"],
                                        "result": "draw" if s["game"]["winner"] is None else ("brain" if s["game"]["winner"] == s["brainPlayer"] else "visitor")})
                g += 1
            bm = [m["brain"] for gm in record["games"] for m in gm["moves"] if "brain" in m]
            check("every_brain_move_is_a_finished_settle_with_a_verdict", bm and all(m["settled"] and m["sweeps"] > 0 and len(m["verdict"]) == 3
                  and abs(sum(m["verdict"]) - 1) < 0.02 for m in bm), [(m["sweeps"], m["settled"], m["verdict"]) for m in bm])
            check("the_search_reports_on_every_move", all(m["search"] is not None for m in bm), [m["search"] for m in bm])
            check("the_brains_column_is_its_strongest_legal_motor_neuron", all(m["brain_column"] == m["own_strongest"] for m in bm),
                  [(m["brain_column"], m["own_strongest"]) for m in bm])
            took = [m for m in bm if m["brain_wins"]]
            threats = [m for m in bm if not m["brain_wins"] and len(m["visitor_wins"]) == 1]
            check("immediate_wins_taken", all(m["column"] in m["brain_wins"] for m in took), {"chances": len(took), "taken": sum(m["column"] in m["brain_wins"] for m in took)})
            check("single_threats_blocked", threats and all(m["column"] in m["visitor_wins"] for m in threats),
                  {"threats": len(threats), "blocked": sum(m["column"] in m["visitor_wins"] for m in threats)})
            record["summary"] = {"brain_moves": len(bm), "win_chances": len(took), "single_threats": len(threats),
                                 "search_changed_brain_column": sum(m["column"] != m["brain_column"] for m in bm),
                                 "results": [gm["result"] for gm in record["games"]]}

            # 3: brain alone
            pg.click("[data-player='brain']")
            pg.click("[data-first='you']")
            wait("() => window.c4.state().moves.length === 0 && window.c4.state().phase === 'human' && window.c4.state().player === 'brain'")
            pg.click("#col-3")
            wait("() => window.c4.state().moves.length === 2")
            wait(idle)
            f = state()["lastFinal"]
            check("brain_alone_plays_its_strongest_legal_motor_neuron", f.get("search") is None and f["column"] == strongest_legal(f["motor"], f["legal"]),
                  {"column": f["column"], "motor": f["motor"], "search": f.get("search")})
            pg.click("[data-player='search']")

            # 4: teaching on the brain's first move
            pg.click("[data-first='brain']")
            wait("() => window.c4.state().first === 'brain' && window.c4.state().moves.length === 1 && window.c4.state().phase === 'human'")
            played, first_choice = state()["lastFinal"]["column"], state()["lastFinal"]["brain_column"]
            column = next(c for c in (played - 1, played + 1, played - 2, played + 2) if 0 <= c < COLS and c not in (played, first_choice))
            pg.click("#teach")
            wait("() => window.c4.state().phase === 'teach'")
            lessons = []
            for k in range(4):
                pg.click(f"#col-{column}")
                wait(f"() => window.c4.state().phase === 'taught' && window.c4.state().lessons === {k + 1}", 60000)
                L = state()["lastLesson"]
                lessons.append({"accepted": L.get("accepted"), "changed": L.get("changed"), "choice_before": L.get("choice_before"),
                                "choice_after": L.get("choice_after"), "taught_before": L["before"][column], "taught_after": L["after"][column]})
                if k == 0 and args.shots:
                    pg.screenshot(path=str(args.shots / "promise-lesson.png"))
                if L.get("choice_after") == column:
                    break
            record["teaching"] = {"played": played, "brain_column": first_choice, "taught": column, "lessons": lessons,
                                  "status": pg.inner_text("#status")}
            check("each_lesson_changes_synapses", all(x["accepted"] and x["changed"] > 0 for x in lessons), lessons)
            check("the_taught_column_becomes_its_move_within_four_lessons", lessons[-1]["choice_after"] == column,
                  {"lessons": len(lessons), "taught": column, "after": lessons[-1]["choice_after"]})
            pg.click("#teach")
            wait(idle)
            pg.click("#reset-brain")
            wait("() => window.c4.state().lessons === 0")
            again = pg.evaluate("window.c4.request('think', { moves: [], search: false })")
            check("reset_brain_brings_back_the_trained_move", again["column"] == first_choice,
                  {"first": first_choice, "after_reset": again["column"]})
            if args.shots:
                pg.screenshot(path=str(args.shots / "promise-end.png"))
            browser.close()
    except Exception as error:  # noqa: BLE001 - the record names it
        check("runner_completed", False, f"{type(error).__name__}: {error}")
    finally:
        if server:
            server.shutdown()
    check("no_console_error_page_error_or_failed_request", not record["errors"], record["errors"][:5])
    record["seconds"] = round(time.monotonic() - began, 1)
    record["passed"] = all(c["passed"] for c in record["checks"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1, default=str) + "\n")
    print("PASS" if record["passed"] else "FAIL", f"{sum(c['passed'] for c in record['checks'])} of {len(record['checks'])}", "->", args.out)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
