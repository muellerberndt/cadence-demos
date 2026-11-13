"""The page's promise, on the real page: one continuing brain per robot, calm in routine, learning
only when a surprise or a want wakes it, kept in the browser from fight to fight.

    python robot-arena/tools/promise_arena.py --out DIR [--shots DIR] [--url URL]

It serves the built page (``showcase-app/dist``, made by ``npm run build``) or uses --url, lets the
league wake, opens the brain of the robot that is aroused most in the first moments (a click on
its row in the standings), plays the fight to its end "as fast as they settle", and reads what the
page showed (``window.__arena``: every robot's mode each moment; the inspected brain's arousal,
surprise, want and changed synapses). It checks:

  1. routine is calm: most robot-moments of the fight are calm (more than half);
  2. the inspected brain wakes and settles back: it is aroused in some moments and calm in others,
     and every calm-to-aroused onset comes with a surprise or a want above zero in that moment or
     the five before it;
  3. learning happens only when aroused: every moment in which its synapses change is an aroused
     moment or the first moment after one (a command's lesson lands with its outcome, one moment
     later); no other calm moment changes a synapse;
  4. one continuing life: after the fight the page saves the six brains in IndexedDB, each one
     differs from the brain it arrived with, and a reload restores them.

The readings go to ``DIR/promise-arena.json``, screenshots to --shots. Exit 1 on a failed check.
"""

from __future__ import annotations

import argparse
import base64
import functools
import hashlib
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
DIST = HERE / "showcase-app" / "dist"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(Quiet, directory=str(directory))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


SAVED = """() => new Promise((res) => { const r = indexedDB.open("cadence-showcase-league", 1);
  r.onsuccess = () => { const g = r.result.transaction("league", "readonly").objectStore("league").get("brains");
    g.onsuccess = () => res(g.result || null); }; r.onerror = () => res(null); })"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="a running server for the built page (default: serve showcase-app/dist)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--pick", type=int, default=60, help="moments before the most aroused robot is opened")
    ap.add_argument("--boot", type=float, default=400.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    server = None
    url = args.url
    if not url:
        if not (DIST / "index.html").exists():
            print("no build: run npm ci && npm run build in robot-arena/showcase-app", file=sys.stderr)
            return 1
        url, server = serve(DIST)
    manifest = json.loads((DIST / "pack" / "manifest.json").read_text()) if not args.url else None
    ev: dict = {"schema": "robot-arena-promise/1", "url": url, "checked_utc": datetime.now(timezone.utc).isoformat(),
                "checks": [], "errors": []}

    def check(name: str, ok: bool, **detail) -> None:
        ev["checks"].append({"check": name, "ok": bool(ok), **detail})
        print(("ok   " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:400], flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1512, "height": 860})
        page = ctx.new_page()
        page.on("console", lambda m: ev["errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ev["errors"].append(str(e)))
        page.on("requestfailed", lambda r: ev["errors"].append("failed " + r.url))
        began = time.time()
        page.goto(url)
        page.wait_for_function("() => /standings/i.test(document.body.innerText) && window.__arena && window.__arena.log.length > 0",
                               timeout=args.boot * 1000)
        ev["boot_seconds"] = round(time.time() - began, 1)
        if manifest is None:
            manifest = page.evaluate("fetch('pack/manifest.json').then(r => r.json())")
        page.wait_for_function(f"() => window.__arena.log.some(e => e.t >= {args.pick})", timeout=600000)
        # the robot aroused most so far: its row in the standings opens its brain
        pick = page.evaluate("""() => { const A = window.__arena, log = A.log.filter(e => e.fight === A.fight);
          const n = A.names.length, c = Array(n).fill(0); for (const e of log) e.mode.forEach((m, i) => { if (m === 1) c[i]++; });
          const i = c.indexOf(Math.max(...c)); return { index: i, name: A.names[i], aroused: c }; }""")
        page.locator("aside button", has_text=pick["name"]).first.click()
        page.wait_for_function("() => window.__brainView && window.__brainView.moments > 5", timeout=120000)
        print(f"info opened {pick['name']} (aroused moments so far {pick['aroused']})", flush=True)
        if args.shots:
            page.wait_for_timeout(1500)
            page.screenshot(path=str(args.shots / "promise-inspected.png"))
        page.locator("button", has_text="as fast as they settle").click()
        page.wait_for_function("() => /fight over/i.test(document.body.innerText)", timeout=1800000)
        A = page.evaluate("window.__arena")
        page.wait_for_function("() => document.body.innerText.includes('saved after the last fight')", timeout=120000)
        if args.shots:
            page.screenshot(path=str(args.shots / "promise-fight-over.png"))
        saved = page.evaluate(SAVED) or {}
        # a reload: the brains come back
        page.reload()
        page.wait_for_function("() => document.body.innerText.includes('restored from your last visit')", timeout=args.boot * 1000)
        restored_fights = page.evaluate("() => (document.body.innerText.match(/(\\d+) fights here/) || [])[1]")
        browser.close()
    if server:
        server.shutdown()

    log = [e for e in A["log"] if e["fight"] == A["fight"]]
    names, n = A["names"], len(A["names"])
    alive = [(e["mode"][i]) for e in log for i in range(n) if e["mode"][i] != 9]
    calm = sum(m == 0 for m in alive) / max(1, len(alive))
    per_robot = {}
    for i, name in enumerate(names):
        ms = [e["mode"][i] for e in log if e["mode"][i] != 9]
        per_robot[name] = {"moments": len(ms), "calm": round(sum(m == 0 for m in ms) / max(1, len(ms)), 3)}
    ev.update({"fight_moments": len(log), "names": names, "inspected": pick["name"], "calm_share": round(calm, 3),
               "per_robot": per_robot})
    check("routine is calm: most robot-moments of the fight are calm", calm > 0.5 and len(alive) > 300,
          calm_share=round(calm, 3), robot_moments=len(alive), per_robot=per_robot)

    ins = [e for e in log if e["ins"] and e["inspected"] == pick["index"]]
    modes = [e["ins"]["mode"] for e in ins]
    onsets, explained, by_surprise, by_want = 0, 0, 0, 0
    for k in range(1, len(ins)):
        if modes[k] == "aroused" and modes[k - 1] != "aroused" and ins[k]["t"] == ins[k - 1]["t"] + 1:
            onsets += 1
            window = [x["ins"] for x in ins[max(0, k - 5):k + 1]]
            explained += any(w["surprise"] > 0 or w["want"] > 0 for w in window)
            by_surprise += any(w["surprise"] > 0 for w in window)
            by_want += any(w["want"] > 0 for w in window)
    aroused_n = sum(m == "aroused" for m in modes)
    check("the inspected brain wakes and settles back; a surprise or a want comes with every onset",
          0 < aroused_n < len(modes) and onsets > 0 and explained == onsets,
          moments=len(modes), aroused=aroused_n, onsets=onsets, with_surprise_or_want=explained,
          with_surprise=by_surprise, with_want=by_want)

    changed, landing, stray = 0, 0, []
    for k, e in enumerate(ins):
        if e["ins"]["changed"] <= 0:
            continue
        changed += 1
        if e["ins"]["mode"] == "aroused":
            continue
        prev = ins[k - 1] if k else None
        if prev and prev["t"] == e["t"] - 1 and prev["ins"]["mode"] == "aroused":
            landing += 1
        else:
            stray.append(e["t"])
    calm_moments = sum(m != "aroused" for m in modes)
    check("learning only when aroused: synapses change in aroused moments and in the moment after, never in other calm moments",
          changed > 0 and not stray, moments_with_changes=changed, landing_after_aroused=landing,
          calm_moments=calm_moments, calm_changes_elsewhere=stray[:10])

    shipped = {r["name"]: r["brain_sha256"] for r in manifest["roster"]}
    hashes = {k: hashlib.sha256(base64.b64decode(v)).hexdigest() for k, v in saved.items()}
    differ = sorted(k for k, h in hashes.items() if shipped.get(k) and h != shipped[k])
    check("one continuing life: the six brains saved in this browser, each changed by its fight, restored on reload",
          len(hashes) == len(shipped) and len(differ) == len(shipped) and restored_fights == "1",
          saved=len(hashes), changed_from_shipped=len(differ), fights_after_reload=restored_fights)

    errors = [e for e in ev["errors"] if "favicon" not in e]
    check("no console errors, page errors or failed requests", not errors, errors=errors[:10])
    ev["passed"] = all(c["ok"] for c in ev["checks"])
    (args.out / "promise-arena.json").write_text(json.dumps(ev, indent=1, default=str) + "\n")
    print("PASS" if ev["passed"] else "FAIL")
    return 0 if ev["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
