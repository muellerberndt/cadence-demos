import json
from pathlib import Path

import amen_matched_render as m
import pytest


def test_plain_legacy_ports_preserve_observed_event():
    previous = [float(k) / 70 for k in range(71)]
    initial = previous.copy()
    for tick in (0, 1, 7, 8, 127):
        values = m.plain_old_inputs(previous, tick)
        assert len(values) == 80
        assert values[0] == (tick == 0)
        assert values[1:9] == [float(k == tick % 8) for k in range(8)]
        assert values[9:] == previous
    assert initial == previous


def test_five_fixed_choices_and_shared_web_settings():
    assert m.CHOICES == [
        ("argmax", 0),
        ("sample", 1),
        ("sample", 2),
        ("sample", 3),
        ("sample", 4),
    ]
    for mode, seed in m.CHOICES:
        value = m.settings(mode, seed)
        assert value == {
            "bars": 16,
            "mode": mode,
            "seed": seed,
            "energy": 1,
            "variation": 0.6 if mode == "sample" else 0,
            "riffBars": 2,
        }
        assert "memory" not in value


def test_digest_matches_json_canonical_roundtrip():
    value = [[0.0, 0.125, -0.25], [1.0, 0.0, 0.5]]
    assert m.digest(value) == m.digest(json.loads(json.dumps(value)))
    changed = json.loads(json.dumps(value))
    changed[1][0] = 0.0
    assert m.digest(value) != m.digest(changed)


@pytest.mark.parametrize("target", ["source", "external", "node"])
def test_binding_rejects_each_source_drift(tmp_path, target):
    paths = {key: tmp_path / key for key in ("source", "external", "node")}
    for key, path in paths.items():
        path.write_text(key)
    protocol = {
        "frozen_files": {"source": m.sha(paths["source"])},
        "external_pins": {str(paths["external"]): m.sha(paths["external"])},
        "node": str(paths["node"]),
        "node_sha256": m.sha(paths["node"]),
    }
    m.bound(tmp_path, protocol)
    paths[target].write_text("changed")
    with pytest.raises(ValueError):
        m.bound(tmp_path, protocol)


def test_original_and_candidate_web_playing_functions_identical():
    workspace = Path(__file__).resolve().parents[2]

    def selected(path):
        source = path.read_text().split("export function executed", 1)[1]
        return source.split("\n}\n", 1)[0]

    assert selected(workspace / "cadence-demos/amen/web/engine.js") == selected(
        workspace / "cadence-amen/page/engine.js"
    )
