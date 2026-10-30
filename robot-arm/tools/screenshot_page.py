"""A screenshot of the page after the caregiver has driven for a while (headless Chrome, CDP).

    python tools/screenshot_page.py --out runs/page.png --seconds 12
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def shoot(url: str, out: Path, seconds: float, driver: str) -> None:
    port = free_port()
    profile = tempfile.mkdtemp(prefix="cadence-arm-shot-")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
                             f"--remote-debugging-port={port}", "--window-size=1600,1100",
                             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with aiohttp.ClientSession() as http_:
            tabs = None
            for _ in range(240):
                try:
                    async with http_.get(f"http://127.0.0.1:{port}/json") as r:
                        tabs = await r.json()
                        break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.25)
            page = next(t for t in tabs if t["type"] == "page")
            async with http_.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=64 << 20) as ws:
                seq = 0

                async def call(method, **params):
                    nonlocal seq
                    seq += 1
                    my = seq
                    await ws.send_str(json.dumps({"id": my, "method": method, "params": params}))
                    while True:
                        msg = json.loads((await asyncio.wait_for(ws.receive(), 300)).data)
                        if msg.get("id") == my:
                            return msg.get("result", {})

                async def ev(expr):
                    r = await call("Runtime.evaluate", expression=expr, returnByValue=True)
                    return r.get("result", {}).get("value")

                await call("Runtime.enable")
                await call("Page.navigate", url=url)
                t0 = time.monotonic()
                while time.monotonic() - t0 < 300:
                    t = await ev("document.getElementById('loading').textContent")
                    if t in ("brain ready", "world ready"):
                        break
                    await asyncio.sleep(0.5)
                print("ready after", round(time.monotonic() - t0, 1), "s:", t)
                await ev(f"window.cadenceArm.setDriver('{driver}'); window.cadenceArm.setSpeed(1); window.cadenceArm.start()")
                await asyncio.sleep(seconds)
                print("frame:", await ev("JSON.stringify({decisions: window.cadenceArm.frame.decisions, played: window.cadenceArm.counters.played})"))
                shot = await call("Page.captureScreenshot", format="png")
                out.write_bytes(base64.b64decode(shot["data"]))
                print("saved", out)
    finally:
        proc.terminate()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(HERE / "runs" / "page.png"))
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--driver", default="caregiver")
    a = p.parse_args()
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(HERE / "web")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        asyncio.run(shoot(f"http://127.0.0.1:{port}/", Path(a.out), a.seconds, a.driver))
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
