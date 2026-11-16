"""The Robot Arm page's promise on the real page, in headless Chromium: move the target bin while
the arm carries the block, and the block lands in the moved bin.

    python robot-arm/tools/promise_moved_bin.py [--shots DIR] [--speed 1] [--out FILE]

Serves robot-arm/site on a free port and works the page as a visitor does, with the mouse. Each
scenario puts the bins at their trained places, clicks the target's button, presses Run, waits
until the hand holds the block and has lifted it (or has carried it half the way across to the
bin), then presses on the target bin, drags it to a new place on the table and lets go. It passes when the page's result line names the target bin
and the block rests inside the bin where it was moved. The new places are places where the brain
placed 19 or 20 of 20 blocks with the bin put there before the trial (evidence/moved_bins.jsonl).
A last scenario clicks the other bin's button while the arm carries the block (the target
changes mid-carry) and passes when the block lands in that bin.

Writes a new file, robot-arm/evidence/promise_moved_bin-<date>-<time>.json (or --out); it never
writes over an existing file. Exit 1 when a scenario fails.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ARM = Path(__file__).resolve().parents[1]
SITE = ARM / "site"
BIN_HOME = {"A": (0.62, -0.22), "B": (0.62, 0.22)}
HALF_BIN = 0.065  # the bin's inner half-width (BIN_SIDE / 2 in site/sim.js)
# The target, where the visitor drags it, and when: "lifted" as soon as the hand has lifted the
# block, "halfway" once the hand has covered half the way across to the bin's trained place.
SCENARIOS = [
    {"kind": "move", "target": "A", "to": (0.70, -0.06), "when": "lifted"},
    {"kind": "move", "target": "B", "to": (0.62, 0.08), "when": "lifted"},
    {"kind": "move", "target": "A", "to": (0.62, -0.33), "when": "halfway"},
    {"kind": "move", "target": "A", "to": (0.70, -0.06), "when": "halfway"},
    {"kind": "move", "target": "A", "to": (0.72, -0.22), "when": "lifted"},
    {"kind": "switch", "target": "A", "switch_to": "B", "when": "lifted"},
]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def drag_bin(page, name: str, to: tuple[float, float]) -> dict:
    """Press on bin `name` where a visitor would, drag it so its centre lands on `to`, let go."""
    start = None
    for _ in range(40):  # the arm may hide the bin from the camera for a moment
        start = page.evaluate(f"window.cadenceArm.grabPoint('{name}')")
        if start:
            break
        page.wait_for_timeout(100)
    if not start:
        return {"grabbed": False}
    before = page.evaluate(f"window.cadenceArm.cell.bins['{name}'].slice()")
    grab = page.evaluate(f"window.cadenceArm.tableAt({start[0]}, {start[1]})")
    offset = (before[0] - grab[0], before[1] - grab[1])
    aim = (to[0] - offset[0], to[1] - offset[1])
    end = page.evaluate(f"window.cadenceArm.screenOf({aim[0]}, {aim[1]}, 0)")
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=24)
    for _ in range(4):  # correct by what the bin did (the page keeps it inside the tested band)
        now = page.evaluate(f"window.cadenceArm.cell.bins['{name}'].slice()")
        err = (to[0] - now[0], to[1] - now[1])
        if abs(err[0]) < 0.004 and abs(err[1]) < 0.004:
            break
        cur = page.evaluate(f"window.cadenceArm.tableAt({end[0]}, {end[1]})")
        end = page.evaluate(f"window.cadenceArm.screenOf({cur[0] + err[0]}, {cur[1] + err[1]}, 0)")
        page.mouse.move(*end, steps=4)
    page.mouse.up()
    after = page.evaluate(f"window.cadenceArm.cell.bins['{name}'].slice()")
    return {"grabbed": True, "from": [round(v, 3) for v in before], "to": [round(v, 3) for v in after]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shots", type=Path, help="save screenshots of each scenario here")
    ap.add_argument("--speed", type=int, default=1, choices=(1, 2, 4), help="the page's speed button (1 is real time)")
    ap.add_argument("--out", type=Path, help="the evidence file (default: a new file in robot-arm/evidence/)")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args()
    out = args.out or ARM / "evidence" / f"promise_moved_bin-{time.strftime('%Y%m%d-%H%M')}.json"
    if out.exists():
        raise SystemExit(f"{out} exists; evidence files are never written over")
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SITE / "pack" / "manifest.json").read_text())
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ARM, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    report: dict = {"schema": "cadence-arm-promise/1", "checked": time.strftime("%Y-%m-%d %H:%M"), "commit": commit,
                    "cadence": manifest.get("cadence"), "brain_sha256": manifest.get("brain_sha256"),
                    "load_average": [round(v, 1) for v in os.getloadavg()], "speed": args.speed,
                    "viewport": [1280, 800], "scenarios": []}
    errors: list[str] = []
    server, port = serve()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            began = time.time()
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_function("document.body.dataset.ready === '1'", timeout=args.timeout * 1000)
            report["brain_ready_s"] = round(time.time() - began, 1)
            page.click(f".speed .seg[data-speed='{args.speed}']")
            if args.shots:
                page.wait_for_timeout(600)
                page.screenshot(path=str(args.shots / "0-ready.png"))
            for n, sc in enumerate(SCENARIOS, 1):
                target = sc["target"]
                page.evaluate("(home) => { const a = window.cadenceArm; for (const k of ['A', 'B']) a.cell.moveBin(k, home[k][0], home[k][1]);"
                              " a.state.thinkMs = []; a.play.expected = 0; a.play.shown = 0; document.body.dataset.result = ''; }",
                              {k: list(v) for k, v in BIN_HOME.items()})
                page.click(f"#target-{target}")
                page.click("#run")
                page.mouse.move(700, 110)  # off the buttons, so no explanation card covers the screenshots
                page.wait_for_function("window.cadenceArm.cell.holding === true && window.cadenceArm.cell.blockPos()[2] > 0.08",
                                       timeout=args.timeout * 1000)
                if sc["when"] == "halfway":
                    page.wait_for_function("([y0, by]) => { const a = window.cadenceArm; return a.state.phase !== 'running'"
                                           " || (a.cell.holding && Math.abs(a.cell.tip()[1] - by) < 0.5 * Math.abs(y0 - by)); }",
                                           arg=[page.evaluate("window.cadenceArm.cell.tip()[1]"), BIN_HOME[target][1]],
                                           timeout=args.timeout * 1000)
                at = page.evaluate("({ decision: window.cadenceArm.state.decision, hand: window.cadenceArm.cell.tip().map(v => Math.round(v * 1000) / 1000),"
                                   " coach: document.body.dataset.coach })")
                if args.shots:
                    page.screenshot(path=str(args.shots / f"{n}-carry.png"))
                row = {"kind": sc["kind"], "when": sc["when"], "target": target, "carrying_at_decision": at["decision"], "hand_at_change": at["hand"],
                       "coach_while_carrying": at["coach"]}
                if sc["kind"] == "move":
                    row.update(drag_bin(page, target, sc["to"]))
                    row["asked"] = list(sc["to"])
                    moves = page.evaluate("(window.cadenceArm.state.moves || []).map(m => m.decision)")
                    row["moved_during_decisions"] = [min(moves), max(moves)] if moves else None
                    expect = target
                else:
                    page.click(f"#target-{sc['switch_to']}")
                    row["switched_to"] = sc["switch_to"]
                    expect = sc["switch_to"]
                if args.shots:
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(args.shots / f"{n}-after.png"))
                page.wait_for_function("document.body.dataset.result && document.body.dataset.result !== 'still'", timeout=args.timeout * 1000)
                result = page.evaluate("document.body.dataset.result")
                block = page.evaluate("Array.from(window.cadenceArm.cell.blockPos())")
                bin_xy = page.evaluate(f"window.cadenceArm.cell.bins['{expect}'].slice()")
                inside = abs(block[0] - bin_xy[0]) <= HALF_BIN and abs(block[1] - bin_xy[1]) <= HALF_BIN and block[2] < 0.06
                ms = sorted(page.evaluate("(window.cadenceArm.state.thinkMs || []).slice()"))
                shown = page.evaluate("window.cadenceArm.play.shown / Math.max(1e-9, window.cadenceArm.play.expected)")
                row.update({"result": result, "decisions": int(page.evaluate("document.body.dataset.decisions")),
                            "bin": [round(v, 3) for v in bin_xy], "block": [round(v, 3) for v in block], "block_in_bin": inside,
                            "think_ms_median": ms[len(ms) // 2] if ms else None, "arm_time_shown_share": round(shown, 3),
                            "passed": result.startswith(f"Placed in bin {expect}") and inside and row.get("grabbed", True)})
                if args.shots:
                    page.wait_for_timeout(800)
                    page.screenshot(path=str(args.shots / f"{n}-end.png"))
                report["scenarios"].append(row)
                print(("ok    " if row["passed"] else "FAIL  ") + json.dumps(row), flush=True)
            browser.close()
    finally:
        server.shutdown()
    loader = ("still waiting on run dependencies", "dependency: ", "(end of list)")
    report["console_errors"] = [e for e in errors if not e.startswith(loader)][:5]
    report["passed"] = all(s["passed"] for s in report["scenarios"]) and not report["console_errors"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as f:
        f.write(json.dumps(report, indent=1) + "\n")
    print(("PASS" if report["passed"] else "FAIL") + f"  {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
