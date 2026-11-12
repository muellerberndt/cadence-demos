"""The promise scenario, read several times with lessons on and with lessons off.

    python tools/promise_runs.py            # from out-of-sight/; writes evidence/promise_runs.json

Each run is the scripted scenario of ``tools/check_page.py`` (``scripted``): the brain as it
arrives, the same route by scene steps, the same seed. Three runs with lessons on, three off.
Where the pack's library takes the sight evidence (``Space.observe(in_sight=)``), the six runs
are read with it and again without it. ``--out`` writes the runs to another file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

import check_page as check

CM = lambda v: "-" if v is None else f"{100 * v:.1f} cm"  # noqa: E731


def table(runs: list[dict]) -> str:
    """The runs as the README's table."""
    lines = ["| Sight evidence | Lessons | In view | Hidden, mean | Hidden, last | Circle holds the hand | Circle's radius | Held back | After return | Lessons taken | A moment |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        held = "-" if not r["held_moments"] else f"{r['held_moments']} moments, from hidden moment {r['first_held'] + 1}"
        lines.append(f"| {'given' if r['sight'] else 'none'} | {'on' if r['teach'] else 'off'} | {CM(r['in_view_m'])} | {CM(r['hidden_m'])} | {CM(r['hidden_last_m'])} | "
                     f"{r['inside_circle']:.2f} | {CM(r['radius_first_m'])} to {CM(r['radius_last_m'])} | {held} | {CM(r['return_m'])} | {r['lessons']} | {r['think_ms']:.0f} ms |")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, default=check.HERE / "evidence" / "promise_runs.json")
    a = p.parse_args()
    url, server = check.serve(check.SITE)
    runs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=check.GPU)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(url + "?sound=0&tour=0", wait_until="domcontentloaded")
        check.ready(page, 300)
        takes = bool(page.evaluate("window.outOfSight.state.takesSight"))
        for sight in ((True, False) if takes else (None,)):
            for teach in (True, True, True, False, False, False):
                run = check.scripted(page, teach, sight=sight)
                runs.append(run)
                print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in run.items()}), flush=True)
        browser.close()
    server.shutdown()
    manifest = json.loads((check.SITE / "pack" / "manifest.json").read_text())
    a.out.write_text(json.dumps({"schema": "cadence-out-of-sight-promise-runs/2", "module": manifest.get("module"), "wheel_sha256": manifest.get("wheel_sha256"),
                                 "library_takes_sight_evidence": takes, "runs": runs}, indent=1) + "\n")
    print(table(runs))
    hidden = runs[0]
    print(f"On the same rows: last seen {CM(hidden['last_seen_hidden_m'])}, Kalman filter {CM(hidden['kalman_hidden_m'])}; bounds: hidden {CM(check.HIDDEN)}, circle {check.COVER}")


if __name__ == "__main__":
    main()
