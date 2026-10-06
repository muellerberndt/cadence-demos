"""The page's promise, tried end to end in a headless browser; run it before every deploy.

    .venv/bin/python check_page.py [--chrome PATH] [--receipt evidence/page_check.txt]

The promise: one continuing Cadence creature lives in the page, in Pyodide, and arrives fed and
calm; it is fed on most trips while the key stays in the chest and answers from routine
settles; when the key is moved to the lamp it is fed again on most trips within 150 trips,
whether it took the lamp at once or starved, was roused and searched (the check reports which);
a saved brain restored mid-trip continues; no console errors. The script serves ``web/``, opens it in a headless Chrome with a throwaway
profile, drives the page through the worker's own messages, and prints what it read. Exit
status 1 on any failure.
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
    profile = tempfile.mkdtemp(prefix="cadence-keydoor-check-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
                             f"--remote-debugging-port={port}", "--window-size=1500,1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            async with http_.get(f"http://127.0.0.1:{port}/json/new?{url}", ) as r:
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
                ready = await js("document.getElementById('loading').textContent === 'ready' ? 'ready' : "
                                 "(document.getElementById('loading').className.includes('failed') ? "
                                 "document.getElementById('loading').textContent : null)")
                if ready != "ready":
                    say(f"FAIL the page did not load the creature: {ready}")
                    return False
                say(f"ok   the creature loaded in Pyodide after {time.time() - t0:.0f} s")
                brain = await js("document.getElementById('brainname').textContent")
                say(f"     {brain}")
                # pause the page's own loop and drive the host directly through the module
                await js("(async () => { window.__kd = await import('./keydoor.js'); return 'ok'; })()")
                await js("(() => { document.getElementById('pause').click(); return 'ok'; })()")
                await asyncio.sleep(1.0)
                run = await js("window.__kd.drive({op: 'run', trips: 40})", timeout=600)
                recent = run["recent"]
                say(f"ok   40 trips with the key in the chest in {run['worker_ms']:.0f} ms: fed {recent['fed']:.2f} of the "
                    f"last 20, {recent['wrong']:.2f} wrong per trip, aroused {run['work']['aroused_share'] * 100:.0f}% of the moments")
                if recent["fed"] < 0.8:
                    say("FAIL the raised creature is not fed on most trips")
                    passed = False
                if run["work"]["aroused_share"] > 0.3:
                    say("FAIL the raised creature is not calm while fed")
                    passed = False
                moved = await js("window.__kd.drive({op: 'move_key'})")
                say(f"ok   the key moved to cell {moved['keyed']} (the lamp)")
                after = await js("window.__kd.drive({op: 'run', trips: 10})", timeout=600)
                first = [r for r in after["rows"] if not r["cut"]]
                say(f"ok   the first 10 trips after the move: fed on {sum(r['fed'] for r in first)} of {len(first)}, "
                    f"want up to {max(r['want'] for r in after['rows']):.2f}, aroused "
                    f"{sum(r['aroused'] for r in after['rows']) / len(after['rows']) * 100:.0f}% of the moments, "
                    f"{sum(r['wrongs'] for r in after['rows'])} wrong interactions")
                later = await js("window.__kd.drive({op: 'run', trips: 150})", timeout=1200)
                rec = later["recent"]
                rows = after["rows"] + later["rows"]
                fed_last = [r["fed"] for r in later["rows"] if not r["cut"]][-20:]
                found = next((i for i in range(len(rows) - 19) if sum(r["fed"] for r in rows[i:i + 20]) >= 18), None)
                say(f"ok   160 trips after the move: fed {rec['fed']:.2f} of the last 20, {rec['wrong']:.2f} wrong per "
                    f"trip, mode {later['mode']}, aroused {sum(r['aroused'] for r in later['rows'][-20:]) / 20 * 100:.0f}% of "
                    f"the last 20 trips' moments; the first 20-trip window at 90% fed began "
                    f"{'at trip ' + str(found + 1) + ' after the move' if found is not None else 'never'}")
                if sum(fed_last) / max(1, len(fed_last)) < 0.8:
                    say("FAIL the creature did not find the moved key within 160 trips")
                    passed = False
                snap = await js("window.__kd.drive({op: 'snapshot'})")
                a = await js("window.__kd.drive({op: 'run', trips: 2})", timeout=600)
                restored = await js(f"window.__kd.drive({{op: 'restore', brain: {json.dumps(snap['brain'])}}})")
                say(f"ok   saved and restored the brain ({len(snap['brain']) // 1024} KB); it continues at trip {restored['trips']}")
                if not restored.get("restored"):
                    say("FAIL the restore did not report")
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
    lines = [f"cadence key door page check, {time.strftime('%Y-%m-%d %H:%M')}"]
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
