"""Load every page of the site in headless Chromium and record console errors, page errors,
failed requests and readiness. Writes receipts/site_check.json and a screenshot per page.

    python tools/check_site.py [--hardware] [--pages index,explain,...]
"""
from __future__ import annotations

import argparse, glob, json, os, threading, time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DEFAULT_PAGES = ["index", "explain", "disclaimers", "copy", "paste", "match", "limits", "why", "fish"]


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D102
        pass


def serve(directory: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def launch(p, hardware: bool):
    """The first Chromium that starts: the default, then Playwright's cached builds, then Chrome."""
    flags = [] if hardware else ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    attempts = [{"channel": "chromium"}] if hardware else [{}]
    for pattern in ("chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell", "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"):
        for path in sorted(glob.glob(os.path.expanduser("~/Library/Caches/ms-playwright/" + pattern)), reverse=True):
            attempts.append({"executable_path": path})
    attempts.append({"channel": "chrome"})
    errors = []
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, args=flags, **kw)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{kw}: {str(error).splitlines()[0]}")
    raise SystemExit("no Chromium could be launched:\n  " + "\n  ".join(errors))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hardware", action="store_true")
    ap.add_argument("--pages", default=",".join(DEFAULT_PAGES))
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--query", default="?nobloom=1")
    ap.add_argument("--receipt", type=Path, default=ROOT / "receipts/site_check.json")
    ap.add_argument("--screenshot-prefix", default="check")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    server, url = serve(WEB)
    pages = [p for p in args.pages.split(",") if (WEB / f"{p}.html").exists()]
    out = {"pages": {}, "date": time.strftime("%Y-%m-%d"), "renderer": "hardware" if args.hardware else "swiftshader"}
    (ROOT / "docs" / "screenshots").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = launch(p, args.hardware)
        for name in pages:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            errors, failed = [], []
            page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda ex, e=errors: e.append(str(ex)))
            page.on("requestfailed", lambda r, f=failed: f.append(r.url))
            t0 = time.time()
            page.goto(url + f"{name}.html{args.query}", wait_until="domcontentloaded")
            ready = False
            try:
                page.wait_for_function("window.__app && window.__app.ready", timeout=90000); ready = True
            except Exception:
                pass
            page.wait_for_timeout(int(args.seconds * 1000))
            app_errors = page.evaluate("(window.__app && window.__app.errors) || []")
            shot = ROOT / "docs" / "screenshots" / f"{args.screenshot_prefix}_{name}.png"
            page.screenshot(path=str(shot))
            out["pages"][name] = {"ready": ready, "seconds_to_ready": round(time.time() - t0, 1), "console_errors": errors, "app_errors": app_errors, "failed_requests": [f for f in failed if "127.0.0.1" in f], "screenshot": str(shot.relative_to(ROOT))}
            print(f"{name:8s} ready {ready} in {out['pages'][name]['seconds_to_ready']} s, errors {len(errors) + len(app_errors)}, failed requests {len(out['pages'][name]['failed_requests'])}", flush=True)
            page.close()
        out["browser"] = browser.version
        browser.close()
    server.shutdown()
    out["clean"] = all(v["ready"] and not v["console_errors"] and not v["app_errors"] and not v["failed_requests"] for v in out["pages"].values())
    (ROOT / "receipts").mkdir(exist_ok=True)
    args.receipt.write_text(json.dumps(out, indent=1))
    print("clean" if out["clean"] else "NOT clean")
    raise SystemExit(0 if out["clean"] else 1)


if __name__ == "__main__":
    main()
