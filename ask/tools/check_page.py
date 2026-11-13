"""The promise test: the page's claim, performed with the keyboard and the mouse a visitor uses.

    python tools/check_page.py [--shots DIR] [--url URL] [--no-evidence]

Serves ``site/`` (or uses --url), opens the page in headless Chromium at 1512x860 with the
tutorial off, and checks, against what a teacher would answer about the room as it stands
(``truth`` in ``site/room.js``, the room's own geometry, never the brain):

1. **From a thing to its place and colour:** "where is the ball?", "what colour is the cup?".
2. **The other way round:** "what is red?" names every red thing the parrot has a word for.
3. **From memory:** the parrot turned by a drag across the floor (no thing moved), "what is behind
   you?" names the things behind it, one at least in its blind spot.
4. **A pistachio** for a right answer: the parrot cracks it, the reward arrives with a surprise above
   zero, and synapses change.
5. **A new word:** the kettle (a kind the parrot has no word for) clicked and named three times by
   typing; then "where is the kettle?", "what colour is the kettle?" and "what is yellow?" use it.
6. **A word never taught:** "where is the zebra?" is answered "i do not know".

Writes ``evidence/promise-<date>-<time>-<commit>.json`` (every question, the answer expected and
the words said, the seconds) unless --no-evidence. Exit 1 on a failed check.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
KINDS = ["ball", "cup", "box", "book", "shoe", "key", "apple", "lamp", "kettle", "drum", "vase", "clock"]
COLOURS = ["red", "blue", "green", "yellow", "white", "black"]
PLACES = ["front", "right", "behind", "left"]
NONE = "i do not know"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--no-evidence", action="store_true")
    a = ap.parse_args()
    manifest = json.loads((HERE / "site" / "pack" / "manifest.json").read_text())
    base, server = (a.url, None) if a.url else serve(HERE / "site")
    if a.shots:
        a.shots.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1512, "height": 860})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        began = time.time()
        page.goto(base + "?tour=0")
        page.wait_for_function("window.__ask && window.__ask.ready", timeout=300000)
        startup = time.time() - began

        def idle() -> None:
            page.wait_for_function("window.__ask && !window.__ask.busy()", timeout=120000)
            page.wait_for_timeout(150)

        def shot(name: str) -> None:
            if a.shots:
                page.screenshot(path=str(a.shots / f"{name}.png"))

        def truth() -> dict:
            return page.evaluate("""() => { const s = window.__ask.state, t = window.__ask.truth();
                return { heading: s.heading, things: s.things.map((q) => ({ id: q.id, kind: q.kind, colour: q.colour, x: q.x, y: q.y, inView: window.__ask.inView(q) })),
                         where: s.things.map((q) => [q.kind, t.where(q.kind)]), words: s.words }; }""")

        def ask(question: str, expected: list[str], what: str) -> list[str]:
            idle()
            page.click("#question")
            page.fill("#question", "")
            page.type("#question", question, delay=8)
            t0 = time.time()
            page.keyboard.press("Enter")
            page.wait_for_function("window.__ask.busy()", timeout=10000)
            idle()
            said = page.evaluate("window.__ask.state.last.said")
            shown = page.inner_text("#bubble")
            ok = sorted(said) == sorted(expected) and len(said) == len(expected)
            checks.append({"check": what, "question": question, "expected": expected, "said": said,
                           "bubble": shown, "seconds": round(time.time() - t0, 2), "ok": ok})
            return said

        def named_words(kinds: list[int], words: list[str]) -> list[str]:
            out = sorted(KINDS[k] for k in kinds if KINDS[k] in words)
            return out or [NONE]

        shot("1-ready")
        room = truth()
        by_kind = {t["kind"]: t for t in room["things"]}
        place_of = lambda t, h: PLACES[page.evaluate(f"(() => {{ const a = Math.atan2(Math.sin(Math.atan2({t['y']}, {t['x']}) - {h}), Math.cos(Math.atan2({t['y']}, {t['x']}) - {h})); const q = (((-a + Math.PI / 4) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI); return Math.floor(q / (Math.PI / 2)); }})()")]  # noqa: E731

        # 1. from a thing to its place and its colour
        ask("where is the ball?", [place_of(by_kind[0], room["heading"])], "where: thing to place")
        shot("2-where")
        ask("what colour is the cup?", [COLOURS[by_kind[1]["colour"]]], "colour: thing to colour")
        # 2. the other way round
        red = [t["kind"] for t in room["things"] if t["colour"] == 0]
        ask("what is red?", named_words(red, room["words"]), "both directions: colour to things")
        shot("3-what-is-red")
        # 3. turned by a drag across the floor, the things behind it from memory
        idle()
        p0 = page.evaluate("window.__ask.floorPx(1.5, -0.5)")  # the floor, clear of things
        p1 = page.evaluate("window.__ask.floorPx(-0.5, 1.6)")
        page.mouse.move(*p0)
        page.mouse.down()
        for k in range(1, 9):
            page.mouse.move(p0[0] + (p1[0] - p0[0]) * k / 8, p0[1] + (p1[1] - p0[1]) * k / 8)
            page.wait_for_timeout(40)
        page.mouse.up()
        page.wait_for_timeout(600)
        idle()
        room2 = truth()
        behind = [t for t in room2["things"] if place_of(t, room2["heading"]) == "behind"]
        unseen = [KINDS[t["kind"]] for t in behind if not t["inView"]]
        said = ask("what is behind you?", named_words([t["kind"] for t in behind], room2["words"]), "both directions: place to things, from memory")
        checks[-1]["heading"] = round(room2["heading"], 3)
        checks[-1]["behind_out_of_view"] = unseen
        moved = [t for t, u in zip(room["things"], room2["things"], strict=True) if (t["x"], t["y"]) != (u["x"], u["y"])]
        checks[-1]["ok"] = checks[-1]["ok"] and abs(room2["heading"]) > 0.4 and not moved and bool(unseen)
        shot("4-behind")
        # 4. a pistachio for the right answer
        before = page.evaluate("window.__ask.state.held.length")
        page.click("#nut")
        page.wait_for_timeout(200)
        idle()
        log = page.inner_text("#log")
        last = log.splitlines()[-1] if log else ""
        # the reward path: a surprise above zero, and synapses changed by it
        import re
        found = re.search(r"Surprise ([0-9.]+): ([0-9]+) synapse", last)
        checks.append({"check": "a pistachio: cracked, and the reward changes synapses", "said_before": said,
                       "log": last, "ok": bool(found) and float(found.group(1)) > 0 and int(found.group(2)) > 0 and before >= 0})
        shot("5-pistachio")
        # 5. a new word, taught by three namings, and used
        kettle = by_kind[8]
        for k in range(3):
            idle()
            xy = page.evaluate(f"window.__ask.thingPx({kettle['id']})")
            if k == 0:
                page.mouse.click(*xy)
                page.wait_for_selector("#teach:not([hidden])", timeout=5000)
            idle()
            page.fill("#teach-word", "kettle")
            page.keyboard.press("Enter")
            page.wait_for_timeout(200)
        idle()
        checks.append({"check": "naming: three namings heard", "count": page.inner_text("#teach-count"),
                       "ok": page.inner_text("#teach-count").startswith("heard 3")})
        shot("6-named")
        page.click("#teach-done")
        room3 = truth()
        kettle3 = next(t for t in room3["things"] if t["kind"] == 8)
        ask("where is the kettle?", [place_of(kettle3, room3["heading"])], "a new word: where")
        ask("what colour is the kettle?", [COLOURS[kettle3["colour"]]], "a new word: colour")
        yellow = [t["kind"] for t in room3["things"] if t["colour"] == kettle3["colour"]]
        ask(f"what is {COLOURS[kettle3['colour']]}?", named_words(yellow, room3["words"] + ["kettle"]), "a new word: the other way round")
        shot("7-new-word")
        # 6. a word never taught
        ask("where is the zebra?", [NONE], "a word never taught")
        browser.close()
    if server:
        server.shutdown()

    passed = sum(c["ok"] for c in checks)
    ok = passed == len(checks) and not errors
    for c in checks:
        print(("ok   " if c["ok"] else "FAIL ") + c["check"] + "  " + json.dumps({k: c[k] for k in ("question", "expected", "said") if k in c}))
    for e in errors[:5]:
        print("console error:", e[:300])
    print(f"{'PASS' if ok else 'FAIL'}: {passed} of {len(checks)}; console errors {len(errors)}; startup {startup:.1f} s")
    if not a.no_evidence:
        commit = manifest["commit"][:8] if manifest.get("commit") else "release"
        out = {"what": "the promise test of the page (tools/check_page.py)", "when": time.strftime("%Y-%m-%d %H:%M"),
               "cadence": manifest["cadence"], "build": manifest.get("build"), "wheel_sha256": manifest["wheel_sha256"],
               "brain_sha256": manifest["brain"]["sha256"], "viewport": [1512, 860], "startup_seconds": round(startup, 1),
               "passed": passed, "checks": len(checks), "console_errors": errors[:10], "results": checks}
        target = HERE / "evidence" / f"promise-{time.strftime('%Y%m%d-%H%M')}-{commit}.json"
        target.write_text(json.dumps(out, indent=1) + "\n")
        print(target)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
