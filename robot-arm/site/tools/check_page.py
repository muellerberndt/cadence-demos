"""The page's promise in headless Chromium (Playwright): the brain loads in Pyodide, places the
block in the lit bin, and follows the target bin when it is moved while the arm carries the block.

    python site/tools/check_page.py                       # from robot-arm/
    python site/tools/check_page.py --shot docs/robot-arm.png

Serves ``site/`` on a free port, runs two trials and writes ``evidence/page_check.json``:
1. target A, the block where the page puts it, run at 4x: the result line names bin A;
2. target B, run; once the hand holds the block, bin B is moved to (0.66, -0.12) m, inside the
   band the brain was tested in: the result line names bin B and the block lies in the moved bin.
With ``--shot`` it saves a 1280x800 screenshot taken while the arm carries the block.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socket
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1]
ARM = SITE.parent
MOVED_B = (0.66, -0.12)


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def wait_result(page, timeout_s: float) -> str:
    page.wait_for_function("document.body.dataset.result && document.body.dataset.result !== 'still'",
                           timeout=timeout_s * 1000)
    return page.evaluate("document.body.dataset.result")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--shot", default=None, help="save a screenshot while the arm carries the block")
    p.add_argument("--timeout", type=float, default=600.0)
    a = p.parse_args()
    server, port = serve()
    checks: list[dict] = []
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            try:  # Playwright's own Chromium, else the installed Google Chrome
                browser = pw.chromium.launch(args=["--enable-unsafe-swiftshader"])
            except Exception:
                browser = pw.chromium.launch(channel="chrome", args=["--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            began = time.time()
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_function("document.body.dataset.ready === '1'", timeout=a.timeout * 1000)
            load_s = time.time() - began
            manifest = json.loads((SITE / "pack" / "manifest.json").read_text())
            checks.append({"name": "the brain loads in Pyodide", "passed": True,
                           "seconds": round(load_s, 1), "cadence": manifest["cadence"]})

            # 1. bin A, untouched
            page.evaluate("window.cadenceArm.setTarget('A'); window.cadenceArm.state.speed = 4;"
                          " window.cadenceArm.run()")
            result = wait_result(page, a.timeout)
            decisions = int(page.evaluate("document.body.dataset.decisions"))
            ms = page.evaluate("(window.cadenceArm.state.thinkMs || []).slice()")
            frames = page.evaluate("(window.cadenceArm.state.frames || []).slice()")
            checks.append({"name": "places the block in bin A", "passed": result.startswith("Placed in bin A"),
                           "result": result, "decisions": decisions,
                           "brain_ms_median": sorted(ms)[len(ms) // 2] if ms else None})
            waved = sorted(f[0] for f in frames if f[1]); plain = sorted(f[0] for f in frames if not f[1])
            checks.append({"name": "the settle plays as a wave", "passed": len(waved) >= decisions // 3,
                           "wave_decisions": len(waved), "decisions": len(frames),
                           "worker_ms_median_wave": waved[len(waved) // 2] if waved else None,
                           "worker_ms_median_plain": plain[len(plain) // 2] if plain else None})

            # 2. bin B, moved while the arm carries the block
            page.evaluate("window.cadenceArm.state.thinkMs = []; document.body.dataset.result = '';"
                          " window.cadenceArm.setTarget('B'); window.cadenceArm.run()")
            page.wait_for_function("window.cadenceArm.cell.holding === true", timeout=a.timeout * 1000)
            page.evaluate(f"window.cadenceArm.cell.moveBin('B', {MOVED_B[0]}, {MOVED_B[1]})")
            if a.shot:
                page.wait_for_timeout(1500)
                out = ARM / a.shot
                out.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out))
            result = wait_result(page, a.timeout)
            block = page.evaluate("Array.from(window.cadenceArm.cell.blockPos())")
            bin_b = page.evaluate("window.cadenceArm.cell.bins['B']")
            inside = abs(block[0] - bin_b[0]) < 0.06 and abs(block[1] - bin_b[1]) < 0.06
            checks.append({"name": "follows bin B moved mid-carry",
                           "passed": result.startswith("Placed in bin B") and inside,
                           "result": result, "moved_to": list(MOVED_B), "bin_b": bin_b,
                           "block": [round(v, 3) for v in block]})

            # 3. smooth motion at the visitor's speed: the arm on screen keeps moving while the
            # brain settles (the share of arm time shown against the clock's)
            page.evaluate("document.body.dataset.result = ''; window.cadenceArm.state.frames = [];"
                          " window.cadenceArm.play.expected = 0; window.cadenceArm.play.shown = 0;"
                          " window.cadenceArm.setTarget('A'); window.cadenceArm.state.speed = 1;"
                          " window.cadenceArm.run()")
            result = wait_result(page, a.timeout)
            shown = page.evaluate("window.cadenceArm.play.shown / Math.max(1e-9, window.cadenceArm.play.expected)")
            frames = page.evaluate("(window.cadenceArm.state.frames || []).slice()")
            worker = [f[0] for f in frames]
            decisions = len(worker)
            # the page before the playback buffer stood still for every worker call
            before = sum(worker) / (sum(worker) + 200.0 * decisions) if decisions else None
            checks.append({"name": "the arm moves smoothly at 1x", "passed": shown >= 0.98 and result.startswith("Placed in bin A"),
                           "result": result, "arm_time_shown_share": round(shown, 4),
                           "still_share_without_buffer": None if before is None else round(before, 4),
                           "worker_ms_mean": round(sum(worker) / decisions, 1) if decisions else None})
            browser.close()
    finally:
        server.shutdown()
    # Emscripten's loader reports on console.error while the WebAssembly instantiates slowly
    # ("still waiting on run dependencies"); those lines are progress, not failures.
    loader = ("still waiting on run dependencies", "dependency: ", "(end of list)")
    real = [e for e in errors if not e.startswith(loader)]
    checks.append({"name": "console errors", "passed": not real, "errors": real[:5],
                   "loader_progress_lines": len(errors) - len(real)})
    report = {"schema": "cadence-arm-page-check/1", "checked": time.strftime("%Y-%m-%d %H:%M"),
              "checks": checks, "passed": all(c["passed"] for c in checks)}
    (ARM / "evidence" / "page_check.json").write_text(json.dumps(report, indent=1) + "\n")
    for c in checks:
        print(("ok    " if c["passed"] else "FAIL  ") + c["name"], json.dumps({k: v for k, v in c.items()
                                                                     if k not in ("name", "passed")}))
    print("PASS" if report["passed"] else "FAIL")


if __name__ == "__main__":
    main()
