#!/usr/bin/env python3
"""The fish page in headless Chromium: the closed loop that tests/life.mjs checks in node,
checked again on the page itself, then a screenshot with the brain view on.

    python3 tools/scenario_fish.py --out docs/screenshots/fish.png --receipt receipts/scenario_fish.json

The checks load fish.html?noscan=1&nobloom=1 (no brain view, no bloom) on SwiftShader and wait
on fish time, not wall time. (a) A requested leftward saccade holds the gaze above 5 degrees
after 2 s and keeps 40 percent of that after 12 s, with the spontaneous saccades quiet, no prey
in the tank and the brain at rest before the request; the left half must not ignite. (b) With
the brain off the gaze reads 0 within 1 s. (c) A tap on the glass is answered by a C-start
within 0.2 s and the acoustic sense rings and fades. (d) The frame rate over 5 s, and no page
or console errors. The receipt goes to --receipt as JSON. The screenshot then uses the hardware
renderer through the chromium channel when it launches and draws WebGL, else SwiftShader, with
the brain view and the bloom on.

Serves the repository over a loopback server unless --url names a running one. Needs the
Python Playwright package; a Chromium build of another Playwright version is accepted through
--executable or found under ~/Library/Caches/ms-playwright, and Google Chrome is the fallback.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHECK_QUERY = "?noscan=1&nobloom=1"
RENDERER = """() => { try { const c = document.createElement('canvas'); const gl = c.getContext('webgl2') || c.getContext('webgl'); if (!gl) return null;
  const x = gl.getExtension('WEBGL_debug_renderer_info'); return x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); } catch (e) { return String(e); } }"""
SUMMARY = """() => { const a = window.__app, s = a.state(); return { fish_seconds: a.life.time, life_steps: a.life.steps, brain_steps: a.life.brain.steps,
  ms_per_brain_step: a.S.brainSteps ? a.S.brainMs / a.S.brainSteps : null, page_fps: a.S.fps, frames: a.S.totalFrames, bouts: s.bouts, saccades: a.life.saccades.count,
  gaze_deg: a.life.gaze, brain_on: a.life.brainOn, prey: a.aquarium.preyList().length, captures: a.S.captures, errors: a.errors.slice() }; }"""
HOT_FRACTION = "() => { const v = window.__app.life.brain.activity('left'); let n = 0; for (const x of v) if (x >= 0.5) n++; return n / v.length; }"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def launch(p, executable: str | None):
    """Playwright's Chromium on SwiftShader, as tools/check_body_dev.py launches it."""
    args = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    attempts = []
    if executable:
        attempts.append({"executable_path": executable})
    attempts.append({})
    for pattern in ("chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell", "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"):
        for path in sorted(glob.glob(os.path.expanduser("~/Library/Caches/ms-playwright/" + pattern)), reverse=True):
            attempts.append({"executable_path": path})
    attempts.append({"channel": "chrome"})
    errors = []
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, args=args, **kw), kw
        except Exception as error:  # noqa: BLE001
            errors.append(f"{kw}: {str(error).splitlines()[0]}")
    raise SystemExit("no Chromium could be launched:\n  " + "\n  ".join(errors))


def fish_time(page, t: float, timeout: int = 180000) -> None:
    page.wait_for_function(f"window.__app.life.time >= {t}", timeout=timeout)


def open_page(browser, url: str, errors: list[str]):
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.__app && (window.__app.ready || window.__app.errors.length)", timeout=120000)
    if not page.evaluate("window.__app.ready"):
        raise RuntimeError("the page did not become ready: " + "; ".join(page.evaluate("window.__app.errors")))
    return page


def checks(page) -> dict:
    out: dict = {}
    page.wait_for_function("window.__app.life.steps > 50", timeout=120000)

    # (a) a requested leftward saccade in a quiet fish with the synapses fixed at the compiled gain: the gaze holds, then decays slowly
    page.evaluate("() => { window.__app.setSpontaneous(false); window.__app.clearPrey(); window.__app.setLearning(false); }")
    page.wait_for_function("window.__app.life.saccades.stepsLeft <= 0 && window.__app.life.burst === 0", timeout=30000)
    page.evaluate("window.__app.life.brain.reset()")
    t0 = page.evaluate("window.__app.life.time")
    bouts0 = page.evaluate("window.__app.state().bouts")
    saccades0 = page.evaluate("window.__app.life.saccades.count")
    page.evaluate("window.__app.life.requestSaccade(1)")
    fish_time(page, t0 + 2)
    g2 = page.evaluate("window.__app.life.gaze")
    fish_time(page, t0 + 12)
    g12 = page.evaluate("window.__app.life.gaze")
    hot = page.evaluate(HOT_FRACTION)
    ratio = g12 / g2 if g2 else 0.0
    out["saccade_hold"] = {
        "gaze_2s_deg": g2, "gaze_12s_deg": g12, "ratio_12s_to_2s": ratio, "hot_fraction_left": hot,
        "bouts_in_window": page.evaluate("window.__app.state().bouts") - bouts0,
        "saccades_in_window": page.evaluate("window.__app.life.saccades.count") - saccades0,
        "conditions": {"spontaneous_saccades": False, "prey": 0, "brain_reset_before_request": True, "pilot_swimming": True},
        "pass": bool(g2 > 5 and g12 > 0.4 * g2 and hot <= 0.05),
    }

    # (b) the brain off: the gaze reads 0 within a second
    page.evaluate("window.__app.life.brainOn = false")
    t1 = page.evaluate("window.__app.life.time")
    fish_time(page, t1 + 1)
    g_off = page.evaluate("window.__app.life.gaze")
    out["brain_off"] = {"gaze_after_1s_deg": g_off, "pass": g_off == 0}
    page.evaluate("window.__app.setBrain(true)")

    # (d) the synapses learn: from the leaky start, requested saccades every 3 s with the fish quiet; the lessons' own
    # hold estimates must grow, and the early ones must see the leak
    page.evaluate("() => { window.__app.setSpontaneous(false); window.__app.setLearning(true); }")
    t_learn = page.evaluate("window.__app.life.time")
    for k in range(16):
        page.evaluate(f"window.__app.life.requestSaccade({1 if k % 2 == 0 else -1})")
        fish_time(page, t_learn + 3 * (k + 1))
    learning = page.evaluate("window.__app.learning()")
    taken = [e for e in learning["log"] if e["taken"]]
    holds = [e["hold"] if e["hold"] is not None and e["hold"] < 1e9 else 999.0 for e in taken]  # 999: the eye ran on, a hold beyond what a fixation measures
    first = min(holds[:3]) if holds[:3] else None
    last = max(holds[-4:]) if holds[-4:] else None
    out["learning"] = {"lessons": learning["lessons"], "fixations": learning["fixations"], "holds_of_lessons_s": [round(h, 1) for h in holds],
                       "first_hold_s": first, "best_of_last_four_s": last, "fish_seconds": 48,
                       "pass": bool(learning["lessons"] >= 4 and first is not None and first < 5 and last is not None and last > 2 * first)}
    page.evaluate("window.__app.setSpontaneous(true)")

    # (e) left alone with its own saccades, from the leaky start again, the fish learns the hold within 150 fish seconds;
    # (f) a world that drifts back then teaches a gaze that falls back within 75 s; (g) a still world brings a hold of
    # eight seconds or more back within 90 s. The page runs at three times wall pace here, in fish time as always.
    page.evaluate("() => { window.__app.resetSynapses(); window.__app.setWorld('still'); window.__app.S.speed = 3; }")

    def phase(world: str, seconds: float) -> dict:
        page.evaluate(f"window.__app.setWorld({world!r})")
        t0 = page.evaluate("window.__app.life.time")
        lessons0 = page.evaluate("window.__app.learning().lessons")
        seen: dict = {}
        while page.evaluate("window.__app.life.time") < t0 + seconds:
            for e in page.evaluate("window.__app.learning().log"):
                if e["taken"]:
                    seen[(e["time"], e["side"])] = e
            page.wait_for_timeout(1500)
        for e in page.evaluate("window.__app.learning().log"):
            if e["taken"]:
                seen[(e["time"], e["side"])] = e
        rows = [seen[k] for k in sorted(seen)]
        finite = [e["hold"] for e in rows if e["hold"] is not None and e["hold"] < 1e9]
        ran_on = sum(1 for e in rows if e["drift"] > 0)
        last4 = sorted(finite[-4:])
        return {"world": world, "fish_seconds": seconds, "lessons": page.evaluate("window.__app.learning().lessons") - lessons0,
                "holds_s": [round(h, 1) for h in finite], "ran_on": ran_on, "median_of_last_four_s": last4[len(last4) // 2] if last4 else None,
                "best_hold_s": max(finite) if finite else None, "quick_phases": page.evaluate("window.__app.life.saccades.quick")}

    alone = phase("still", 150)
    alone["pass"] = bool(alone["lessons"] >= 8 and alone["median_of_last_four_s"] is not None and alone["median_of_last_four_s"] >= 5)
    out["learning_alone"] = alone
    back = phase("back", 75)
    back["pass"] = bool(back["lessons"] >= 4 and back["median_of_last_four_s"] is not None and back["median_of_last_four_s"] < 6)
    still = phase("still", 90)
    still["pass"] = bool(still["lessons"] >= 2 and ((still["best_hold_s"] is not None and still["best_hold_s"] >= 8) or still["ran_on"] >= 1))
    out["worlds"] = {"back": back, "still_again": still, "pass": back["pass"] and still["pass"]}
    page.evaluate("() => { window.__app.S.speed = 1; }")

    # (c) a tap on the glass: a C-start within 0.2 s, the acoustic sense rings and fades
    bouts_tap = page.evaluate("window.__app.state().bouts")
    t_tap = page.evaluate("() => { const a = window.__app; const t = a.life.body.t; a.tap(-1); return t; }")
    page.wait_for_function(f"window.__app.state().bouts > {bouts_tap} || window.__app.life.time > {t_tap + 0.5}", timeout=15000)
    last = page.evaluate("window.__app.state().lastBout")  # the first bout after the tap
    latency = (last["time"] - t_tap) if last else None
    # the senses are sampled once per brain step (40 ms); the tap's pulse stays above 0.1 for 160 ms
    page.wait_for_function("window.__app.senses().acoustic > 0.1", timeout=15000)
    acoustic = page.evaluate("window.__app.senses().acoustic")
    page.wait_for_function("window.__app.senses().acoustic < 0.05", timeout=15000)
    out["tap"] = {
        "pane": "left", "last_bout": last and last["type"], "latency_s": latency, "acoustic_seen": acoustic,
        "pass": bool(last and last["type"] == "cstart" and latency is not None and 0 <= latency <= 0.2 and acoustic > 0.1),
    }
    page.evaluate("() => { for (let k = 0; k < 3; k++) window.__app.dropPrey(); }")

    # (d) the frame rate over five seconds of wall time
    f0 = page.evaluate("window.__app.S.totalFrames")
    w0 = time.time()
    page.wait_for_timeout(5000)
    f1 = page.evaluate("window.__app.S.totalFrames")
    seconds = time.time() - w0
    out["fps"] = {"frames": f1 - f0, "seconds": round(seconds, 3), "fps": (f1 - f0) / seconds, "page_fps": page.evaluate("window.__app.S.fps")}
    out["summary"] = page.evaluate(SUMMARY)
    return out


def shoot(p, url: str, out: Path, executable: str | None) -> dict:
    """The screenshot with the brain view and the bloom on: the hardware renderer first."""
    notes = []
    attempts = [("hardware", lambda: p.chromium.launch(headless=True, channel="chromium", args=["--ignore-gpu-blocklist"])), ("swiftshader", lambda: launch(p, executable)[0])]
    for name, start in attempts:
        try:
            browser = start()
        except Exception as error:  # noqa: BLE001
            notes.append(f"{name}: {str(error).splitlines()[0]}")
            continue
        errors: list[str] = []
        try:
            page = open_page(browser, url, errors)
            page.wait_for_function("window.__app.brainView", timeout=120000)
            renderer = page.evaluate(RENDERER)
            # a leftward saccade from rest, two seconds before the shot, so the hold is in the picture
            fish_time(page, 4.0)
            page.evaluate("window.__app.setSpontaneous(false)")
            page.wait_for_function("window.__app.life.saccades.stepsLeft <= 0 && window.__app.life.burst === 0", timeout=30000)
            page.evaluate("() => { window.__app.life.brain.reset(); window.__app.life.requestSaccade(1); }")
            t_shot = page.evaluate("window.__app.life.time") + 2.0
            fish_time(page, t_shot)
            page.evaluate("window.__app.setSpontaneous(true)")
            f0 = page.evaluate("window.__app.S.totalFrames")
            w0 = time.time()
            page.wait_for_timeout(3000)
            frames = page.evaluate("window.__app.S.totalFrames") - f0
            seconds = time.time() - w0
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out))
            info = {
                "path": str(out), "launch": name, "browser": browser.version, "renderer": renderer, "fps": frames / seconds,
                "active_skeletons": page.evaluate("window.__app.brainView.activeCount"), "skeletons": page.evaluate("window.__app.brainView.n"),
                "gaze_deg": page.evaluate("window.__app.life.gaze"), "fish_seconds": page.evaluate("window.__app.life.time"),
                "errors": page.evaluate("window.__app.errors.slice()") + errors, "bytes": out.stat().st_size,
            }
            browser.close()
            if info["errors"] and name == "hardware":
                notes.append(f"hardware: {info['errors'][0]}")
                continue
            info["notes"] = notes
            return info
        except Exception as error:  # noqa: BLE001
            notes.append(f"{name}: {str(error).splitlines()[0]}")
            browser.close()
    raise SystemExit("no screenshot could be taken:\n  " + "\n  ".join(notes))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="a running server's page URL; otherwise a loopback server serves the repository")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots" / "fish.png")
    ap.add_argument("--receipt", type=Path, default=ROOT / "receipts" / "scenario_fish.json")
    ap.add_argument("--executable", default=None)
    ap.add_argument("--no-screenshot", action="store_true")
    args = ap.parse_args()
    server = None
    url = args.url
    if url is None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/web/fish.html"
    t0 = time.time()
    receipt: dict = {"page": "web/index.html", "query": CHECK_QUERY, "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    try:
        with sync_playwright() as p:
            browser, how = launch(p, args.executable)
            errors: list[str] = []
            page = open_page(browser, url + CHECK_QUERY, errors)
            receipt["browser"] = browser.version
            receipt["launch"] = how or "the default build"
            receipt["renderer"] = page.evaluate(RENDERER)
            receipt["checks"] = checks(page)
            page_errors = receipt["checks"]["summary"].pop("errors") + errors
            receipt["errors"] = page_errors
            browser.close()
            passed = [receipt["checks"][k]["pass"] for k in ("saccade_hold", "brain_off", "learning", "learning_alone", "worlds", "tap")] + [not page_errors]
            if not args.no_screenshot:
                receipt["screenshot"] = shoot(p, url, args.out, args.executable)
                passed.append(not receipt["screenshot"]["errors"])
    finally:
        if server:
            server.shutdown()
    receipt["passed"] = all(passed)
    receipt["seconds"] = round(time.time() - t0, 1)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    c = receipt["checks"]
    a, b, t, f = c["saccade_hold"], c["brain_off"], c["tap"], c["fps"]
    print(f"chromium {receipt['browser']} via {receipt['launch']} on {receipt['renderer']}")
    print(f"{'ok  ' if a['pass'] else 'FAIL'} saccade: gaze {a['gaze_2s_deg']:.1f} deg after 2 s, {a['gaze_12s_deg']:.1f} deg after 12 s (ratio {a['ratio_12s_to_2s']:.2f}), hot fraction {a['hot_fraction_left']:.3f}, {a['bouts_in_window']} bouts meanwhile")
    print(f"{'ok  ' if b['pass'] else 'FAIL'} brain off: gaze {b['gaze_after_1s_deg']} after 1 s")
    l = c["learning"]
    print(f"{'ok  ' if l['pass'] else 'FAIL'} learning: {l['lessons']} lessons in {l['fixations']} fixations over {l['fish_seconds']} fish seconds; the lessons' holds {l['holds_of_lessons_s']} s (first {l['first_hold_s']}, best of the last four {l['best_of_last_four_s']})")
    la = c["learning_alone"]
    print(f"{'ok  ' if la['pass'] else 'FAIL'} learning alone: {la['lessons']} lessons in {la['fish_seconds']} fish seconds of the fish's own saccades; holds {la['holds_s']} s, median of the last four {la['median_of_last_four_s']}, {la['ran_on']} saw the eye run on, {la['quick_phases']} quick phases")
    w = c["worlds"]
    for name, ph in (("drifts back", w["back"]), ("still again", w["still_again"])):
        print(f"{'ok  ' if ph['pass'] else 'FAIL'} world {name}: {ph['lessons']} lessons in {ph['fish_seconds']} s; holds {ph['holds_s']} s, median of the last four {ph['median_of_last_four_s']}, best {ph['best_hold_s']}, {ph['ran_on']} saw the eye run on")
    print(f"{'ok  ' if t['pass'] else 'FAIL'} tap: {t['last_bout']} after {t['latency_s'] if t['latency_s'] is None else round(t['latency_s'], 3)} s, acoustic {t['acoustic_seen']:.2f}")
    print(f"ok   fps: {f['fps']:.1f} over {f['seconds']} s ({f['frames']} frames), brain step {c['summary']['ms_per_brain_step']:.3f} ms, {c['summary']['brain_steps']} brain steps in {c['summary']['fish_seconds']:.1f} fish seconds")
    print(("ok   " if not page_errors else "FAIL ") + (f"{len(page_errors)} browser errors: " + " | ".join(page_errors) if page_errors else "no page or console errors"))
    if "screenshot" in receipt:
        s = receipt["screenshot"]
        print(f"ok   screenshot {s['path']} ({s['bytes'] / 1e3:.0f} kB) via {s['launch']} on {s['renderer']} at {s['fps']:.1f} fps, {s['active_skeletons']} of {s['skeletons']} skeletons lit" + (f", errors: {s['errors']}" if s["errors"] else ""))
    print(f"receipt {args.receipt}")
    print(f"{'all passed' if receipt['passed'] else 'FAILED'} in {receipt['seconds']} s")
    raise SystemExit(0 if receipt["passed"] else 1)


if __name__ == "__main__":
    main()
