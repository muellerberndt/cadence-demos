"""The player page's brain-alone recording, tried end to end in a headless Chromium: it loads,
plays, stays on the decision the video shows (after playing, a seek, a pause and a speed change),
and live mode settles the brain on the recorded inputs and chooses the recorded buttons. Frame
time with the brain view on is measured. The page is served from player/ by itself, as the demos
site serves it. Writes player/evidence/player_check.json (or --out).

    python player/check_player.py --live 40
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import statistics
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with HTTP Range requests, as a static host serves them (a browser seeks a
    video with byte ranges; Python's plain handler answers every request with the whole file)."""

    def log_message(self, *a, **k):
        pass

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not rng.startswith("bytes=") or not Path(path).is_file():
            return super().send_head()
        size = Path(path).stat().st_size
        a, _, b = rng[6:].partition("-")
        start = int(a) if a else max(0, size - int(b))
        end = min(size - 1, int(b)) if (a and b) else size - 1
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_remaining", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(65536, left))
            if not chunk:
                break
            try:
                outputfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            left -= len(chunk)
        self._remaining = None


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(RangeHandler, directory=str(HERE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", type=int, default=40, help="decisions live mode must settle and compare")
    p.add_argument("--live-timeout", type=float, default=900)
    p.add_argument("--screenshot", type=Path, default=ROOT / "docs" / "player.png")
    p.add_argument("--only-live", action="store_true", help="skip the recorded-mode checks")
    p.add_argument("--out", type=Path, default=HERE / "evidence" / "player_check.json")
    a = p.parse_args()
    from playwright.sync_api import sync_playwright
    server, port = serve()
    url = f"http://127.0.0.1:{port}/index.html?rec=alone"
    report = {"url": "player/index.html?rec=alone", "checks": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1500, "height": 960})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_function("window.__player && window.__player.ready === true", timeout=60000)
        page.wait_for_function("document.getElementById('video').readyState >= 2", timeout=60000)

        def sync_state():
            return page.evaluate("""() => { const s = window.__player, v = document.getElementById('video');
                return {time: v.currentTime, frame: s.frame, decision: s.decision, shown: s.shown,
                        expected: Math.floor(v.currentTime * 60 / 12)}; }""")

        def in_step(s):  # the decision shown is the one the video is on (one frame of slack)
            return s["shown"] == s["decision"] and abs(s["decision"] - s["expected"]) <= 1

        page.evaluate("document.getElementById('video').play()")
        page.wait_for_timeout(4000)
        s = sync_state()
        report["checks"]["plays"] = {"ok": s["time"] > 2 and in_step(s), **s}
        page.evaluate("document.getElementById('video').currentTime = 150")
        page.wait_for_timeout(1500)
        s = sync_state()
        report["checks"]["seek_150s"] = {"ok": abs(s["time"] - 150) < 3 and in_step(s), **s}
        page.evaluate("document.getElementById('video').pause()")
        page.wait_for_timeout(800)
        s1 = sync_state(); page.wait_for_timeout(800); s2 = sync_state()
        report["checks"]["pause"] = {"ok": s1["frame"] == s2["frame"] and in_step(s2), **s2}
        page.evaluate("const v = document.getElementById('video'); v.playbackRate = 2; v.play()")
        page.wait_for_timeout(3000)
        s = sync_state()
        report["checks"]["speed_2x"] = {"ok": in_step(s), **s}
        page.evaluate("window.__player.frameTimes.length = 0")
        page.wait_for_timeout(3000)
        times = page.evaluate("window.__player.frameTimes.slice()")
        report["frame_ms"] = {"median": round(statistics.median(times), 2), "p95": round(sorted(times)[int(0.95 * len(times))], 2),
                              "samples": len(times)}
        if a.screenshot:
            page.evaluate("const v = document.getElementById('video'); v.pause(); v.playbackRate = 1; v.currentTime = 151.3")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(a.screenshot), full_page=True)
        if a.live:
            page.evaluate("const v = document.getElementById('video'); v.pause(); v.currentTime = 0")
            page.wait_for_timeout(500)
            page.click("#live")
            t0 = time.time()
            try:
                page.wait_for_function("window.__player.live.ready === true || document.getElementById('live-status').textContent.startsWith('live mode stopped')",
                                       timeout=a.live_timeout * 1000)
            except Exception:
                pass
            report["live_status_at_ready"] = page.inner_text("#live-status")
            if not page.evaluate("window.__player.live.ready"):
                report["checks"]["live_matches"] = {"ok": False, "status": report["live_status_at_ready"]}
                a.live = 0
            report["live_load_seconds"] = round(time.time() - t0, 1)
        if a.live:
            # play at 1x and let live mode follow: it settles in order from the start
            page.evaluate("document.getElementById('video').play()")
            t1 = time.time()
            page.wait_for_function(f"window.__player.live.checked >= {a.live}", timeout=a.live_timeout * 1000)
            L = page.evaluate("""() => { const L = window.__player.live;
                return {checked: L.checked, matches: L.matches, ms: L.ms.slice(),
                        mismatched: [...L.results.entries()].filter(([k, r]) => !r.same).map(([k]) => k)}; }""")
            report["live"] = {"decisions": L["checked"], "matches": L["matches"], "mismatched": L["mismatched"][:20],
                              "ms_per_decision_median": round(statistics.median(L["ms"]), 1) if L["ms"] else None,
                              "seconds": round(time.time() - t1, 1),
                              "real_time_needs_ms": 200}
            report["checks"]["live_matches"] = {"ok": L["matches"] == L["checked"], "matches": L["matches"], "of": L["checked"]}
        report["page_errors"] = errors
        browser.close()
    server.shutdown()
    report["ok"] = all(c["ok"] for c in report["checks"].values()) and not report["page_errors"]
    out = a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
