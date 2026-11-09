"""The page's promise, tried end to end in headless Chromium.

    python check_page.py                  # serves web/ on a free port
    python check_page.py --url http://127.0.0.1:8792/ --moments 400

The page must boot (the world worker and the brain workers, every file checked against the
manifest), run the world, keep its creatures alive and learning through a season flip (the
learners' brains report aroused, learning moments after the flip), open the inspector on a
learner and draw its settled brain, drop food and add a predator, and stay without horizontal
scroll at phone width. Console errors, page errors, failed requests and HTTP errors fail the
check. The readings and two screenshots go to ``evidence/``.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BOOT_S = 240.0


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *args: None
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


READ = """() => { const s = window.patchWorld; if (!s || !s.snapshot) return null;
  const kinds = {}; for (const c of s.snapshot.creatures) kinds[c.kind] = (kinds[c.kind] || 0) + 1;
  return { t: s.snapshot.t, summer: s.snapshot.summer, ready: s.ready, kinds,
           ms: s.msPerMoment, tally: s.snapshot.tally, flips: s.snapshot.flips,
           history: s.snapshot.history, selected: s.selected }; }"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="a running server for web/ (default: serve it here)")
    parser.add_argument("--moments", type=int, default=300, help="moments before and after the flip")
    parser.add_argument("--out", type=Path, default=HERE / "evidence")
    parser.add_argument("--shots", type=Path, default=HERE / "evidence" / "screens")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.shots.mkdir(parents=True, exist_ok=True)
    server = None
    url = args.url
    if not url:
        url, server = serve(HERE / "web")
    ev: dict = {"schema": "patch-world-page-check/1", "url": url,
                "checked_utc": datetime.now(timezone.utc).isoformat(), "checks": [],
                "console_errors": [], "page_errors": [], "request_failures": [], "http_errors": []}

    def check(name: str, ok: bool, **detail) -> None:
        ev["checks"].append({"check": name, "ok": bool(ok), **detail})
        print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:300], flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda m: ev["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ev["page_errors"].append(str(e)))
        page.on("requestfailed", lambda r: ev["request_failures"].append(r.url))
        page.on("response", lambda r: ev["http_errors"].append(f"{r.status} {r.url}") if r.status >= 400 else None)
        began = time.time()
        page.goto(url)
        page.wait_for_function("() => window.patchWorld && window.patchWorld.ready", timeout=BOOT_S * 1000)
        boot_s = time.time() - began
        first = page.evaluate(READ)
        check("boots: world and brain workers ready", True, seconds=round(boot_s, 1),
              runtime=page.inner_text("#runtime"), creatures=first["kinds"])
        page.click('[data-speed="1000"]')
        t0 = time.time()
        page.wait_for_function(f"() => window.patchWorld.snapshot.t >= {first['t'] + args.moments}",
                               timeout=args.moments * 2000)
        before = page.evaluate(READ)
        rate = (before["t"] - first["t"]) / (time.time() - t0)
        check("runs the world", before["t"] >= first["t"] + args.moments, moments=before["t"],
              moments_per_second=round(rate, 2), ms_per_moment=round(before["ms"] or 0, 1),
              creatures=before["kinds"])
        # a learner in the inspector, its brain drawn
        lid = page.evaluate("() => { const cs = window.patchWorld.snapshot.creatures; const c = cs.find(c => c.kind === 'live' && c.recall) || cs.find(c => c.kind === 'live'); return c ? c.id : null; }")
        if lid is not None:
            page.evaluate(f"""() => {{ const c = window.patchWorld.cur.get({lid});
              const r = document.getElementById('world').getBoundingClientRect();
              const x = r.left + (c.x + 0.5) / window.patchWorld.width * r.width, y = r.top + (c.y + 0.5) / window.patchWorld.height * r.height;
              document.getElementById('world').dispatchEvent(new MouseEvent('click', {{ clientX: x, clientY: y, bubbles: true }})); }}""")
            page.wait_for_function("() => !document.getElementById('inspector').hidden", timeout=10000)
            page.wait_for_function("() => document.getElementById('settle-line').textContent.includes('settled')", timeout=30000)
            page.wait_for_function("() => window.patchWorld.brainView.layout && window.patchWorld.brainView.cur && window.patchWorld.brainView.cur.frames", timeout=30000)
            page.wait_for_timeout(2500)
            bv = page.evaluate("""() => { const v = window.patchWorld.brainView; return { frame_ms: v.frameMs, frames: v.frames,
              sweeps: v.cur.sweeps, settle_frames: v.cur.frames.length, tracts: Object.keys(v.cur.tracts || {}).length,
              populations: v.anat.populations, slots: v.anat.slots, changed_total: v.changedTotal,
              mode: v.cur.arousal && v.cur.arousal.mode }; }""")
            check("inspector opens on a learner and draws its brain from its real state", bv["settle_frames"] > 1 and bv["tracts"] > 0,
                  title=page.inner_text("#insp-title"), settle=page.inner_text("#settle-line"), brain_view=bv)
            check("brain view draws within a 60 fps frame budget", bv["frame_ms"] < 16.7, frame_ms=round(bv["frame_ms"], 2))
            page.locator("#inspector").scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            page.locator(".bv-wrap").screenshot(path=str(args.shots / "brain.png"))
        page.screenshot(path=str(args.shots / "summer.png"))
        page.wait_for_timeout(1000)
        aroused_before = page.evaluate("() => (window.patchWorld.describe?.arousal?.modes?.aroused) ?? null")
        # the season turns
        page.click("#flip")
        page.wait_for_function("() => window.patchWorld.snapshot && !window.patchWorld.snapshot.summer", timeout=20000)
        flip_t = page.evaluate(READ)["t"]
        page.wait_for_function(f"() => window.patchWorld.snapshot.t >= {flip_t + args.moments}",
                               timeout=args.moments * 2000)
        after = page.evaluate(READ)
        aroused = page.evaluate("""async () => { const s = window.patchWorld; let n = 0, m = 0;
          for (const [id, r] of s.details) { n += 1; if (r.mode === 'aroused') m += 1; } return { n, m }; }""")
        lives = after["kinds"].get("live", 0)
        winter_events = [h for h in after["history"] if not h["summer"]]
        poisoned = sum(((h.get("events") or {}).get("live") or {}).get("poisoned", 0) for h in winter_events)
        check("creatures keep living through the flip", lives > 0 and not after["summer"],
              moments=after["t"], creatures=after["kinds"], tally=after["tally"])
        page.wait_for_timeout(1000)
        alive = page.evaluate("() => window.patchWorld.cur.has(window.patchWorld.selected)")
        aroused_after = page.evaluate("() => (window.patchWorld.describe?.arousal?.modes?.aroused) ?? null")
        levels = page.evaluate("() => window.patchWorld.levels.map(l => l.mode)")
        learned = alive and aroused_before is not None and aroused_after is not None and aroused_after > aroused_before
        check("the inspected learner learns after the flip (its aroused, learning moments grow)",
              learned or not alive, alive=alive, aroused_before=aroused_before, aroused_after=aroused_after,
              aroused_in_last_160=levels.count("aroused"), learner_winter_poisonings=poisoned)
        page.evaluate("() => document.getElementById('world').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(300)
        page.click('[data-tool="berry"]')
        page.mouse.click(*page.evaluate("() => { const r = document.getElementById('world').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }"))
        page.click('[data-tool="predator"]')
        page.mouse.click(*page.evaluate("() => { const r = document.getElementById('world').getBoundingClientRect(); return [r.left + r.width / 3, r.top + r.height / 3]; }"))
        page.wait_for_timeout(1500)
        preds = page.evaluate("() => window.patchWorld.snapshot.predators.length")
        check("visitor tools: drop berries, add a predator", preds >= 2, predators=preds)
        page.click('[data-tool="predator"]')
        page.wait_for_timeout(3000)
        page.screenshot(path=str(args.shots / "winter.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(800)
        scroll = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        check("phone width: no horizontal scroll", scroll <= 0, overflow=scroll)
        browser.close()
    if server:
        server.shutdown()
    errors = ev["console_errors"] + ev["page_errors"] + ev["request_failures"] + ev["http_errors"]
    check("no console errors, page errors or failed requests", not errors, errors=errors[:10])
    ev["passed"] = all(c["ok"] for c in ev["checks"])
    (args.out / "page-check.json").write_text(json.dumps(ev, indent=1, default=str) + "\n")
    print("passed" if ev["passed"] else "FAILED")
    return 0 if ev["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
