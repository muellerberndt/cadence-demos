"""The page's promise, on the real page: flip the season, and the learners change what they eat
while their frozen twins do not.

    python patch-world/tools/promise_flip.py --out DIR [--shots DIR] [--summer 400] [--winter 900]

It serves ``web/`` (or uses --url), lets the world run through some summer at full speed, presses
the page's own "Flip the season" button, and lets the winter run. It reads the same per-50-moment
counts the page's chart "Berries eaten when standing on one" draws (``window.patchWorld``), for
the learners and for the frozen twins, and checks:

  1. in summer the learners eat most berries they stand on (at least 80%);
  2. late in the winter the learners eat at most half the share they ate in summer, and less than
     in the first moments of the winter: they learned, within their lives, to leave the berries;
  3. in winter the frozen twins (the same brains, never learning) eat at least 80% of the berries
     they stand on, and at least 30 points more than the learners late in the winter.

The bounds are looser than the measured worlds of ``evidence/flip.json`` (learners 99% in summer,
45% in the first 100 moments of winter, 5% in the last 100; twins 97% and 96%), since the page's
world also has births, deaths and a predator. Two twins stand on few berries: the winter runs on
(up to --max-winter moments) until the twins have stood on at least --min-twin berries.
The readings go to ``DIR/promise-flip.json``, a screenshot of the page to --shots. Exit 1 on a
failed check.
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
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(Quiet, directory=str(directory))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


READ = """() => { const s = window.patchWorld; if (!s || !s.snapshot) return null;
  const kinds = {}; for (const c of s.snapshot.creatures) kinds[c.kind] = (kinds[c.kind] || 0) + 1;
  return { t: s.snapshot.t, summer: s.snapshot.summer, kinds, flips: s.snapshot.flips,
           history: s.snapshot.history, ms: s.msPerMoment, tally: s.snapshot.tally }; }"""


def counts(windows: list[dict], kind: str) -> dict:
    """Berries eaten (a good berry or a poisoning) and berries walked past, summed over windows."""
    ate = passed = 0
    for h in windows:
        e = (h.get("events") or {}).get(kind) or {}
        ate += e.get("berry", 0) + e.get("poisoned", 0)
        passed += e.get("passed", 0)
    n = ate + passed
    return {"ate": ate, "passed": passed, "stood_on": n, "share": round(ate / n, 3) if n else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="a running server for web/ (default: serve it here)")
    ap.add_argument("--out", type=Path, required=True, help="folder for promise-flip.json")
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--summer", type=int, default=400, help="summer moments before the flip")
    ap.add_argument("--winter", type=int, default=900, help="winter moments after the flip")
    ap.add_argument("--max-winter", type=int, default=1400, help="the longest winter to wait for the twins")
    ap.add_argument("--min-twin", type=int, default=6, help="berries the twins stood on in winter")
    ap.add_argument("--boot", type=float, default=300.0, help="seconds to let the page start")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    server = None
    url = args.url
    if not url:
        url, server = serve(HERE / "web")
    ev: dict = {"schema": "patch-world-promise-flip/1", "url": url,
                "checked_utc": datetime.now(timezone.utc).isoformat(), "checks": [], "errors": []}

    def check(name: str, ok: bool, **detail) -> None:
        ev["checks"].append({"check": name, "ok": bool(ok), **detail})
        print(("ok   " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:400], flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: ev["errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ev["errors"].append(str(e)))
        page.on("requestfailed", lambda r: ev["errors"].append("failed " + r.url))
        began = time.time()
        page.goto(url)
        page.wait_for_function("() => window.patchWorld && window.patchWorld.ready", timeout=args.boot * 1000)
        ev["boot_seconds"] = round(time.time() - began, 1)
        page.click('[data-speed="1000"]')
        page.wait_for_function(f"() => window.patchWorld.snapshot.t >= {args.summer}", timeout=args.summer * 3000)
        before = page.evaluate(READ)
        if not before["summer"]:
            check("the world is in summer before the flip", False, t=before["t"])
            return finish(ev, args, browser, server)
        # the page's own button
        page.click("#flip")
        page.wait_for_function("() => !window.patchWorld.snapshot.summer", timeout=60000)
        flip_t = page.evaluate(READ)["flips"][-1]
        print(f"info flipped at moment {flip_t}", flush=True)
        target = flip_t + args.winter
        while True:
            page.wait_for_function(f"() => window.patchWorld.snapshot.t >= {target}", timeout=args.winter * 3000)
            after = page.evaluate(READ)
            winter = [h for h in after["history"] if h["t"] - 50 >= flip_t]
            if counts(winter, "frozen")["stood_on"] >= args.min_twin or target >= flip_t + args.max_winter:
                break
            target = min(flip_t + args.max_winter, target + 200)
            print(f"info the twins stood on {counts(winter, 'frozen')['stood_on']} berries; the winter runs to {target}", flush=True)
        if args.shots:
            page.screenshot(path=str(args.shots / "promise-winter.png"))
            page.locator("#chart").screenshot(path=str(args.shots / "promise-chart.png"))
        browser.close()
    if server:
        server.shutdown()

    hist = after["history"]
    summer = [h for h in hist if h["t"] <= flip_t and h["t"] > 100]       # skip the first 100 moments
    early = [h for h in hist if flip_t <= h["t"] - 50 and h["t"] <= flip_t + 200]
    late = [h for h in hist if h["t"] - 50 >= flip_t + 500]
    winter = [h for h in hist if h["t"] - 50 >= flip_t]
    L = {"summer": counts(summer, "live"), "winter_first_150": counts(early, "live"),
         "winter_from_500": counts(late, "live"), "winter": counts(winter, "live")}
    F = {"summer": counts(summer, "frozen"), "winter": counts(winter, "frozen")}
    R = {"summer": counts(summer, "random"), "winter": counts(winter, "random")}
    ev.update({"flip_moment": flip_t, "last_moment": after["t"], "creatures": after["kinds"],
               "ms_per_moment": round(after["ms"] or 0, 1), "learners": L, "frozen_twins": F,
               "random_walkers": R, "tally": after["tally"]})
    ls, le, ll = L["summer"]["share"], L["winter_first_150"]["share"], L["winter_from_500"]["share"]
    fw = F["winter"]["share"]
    check("summer: the learners eat most berries they stand on (at least 80%)",
          ls is not None and ls >= 0.8 and L["summer"]["stood_on"] >= 20, learners=L["summer"])
    check("winter: late in the winter the learners eat at most half their summer share, and less than early in the winter",
          ls is not None and ll is not None and le is not None and ll <= ls / 2 and ll < le and L["winter_from_500"]["stood_on"] >= 20,
          summer=ls, first_150=le, from_500=ll, stood_on_late=L["winter_from_500"]["stood_on"])
    check("winter: the frozen twins keep eating the berries (at least 80%, 30 points above the learners late in the winter)",
          fw is not None and fw >= 0.8 and ll is not None and fw - ll >= 0.3 and F["winter"]["stood_on"] >= args.min_twin,
          twins=F["winter"], learners_late=ll)
    return finish(ev, args, None, None)


def finish(ev: dict, args, browser, server) -> int:
    if browser:
        browser.close()
    if server:
        server.shutdown()
    errors = [e for e in ev["errors"] if "favicon" not in e]
    ev["checks"].append({"check": "no console errors, page errors or failed requests", "ok": not errors, "errors": errors[:10]})
    print(("ok   " if not errors else "FAIL ") + "no console errors, page errors or failed requests", errors[:3])
    ev["passed"] = all(c["ok"] for c in ev["checks"])
    (args.out / "promise-flip.json").write_text(json.dumps(ev, indent=1, default=str) + "\n")
    print("PASS" if ev["passed"] else "FAIL")
    return 0 if ev["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
