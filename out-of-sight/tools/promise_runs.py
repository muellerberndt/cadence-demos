"""The promise on the two scene files, replayed on the page three times each.

    python tools/promise_runs.py            # from out-of-sight/; writes evidence/promise_runs-<date>-<time>-<wheel>.json

Each run replays a scene file of the tracking chamber on the page (``promise`` of
``tools/check_page.py``): the map emptied, then the file's camera reports, with the page's own
rule for which of the map's cells the camera sees. The map holds no randomness, so the three runs
of a file read alike; the moment's milliseconds differ. Each run of the tool writes a file of its
own, named by its date, time and the wheel's SHA-256 (first 8 characters); ``--out`` names another.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import check_page as check
from playwright.sync_api import sync_playwright

CM = lambda v: "-" if v is None else f"{100 * v:.1f} cm"
SCENE = {"default": "arm folded", "merged": "arm's shadow joined to the pillar's"}


def table(runs: list[dict]) -> str:
    """The runs as the README's table."""
    lines = ["| Scene | In view | Hidden, mean | Last seen, hidden | Kalman filter, hidden | Cells hold the hand | Cells, mean | After return | A moment |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        lines.append(f"| {SCENE.get(r['scene'], r['scene'])} | {CM(r['in_view_m'])} | {CM(r['hidden_m'])} | {CM(r['last_seen_hidden_m'])} | {CM(r['kalman_hidden_m'])} | "
                     f"{r['cells_hold']:.2f} | {r['cells_mean']:.0f} | {CM(r['return_m'])} | {r['think_ms']:.1f} ms |")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--runs", type=int, default=3)
    a = p.parse_args()
    url, server = check.serve(check.SITE)
    runs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=check.GPU)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(url + "?sound=0&tour=0", wait_until="domcontentloaded")
        check.ready(page, 300)
        for scene in check.SCENES:
            for _ in range(a.runs):
                run = check.promise(page, scene)
                runs.append(run)
                print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in run.items()}), flush=True)
        browser.close()
    server.shutdown()
    manifest = json.loads((check.SITE / "pack" / "manifest.json").read_text())

    a.out = a.out or check.HERE / "evidence" / f"promise_runs-{time.strftime('%Y%m%d-%H%M')}-{manifest['wheel_sha256'][:8]}.json"
    a.out.write_text(json.dumps({"schema": "cadence-out-of-sight-promise-runs/4", "map": manifest.get("map"), "wheel_sha256": manifest.get("wheel_sha256"),
                                 "wheel_source": manifest.get("wheel_source"), "runs": runs}, indent=1) + "\n")
    print(table(runs))
    print(f"evidence in {a.out}")


if __name__ == "__main__":
    main()
