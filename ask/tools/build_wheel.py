"""Build the cadence-net wheel of one commit of the library, into a folder named by the commit.

    python tools/build_wheel.py --repo PATH/TO/cadence [--ref origin/lane-0100-words]

The commit's tree is exported (``git archive``, nothing in the repository changes), its version
is marked as a development build (``<released version>+words.<commit>``, a local version in the
sense of PEP 440: the release plus the commits of the words lane), and the wheel is built with the
project's own build backend. It lands in ``site/pack/<commit>/``; a folder that holds a wheel is
left as it is. Prints the wheel's path.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PACK = HERE / "site" / "pack"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True, type=Path, help="a clone of the cadence repository")
    ap.add_argument("--ref", default="origin/lane-0100-words", help="the commit to build")
    ap.add_argument("--label", default="words", help="the local version's label")
    a = ap.parse_args()
    git = ["git", "-C", str(a.repo)]
    commit = subprocess.run([*git, "rev-parse", a.ref], capture_output=True, text=True,
                            check=True).stdout.strip()
    short = commit[:8]
    folder = PACK / short
    found = sorted(folder.glob("cadence_net-*.whl")) if folder.is_dir() else []
    if found:
        print(found[0])
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        tree.mkdir()
        archive = subprocess.run([*git, "archive", "--format=tar", commit], capture_output=True,
                                 check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        project = tree / "pyproject.toml"
        text = project.read_text()
        released = re.search(r'^version = "([^"]+)"', text, re.M)
        if not released:
            raise SystemExit("pyproject.toml names no version")
        version = f"{released.group(1)}+{a.label}.{short}"
        project.write_text(text.replace(released.group(0), f'version = "{version}"', 1))
        init = tree / "src" / "cadence" / "__init__.py"
        init.write_text(re.sub(r'^__version__ = "[^"]+"', f'__version__ = "{version}"',
                               init.read_text(), count=1, flags=re.M))
        out = Path(tmp) / "dist"
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(tree)],
                       check=True, stdout=subprocess.DEVNULL)
        wheels = sorted(out.glob("cadence_net-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel, built {[w.name for w in wheels]}")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / wheels[0].name
        shutil.copyfile(wheels[0], target)
        (folder / "COMMIT").write_text(f"{commit}\n{a.ref}\n{version}\n")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
