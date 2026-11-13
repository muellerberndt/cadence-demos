"""The page's promise, tried end to end in a headless browser; run it before every deploy.

    .venv/bin/python check_page.py [--chrome PATH] [--receipt evidence/page_check-DATE.txt] [--hardware]

The promise: one Cadence brain runs in the page and follows every shape with its own eye,
seeing only the page's pixels; when nothing moves, the brain rests and does no settling; a
shape dragged away is found again by its eye, and the brain works only for that move. The
script serves ``web/``, opens it in a headless Chrome with a throwaway profile, and checks in
order: the brain loads in Pyodide; six eyes answer; while all shapes move, most eyes stay on
their own shapes (and the brain's sweeps and time per frame are read); with the shapes held,
every frame for three seconds costs zero sweeps; a shape dragged 20 px in 150 ms is centred in
its eye again (the eye's jumps after the release are counted); then every frame for three
seconds costs zero sweeps again; no console errors. Exit status 1 on any failure.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import os
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


async def check(chrome: str, url: str, lines: list[str], hardware: bool = False) -> bool:
    say = lambda text: (lines.append(text), print(text, flush=True))  # noqa: E731
    port = free_port()
    profile = tempfile.mkdtemp(prefix="cadence-eyes-check-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
                             f"--remote-debugging-port={port}", "--window-size=1600,1100",
                             *(["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] if hardware
                               else ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]), "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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
                moving = json.loads(await ev("JSON.stringify(window.cadenceEyes.gazes.slice(-60))"))
                if moving:
                    sweeps = [g["sweeps"] for g in moving]
                    work = [g for g in moving if g["sweeps"] > 0]
                    say(f"      moving: {len(work)} of the last {len(moving)} frames settled, {sum(sweeps) / len(sweeps):.1f} sweeps "
                        f"and {sum(g['ms'] for g in moving) / len(moving):.0f} ms per frame on average")

                async def at_rest(what):
                    """Every frame of three seconds of a motionless scene costs zero sweeps."""
                    nonlocal passed
                    t0 = await ev("performance.now()")
                    await asyncio.sleep(3.0)
                    rest = json.loads(await ev(f"JSON.stringify(window.cadenceEyes.gazes.filter((g) => g.t > {t0}))"))
                    ok = len(rest) >= 5 and all(g["sweeps"] == 0 for g in rest)
                    passed &= ok
                    ms = sum(g["ms"] for g in rest) / max(len(rest), 1)
                    say(f"{'ok   ' if ok else 'FAIL '} {what}: {sum(g['sweeps'] == 0 for g in rest)} of {len(rest)} frames "
                        f"in 3 s at zero sweeps, {ms:.1f} ms per frame")

                await ev("document.getElementById('animate').checked = false")
                await until("document.getElementById('state').textContent === 'at rest: no work' ? document.getElementById('ms').textContent + ' ms per frame' : null",
                            "with the shapes held, the brain comes to rest", 120)
                await at_rest("nothing moves, the brain does no work")
                box = json.loads(await ev("JSON.stringify(document.getElementById('surface').getBoundingClientRect())"))
                t = json.loads(await ev("JSON.stringify(window.cadenceEyes.things.find((t) => t.eye))"))
                k = box["width"] / 160
                x0, y0 = box["x"] + t["x"] * k, box["y"] + t["y"] * k
                await mouse("mouseMoved", x0, y0)
                await mouse("mousePressed", x0, y0, 1, "left", 1)
                for s in range(1, 4):
                    await mouse("mouseMoved", x0 + s * 6.0 * k, y0 + s * 3.0 * k, 1, "left")
                    await asyncio.sleep(0.05)
                released = await ev("performance.now()")
                await mouse("mouseReleased", x0 + 18 * k, y0 + 9 * k, 0, "left", 1)
                moved = json.loads(await ev(f"JSON.stringify(window.cadenceEyes.things.find((s) => s.id === {t['id']}))"))
                say(f"      dragged the {t['kind']} from ({t['x']:.1f}, {t['y']:.1f}) to ({moved['x']:.1f}, {moved['y']:.1f}) in 150 ms")
                await until(f"(() => {{ const r = window.cadenceEyes.result; const e = r && r.eyes.find((e) => e.id === {t['id']}); "
                            f"if (!e || !e.own) return null; const d = Math.hypot(e.gaze[0] - {moved['x']}, e.gaze[1] - {moved['y']}); "
                            f"return d <= 4 ? 'its eye is centred on it, ' + d.toFixed(1) + ' px away' : null; }})()",
                            "the dragged shape is found again", 30)
                after = json.loads(await ev(f"JSON.stringify(window.cadenceEyes.gazes.filter((g) => g.t > {released}))"))
                track = [next((e for e in g["eyes"] if e[0] == t["id"]), None) for g in after]
                jumps, centred_at, last = 0, None, None
                for g, e in zip(after, track):
                    if e is None:
                        continue
                    if last is not None and (abs(e[1] - last[1]) > 0.01 or abs(e[2] - last[2]) > 0.01):
                        jumps += 1
                    last = e
                    if centred_at is None and ((e[1] - moved["x"]) ** 2 + (e[2] - moved["y"]) ** 2) ** 0.5 <= 4 and e[3]:
                        centred_at = jumps
                work = [g["sweeps"] for g in after if g["sweeps"] > 0]
                say(f"      after the release the eye jumped {centred_at if centred_at is not None else jumps} time(s) to centre its shape; "
                    f"{len(work)} frame(s) settled, up to {max(work) if work else 0} sweeps")
                await at_rest("the shape found, the brain rests again")
                ok = not errors
                passed &= ok
                say(f"{'ok   ' if ok else 'FAIL '} console errors: {len(errors)}")
                for e in errors[:3]:
                    say("      " + e)
    finally:
        try:  # the browser and every helper it started (they share its new session's process group)
            os.killpg(proc.pid, 15)
        except OSError:
            proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
    return passed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--chrome", default=None)
    p.add_argument("--receipt", default=None)
    p.add_argument("--hardware", action="store_true", help="draw the brain view with the GPU instead of SwiftShader (a busy machine)")
    a = p.parse_args()
    chrome = a.chrome or next((c for c in CHROMES if shutil.which(c) or Path(c).exists()), None)
    if chrome is None:
        sys.exit("no Chrome found; pass --chrome")
    port = free_port()
    handler = functools.partial(Quiet, directory=str(HERE / "web"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    lines = [f"check_page.py, {time.strftime('%Y-%m-%d %H:%M')}, renderer {'GPU (Metal)' if a.hardware else 'SwiftShader'}, "
             f"load average {' '.join(f'{v:.0f}' for v in os.getloadavg())}"]
    try:
        passed = asyncio.run(asyncio.wait_for(check(chrome, f"http://127.0.0.1:{port}/", lines, a.hardware), 900))
    finally:
        server.shutdown()
    lines.append("PASS" if passed else "FAIL")
    print(lines[-1])
    if a.receipt:
        Path(a.receipt).write_text("\n".join(lines) + "\n")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
