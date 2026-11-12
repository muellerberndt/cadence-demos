"""The promise scenario, read several times with lessons on and with lessons off.

    python tools/promise_runs.py            # from out-of-sight/; writes evidence/promise_runs.json

Each run is the scripted scenario of ``tools/check_page.py`` (``scripted``): the brain as it
arrives, the same route by scene steps, the same seed. Three runs with lessons on, three off.
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

import check_page as check


def main() -> None:
    url, server = check.serve(check.SITE)
    runs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=check.GPU)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(url + "?sound=0&tour=0", wait_until="domcontentloaded")
        check.ready(page, 300)
        for teach in (True, True, True, False, False, False):
            run = check.scripted(page, teach)
            runs.append(run)
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in run.items()}), flush=True)
        browser.close()
    server.shutdown()
    (check.HERE / "evidence" / "promise_runs.json").write_text(json.dumps({"schema": "cadence-out-of-sight-promise-runs/1", "runs": runs}, indent=1) + "\n")


if __name__ == "__main__":
    main()
