"""Screenshots of a parrot body on the perch in the page's room and light (look.html), one per view.

    python tools/shoot_looks.py --out DIR --name NAME [--query 'src=...&height=0.29&grip=0.2'] [--views front,side,head]

Serves site/ on a free port, opens look.html?<query>&view=<view> in headless Chromium at 1200x900,
waits for the first frames, and writes DIR/NAME-<view>.png.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--query", default="")
    ap.add_argument("--views", default="front,side,head")
    ap.add_argument("--size", default="1200x900")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    w, h = (int(v) for v in args.size.split("x"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": w, "height": h})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        for view in args.views.split(","):
            page.goto(f"{base}look.html?{args.query}&view={view}")
            page.wait_for_selector("body[data-ready='1']", timeout=180000)
            page.wait_for_timeout(500)
            path = args.out / f"{args.name}-{view}.png"
            page.screenshot(path=str(path))
            print(path)
        browser.close()
    server.shutdown()
    if errors:
        print("errors:", *errors[:5], sep="\n  ")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
