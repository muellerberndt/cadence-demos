#!/usr/bin/env python3
"""The larva page in headless Chromium: the closed loop that tests/larva_life.mjs checks in
node, checked again on the page itself, then a screenshot with the brain view on.

    python3 tools/scenario_larva.py --out docs/screenshots/larva.png --receipt receipts/scenario_larva.json

The checks load index.html?noscan=1&nobloom=1 (no brain view, no bloom) on SwiftShader and wait
on larva time, not wall time. (a) A lamp beside the larva on one side for 3 s of larva time
bends the course with one sign and the mirrored lamp with the opposite sign; the lamp's place
is computed from the larva's heading as the node check does with y offsets, and before each
lamp the body is placed near the surface with the tank ahead and the net rested, as the node
check does. (b) A tap on the glass: the arrest command exceeds 0.3 within 0.5 s and the larva
is lower a second later; the same window without a tap is measured first as the control, since
the depth's pressure on the ciliary photoreceptors raises the arrest by itself. (c) With the
brain off the ciliary commands sit at the dictionary's baseline, the arrest and the muscles at
zero, the course does not turn and the net takes no step. (d) The frame rate over 5 s, and no
page or console errors. The receipt goes to --receipt as JSON. The screenshot then uses the
hardware renderer through the chromium channel when it launches and draws WebGL, else
SwiftShader, with the brain view and the bloom on and the lamp beside the larva.

Serves the repository over a loopback server unless --url names a running one. Needs the
Python Playwright package; a Chromium build of another Playwright version is accepted through
--executable or found under ~/Library/Caches/ms-playwright, and Google Chrome is the fallback.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHECK_QUERY = "?noscan=1&nobloom=1"
LAMP_SIDE = 4.5     # mm beside the larva, as tests/larva_life.mjs places the lamp
LAMP_AHEAD = 0.001  # mm ahead of it
LAMP_ABOVE = 2.0    # mm above it
LAMP_PLACE = ([4.0, 5.0, 8.2], 0.0)   # the body near the surface, heading along +x, 16 mm of tank ahead
TAP_PLACE = ([10.0, 5.0, 5.0], 0.5)   # the node check's start for the tap, mid-water
OFF_PLACE = ([10.0, 5.0, 8.2], 0.0)   # the brain-off window: the tank ahead, no pane within reach
SHOT_LAMP_Z = 13.0                    # mm, the screenshot's lamp at the tank's lamp height, so the floor under it stays dim
RENDERER = """() => { try { const c = document.createElement('canvas'); const gl = c.getContext('webgl2') || c.getContext('webgl'); if (!gl) return null;
  const x = gl.getExtension('WEBGL_debug_renderer_info'); return x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); } catch (e) { return String(e); } }"""
CONSTANTS = """() => Promise.all([import('./larva_dictionary.js'), import('./larva_body.js')]).then(([d, b]) => ({ baseline_beat: d.BASELINE_BEAT, step_ms: d.STEP_MS, water: b.WATER, tank: b.TANK }))"""
SAMPLE = """() => { const a = window.__app, s = a.state(); return { t: a.life.time, heading: s.heading, z: s.position[2], on_floor: s.onFloor, eyes: [s.senses.eye_left, s.senses.eye_right],
  command: a.command(), reflections: a.S.reflections, brain_steps: a.brain.steps }; }"""
SUMMARY = """() => { const a = window.__app, s = a.state(); let hot = 0; for (const x of a.brain.s) if (x >= 0.5) hot++; return { larva_seconds: a.life.time, life_steps: a.life.steps, brain_steps: a.brain.steps,
  ms_per_brain_step: a.S.brainSteps ? a.S.brainMs / a.S.brainSteps : null, page_fps: a.S.fps, frames: a.S.totalFrames, position: s.position, on_floor: s.onFloor, command: a.command(), senses: a.senses(),
  brain_on: a.life.brainOn, light: { ...a.world.light }, uv: a.world.uv, reflections: a.S.reflections, hot_fraction: hot / a.brain.n, errors: a.errors.slice() }; }"""
HOT_FRACTION = "() => { const b = window.__app.brain; let n = 0; for (const x of b.s) if (x >= 0.5) n++; return n / b.n; }"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def launch(p, executable: str | None):
    """Playwright's Chromium on SwiftShader, as tools/scenario_fish.py launches it."""
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


def larva_time(page, t: float, timeout: int = 180000) -> None:
    page.wait_for_function(f"window.__app.life.time >= {t}", timeout=timeout)


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def open_page(browser, url: str, errors: list[str]):
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.__app && (window.__app.ready || window.__app.errors.length)", timeout=120000)
    if not page.evaluate("window.__app.ready"):
        raise RuntimeError("the page did not become ready: " + "; ".join(page.evaluate("window.__app.errors")))
    return page


def place(page, position: list[float], heading: float, rest: bool = True) -> None:
    """The body at a position and heading; `rest` also rests the net and clears its stimuli, as the node check does."""
    page.evaluate("([p, h, rest]) => { const a = window.__app; a.life.body.reset(p, h); if (rest) { a.brain.reset(); a.brain.clearStimuli(); } }", [position, heading, rest])


def lamp_beside(page, side: int, z: float | None = None) -> dict:
    """The lamp beside the larva on `side` (+1 its left, -1 its right), from its heading; `z`
    sets the lamp's height, else LAMP_ABOVE above the larva."""
    s = page.evaluate("window.__app.state()")
    x, y, lz = s["position"]
    h = s["heading"]
    fx, fy, lx, ly = math.cos(h), math.sin(h), -math.sin(h), math.cos(h)
    light = {"on": True, "x": x + LAMP_AHEAD * fx + side * LAMP_SIDE * lx, "y": y + LAMP_AHEAD * fy + side * LAMP_SIDE * ly, "z": lz + LAMP_ABOVE if z is None else z}
    page.evaluate("(L) => window.__app.setLight(L)", light)
    return light


def track(page, seconds: float, poll_ms: int = 40) -> dict:
    """The course over `seconds` of larva time, sampled every poll: the heading change split by
    sign (a pane reflection, a jump past 60 degrees in one sample, is left out and counted), the
    eyes' mean levels, the peak arrest."""
    first = page.evaluate(SAMPLE)
    t0, h_prev, refl0 = first["t"], first["heading"], first["reflections"]
    plus = minus = 0.0
    eye_l = eye_r = 0.0
    n = jumps = 0
    arrest_peak = 0.0
    last = first
    while True:
        page.wait_for_timeout(poll_ms)
        s = page.evaluate(SAMPLE)
        d = wrap(s["heading"] - h_prev)
        h_prev = s["heading"]
        if abs(d) > math.pi / 3:
            jumps += 1
        elif d > 0:
            plus += d
        else:
            minus -= d
        eye_l += s["eyes"][0]
        eye_r += s["eyes"][1]
        arrest_peak = max(arrest_peak, s["command"]["arrest"])
        n += 1
        last = s
        if s["t"] >= t0 + seconds:
            break
    total = plus - minus
    return {
        "seconds": last["t"] - t0, "samples": n, "turn_deg": math.degrees(total), "turned_left_deg": math.degrees(plus), "turned_right_deg": math.degrees(minus),
        "one_sign": bool((plus >= minus and minus <= 0.1 * plus) or (minus > plus and plus <= 0.1 * minus)),
        "reflections": last["reflections"] - refl0 + jumps, "eye_left_mean": eye_l / n, "eye_right_mean": eye_r / n, "arrest_peak": arrest_peak,
        "command_end": last["command"], "z_end": last["z"],
    }


def tap_window(page, tap: bool) -> dict:
    """From the node check's start, one second of life, then (with or without a tap on the left
    pane) the arrest over 0.5 s and the height a second later."""
    place(page, *TAP_PLACE)
    t0 = page.evaluate("window.__app.life.time")
    larva_time(page, t0 + 1.0)
    before = page.evaluate(SAMPLE)
    if tap:
        page.evaluate("window.__app.tap(-1)")
    t_tap = before["t"]
    peak = 0.0
    first_above = None
    parapodia = 0.0
    while True:
        page.wait_for_timeout(30)
        s = page.evaluate(SAMPLE)
        peak = max(peak, s["command"]["arrest"])
        parapodia = max(parapodia, s["command"]["parapodia"])
        if first_above is None and s["command"]["arrest"] > 0.3:
            first_above = s["t"] - t_tap
        if s["t"] >= t_tap + 0.5:
            break
    larva_time(page, t_tap + 1.0)
    after = page.evaluate(SAMPLE)
    return {
        "tap": tap, "pane": "left" if tap else None, "arrest_before": before["command"]["arrest"], "arrest_peak_0_5s": peak, "arrest_above_0_3_after_s": first_above,
        "arrest_1s": after["command"]["arrest"], "parapodia_peak_0_5s": parapodia, "z_before_mm": before["z"], "z_1s_mm": after["z"], "z_change_1s_mm": after["z"] - before["z"],
        "on_floor_1s": after["on_floor"], "seconds": after["t"] - t_tap,
    }


def checks(page) -> dict:
    out: dict = {}
    const = page.evaluate(CONSTANTS)
    out["constants"] = const
    page.wait_for_function("window.__app.life.steps > 50", timeout=120000)
    page.evaluate("window.__app.setUv(0)")

    # (a) a lamp beside the larva, one side then the other: the course bends toward one side, then the other
    lamps = {}
    for name, side in (("left", 1), ("right", -1)):
        place(page, *LAMP_PLACE)
        light = lamp_beside(page, side)
        lamps[name] = {"lamp": light, **track(page, 3.0)}
        lamps[name]["hot_fraction"] = page.evaluate(HOT_FRACTION)
        page.evaluate("window.__app.setLight({ on: false })")
    left, right = lamps["left"], lamps["right"]
    lit_left = "left" if left["eye_left_mean"] > left["eye_right_mean"] else "right"
    lit_right = "left" if right["eye_left_mean"] > right["eye_right_mean"] else "right"
    out["lamp"] = {
        "left": left, "right": right, "lit_eye_left_lamp": lit_left, "lit_eye_right_lamp": lit_right,
        "conditions": {"body_placed": {"position": LAMP_PLACE[0], "heading": LAMP_PLACE[1]}, "brain_rested": True, "uv": 0, "lamp_offset_mm": {"side": LAMP_SIDE, "ahead": LAMP_AHEAD, "above": LAMP_ABOVE}, "seconds": 3.0},
        "pass": bool(lit_left != lit_right and left["one_sign"] and right["one_sign"] and abs(left["turn_deg"]) > 1 and abs(right["turn_deg"]) > 1
                     and math.copysign(1, left["turn_deg"]) == -math.copysign(1, right["turn_deg"]) and left["reflections"] == 0 and right["reflections"] == 0
                     and left["hot_fraction"] <= 0.05 and right["hot_fraction"] <= 0.05),
    }
    page.evaluate("window.__app.setLight({ on: true, x: 10, y: 5, z: 13 })")

    # (b) a tap on the glass: the control window first, then the tap
    control = tap_window(page, False)
    tapped = tap_window(page, True)
    out["tap"] = {
        "control": control, "tap": tapped,
        "tap_effect": {"arrest_peak_0_5s": tapped["arrest_peak_0_5s"] - control["arrest_peak_0_5s"], "arrest_1s": tapped["arrest_1s"] - control["arrest_1s"], "z_change_1s_mm": tapped["z_change_1s_mm"] - control["z_change_1s_mm"]},
        "conditions": {"body_placed": {"position": TAP_PLACE[0], "heading": TAP_PLACE[1]}, "brain_rested": True, "seconds_before_tap": 1.0, "uv": 0},
        "pass": bool(tapped["arrest_peak_0_5s"] > 0.3 and tapped["z_1s_mm"] < tapped["z_before_mm"]),
    }

    # (c) the brain off: the baseline beat, no arrest, no muscles, no turn, no step
    place(page, *OFF_PLACE, rest=False)
    page.evaluate("window.__app.setBrain(false)")
    t0 = page.evaluate("window.__app.life.time")
    steps0 = page.evaluate("window.__app.brain.steps")
    larva_time(page, t0 + 1.0)
    first = page.evaluate(SAMPLE)
    larva_time(page, t0 + 3.0)
    last = page.evaluate(SAMPLE)
    activity_max = page.evaluate("() => { let m = 0; for (const x of window.__app.brain.s) if (x > m) m = x; return m; }")
    c0, c1 = first["command"], last["command"]
    turn = math.degrees(wrap(last["heading"] - first["heading"]))
    base = const["baseline_beat"]
    out["brain_off"] = {
        "command_1s": c0, "command_3s": c1, "baseline_beat": base, "turn_deg_1s_to_3s": turn, "reflections": last["reflections"] - first["reflections"],
        "brain_steps_while_off": last["brain_steps"] - steps0, "activity_max": activity_max,
        "pass": bool(all(abs(c[k] - base) < 1e-9 for c in (c0, c1) for k in ("ciliaLeft", "ciliaRight")) and all(c[k] == 0 for c in (c0, c1) for k in ("arrest", "muscleLeft", "muscleRight", "parapodia"))
                     and abs(turn) < 1e-6 and last["reflections"] == first["reflections"] and last["brain_steps"] == steps0 and activity_max == 0),
    }
    page.evaluate("window.__app.setBrain(true)")

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
    """The screenshot with the brain view and the bloom on: the hardware renderer first. The
    larva near the surface with the lamp on its left, a second and a half later, so the eye
    circuit is lit and the course is bending."""
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
            larva_time(page, 2.0)
            page.evaluate("window.__app.setUv(0)")
            place(page, *LAMP_PLACE)
            light = lamp_beside(page, 1, z=SHOT_LAMP_Z)
            t_shot = page.evaluate("window.__app.life.time") + 1.5
            larva_time(page, t_shot)
            f0 = page.evaluate("window.__app.S.totalFrames")
            w0 = time.time()
            page.wait_for_timeout(3000)
            frames = page.evaluate("window.__app.S.totalFrames") - f0
            seconds = time.time() - w0
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out))
            info = {
                "path": str(out), "launch": name, "browser": browser.version, "renderer": renderer, "fps": frames / seconds, "lamp": light,
                "active_skeletons": page.evaluate("window.__app.brainView.activeCount"), "active_cells": page.evaluate("window.__app.brainView.vectorActiveCount"), "skeletons": page.evaluate("window.__app.brainView.n"),
                "heading_deg": math.degrees(page.evaluate("window.__app.state().heading")), "command": page.evaluate("window.__app.command()"), "larva_seconds": page.evaluate("window.__app.life.time"),
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
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots" / "larva.png")
    ap.add_argument("--receipt", type=Path, default=ROOT / "receipts" / "scenario_larva.json")
    ap.add_argument("--executable", default=None)
    ap.add_argument("--no-screenshot", action="store_true")
    args = ap.parse_args()
    server = None
    url = args.url
    if url is None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/web/index.html"
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
            passed = [receipt["checks"][k]["pass"] for k in ("lamp", "tap", "brain_off")] + [not page_errors]
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
    a, b, o, f = c["lamp"], c["tap"], c["brain_off"], c["fps"]
    print(f"chromium {receipt['browser']} via {receipt['launch']} on {receipt['renderer']}")
    print(f"{'ok  ' if a['pass'] else 'FAIL'} lamp: left {a['left']['turn_deg']:+.1f} deg (eyes {a['left']['eye_left_mean']:.2f}/{a['left']['eye_right_mean']:.2f}), right {a['right']['turn_deg']:+.1f} deg (eyes {a['right']['eye_left_mean']:.2f}/{a['right']['eye_right_mean']:.2f}) over 3 s, "
          f"one sign {a['left']['one_sign']} and {a['right']['one_sign']}, hot fraction {max(a['left']['hot_fraction'], a['right']['hot_fraction']):.3f}")
    print(f"{'ok  ' if b['pass'] else 'FAIL'} tap: arrest {b['tap']['arrest_before']:.3f} -> peak {b['tap']['arrest_peak_0_5s']:.3f} within 0.5 s (above 0.3 after {b['tap']['arrest_above_0_3_after_s']} s), z {b['tap']['z_before_mm']:.2f} -> {b['tap']['z_1s_mm']:.2f} mm in 1 s; "
          f"control without a tap: peak {b['control']['arrest_peak_0_5s']:.3f}, z change {b['control']['z_change_1s_mm']:+.3f} mm; the tap's own effect {b['tap_effect']['arrest_peak_0_5s']:+.3f} on the arrest, {b['tap_effect']['z_change_1s_mm']:+.3f} mm")
    print(f"{'ok  ' if o['pass'] else 'FAIL'} brain off: cilia {o['command_3s']['ciliaLeft']:.3f}/{o['command_3s']['ciliaRight']:.3f} at the baseline {o['baseline_beat']}, arrest {o['command_3s']['arrest']}, turn {o['turn_deg_1s_to_3s']:.4f} deg over 2 s, {o['brain_steps_while_off']} brain steps, activity max {o['activity_max']}")
    print(f"ok   fps: {f['fps']:.1f} over {f['seconds']} s ({f['frames']} frames), brain step {c['summary']['ms_per_brain_step']:.3f} ms, {c['summary']['brain_steps']} brain steps in {c['summary']['larva_seconds']:.1f} larva seconds")
    print(("ok   " if not page_errors else "FAIL ") + (f"{len(page_errors)} browser errors: " + " | ".join(page_errors) if page_errors else "no page or console errors"))
    if "screenshot" in receipt:
        s = receipt["screenshot"]
        print(f"ok   screenshot {s['path']} ({s['bytes'] / 1e3:.0f} kB) via {s['launch']} on {s['renderer']} at {s['fps']:.1f} fps, {s['active_skeletons']} of {s['skeletons']} skeletons lit, {s['active_cells']} cells at or above 0.05" + (f", errors: {s['errors']}" if s["errors"] else ""))
    print(f"receipt {args.receipt}")
    print(f"{'all passed' if receipt['passed'] else 'FAILED'} in {receipt['seconds']} s")
    raise SystemExit(0 if receipt["passed"] else 1)


if __name__ == "__main__":
    main()
