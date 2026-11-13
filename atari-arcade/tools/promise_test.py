"""The promise of the Atari Arcade page, run on the real page in a headless browser: a newborn
brain learns each game by watching the teacher, takes the controls, and then plays whole games of
its own. In Freeway its games score above the teacher's; in Atlantis most of them tie with the
teacher's.

    python tools/promise_test.py --out evidence/promise-<date>.json [--games 5] [--minutes 25]

Serves web/ on a free port (or uses --url), opens the page at 1280 x 800 (both games run), and
reads every state the two brain workers and the two game workers send to the page. It waits until
each brain has played --games whole games at the controls, then checks:

  - both brains are born on the released cadence-net wheel (0.95.2);
  - both watched the teacher (at least 500 lessons) and took the controls;
  - each played --games whole games at the controls, with no fault and no refused decision;
  - the page shows the teacher's score beside the brain's, and the badge leaves "hatchling";
  - Freeway: the mean of the brain's whole games is above the mean of the teacher's games;
  - Atlantis: most of the brain's whole games (their median) score the teacher's mean or more;
  - no page error.

A game the teacher started and the brain finished counts for neither. The game does not wait for
the brain, so a loaded machine means fewer screens seen and a later takeover; the run records the
load average. Needs Playwright and its Chromium. Exit 1 on a failed check.
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
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]

WRAP = """
  const Native = Worker;
  window.Worker = function (url, options) {
    const w = new Native(url, options);
    const u = String(url);
    if (u.includes('brain_worker')) {
      const g = 'brain' + (window.__nb = (window.__nb || 0) + 1);
      w.addEventListener('message', (e) => {
        const d = e.data || {};
        if (d.type === 'state') window.__report(g, JSON.stringify(d.state));
        if (d.type === 'ready') window.__report(g + ':ready', JSON.stringify({cadence: d.graph.cadence, meanings: d.graph.meanings}));
        if (d.type === 'error') window.__report(g + ':error', JSON.stringify(d));
      });
    } else if (u.includes('emulator_worker')) {
      w.addEventListener('message', (e) => {
        const d = e.data || {};
        if (d.type === 'frame' && d.state) {
          const s = d.state, key = 'game:' + s.game;
          const sig = [s.phase, s.episode, (s.returns || []).length, (s.teacher_returns || []).length, s.badge].join('|');
          if (window['__sig' + key] !== sig) {
            window['__sig' + key] = sig;
            window.__report(key, JSON.stringify({game: s.game, phase: s.phase, episode: s.episode, badge: s.badge,
              teacher: s.teacher, teacher_returns: s.teacher_returns || null, returns: s.returns, best: s.best}));
          }
        }
        if (d.type === 'error') window.__report('game:error', JSON.stringify(d));
      });
    }
    return w;
  };
"""


def serve(folder: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=5, help="whole games at the controls, per brain")
    ap.add_argument("--minutes", type=float, default=25.0)
    ap.add_argument("--url", help="a running server for web/")
    ap.add_argument("--out", help="write the readings here (a new evidence file)")
    ap.add_argument("--shot", help="a screenshot of the page at the end")
    args = ap.parse_args()

    server = None
    base = args.url
    if not base:
        server, base = serve(HERE / "web")
    states: dict[str, dict] = {}
    took: dict[str, float] = {}
    errors: list[str] = []
    load = [os.getloadavg()]
    began = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        def report(name: str, text: str) -> None:
            states[name] = json.loads(text)
            if name.startswith("brain") and ":" not in name and states[name].get("phase") == "playing" and name not in took:
                took[name] = round(time.time() - began, 1)

        page.expose_function("__report", report)
        page.add_init_script(WRAP)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(base, wait_until="load")
        done = False
        last_print = 0.0
        while time.time() - began < args.minutes * 60:
            page.wait_for_timeout(3000)
            games = {k: v for k, v in states.items() if k.startswith("game:") and k != "game:error"}
            done = len(games) == 2 and all(len(g.get("returns") or []) >= args.games for g in games.values())
            if time.time() - last_print > 30:
                last_print = time.time()
                load.append(os.getloadavg())
                print(f"{time.time() - began:6.0f} s  " + "  ".join(
                    f"{g['game']}: {g['phase']} teacher {g.get('teacher_returns')} brain {g.get('returns')} {g['badge']}"
                    for g in games.values()), flush=True)
            if done:
                break
        shown = page.evaluate("""() => Object.fromEntries(['freeway', 'atlantis'].map((n) => [n, {
            header: document.getElementById('s-' + n)?.textContent || '',
            badge: document.getElementById('b-' + n)?.textContent || '',
            phase: document.getElementById('p-' + n)?.textContent || ''}]))""")
        if args.shot:
            page.screenshot(path=args.shot)
        browser.close()
    if server:
        server.shutdown()

    brains = {k: v for k, v in states.items() if k.startswith("brain") and ":" not in k}
    ready = {k.split(":")[0]: v for k, v in states.items() if k.endswith(":ready")}
    games = {v["game"]: v for k, v in states.items() if k.startswith("game:") and k != "game:error"}
    mean = lambda xs: round(statistics.mean(xs), 2) if xs else None  # noqa: E731
    per_game = {}
    for name, g in games.items():
        brain_games = list(g.get("returns") or [])
        per_game[name] = {"teacher_games": g.get("teacher_returns"), "teacher_mean": mean(g.get("teacher_returns") or []),
                          "brain_games": brain_games, "brain_mean": mean(brain_games),
                          "brain_median": statistics.median(brain_games) if brain_games else None,
                          "games_at_or_above_the_teacher": sum(x >= (mean(g.get("teacher_returns") or []) or 0) for x in brain_games),
                          "brain_best": g.get("best"),
                          "badge": g.get("badge"), "page_shows": shown.get(name.lower())}
    fw, at = per_game.get("Freeway", {}), per_game.get("Atlantis", {})
    checks = {
        "two_brains_born_on_the_wheel": len(ready) == 2 and all(r.get("cadence") == "0.95.2" for r in ready.values()),
        "both_watched_the_teacher": len(brains) == 2 and all((b.get("watch") or {}).get("lessons", 0) >= 500 for b in brains.values()),
        "both_took_the_controls": len(brains) == 2 and all(b.get("phase") == "playing" for b in brains.values()),
        "whole_games_at_the_controls": done,
        "no_faults_or_refusals": len(brains) == 2 and all(b["brain"]["faults"] == 0 and b["life"]["refused"] == 0 for b in brains.values()),
        "page_shows_teacher_and_badge": all("teacher" in (p.get("page_shows") or {}).get("header", "")
                                            and (p.get("page_shows") or {}).get("badge") not in ("", "hatchling") for p in per_game.values()) and len(per_game) == 2,
        "freeway_above_the_teacher": bool(fw.get("brain_mean") is not None and fw.get("teacher_mean") is not None
                                          and fw["brain_mean"] > fw["teacher_mean"]),
        "atlantis_at_the_teacher": bool(at.get("brain_games") and at.get("teacher_mean") is not None
                                        and statistics.median(at["brain_games"]) >= at["teacher_mean"]),
        "no_page_errors": not errors and not any(k.endswith(":error") for k in states),
    }
    checks["PASS"] = all(checks.values())
    result = {
        "what": "tools/promise_test.py: the Atari Arcade page in headless Chromium, both games, until each brain played "
                f"{args.games} whole games at the controls",
        "checks": checks, "games": per_game,
        "brains": {k: {"phase": v.get("phase"), "takeover": (v.get("watch") or {}).get("takeover"),
                       "took_the_controls_s_after_open": took.get(k), "life": v.get("life"), "brain": v.get("brain")}
                   for k, v in brains.items()},
        "cadence": [r.get("cadence") for r in ready.values()],
        "seconds": round(time.time() - began, 1), "load_average": [[round(x, 1) for x in t] for t in load],
        "page_errors": errors[:10], "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    text = json.dumps(result, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(json.dumps({"checks": checks, "games": {k: {kk: v[kk] for kk in ("teacher_games", "teacher_mean", "brain_games", "brain_mean", "badge")}
                                                  for k, v in per_game.items()}}, indent=1))
    print("PASS" if checks["PASS"] else "FAIL")
    return 0 if checks["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
