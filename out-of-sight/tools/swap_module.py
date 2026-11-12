"""Put another place module on the page and read it: the pack, the promise runs, the page check.

    python tools/swap_module.py --module place.npz --wheel cadence_net-0.99.0-py3-none-any.whl \\
        --label "Settling place module" --note "One or two sentences on what this file is." \\
        --wheel-source "PyPI" [--shots shots] [--no-check]

Run from ``out-of-sight/`` with the Python that holds Playwright. It rebuilds ``site/pack/``
(``tools/build.py``: the wheel, the module file, the manifest with SHA-256 sums), reads the
promise scenario six times, three with lessons on and three off (``tools/promise_runs.py``; twice
where the library takes the sight evidence), performs the page check with screenshots
(``tools/check_page.py``), and prints the readings. The evidence files are rewritten:
``evidence/promise_runs.json`` and ``evidence/page_check.json``.

Without ``--label`` the page's badge is the module file's name. Without ``--wheel-source`` the
manifest keeps its statement where the wheel's bytes are the same, and names the file otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
TOOLS = HERE / "tools"


def run(*args: str) -> int:
    print("$ " + " ".join(args), flush=True)
    return subprocess.call([sys.executable, *args], cwd=HERE)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--module", required=True, nargs="+", help="the place module's file (and its JSON record where it has one)")
    p.add_argument("--wheel", required=True, help="the cadence-net wheel the module runs on")
    p.add_argument("--label", default=None, help="what the page calls this file (its badge)")
    p.add_argument("--note", default=None, help="one or two sentences on what this file is")
    p.add_argument("--wheel-source", default=None, help="where the wheel comes from, as the page states it")
    p.add_argument("--space", default=None, help='settings of cadence.space.Space the module is run with, as JSON, e.g. \'{"course": true}\'')
    p.add_argument("--shots", default="shots", help="the folder for the page check's screenshots (not tracked)")
    p.add_argument("--no-check", action="store_true", help="the pack and the promise runs alone")
    a = p.parse_args()
    manifest_path = HERE / "site" / "pack" / "manifest.json"
    before = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    wheel = Path(a.wheel)
    same = before.get("wheel_sha256") == hashlib.sha256(wheel.read_bytes()).hexdigest()
    source = a.wheel_source or (before.get("wheel_source") if same else f"a local wheel, {wheel.name}")
    label = a.label or Path(a.module[0]).stem
    build = [str(TOOLS / "build.py"), "--wheel", str(wheel), "--wheel-source", source, "--module", *a.module, "--module-label", label]
    if a.note:
        build += ["--module-note", a.note]
    if a.space:
        build += ["--space", a.space]
    if subprocess.call([sys.executable, *build], cwd=HERE, stdout=subprocess.DEVNULL):
        return 1
    manifest = json.loads(manifest_path.read_text())
    print(f"pack: {manifest['wheel']} ({manifest['wheel_sha256'][:16]}…, {manifest['wheel_source']}); module "
          + ", ".join(f"{f['name']} ({f['bytes']:,} B, {f['sha256'][:16]}…)" for f in manifest["module"]["files"]) + f"; badge \"{label}\"", flush=True)
    if run(str(TOOLS / "promise_runs.py")):
        return 1
    passed = None
    if not a.no_check:
        run(str(TOOLS / "check_page.py"), "--shots", a.shots)  # exits 1 where a check fails: the tally below says which
        report = json.loads((HERE / "evidence" / "page_check.json").read_text())
        passed = sum(1 for row in report["checks"] if row["passed"])
        print(f"page check: {passed} of {len(report['checks'])}" + ("" if report["passed"] else "; failing: " + "; ".join(report["failed"])))
        print(f"screenshots: {(HERE / a.shots).resolve()}")
    runs = json.loads((HERE / "evidence" / "promise_runs.json").read_text())["runs"]
    sys.path.insert(0, str(TOOLS))
    import promise_runs  # noqa: PLC0415  after the pack is built

    print(promise_runs.table(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
