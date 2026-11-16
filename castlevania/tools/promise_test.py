"""The claim of the Castlevania page, played on the page itself in headless Chromium.

    python castlevania/tools/promise_test.py --out castlevania/evidence/promise_test-<date>.json [--live 40] [--shots DIR]

The claim (site.json): a frozen Cadence brain plays from what its eye sees, with a memory of this
game's moments and a state it carries from move to move; a look-ahead on the emulator checks its
moves near enemies: stage 3 on all nine starts, lives lost 36 to 5. The page is served from
player/ by itself, as the demos site serves it, and a scripted visitor checks:

  1. the numbers the claim quotes are the ones in evidence/lookahead_receipt.json (stage 3 on 9 of
     9 selection starts with the look-ahead, 3 of 9 without; lives lost 36 without, 5 with);
  2. brain + look-ahead is the page's first recording: the highlights video named in the pack's
     manifest loads, matches its SHA-256 and plays;
  3. brain alone: the brain view follows the video (the decision it shows is the one the video is
     on, after playing and after a seek), and its recall memory fills with moments of this game
     as the game goes (slots held early and late in the game);
  4. live: the brain itself runs in the tab on the recorded eye inputs, from the game's start, and
     presses the recorded buttons on every decision checked; the time a decision takes is
     recorded beside the 200 ms the game allows, with the machine's load average;
  5. no console error, page error or failed request.
Writes one JSON record to --out.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "player"))
from check_player import RangeHandler  # noqa: E402  (static files with byte ranges, as a host serves video)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--live", type=int, default=40, help="decisions live mode settles and compares")
    ap.add_argument("--shots", type=Path)
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    meta = json.loads((HERE / "site.json").read_text())
    record: dict = {"schema": "castlevania-promise/1", "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "claim": meta["feature"], "checks": [], "errors": [], "load_average": list(os.getloadavg())}

    def check(name: str, ok: bool, detail=None) -> None:
        record["checks"].append({"name": name, "passed": bool(ok), "detail": detail})
        print(("ok   " if ok else "FAIL ") + name, "" if ok else json.dumps(detail, default=str)[:300], flush=True)

    # 1. the numbers
    la = json.loads((HERE / "evidence" / "lookahead_receipt.json").read_text())["selection"]
    alone, look = la["brain_alone"], la["brain_lookahead"]
    check("claim_numbers_are_the_evidence",
          (look["stage3"], alone["stage3"], alone["lives_lost_total"], look["lives_lost_total"], len(la["starts"])) == (9, 3, 36, 5, 9)
          and "stage 3 on all nine starts" in meta["feature"] and "36 to 5" in meta["feature"] and "not beaten" in meta["tagline"],
          {"starts": la["starts"], "stage3": [alone["stage3"], look["stage3"]], "lives_lost": [alone["lives_lost_total"], look["lives_lost_total"]]})

    handler = functools.partial(RangeHandler, directory=str(HERE / "player"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    began = time.monotonic()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
            page = browser.new_page(viewport={"width": 1512, "height": 860})
            page.on("console", lambda m: record["errors"].append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: record["errors"].append(str(e)))
            page.on("requestfailed", lambda r: record["errors"].append("failed " + r.url) if not r.url.endswith(".mp4") else None)
            page.goto(url)
            # 2. the highlights
            page.wait_for_function("document.getElementById('hl').src.endsWith('castlevania-highlights.mp4')", timeout=60000)
            first = page.evaluate("window.__player.rec")
            digest = page.evaluate("""async () => { const m = await (await fetch('pack/manifest.json')).json();
                const b = await (await fetch('pack/' + m.highlights.file)).arrayBuffer();
                const h = [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map((x) => x.toString(16).padStart(2, '0')).join('');
                return { expected: m.highlights.sha256, got: h, bytes: b.byteLength }; }""")
            page.evaluate("document.getElementById('hl').play()")
            page.wait_for_function("document.getElementById('hl').currentTime > 2", timeout=120000)
            played = page.evaluate("document.getElementById('hl').currentTime")
            check("the_first_recording_is_brain_plus_lookahead_and_plays", first == "lookahead" and digest["got"] == digest["expected"] and played > 2,
                  {"first": first, "digest": digest, "played_s": played})
            if args.shots:
                page.wait_for_timeout(1500)
                page.screenshot(path=str(args.shots / "promise-highlights.png"))

            # 3. brain alone: the view follows the video; the memory fills
            page.click("[data-rec='alone']")
            page.wait_for_function("window.__player.ready === true && document.getElementById('video').readyState >= 2", timeout=120000)
            on_step = """() => { const s = window.__player, v = document.getElementById('video');
                return { time: v.currentTime, decision: s.decision, shown: s.shown, expected: Math.floor(v.currentTime * 60 / 12),
                         held: (trace.decisions[s.shown] || {snap: {}}).snap.memory?.held ?? null }; }"""
            page.evaluate("document.getElementById('video').play()")
            page.wait_for_timeout(4000)
            early = page.evaluate(on_step)
            page.evaluate("document.getElementById('video').currentTime = 150")
            page.wait_for_timeout(2000)
            late = page.evaluate(on_step)
            follows = all(s["shown"] == s["decision"] and abs(s["decision"] - s["expected"]) <= 1 for s in (early, late))
            check("the_brain_view_follows_the_video", follows, {"early": early, "late": late})
            curve = page.evaluate("""() => [0, 10, 50, 100, 127, 200, 500, 750].filter((k) => k < trace.decisions.length)
                .map((k) => [k, trace.decisions[k].snap.memory.held, trace.decisions[k].snap.memory.capacity])""")
            record["memory_held_by_decision"] = curve
            check("its_recall_memory_fills_with_moments_of_the_game", curve[0][1] < 8 and curve[-1][1] == curve[-1][2] and all(a[1] <= b[1] for a, b in zip(curve, curve[1:])),
                  curve)
            if args.shots:
                page.evaluate("document.getElementById('video').pause()")
                page.wait_for_timeout(1500)
                page.screenshot(path=str(args.shots / "promise-brain-alone.png"))

            # 4. live
            page.evaluate("const v = document.getElementById('video'); v.pause(); v.currentTime = 0")
            page.wait_for_timeout(500)
            t0 = time.monotonic()
            page.click("#live")
            try:
                page.wait_for_function("window.__player.live.ready === true || document.getElementById('live-status').textContent.startsWith('live mode stopped')", timeout=900000)
            except Exception:  # noqa: BLE001 - recorded below
                pass
            ready = page.evaluate("window.__player.live.ready")
            record["live_load_seconds"] = round(time.monotonic() - t0, 1)
            if ready and args.live:
                page.evaluate("document.getElementById('video').play()")
                page.wait_for_function(f"window.__player.live.checked >= {args.live}", timeout=900000)
                L = page.evaluate("""() => { const L = window.__player.live;
                    return { checked: L.checked, matches: L.matches, ms: L.ms.slice(), status: document.getElementById('live-status').textContent }; }""")
                ms = statistics.median(L["ms"]) if L["ms"] else None
                record["live"] = {"decisions": L["checked"], "matches": L["matches"], "ms_per_decision_median": ms and round(ms, 1),
                                  "real_time_needs_ms": 200, "status": L["status"], "load_average": list(os.getloadavg())}
                check("live_the_brain_runs_in_the_tab_and_presses_the_recorded_buttons", L["matches"] == L["checked"] >= args.live,
                      record["live"])
                if args.shots:
                    page.screenshot(path=str(args.shots / "promise-live.png"))
            else:
                check("live_the_brain_runs_in_the_tab_and_presses_the_recorded_buttons", False,
                      {"status": page.inner_text("#live-status"), "load_seconds": record["live_load_seconds"]})
            browser.close()
    except Exception as error:  # noqa: BLE001 - the record names it
        check("runner_completed", False, f"{type(error).__name__}: {error}")
    finally:
        server.shutdown()
    check("no_console_error_page_error_or_failed_request", not record["errors"], record["errors"][:5])
    record["seconds"] = round(time.monotonic() - began, 1)
    record["passed"] = all(c["passed"] for c in record["checks"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1, default=str) + "\n")
    print("PASS" if record["passed"] else "FAIL", f"{sum(c['passed'] for c in record['checks'])} of {len(record['checks'])}", "->", args.out)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
