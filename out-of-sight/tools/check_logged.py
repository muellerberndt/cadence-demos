"""The page check, with the map's apple logged moment by moment on the desktop page.

    python tools/check_logged.py --log apple.json [--shots shots]     # from out-of-sight/

Runs ``tools/check_page.py`` as it is (its evidence goes to a file of its own in ``evidence/``)
and records, at every moment of the desktop page, the camera's heading, whether the camera
reports the apple, the tutorial's step and every apple entry on the map (its state, cells, place
and moments since a sense wrote it). At the end it prints each change of the apple's state with
the moments around it, and the largest step of the camera's heading between two moments.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_page as cp

HOOK = """() => { if (window.__log) return; window.__log = []; let m = -1;
  setInterval(() => { const o = window.outOfSight, r = o.state.record; if (!r || r.moment === m) return; m = r.moment;
    const k = o.stage.names.indexOf('apple');
    const a = o.state.inventory.filter((e) => e.name === 'apple').map((e) => ({ state: e.state, cells: e.cells.length, place: e.place, since: e.since }));
    window.__log.push({ m, tour: document.body.dataset.tour || '', h: +o.stage.geometry.camera.heading.toFixed(4), on: o.stage.cameraOn,
      seen: r.in_view[k], report: r.report[k], truth: r.truth[k], apple: a }); }, 4); }"""


def summary(log: list[dict]) -> None:
    previous = None
    for k, row in enumerate(log):
        state = "|".join(f"{e['state']}:{e['cells']}" for e in row["apple"])
        if previous is not None and state.split(":")[0] != previous.split(":")[0]:
            print(f"-- the apple at moment {row['m']} ({row['tour']}): {previous} -> {state}")
            for q in log[max(0, k - 3): k + 2]:
                print(f"   moment {q['m']} heading {q['h']:+.4f} reported {q['seen']} "
                      f"{[(e['state'], e['cells'], e['place'] and [round(v, 3) for v in e['place']]) for e in q['apple']]}")
        previous = state
    headings = [row["h"] for row in log]
    steps = [abs(math.atan2(math.sin(b - a), math.cos(b - a))) for a, b in itertools.pairwise(headings)]
    print(f"moments {len(log)}; the largest step of the camera's heading between moments {max(steps, default=0.0):.3f} rad")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--shots", default=None)
    a = p.parse_args()
    pages: list = []
    ready, tutorial, moved = cp.ready, cp.tutorial, cp.kept_and_moved

    def dump() -> None:
        if pages:
            a.log.write_text(json.dumps(pages[0].evaluate("window.__log")))

    def logged_ready(page, timeout_s):
        seconds = ready(page, timeout_s)
        if not pages:  # the desktop page, the first to load
            page.evaluate(HOOK)
            pages.append(page)
        return seconds

    def logged_tutorial(page, c, cell):
        try:
            return tutorial(page, c, cell)
        finally:
            dump()

    def logged_moved(page, c, cell):
        try:
            return moved(page, c, cell)
        finally:
            dump()

    cp.ready, cp.tutorial, cp.kept_and_moved = logged_ready, logged_tutorial, logged_moved
    sys.argv = [sys.argv[0]] + (["--shots", a.shots] if a.shots else [])
    code = cp.main()
    if a.log.exists():
        summary(json.loads(a.log.read_text()))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
