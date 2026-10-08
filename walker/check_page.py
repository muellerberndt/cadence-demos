"""The page's promise, tried end to end in a headless browser; run it before every deploy.

    .venv/bin/python walker/check_page.py [--chrome PATH] [--receipt walker/evidence/page_check.txt]

The promise: two Cadence brains born in the page learn, from the world's pay alone, to
alternate their feet; the one that carries a copy of its own last step finds the beat and
walks it calmly, the one without does not, and a coin stays at half. The script serves
``web/``, opens it in a headless Chrome with a throwaway profile, and checks in order: the
walkers load in Pyodide; after 300 moments the first walker's beat over its last 50 steps is
at least 0.9 and it is calm, the second's is below 0.75 and the coin's within 0.3 to 0.7;
erasing the first walker's copy costs it at most two steps; three frozen moments cost it at
most two; no console errors. Exit status 1 on any failure.
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
CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


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
    profile = tempfile.mkdtemp(prefix="cadence-walker-check-")
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
         f"--remote-debugging-port={port}", "--window-size=1500,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    passed = True
    try:
        async with aiohttp.ClientSession() as http_:
            for _ in range(240):
                try:
                    async with http_.get(f"http://127.0.0.1:{port}/json/version") as r:
                        await r.json()
                    break
                except Exception:
                    await asyncio.sleep(0.25)
            async with http_.get(f"http://127.0.0.1:{port}/json/new?{url}"):
                pass
            async with http_.get(f"http://127.0.0.1:{port}/json") as r:
                tabs = await r.json()
            tab = next(t for t in tabs if t.get("url", "").startswith(url) or t.get("type") == "page")
            async with http_.ws_connect(tab["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                seq = 0
                errors: list[str] = []

                async def send(method: str, **params):
                    nonlocal seq
                    seq += 1
                    await ws.send_json({"id": seq, "method": method, "params": params})
                    while True:
                        m = await ws.receive_json()
                        if m.get("method") == "Runtime.exceptionThrown":
                            errors.append(json.dumps(m["params"]["exceptionDetails"])[:300])
                        if m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] == "error":
                            errors.append(json.dumps(m["params"]["args"])[:300])
                        if m.get("id") == seq:
                            return m.get("result", {})

                async def js(expr: str, timeout: float = 300.0):
                    deadline = time.time() + timeout
                    while True:
                        r = await send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
                        if "result" in r and r["result"].get("value") is not None:
                            return r["result"]["value"]
                        if "exceptionDetails" in r:
                            raise RuntimeError(json.dumps(r["exceptionDetails"])[:300])
                        if time.time() > deadline:
                            raise TimeoutError(expr[:60])
                        await asyncio.sleep(0.5)

                await send("Runtime.enable")
                await send("Page.enable")
                await send("Page.navigate", url=url)
                t0 = time.time()
                ready = await js(
                    "document.getElementById('loading').textContent === 'ready' ? 'ready' : "
                    "(document.getElementById('loading').className.includes('failed') ? "
                    "document.getElementById('loading').textContent : null)"
                )
                if ready != "ready":
                    say(f"FAIL the page did not load the walkers: {ready}")
                    return False
                say(f"ok   the walkers loaded in Pyodide after {time.time() - t0:.0f} s")
                say("     " + await js("document.getElementById('brainname').textContent"))
                await js("(async () => { window.__walk = await import('./walker.js'); return 'ok'; })()")
                await js("window.__walk.drive({op: 'pause'}).then(() => 'ok')")
                run = await js("window.__walk.drive({op: 'run', moments: 300})", timeout=900)
                copy, bare, coin = run["copy"], run["bare"], run["random"]
                work = copy["status"]["work"]
                say(f"ok   300 moments: the first walker's beat over its last 50 steps is {copy['beat50']:.2f} "
                    f"(found the beat at moment {copy['found']}), aroused in {work['aroused_recent'] * 100:.0f}% of "
                    f"its last 50 moments, {work['ms_per_moment']:.1f} ms per moment in the worker; the second's "
                    f"beat is {bare['beat50']:.2f} (aroused {bare['status']['work']['aroused_recent'] * 100:.0f}%); "
                    f"the coin's is {coin['beat50']:.2f}; steps forward {copy['position']} / {bare['position']} / "
                    f"{coin['position']}")
                if copy["beat50"] < 0.9:
                    say("FAIL the walker with the copy did not find the beat")
                    passed = False
                if work["aroused_recent"] > 0.1:
                    say("FAIL the walker with the copy is not calm on its beat")
                    passed = False
                if bare["beat50"] >= 0.75:
                    say("FAIL the walker without the copy found a beat it cannot carry")
                    passed = False
                if not 0.3 <= coin["beat50"] <= 0.7:
                    say("FAIL the coin is not a coin")
                    passed = False
                if work["refusals"]:
                    say(f"FAIL {work['refusals']} refused answers")
                    passed = False
                forgot = await js("window.__walk.drive({op: 'forget'})")
                after = await js("window.__walk.drive({op: 'run', moments: 20})", timeout=600)
                lost = round((1 - after["copy"]["beat20"]) * 19)
                say(f"ok   the copy erased at moment {forgot['moment']}: the next 20 steps changed foot "
                    f"{after['copy']['beat20']:.2f} of the time ({lost} stumbles)")
                if lost > 2:
                    say("FAIL erasing the copy cost more than two steps")
                    passed = False
                await js("window.__walk.drive({op: 'queue', kinds: [1, 1, 1]})")
                frozen = await js("window.__walk.drive({op: 'run', moments: 3, kind: 1})", timeout=600)
                after = await js("window.__walk.drive({op: 'run', moments: 20})", timeout=600)
                lost = round((1 - after["copy"]["beat20"]) * 19)
                say(f"ok   the floor frozen for three moments (beat through them {frozen['copy']['beat20']:.2f}): "
                    f"the next 20 steps changed foot {after['copy']['beat20']:.2f} of the time ({lost} stumbles)")
                if lost > 2:
                    say("FAIL the frozen floor cost more than two steps")
                    passed = False
                if errors:
                    say(f"FAIL {len(errors)} console errors: {errors[0]}")
                    passed = False
                else:
                    say("ok   no console errors")
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
    return passed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--chrome", default=None)
    p.add_argument("--receipt", default=None)
    a = p.parse_args()
    chrome = a.chrome or next((c for c in CHROMES if shutil.which(c) or Path(c).exists()), None)
    if not chrome:
        print("no Chrome found; pass --chrome", file=sys.stderr)
        return 2
    port = free_port()
    handler = functools.partial(Quiet, directory=str(HERE / "web"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    lines = [f"cadence walkers page check, {time.strftime('%Y-%m-%d %H:%M')}"]
    try:
        passed = asyncio.run(check(chrome, f"http://127.0.0.1:{port}/", lines))
    finally:
        server.shutdown()
    lines.append("PASSED" if passed else "FAILED")
    print(lines[-1])
    if a.receipt:
        Path(a.receipt).write_text("\n".join(lines) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
