"""The shared gate of a demo page: site.json, the help page, the explanations, the embedded rule.

    python tools/check_explain.py <demo-folder> [--shots DIR] [--min-explain N] [--url URL]

It serves the demo's page folder (or uses --url), opens the page by itself and inside a frame,
and checks:
  - site.json has every field, within its length, and the words rules hold in it and in help.html;
  - the page loads with no console error, page error or failed request;
  - the page carries the shared explanation files and at least N explained parts ([data-explain]
    and canvas spots), and a help link;
  - help.html loads, has the template's sections and links back to the demo;
  - inside a frame the page is marked embedded and hides what only the page by itself shows;
  - neither view scrolls sideways at 1512x860 and 1280x720.
In the frame the page wears the demos site's theme (shared/site/cadence-theme.css, a copy of the
site's file, with data-demo on <body>), as the site serves it. It writes nothing outside --shots.
Exit 1 on a failed check.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

FIELDS = {"slug": 40, "title": 40, "page_dir": 60, "card": 140, "tagline": 80, "kicker": 48, "feature": 240, "howTo": 240, "help": 60}
SECTIONS = ("see", "why", "do", "how", "numbers", "limits")
# public text: state-only words, no em dash, no "honest"
BANNED = re.compile(r"\b(now|still|already|remains|currently|honest|honestly)\b|no longer|not yet|—", re.I)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # no request log on the console
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(Quiet, directory=str(directory))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


def visible_text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", type=Path)
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--min-explain", type=int, default=6)
    ap.add_argument("--url", help="a running server for the page folder")
    ap.add_argument("--wait", type=float, default=8.0, help="seconds to let the page start")
    ap.add_argument("--theme", type=Path, default=Path(__file__).resolve().parents[1] / "shared" / "site" / "cadence-theme.css",
                    help="the demos site's theme, put on the page in the frame")
    args = ap.parse_args()
    results: list[tuple[bool, str, object]] = []

    def check(ok: bool, name: str, detail: object = "") -> None:
        results.append((bool(ok), name, detail))

    meta = json.loads((args.demo / "site.json").read_text())
    missing = [k for k in FIELDS if not meta.get(k)]
    long = {k: len(meta[k]) for k, n in FIELDS.items() if meta.get(k) and len(meta[k]) > n}
    check(not missing and not long, "site.json: every field, within its length", {"missing": missing, "too_long": long})
    words = [m.group(0) for k in ("card", "tagline", "kicker", "feature", "howTo") for m in BANNED.finditer(meta.get(k, ""))]
    check(not words, "site.json: the words rules", words)

    page_dir = args.demo / meta.get("page_dir", "web")
    help_path = page_dir / meta.get("help", "help.html")
    help_html = help_path.read_text() if help_path.exists() else ""
    check(bool(help_html), "help.html exists", str(help_path))
    found = [s for s in SECTIONS if f'id="{s}"' in help_html]
    check(len(found) == len(SECTIONS), "help.html has the template's sections", {"found": found})
    hwords = sorted({m.group(0) for m in BANNED.finditer(visible_text(help_html))})
    check(not hwords, "help.html: the words rules", hwords)

    server = None
    base = args.url
    if not base:
        # a built app is served from its build output (deploy_dir) when the page folder holds only
        # its static files
        served = page_dir
        if not (page_dir / "index.html").exists() and meta.get("deploy_dir"):
            served = args.demo / meta["deploy_dir"]
            if not (served / "index.html").exists():
                print(f"build the app first: {meta.get('build', 'its build')} (in {args.demo})", file=sys.stderr)
                return 1
        base, server = serve(served)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
        for w, h in ((1512, 860), (1280, 720)):
            ctx = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("requestfailed", lambda r: errors.append("failed " + r.url))
            page.goto(base, wait_until="load")
            page.wait_for_timeout(int(args.wait * 1000))
            info = page.evaluate("""() => ({
                explain: !!window.CadenceExplain,
                parts: document.querySelectorAll('[data-explain]').length,
                help: !!document.querySelector('a[data-help]'),
                sideways: document.documentElement.scrollWidth > innerWidth + 1,
                embedded: document.documentElement.classList.contains('embedded') })""")
            check(not errors, f"{w}x{h} by itself: no console error, page error or failed request", errors[:5])
            check(info["explain"] and info["parts"] >= args.min_explain, f"{w}x{h} by itself: the shared explanations, at least {args.min_explain} parts", info)
            check(info["help"], f"{w}x{h} by itself: a help link (a[data-help])", info)
            check(not info["sideways"] and not info["embedded"], f"{w}x{h} by itself: no sideways scroll, not marked embedded", info)
            if args.shots:
                page.screenshot(path=str(args.shots / f"alone-{w}x{h}.png"))
            # the page inside a frame, as the demos site shows it under its header. The wrapper is
            # written into a page of the same origin, so the frame is a secure context as on the
            # site (https): crypto.subtle and the like exist in it.
            frame_page = ctx.new_page()
            ferrors: list[str] = []
            frame_page.on("console", lambda m: ferrors.append(m.text) if m.type == "error" else None)
            frame_page.on("pageerror", lambda e: ferrors.append(str(e)))
            frame_page.on("requestfailed", lambda r: ferrors.append("failed " + r.url))
            frame_page.goto(base + meta.get("help", "help.html"))
            frame_page.set_content(f'<html><body style="margin:0;background:#0b1215"><div style="height:150px"></div>'
                                   f'<iframe src="{base}" style="border:0;width:100%;height:{h - 150}px"></iframe></body></html>')
            frame_page.wait_for_timeout(int(args.wait * 1000))
            frame = frame_page.frames[1] if len(frame_page.frames) > 1 else None
            if frame and args.theme and args.theme.exists():
                frame.add_style_tag(content=args.theme.read_text())
                frame.evaluate("(slug) => document.body.setAttribute('data-demo', slug)", meta["slug"])
                frame_page.wait_for_timeout(600)
            fstatus = frame.evaluate("document.querySelector('.runtime, #runtime, .status')?.innerText || ''") if frame else ""
            check(not ferrors, f"{w}x{h} in a frame: no console error, page error or failed request", {"errors": ferrors[:5], "status": fstatus[:120]})
            emb = frame.evaluate("""() => ({ embedded: document.documentElement.classList.contains('embedded'),
                shown: [...document.querySelectorAll('[data-standalone]')].filter(e => e.getClientRects().length).length,
                sideways: document.documentElement.scrollWidth > innerWidth + 1 })""") if frame else None
            check(bool(emb) and emb["embedded"] and emb["shown"] == 0 and not emb["sideways"], f"{w}x{h} in a frame: embedded, standalone parts hidden, no sideways scroll", emb)
            if args.shots:
                frame_page.screenshot(path=str(args.shots / f"framed-{w}x{h}.png"))
            ctx.close()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        resp = page.goto(base + meta.get("help", "help.html"))
        back = page.evaluate("!!document.querySelector('a[href=\"./\"]')")
        check(resp is not None and resp.ok and back, "help.html loads and links back to the demo", {"status": resp.status if resp else None})
        if args.shots:
            page.screenshot(path=str(args.shots / "help.png"), full_page=True)
        browser.close()
    if server:
        server.shutdown()

    for ok, name, detail in results:
        print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {json.dumps(detail, default=str)[:400]}"))
    passed = sum(ok for ok, _, _ in results)
    print(f"{'PASS' if passed == len(results) else 'FAIL'}: {passed} of {len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
