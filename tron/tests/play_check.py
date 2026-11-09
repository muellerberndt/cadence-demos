"""The page's promise, tried in headless Chromium: both brains wake in the browser, play the moves
the native brain plays, and play whole games from the keyboard and from the phone's buttons.

    python tests/play_check.py [--games 1] [--parity 3] [--out evidence/page_check.json]

Serves web/ itself on a free port. Per brain (`?brain=flat`, `?brain=deep`):
1. The page boots and the brain wakes (Pyodide, the 0.95.2 wheel, the hashed pack).
2. Move parity: `--parity` games of the brain against `voronoi` (seat 1), played natively here as the
   readings play them (reset, then a greedy act each move) and replayed through the page's worker
   (`window.__tron.call`): every brain move, every head and the winner must match.
3. Whole games from the keyboard, screenshots mid-game; the record counts them, apart per brain.
Then the phone width: a game from the on-screen buttons, no sideways scroll.
Console errors and page errors fail the check. Screenshots go to `--shots` (not tracked).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright  # noqa: E402

from tron import bots  # noqa: E402
from tron.world import DC, DR, Arena  # noqa: E402

TICK_JS = """async (move) => { const t0 = performance.now(); const s = await window.__tron.call("tick", {move});
  return {moved: s.moved, heads: s.heads, over: s.over, worker_ms: s.worker_ms, round_ms: performance.now() - t0}; }"""
BEGIN_JS = """async (seed) => { const s = await window.__tron.call("begin", {seed}); return {heads: s.heads}; }"""
KEYS = ("ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft")


def serve(folder: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "p90": round(xs[int(len(xs) * 0.9)], 1),
            "max": round(xs[-1], 1)}


def wait_phase(page, phases, timeout=400.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = page.evaluate("window.__tron && window.__tron.view()")
        except Exception:
            v = None
        if v and v["phase"] in phases:
            return v
        if v and v["phase"] == "error":
            raise RuntimeError("the page reports an error: " + page.inner_text("#overlay"))
        time.sleep(0.25)
    raise TimeoutError(f"phase {phases} not reached")


def free_space(occ, n, r, c, cap=120):
    if not (0 <= r < n and 0 <= c < n) or occ[r * n + c]:
        return -1
    seen, stack = {(r, c)}, [(r, c)]
    while stack and len(seen) < cap:
        a, b = stack.pop()
        for d in range(4):
            y, x = a + DR[d], b + DC[d]
            if 0 <= y < n and 0 <= x < n and not occ[y * n + x] and (y, x) not in seen:
                seen.add((y, x))
                stack.append((y, x))
    return len(seen)


def choose(v):
    """A scripted player: the direction with the most room (the page applies a key at its next
    tick, so riding on also needs the cell after next to be free)."""
    n, occ = v["size"], v["occupied"]
    r, c = v["heads"][1]
    h = v["headings"][1]
    best, pick = -9, h
    for d in (h, (h + 1) % 4, (h + 3) % 4):
        score = free_space(occ, n, r + DR[d], c + DC[d])
        if d == h:
            ahead = free_space(occ, n, r + 2 * DR[d], c + 2 * DC[d], cap=2)
            score = score + 2 if ahead > 0 else score - 60
        if score > best:
            best, pick = score, d
    return h, pick


def play(page, shots, prefix, buttons=False):
    if buttons:
        page.tap("#arena-wrap")
    else:
        page.keyboard.press("Space")
    wait_phase(page, ("countdown", "playing"), 60)
    taken = set()
    while True:
        v = page.evaluate("window.__tron.view()")
        if v["phase"] in ("over", "ready", "error"):
            break
        if v["phase"] == "playing" and v["heads"] and not v["queued"]:
            h, pick = choose(v)
            if pick != h:
                if buttons:
                    page.tap("#left" if pick == (h + 3) % 4 else "#right")
                else:
                    page.keyboard.press(KEYS[pick])
        for t in (25, 60):
            if t not in taken and v["tick"] >= t:
                page.screenshot(path=str(shots / f"{prefix}-tick{t}.png"))
                taken.add(t)
        time.sleep(0.03)
    time.sleep(1.2)
    page.screenshot(path=str(shots / f"{prefix}-over.png"))
    return page.evaluate("window.__tron.view()"), page.evaluate("window.__tron.last()")


def reference(slot: str, seeds: list[int]) -> list[dict]:
    """The brain against `voronoi`, played natively as the readings play it."""
    from cadence import Brain
    from tron import r3

    brain = Brain.load(str(ROOT / "web" / "pack" / slot / "brain" / "brain.npz"), backend="cpu")
    pol = r3.policy(brain, "field")
    out = []
    for s in seeds:
        a = Arena(24, seed=s)
        mine, theirs = [], []
        while not a.over:
            m, t = pol(a, 0), bots.voronoi(a, 1)
            mine.append(m)
            theirs.append(t)
            a.step((m, t))
        out.append({"seed": s, "brain": "".join(map(str, mine)), "bot": "".join(map(str, theirs)), "winner": a.winner})
    return out


def check_slot(browser, url, slot, a, shots, errors):
    report: dict = {}
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"[{slot}] console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"[{slot}] pageerror: {e}"))
    t0 = time.time()
    page.goto(f"{url}?brain={slot}")
    wait_phase(page, ("ready",))
    report["boot_s"] = round(time.time() - t0, 1)
    view = page.evaluate("window.__tron.view()")
    report["brain"] = view["brain"]
    report["switch_marks"] = page.evaluate("[...document.querySelectorAll('#pick a.on')].map(a => a.dataset.slot)")
    page.screenshot(path=str(shots / f"{slot}-start.png"))

    seeds = [9_300_000 + k for k in range(a.parity)]
    ref = reference(slot, seeds)
    parity, rounds, worker = [], [], []
    for g in ref:
        s = page.evaluate(BEGIN_JS, g["seed"])
        arena = Arena(24, seed=g["seed"])
        ok = [list(h) for h in arena.heads] == s["heads"]
        mine = []
        while True:
            t = bots.voronoi(arena, 1)
            r = page.evaluate(TICK_JS, t)
            mine.append(r["moved"][0])
            arena.step((r["moved"][0], t))
            ok = ok and [list(h) for h in arena.heads] == r["heads"] and arena.over == r["over"]
            rounds.append(r["round_ms"])
            worker.append(r["worker_ms"])
            if r["over"]:
                break
        parity.append({"seed": g["seed"], "moves": len(mine), "brain_identical": "".join(map(str, mine)) == g["brain"],
                       "replica_agrees": ok, "winner_identical": arena.winner == g["winner"]})
    report["parity"] = parity
    report["parity_ok"] = all(x["brain_identical"] and x["replica_agrees"] and x["winner_identical"] for x in parity)
    report["parity_ms"] = {"round": stats(rounds), "worker": stats(worker)}

    page.reload()
    wait_phase(page, ("ready",))
    games = []
    for k in range(a.games):
        v, last = play(page, shots, f"{slot}-game{k + 1}")
        games.append({"result_for_brain": last["result"], "ticks": last["tick"]})
    report["games"] = games
    report["record"] = v["record"]
    tim = page.evaluate("window.__tron.timings()")
    report["play_ms"] = {"round": stats([t["round"] for t in tim]), "worker": stats([t["worker"] for t in tim]),
                         "python_act": stats([t["act"] for t in tim])}
    gaps = sorted(page.evaluate("window.__tron.frameGaps()"))
    if gaps:
        report["fps_median"] = round(1000 / statistics.median(gaps), 1)
    page.locator("#brain").screenshot(path=str(shots / f"{slot}-brain.png"))
    page.reload()
    wait_phase(page, ("ready",))
    report["record_after_reload"] = page.evaluate("window.__tron.view().record")
    ctx.close()
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--parity", type=int, default=3)
    ap.add_argument("--slots", nargs="+", default=["deep", "flat"])
    ap.add_argument("--shots", default=str(ROOT / "evidence" / "screens"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)
    server, port = serve(ROOT / "web")
    url = f"http://127.0.0.1:{port}/index.html"
    errors: list[str] = []
    report: dict = {"url": url, "slots": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        report["chromium"] = browser.version
        for slot in a.slots:
            report["slots"][slot] = check_slot(browser, url, slot, a, shots, errors)
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = phone.new_page()
        page.on("console", lambda m: errors.append(f"[phone] console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[phone] pageerror: {e}"))
        page.goto(url)
        wait_phase(page, ("ready",))
        v, last = play(page, shots, "phone-game", buttons=True)
        ov = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        report["phone"] = {"result_for_brain": last["result"], "ticks": last["tick"], "no_overflow": ov[0] <= ov[1],
                           "scroll_vs_client": ov}
        phone.close()
        browser.close()
    server.shutdown()
    report["console_errors"] = errors[:20]
    slots = report["slots"].values()
    ok = (not errors and report["phone"]["no_overflow"]
          and all(s["parity_ok"] for s in slots)
          and all(s["record_after_reload"]["games"] >= a.games for s in slots)
          and len({s["brain"] for s in slots}) == len(a.slots))
    report["pass"] = ok
    text = json.dumps(report, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
