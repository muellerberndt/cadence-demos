"""The page draws its surface with web/shapes.js; the brain was raised on tracker/shapes.py.

Both must give the brain the same pixels. Sines and cosines may differ in the last bit between
numpy and JavaScript, which can move a sample that lies exactly on an edge; one such sample
changes a pixel by at most a sixteenth of the shape's contrast.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tracker.shapes import KINDS, ROTATES, Thing, render

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = """
import { render } from "%s";
import { readFileSync } from "node:fs";
const f = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = render(f.height, f.width, f.things, Float64Array.from(f.background));
process.stdout.write(JSON.stringify(Array.from(out)));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_js_renderer_gives_the_same_pixels(tmp_path):
    rng = np.random.default_rng(3)
    height, width = 40, 48
    things = []
    for k in range(36):
        kind = KINDS[k % len(KINDS)]
        things.append(Thing(kind, float(rng.uniform(-2, width + 2)), float(rng.uniform(-2, height + 2)),
                            float(rng.uniform(4, 12)), float(rng.uniform(0.3, 1.0)),
                            float(rng.uniform(0, 2 * np.pi)) if kind in ROTATES else 0.0))
    background = np.clip(0.1 + 0.03 * rng.standard_normal((height, width)), 0, 1)
    expected = render(height, width, things, background)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({
        "height": height, "width": width, "background": background.ravel().tolist(),
        "things": [t.__dict__ for t in things],
    }))
    script = tmp_path / "render.mjs"
    script.write_text(SCRIPT % (ROOT / "web" / "shapes.js").as_uri())
    done = subprocess.run(["node", str(script), str(fixture)], capture_output=True, text=True,
                          check=True, timeout=120)
    got = np.array(json.loads(done.stdout)).reshape(height, width)
    diff = np.abs(got - expected)
    assert diff.max() <= 1 / 16 + 1e-9
    assert (diff > 1e-9).mean() < 0.002
