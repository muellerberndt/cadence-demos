"""The page's promise, tried end to end in a headless browser; run it before every deploy.

    .venv/bin/python check_page.py [--chrome PATH] [--receipt evidence/page_check.txt]

The promise: one Cadence brain runs in the page and follows every shape with its own eye,
seeing only the page's pixels; a shape dragged away fast is found again; when nothing moves,
the brain does no settling. The script serves ``web/``, opens it in a headless Chrome with a
throwaway profile, and checks in order: the brain loads in Pyodide; six eyes answer; while all
shapes move, most eyes stay on their own shapes; a still world costs zero sweeps; a shape
dragged 20 px in 150 ms is centred in its eye again; no console errors. Exit status 1 on any
failure.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome",
           "google-chrome-stable", "chromium", "chromium-browser"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def check(chrome: str, url: str, lines: list[str]) -> bool:
    say = lambda text: (lines.append(text), print(text, flush=True))  # noqa: E731
    port = free_port()
    profile = tempfile.mkdtemp(prefix="cadence-eyes-check-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
                             f"--remote-debugging-port={port}", "--window-size=1600,1100",
                             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    passed = True
    try:
        async with aiohttp.ClientSession() as http_:
            for _ in range(240):
                try:
                    async with http_.get(f"http://127.0.0.1:{port}/json") as r:
                        tabs = await r.json()
                        break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.25)
            page = next(t for t in tabs if t["type"] == "page")
            async with http_.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=64 << 20) as ws:
                seq, errors = 0, []

                async def call(method, **params):
                    nonlocal seq
                    seq += 1
                    my = seq
                    await ws.send_str(json.dumps({"id": my, "method": method, "params": params}))
                    while True:
                        msg = json.loads((await asyncio.wait_for(ws.receive(), 300)).data)
                        if msg.get("method") == "Runtime.exceptionThrown" or (
                                msg.get("method") == "Runtime.consoleAPICalled"
                                and msg["params"].get("type") == "error"):
                            errors.append(json.dumps(msg["params"])[:300])
                        if msg.get("id") == my:
                            return msg.get("result", {})

                async def ev(expr):
                    r = await call("Runtime.evaluate", expression=expr, returnByValue=True)
                    return r.get("result", {}).get("value")

                async def until(expr, what, limit):
                    nonlocal passed
                    t0 = time.monotonic()
                    while time.monotonic() - t0 < limit:
                        v = await ev(expr)
                        if v:
                            say(f"ok    {what} ({time.monotonic() - t0:.1f} s): {v}")
                            return v
                        await asyncio.sleep(0.5)
                    say(f"FAIL  {what}: not within {limit} s")
                    passed = False
                    return None

                async def mouse(kind, x, y, buttons=0, button="none", clicks=0):
                    await call("Input.dispatchMouseEvent", type=kind, x=x, y=y, buttons=buttons,
                               button=button, clickCount=clicks)

                await call("Runtime.enable")
                await call("Page.navigate", url=url)
                if not await until("document.getElementById('loading').textContent === 'brain ready' ? 'ready' : null",
                                   "the brain loads in Pyodide", 300):
                    say("      " + str(await ev("document.getElementById('loading').textContent")))
                    return False
                say("      " + str(await ev("document.getElementById('brainname').textContent")))
                await until("document.getElementById('own').textContent.includes('of 6') ? document.getElementById('own').textContent : null",
                            "six eyes answer", 120)
                samples = []
                for _ in range(30):
                    text = await ev("document.getElementById('own').textContent") or ""
                    if " of " in text:
                        samples.append(int(text.split(" of ")[0]))
                    await asyncio.sleep(0.5)
                mean = sum(samples) / max(len(samples), 1)
                ok = len(samples) >= 10 and mean >= 4.5
                passed &= ok
                say(f"{'ok   ' if ok else 'FAIL '} while every shape moves, eyes on their own shape: {mean:.2f} of 6 "
                    f"on average over {len(samples)} samples (needs 4.5)")
                await ev("document.getElementById('animate').checked = false")
                await until("document.getElementById('state').textContent === 'equilibrium: no work' ? document.getElementById('ms').textContent + ' ms per frame' : null",
                            "a still world costs zero sweeps", 120)
                box = json.loads(await ev("JSON.stringify(document.getElementById('surface').getBoundingClientRect())"))
                t = json.loads(await ev("JSON.stringify(window.cadenceEyes.things.find((t) => t.eye))"))
                k = box["width"] / 160
                x0, y0 = box["x"] + t["x"] * k, box["y"] + t["y"] * k
                await mouse("mouseMoved", x0, y0)
                await mouse("mousePressed", x0, y0, 1, "left", 1)
                for s in range(1, 4):
                    await mouse("mouseMoved", x0 + s * 6.0 * k, y0 + s * 3.0 * k, 1, "left")
                    await asyncio.sleep(0.05)
                await mouse("mouseReleased", x0 + 18 * k, y0 + 9 * k, 0, "left", 1)
                moved = json.loads(await ev(f"JSON.stringify(window.cadenceEyes.things.find((s) => s.id === {t['id']}))"))
                say(f"      dragged the {t['kind']} from ({t['x']:.1f}, {t['y']:.1f}) to ({moved['x']:.1f}, {moved['y']:.1f}) in 150 ms")
                await until(f"(() => {{ const r = window.cadenceEyes.result; const e = r && r.eyes.find((e) => e.id === {t['id']}); "
                            f"if (!e || !e.own) return null; const d = Math.hypot(e.gaze[0] - {moved['x']}, e.gaze[1] - {moved['y']}); "
                            f"return d <= 4 ? 'its eye is centred on it, ' + d.toFixed(1) + ' px away' : null; }})()",
                            "the dragged shape is found again", 30)
                ok = not errors
                passed &= ok
                say(f"{'ok   ' if ok else 'FAIL '} console errors: {len(errors)}")
                for e in errors[:3]:
                    say("      " + e)
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
    return passed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--chrome", default=None)
    p.add_argument("--receipt", default=None)
    a = p.parse_args()
    chrome = a.chrome or next((c for c in CHROMES if shutil.which(c) or Path(c).exists()), None)
    if chrome is None:
        sys.exit("no Chrome found; pass --chrome")
    port = free_port()
    handler = functools.partial(Quiet, directory=str(HERE / "web"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    lines = [f"check_page.py, {time.strftime('%Y-%m-%d %H:%M')}"]
    try:
        passed = asyncio.run(asyncio.wait_for(check(chrome, f"http://127.0.0.1:{port}/", lines), 900))
    finally:
        server.shutdown()
    lines.append("PASS" if passed else "FAIL")
    print(lines[-1])
    if a.receipt:
        Path(a.receipt).write_text("\n".join(lines) + "\n")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
