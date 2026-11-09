"""The browser edition's promise, checked in a headless browser: both brains are born on the
released cadence-net wheel in Pyodide, learn from the teacher, take the controls and keep
playing on reward, with no fault and no refusal. Writes the readings and a screenshot.

    python check_page.py --out evidence/page_check.json --shot docs/browser.png

Needs Playwright (`pip install playwright && playwright install chromium`); `--chromium` points
it at another headless Chromium binary. The first visit downloads Pyodide and NumPy from jsDelivr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


async def check(port: int, minutes: float, shot: str | None, chromium: str | None) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": chromium} if chromium else {}))
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        states: dict[str, dict] = {}
        await page.expose_function("__report", lambda name, text: states.__setitem__(name, json.loads(text)))
        # every brain worker's state message is copied out of the page as it arrives
        await page.add_init_script("""
          const Native = Worker;
          window.Worker = function (url, options) {
            const w = new Native(url, options);
            if (String(url).includes('brain_worker')) {
              const game = 'g' + (window.__brains = (window.__brains || 0) + 1);
              w.addEventListener('message', (e) => {
                if (e.data && e.data.type === 'state') window.__report(game, JSON.stringify(e.data.state));
                if (e.data && e.data.type === 'ready') window.__report(game + ':ready', JSON.stringify(e.data.graph));
                if (e.data && e.data.type === 'error') window.__report(game + ':error', JSON.stringify(e.data));
              });
            }
            return w;
          };
        """)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        began = time.time()
        await page.goto(f"http://127.0.0.1:{port}/")
        played = False
        while time.time() - began < minutes * 60:
            await asyncio.sleep(5)
            brains = [v for k, v in states.items() if ":" not in k]
            played = len(brains) == 2 and all(b["phase"] == "playing" and b["life"]["decisions"] >= 300 for b in brains)
            if played:
                break
        if shot:
            await page.screenshot(path=shot)
        await browser.close()
    brains = {k: v for k, v in states.items() if ":" not in k}
    ready = {k.split(":")[0]: v for k, v in states.items() if k.endswith(":ready")}
    checks = {
        "two_brains_born_on_the_wheel": len(ready) == 2 and all(r.get("cadence") == "0.95.2" for r in ready.values()),
        "both_took_the_controls": len(brains) == 2 and all(b["phase"] == "playing" for b in brains.values()),
        "kept_playing": played,
        "no_faults_or_refusals": all(b["brain"]["faults"] == 0 and b["life"]["refused"] == 0 for b in brains.values()),
        "no_page_errors": not errors and not any(k.endswith(":error") for k in states),
    }
    checks["PASS"] = all(checks.values())
    return {"checks": checks, "seconds": round(time.time() - began, 1), "brains": brains,
            "page_errors": errors, "cadence": [r.get("cadence") for r in ready.values()]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8811)
    ap.add_argument("--minutes", type=float, default=6)
    ap.add_argument("--out", default=str(HERE / "evidence" / "page_check.json"))
    ap.add_argument("--shot", default=None)
    ap.add_argument("--chromium", default=None)
    a = ap.parse_args()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(a.port), "--bind", "127.0.0.1",
                               "--directory", str(HERE / "web")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        result = asyncio.run(check(a.port, a.minutes, a.shot, a.chromium))
    finally:
        server.terminate()
    result["checked_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(a.out).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["checks"], indent=1))
    sys.exit(0 if result["checks"]["PASS"] else 1)


if __name__ == "__main__":
    main()
