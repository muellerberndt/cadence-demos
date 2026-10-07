"""Exercise the visible fish teaching controls in Chromium; preserve historical receipts.

python3 tools/check_learning_ui.py [--url http://127.0.0.1:8000/]
The practice button runs its ordinary visible 8x schedule, without injecting lessons.
"""
import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from check_site import launch, serve

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url")
    parser.add_argument("--out", default="receipts/learning_ui.json")
    args = parser.parse_args()
    server, url = (None, args.url) if args.url else serve(ROOT / "web")
    files = ["web/fish.html", "web/fish_page.js", "web/learning_probe.js", "web/brain.js",
             "web/twin.js", "web/life.js", "web/dictionary.js", "tools/check_learning_ui.py"]
    hashes = lambda: {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}
    sources = hashes()
    out = {"scope": "Visible practice, freeze, probe, return, reset and mobile controls", "sources_sha256": sources}
    errors = []
    with sync_playwright() as p:
        browser = launch(p, False)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(url + "fish.html?noscan=1&nobloom=1&seed=7")
        page.wait_for_function("window.__app?.ready", timeout=90000)
        page.locator("#pause").click()
        page.locator("#reset-synapses").click()
        page.locator("#measure-learning").click()
        initial = page.evaluate("window.__app.lastProbe")
        assert initial["left"]["ratio"] == initial["baseline"]["ratio"] == initial["right"]["ratio"]
        out["initial"] = initial
        page.locator("#practice-lesson").click()
        print("visible hold practice started (600 fish seconds at 8x)", flush=True)
        page.wait_for_function("window.__app.S.practiceEnd === null && !window.__app.learning().on", timeout=300000)
        held = page.evaluate("window.__app.lastProbe")
        for side in ("left", "right"):
            assert .45 < held[side]["ratio"] <= 1.05, held
        out["hold"] = held
        digest = "JSON.stringify(Object.values(window.__app.brain.halves).map(b => [Array.from(b.w), Array.from(b.bias)]))"
        acquired = page.evaluate(digest)
        page.wait_for_timeout(1000)
        assert page.evaluate(digest) == acquired, "paused learning changed the acquired weights"
        page.locator("#measure-learning").click()
        frozen = page.evaluate("window.__app.lastProbe")
        assert all(frozen[side] == held[side] for side in ("left", "right")), "frozen response changed with live activity"
        page.locator("#world [data-world=back]").click()
        assert page.evaluate(digest) == acquired, "selecting feedback erased learning"
        page.locator("#practice-lesson").click()
        print("visible return practice started (150 fish seconds at 8x)", flush=True)
        page.wait_for_function("window.__app.S.practiceEnd === null && !window.__app.learning().on", timeout=180000)
        returned = page.evaluate("window.__app.lastProbe")
        for side in ("left", "right"):
            assert returned[side]["ratio"] < held[side]["ratio"] / 2, returned
        out["return"] = returned
        screenshot = ROOT / "docs/screenshots/learning_ui.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot))
        page.locator("#learning-toggle").click()
        page.locator("#learning-toggle").click()
        page.locator("#reset-synapses").click()
        page.locator("#measure-learning").click()
        reset = page.evaluate("window.__app.lastProbe")
        assert reset["lessons"] == 0
        assert reset["left"]["ratio"] == initial["baseline"]["ratio"] == reset["right"]["ratio"]
        out["reset"] = reset
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal mobile overflow"
        page.locator("#practice-lesson").scroll_into_view_if_needed()
        page.screenshot(path=str(ROOT / "docs/screenshots/learning_mobile.png"))
        out["page_errors"] = errors
        assert not errors, errors
        out["browser"] = browser.version
        browser.close()
    if server:
        server.shutdown()
    assert hashes() == sources, "source changed during browser audit"
    out["passed"] = True
    (ROOT / args.out).write_text(json.dumps(out, indent=2) + "\n")
    print("learning UI: hold, return, frozen retention, reset and mobile layout passed", flush=True)


if __name__ == "__main__":
    main()
