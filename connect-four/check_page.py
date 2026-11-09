"""The page's promise, tried end to end in headless Chromium.

    python check_page.py                  # serves web/ on a free port and runs every scenario
    python check_page.py --url http://127.0.0.1:8790/

A visitor plays a whole game by clicking columns; each brain answer must be a legal column and
its settle must finish in the worker within the latency bound; the brain view must draw changing
frames while the brain settles; hovering a neuron shows its detail; a lesson changes synapses and
the brain settles again; undo, a new game with the brain first, the model card and a brain reset
work; phone width has no horizontal scroll; a browser without fast WebGL gets the Canvas2D view
and stays responsive. Console errors, page errors, failed requests and HTTP errors fail the check.
Evidence (checks, per-move latency, screenshots) goes to evidence/.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import platform
import socketserver
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
LATENCY_MS = 8000.0  # a settle, as the worker measures it, must finish within this (the page draws it as it runs)
ANSWER_S = 10.0  # a click to the brain's stone on the board, animations included
GPU = (["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] if platform.system() == "Darwin"
       else ["--enable-gpu", "--ignore-gpu-blocklist"])


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *args: None
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="a running server for web/ (default: serve it here)")
    parser.add_argument("--out", type=Path, default=HERE / "evidence")
    parser.add_argument("--seed", type=int, default=7, help="the visitor's column choices")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    server = None
    url = args.url
    if not url:
        url, server = serve(HERE / "web")
    evidence = {"schema": "connect-four-page-check/1", "url": url,
                "checked_utc": datetime.now(timezone.utc).isoformat(), "checks": [], "moves": [],
                "console_errors": [], "page_errors": [], "request_failures": [], "http_errors": [],
                "screenshots": []}
    evidence["source_sha256"] = {
        name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        for name in ("web/app.js", "web/board.js", "web/brain.js", "web/index.html",
                     "web/styles.css", "web/worker.js", "web/pack/manifest.json")}
    manifest = json.loads((HERE / "web" / "pack" / "manifest.json").read_text())

    def check(name, passed, detail=None):
        entry = {"name": name, "passed": bool(passed)}
        if detail is not None:
            entry["detail"] = detail
        evidence["checks"].append(entry)
        print(json.dumps(entry), flush=True)

    def watch(page, label):
        page.on("console", lambda m: evidence["console_errors"].append({"page": label, "text": m.text})
                if m.type == "error" else None)
        page.on("pageerror", lambda e: evidence["page_errors"].append({"page": label, "text": str(e)}))
        page.on("requestfailed", lambda r: evidence["request_failures"].append(
            {"page": label, "url": r.url, "failure": r.failure}))
        page.on("response", lambda r: evidence["http_errors"].append(
            {"page": label, "url": r.url, "status": r.status}) if r.status >= 400 else None)

    def state(page):
        return page.evaluate("window.c4.state()")

    def wait(page, predicate, timeout=60000):
        page.wait_for_function(predicate, timeout=timeout, polling=100)

    def ready(page):
        wait(page, "() => window.c4 && window.c4.state().ready && ['human', 'over'].includes(window.c4.state().phase)", 120000)

    def idle(page, timeout=60000):
        wait(page, "() => ['human', 'over'].includes(window.c4.state().phase)", timeout)

    def shot(page, name, full=False):
        page.screenshot(path=str(args.out / name), full_page=full)
        evidence["screenshots"].append(name)

    def overflow(page, label):
        v = page.evaluate("() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
        check(f"{label}_no_horizontal_scroll", max(v["document"], v["body"]) <= v["viewport"] + 1, v)

    rng = __import__("random").Random(args.seed)

    def visitor_column(page):
        legal = state(page)["game"]["legal"]
        options = [c for c, ok in enumerate(legal) if ok]
        return rng.choice(options)

    def play_move(page, label, sample=False, settle_shot=None):
        """Click one column as the visitor and wait for the brain's answer; record it."""
        before = state(page)
        column = visitor_column(page)
        began = time.monotonic()
        page.click(f"#col-{column}")
        samples = []
        if sample:  # the brain view while the brain settles
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and len(samples) < 4:
                s = state(page)
                if s["phase"] == "thinking" and s["view"]["playing"] and s["view"]["playhead"] > 1.2:
                    samples.append(page.evaluate("window.c4.view.sample()") | {"playhead": s["view"]["playhead"], "frames": s["view"]["frames"],
                                                                                "t": round(time.monotonic() - began, 3)})
                    if len(samples) == 2 and settle_shot:
                        shot(page, settle_shot)
                    page.wait_for_timeout(140)
                elif s["phase"] in ("human", "over") and len(s["moves"]) > len(before["moves"]) and (
                        s["phase"] == "over" or len(s["moves"]) > len(before["moves"]) + 1):
                    break
                else:
                    page.wait_for_timeout(25)
        idle(page)
        after = state(page)
        answered = time.monotonic() - began
        record = {"page": label, "visitor": column, "seconds_to_answer": round(answered, 2)}
        if len(after["timings"]) > len(before["timings"]):
            t = after["timings"][-1]
            record.update({"brain": t["column"], "legal": t["legal"], "settle_ms": t["ms"],
                           "worker_ms": t["wall_ms"], "sweeps": t["sweeps"], "brain_column": t.get("brain_column"),
                           "search_ms": t.get("search_ms"), "search_depth": t.get("search_depth")})
        evidence["moves"].append(record)
        return before, after, record, samples

    began = time.monotonic()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=GPU)
            context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            page = context.new_page()
            watch(page, "desktop")
            page.goto(url, wait_until="domcontentloaded")
            ready(page)
            s = state(page)
            check("runtime_is_released_cadence", s["brain"]["cadence"] == manifest["cadence"] == "0.95.2",
                  {"brain": s["brain"], "startup_ms": s["startup"]})
            check("startup_measured", isinstance(s["startup"], (int, float)) and s["startup"] > 0, s["startup"])
            check("brain_view_renderer", s["view"]["mode"] in ("webgl2", "canvas2d"), s["view"])
            evidence["desktop_renderer"] = s["view"]["mode"]
            overflow(page, "desktop")

            # a whole game, clicked column by column
            moves_played, sampled, game_over = 0, None, False
            while moves_played < 30:
                s = state(page)
                if s["phase"] == "over":
                    game_over = True
                    break
                before, after, record, samples = play_move(page, "desktop", sample=sampled is None,
                                                           settle_shot="desktop-1280x800-settling.png")
                if samples:
                    sampled = samples
                moves_played += 1
                if moves_played == 2:
                    shot(page, "desktop-1280x800.png")
                    # hover a motor neuron and an association neuron: their detail appears
                    box = page.locator("#brain-gl").bounding_box()
                    target = page.evaluate("""() => { const v = c4.view, m = v.groups.motor[3], a = v.groups.association[0];
                        return {motor: [v.pos[2 * m], v.pos[2 * m + 1]], assoc: [v.pos[2 * a], v.pos[2 * a + 1]]}; }""")
                    page.mouse.move(box["x"] + target["motor"][0], box["y"] + target["motor"][1])
                    page.wait_for_timeout(150)
                    tip = page.locator("#tooltip")
                    check("hover_shows_motor_neuron", tip.is_visible() and "Motor neuron" in tip.inner_text(),
                          tip.inner_text()[:160] if tip.is_visible() else None)
                    page.mouse.move(box["x"] + target["assoc"][0], box["y"] + target["assoc"][1])
                    page.wait_for_timeout(150)
                    check("hover_shows_association_inputs", tip.is_visible() and "strongest inputs" in tip.inner_text().lower(),
                          tip.inner_text()[:200] if tip.is_visible() else None)
                    shot(page, "desktop-1280x800-hover.png")
                    page.mouse.move(5, 5)
            s = state(page)
            brain_moves = [m for m in evidence["moves"] if m.get("page") == "desktop" and "brain" in m]
            check("game_reached_an_end", game_over and s["phase"] == "over",
                  {"moves": s["moves"], "winner": s["game"]["winner"], "draw": s["game"]["draw"],
                   "line": s["game"]["line"], "brain_player": s["brainPlayer"]})
            status = page.locator("#status").inner_text()
            check("result_is_shown", any(w in status for w in ("You win", "brain wins", "draw")), status)
            check("brain_answers_are_legal", brain_moves and all(m["legal"] for m in brain_moves),
                  [m["brain"] for m in brain_moves])
            check("player_is_brain_plus_search_by_default", s["player"] == "search" and all(m.get("search_ms") is not None for m in brain_moves),
                  {"player": s["player"], "search_ms": [m.get("search_ms") for m in brain_moves],
                   "search_depth": [m.get("search_depth") for m in brain_moves],
                   "overruled": sum(1 for m in brain_moves if m.get("brain_column") is not None and m["brain_column"] != m["brain"])})
            check("settle_within_latency_bound", brain_moves and all(m["worker_ms"] < LATENCY_MS for m in brain_moves),
                  {"bound_ms": LATENCY_MS, "worker_ms": [m["worker_ms"] for m in brain_moves],
                   "settle_ms": [m["settle_ms"] for m in brain_moves], "sweeps": [m["sweeps"] for m in brain_moves]})
            check("answer_on_board_within_bound", brain_moves and all(m["seconds_to_answer"] < ANSWER_S for m in brain_moves),
                  {"bound_s": ANSWER_S, "seconds": [m["seconds_to_answer"] for m in brain_moves]})
            stones = sum(1 for v in s["game"]["cells"] if v)
            check("board_matches_moves", stones == len(s["moves"]), {"stones": stones, "moves": len(s["moves"])})
            check("brain_view_animates_while_settling", bool(sampled) and len({x["hash"] for x in sampled}) >= 2
                  and all(x["mean"] > 2 and x["litShare"] > 0 for x in sampled)
                  and sampled[-1]["frames"] > sampled[0]["frames"], sampled)
            if sampled and len(sampled) >= 2 and sampled[-1]["t"] > sampled[0]["t"]:
                fps = (sampled[-1]["frames"] - sampled[0]["frames"]) / (sampled[-1]["t"] - sampled[0]["t"])
                evidence["settle_frames_per_second"] = round(fps, 1)
                check("brain_view_frame_rate_while_settling", fps >= 20, {"frames_per_second": round(fps, 1), "renderer": s["view"]["mode"]})
            check("imagination_off_by_default", s["imagined"] is None, s["imagined"])
            shot(page, "desktop-1280x800-end.png")

            # a new game where the brain moves first, imagining your replies; then teach it
            page.check("#imagine-toggle")
            imagine_began = time.monotonic()
            page.click('[data-first="brain"]')
            wait(page, "() => window.c4.state().first === 'brain' && window.c4.state().moves.length === 1 && window.c4.state().phase === 'human'", 120000)
            s = state(page)
            check("imagined_replies_for_legal_columns", (lambda im: bool(im) and len(im["candidates"]) >= 1)(s["imagined"]),
                  {"candidates": len((s["imagined"] or {}).get("candidates", [])), "sweeps": (s["imagined"] or {}).get("sweeps"),
                   "ms": (s["imagined"] or {}).get("ms"), "seconds_to_answer": round(time.monotonic() - imagine_began, 2)})
            check("brain_starts_a_new_game", s["moves"] and s["brainPlayer"] == 0, s["moves"])
            first_choice = s["lastFinal"]["column"]
            page.click("#teach")
            wait(page, "() => window.c4.state().phase === 'teach'")
            # the visitor's correction: the column next to the brain's choice (on the empty board
            # every other column's bar rests at the activation floor, so the lessons show as the
            # taught column becoming the move)
            column = next(c for c in (first_choice - 1, first_choice + 1, 0, 6) if 0 <= c < 7 and c != first_choice)
            page.click(f"#col-{column}")
            wait(page, "() => window.c4.state().phase === 'taught'", 30000)
            s = state(page)
            lesson = s["lastLesson"]
            check("lesson_changes_synapses", lesson and lesson.get("accepted") and lesson.get("changed", 0) > 0,
                  {k: lesson.get(k) for k in ("column", "accepted", "changed", "max_change", "choice_before", "choice_after", "ms")} if lesson else None)
            check("lesson_counted", s["lessons"] == 1 and page.locator("#reset-brain").is_visible(), s["lessons"])
            shot(page, "desktop-1280x800-teach.png")
            first = lesson
            page.click(f"#col-{column}")  # tap again: the same lesson once more
            wait(page, "() => window.c4.state().phase === 'taught' && window.c4.state().lessons === 2", 30000)
            again = state(page)["lastLesson"]
            check("repeated_lessons_move_the_taught_column_or_make_it_the_move",
                  again["accepted"] and (again["after"][column] != first["after"][column]
                                         or again["choice_after"] == column or first["choice_after"] == column),
                  {"column": column, "first": [first["before"][column], first["after"][column], first["choice_after"]],
                   "again": [again["before"][column], again["after"][column], again["choice_after"]]})
            page.click("#teach")
            idle(page)
            check("teach_returns_to_game", state(page)["phase"] == "human" and len(state(page)["moves"]) == 1)
            page.click("#reset-brain")
            wait(page, "() => window.c4.state().lessons === 0")
            check("reset_brain_restores_shipped_brain", state(page)["lessons"] == 0)

            # undo: back to the visitor's previous turn
            play_move(page, "desktop")
            before_undo = state(page)["moves"]
            page.click("#undo")
            wait(page, f"() => window.c4.state().moves.length === {len(before_undo) - 2} && window.c4.state().phase === 'human'")
            check("undo_takes_back_a_turn", state(page)["moves"] == before_undo[:-2],
                  {"before": before_undo, "after": state(page)["moves"]})

            page.locator("#model-card summary").click()
            body = page.locator("#card-body").inner_text()
            last = (manifest["training"].get("curve") or [{}])[-1]
            expect = f"{100 * last['optimal']:.1f}%" if last else "pending"
            check("model_card_reads_receipt", expect in body and "GPL-3.0" in body and manifest["brain_sha256"] in body,
                  {"expected": expect, "chars": len(body)})
            shot(page, "desktop-1280x800-model-card.png", full=True)
            context.close()

            # a phone
            context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1,
                                          is_mobile=True, has_touch=True)
            page = context.new_page()
            watch(page, "mobile")
            page.goto(url, wait_until="domcontentloaded")
            ready(page)
            overflow(page, "mobile")
            for _ in range(2):
                if state(page)["phase"] == "over":
                    break
                column = visitor_column(page)
                began_tap = time.monotonic()
                page.locator(f"#col-{column}").tap()
                idle(page)
                s = state(page)
                if s["timings"]:
                    t = s["timings"][-1]
                    evidence["moves"].append({"page": "mobile", "visitor": column, "brain": t["column"], "legal": t["legal"],
                                              "settle_ms": t["ms"], "worker_ms": t["wall_ms"], "sweeps": t["sweeps"],
                                              "seconds_to_answer": round(time.monotonic() - began_tap, 2)})
            s = state(page)
            check("mobile_brain_answers", len(s["timings"]) >= 1 and all(t["legal"] for t in s["timings"]),
                  [t["column"] for t in s["timings"]])
            overflow(page, "mobile_after_play")
            shot(page, "mobile-390x844.png")
            shot(page, "mobile-390x844-full.png", full=True)
            context.close()
            browser.close()

            # a browser without fast WebGL (software rendering): the Canvas2D view
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            page = context.new_page()
            watch(page, "software")
            page.goto(url, wait_until="domcontentloaded")
            ready(page)
            check("software_rendering_uses_canvas2d", state(page)["view"]["mode"] == "canvas2d", state(page)["view"])
            _, after, record, samples = play_move(page, "software", sample=True)
            check("software_rendering_stays_responsive", record.get("legal") and record["seconds_to_answer"] < ANSWER_S
                  and bool(samples) and all(x["mean"] > 2 for x in samples), record | {"samples": samples})
            shot(page, "software-canvas2d-1280x800.png")
            context.close()
            browser.close()
    except Exception as error:  # noqa: BLE001 - the evidence names it
        check("runner_completed", False, f"{type(error).__name__}: {error}")
    finally:
        if server:
            server.shutdown()
    check("no_console_errors", not evidence["console_errors"], evidence["console_errors"])
    check("no_page_errors", not evidence["page_errors"], evidence["page_errors"])
    check("no_request_failures", not evidence["request_failures"], evidence["request_failures"])
    check("no_http_errors", not evidence["http_errors"], evidence["http_errors"])
    evidence["seconds"] = round(time.monotonic() - began, 1)
    evidence["passed"] = all(c["passed"] for c in evidence["checks"])
    (args.out / "page_check.json").write_text(json.dumps(evidence, indent=1) + "\n")
    print(json.dumps({"passed": evidence["passed"], "seconds": evidence["seconds"],
                      "evidence": "evidence/page_check.json"}), flush=True)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
