"""No text overlaps text in the page's panels: the brain panel's drawn labels (each fitted to its
column) and every element with text of its own in the panels and the toolbar, at 1512x860,
1280x800 and 1920x1080. Exit 1 on an overlap.

    python parrot/site/tools/check_text.py [--brain composed|placeholder] [--wait 40]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1]
JS = r"""() => {
  const out = { canvas: [], dom: [] };
  const v = window.parrotPage.view, wrap = document.getElementById('brain').getBoundingClientRect();
  const boxes = (v && v.labelBoxes) || [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1) out.canvas.push([a.text, b.text]);
  }
  for (const b of boxes) if (b.x + b.w > wrap.width + 1) out.canvas.push([b.text, 'beyond the panel']);
  // elements with text of their own, in the panels and the toolbar
  const scopes = [...document.querySelectorAll('.brain, .mind-foot, .controls, .mind-head')];
  const els = [];
  for (const scope of scopes) for (const el of scope.querySelectorAll('*')) {
    if (el.closest('.cx-card') || el.classList.contains('cx-q') || el.closest('.b3-labels')) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const st = getComputedStyle(el); if (st.visibility === 'hidden' || st.display === 'none') continue;
    const range = document.createRange(); range.selectNodeContents(el);
    for (const r of range.getClientRects()) if (r.width > 1 && r.height > 1) els.push({ el, r, text: el.textContent.trim().slice(0, 40) });
  }
  for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i], b = els[j];
    if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (ox > 2 && oy > 2) out.dom.push([a.text, b.text]);
  }
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brain", default="composed")
    ap.add_argument("--wait", type=float, default=40.0)
    args = ap.parse_args()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu"])
        for w, h in ((1512, 860), (1280, 800), (1920, 1080)):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(f"{base}index.html?brain={args.brain}")
            page.wait_for_selector("body[data-ready='1']", timeout=240000)
            page.wait_for_timeout(int(args.wait * 1000) // 4)
            page.evaluate("document.getElementById('talk').hidden = true")
            found = page.evaluate(JS)
            ok = not found["canvas"] and not found["dom"]
            failed += not ok
            print(("ok   " if ok else "FAIL ") + f"{w}x{h}: no text overlaps text" + ("" if ok else "  " + json.dumps(found)[:600]))
            page.close()
        browser.close()
    server.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
