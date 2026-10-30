import base64
import json
from pathlib import Path

import numpy as np
import pytest

from arm.host import SHIMMED, Host

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "runs" / "smoke"


def call(host: Host, **msg):
    out = json.loads(host.handle_json(json.dumps(msg)))
    assert "error" not in out, out
    return out


def test_describe_without_a_brain():
    d = call(Host(seed=0), op="describe")
    assert d["has_brain"] is False and d["brain"] is None and SHIMMED is False
    assert d["head"]["size"] == 40 and d["head"]["eyes"] == 2 and len(d["head"]["cameras"]) == 2
    assert d["world"]["links"] == [0.26, 0.22, 0.08] and d["world"]["link_radius"] == [0.03, 0.024, 0.016]
    frame = d["frame"]
    for key in ("t", "q", "rest", "points", "tip", "block", "bins", "order", "closed", "holding", "load", "wear",
                "decisions", "placed", "wrong", "dropped"):
        assert key in frame
    assert len(frame["points"]) == 4 and frame["tip"] == frame["points"][3]


def test_caregiver_moments_place_a_block_within_400_decisions():
    host = Host(seed=3)
    phases = set()
    m = None
    for n in range(1, 401):
        m = call(host, op="moment", driver="caregiver")
        assert m["used"] == "caregiver" and m["mode"] == "caregiver"
        assert len(m["frames"]) == 12 and m["frame"] == m["frames"][-1]
        assert len(m["commands"]) == 5 and all(c in (-2, -1, 0, 1, 2) for c in m["commands"][:4]) and m["commands"][4] in (0, 1)
        assert m["labels"] == [(-2, -1, 0, 1, 2).index(c) for c in m["commands"][:4]] + [m["commands"][4]]
        phases.add(m["phase"])
        if m["frame"]["placed"] >= 1:
            break
    assert m is not None and m["frame"]["placed"] >= 1 and m["frame"]["wrong"] == 0, (n, phases)
    assert m["event"].startswith("placed:") and m["event"].endswith(":right") and m["reward"] == 1.0
    assert {"approach", "lower", "grasp", "lift", "carry", "release"} <= phases
    assert m["frame"]["decisions"] == n == m["moments"]


def test_frames_advance_the_physics_only():
    host = Host(seed=0)
    before = call(host, op="describe")["frame"]
    out = call(host, op="frames", n=30)
    assert out["n"] == 30 and len(out["frames"]) == 30 and out["frame"] == out["frames"][-1]
    assert out["frame"]["t"] > before["t"] and out["frame"]["decisions"] == before["decisions"]
    call(host, op="set_load", kg=1.0)
    sagged = call(host, op="frames", n=300)["frame"]
    assert sagged["q"][1] < sagged["rest"][1] - 0.03  # the shoulder sags under the load


def test_retinas_shapes():
    host = Host(seed=0)
    r = call(host, op="retinas")
    assert r["size"] == 40 and len(r["eyes"]) == 2 and len(r["labels"]) == 6
    for eye in r["eyes"]:
        a = np.frombuffer(base64.b64decode(eye), dtype=np.uint8)
        assert a.shape == (1600,) and a.max() > 0 and len(np.unique(a)) >= 3


def test_snapshot_and_restore():
    host = Host(seed=2)
    for _ in range(5):
        call(host, op="moment", driver="caregiver")
    s = call(host, op="snapshot")["snapshot"]
    tip = call(host, op="frame")["frame"]["tip"]
    for _ in range(10):
        call(host, op="moment", driver="caregiver")
    assert call(host, op="frame")["frame"]["tip"] != tip
    f = call(host, op="restore", snapshot=s)["frame"]
    assert f["tip"] == tip and f["decisions"] == 5


def test_changes_and_erase_memory_without_a_brain():
    host = Host(seed=0)
    f = call(host, op="move_block", x=0.1, y=0.2)["frame"]
    assert f["block"][:2] == [0.1, 0.2]
    f = call(host, op="move_block", x=9.0, y=-9.0)["frame"]  # clipped to the table
    assert f["block"][:2] == [0.35, 0.1]
    f = call(host, op="move_bin", name="A", x=-0.1, y=0.4)["frame"]
    assert f["bins"]["A"] == [-0.1, 0.4]
    assert call(host, op="set_load", kg=0.5)["frame"]["load"] == 0.5
    assert call(host, op="set_wear", metres=0.02)["frame"]["wear"] == 0.02
    assert call(host, op="order", order=2)["frame"]["order"] == 2
    assert call(host, op="order", order="toggle")["frame"]["order"] == 1
    assert call(host, op="erase_memory")["erased"] is False
    out = json.loads(host.handle_json(json.dumps({"op": "nonsense"})))
    assert "error" in out and "nonsense" in out["error"]
    out = json.loads(host.handle_json(json.dumps({"op": "move_bin", "name": "C", "x": 0, "y": 0.3})))
    assert "error" in out
    f = call(host, op="reset")["frame"]
    assert f["decisions"] == 0 and f["load"] == 0.0 and f["wear"] == 0.0 and f["bins"]["A"] == [-0.2, 0.38]


@pytest.fixture(scope="module")
def smoke() -> Host:
    if not (SMOKE / "brain.npz").exists():
        pytest.skip("no placeholder brain under runs/smoke")
    return Host(SMOKE / "brain.npz", json.loads((SMOKE / "run.json").read_text()), seed=1)


def test_brain_moments_with_the_placeholder_brain(smoke: Host):
    d = call(smoke, op="describe")
    assert d["has_brain"] and d["head"]["size"] == json.loads((SMOKE / "run.json").read_text())["head"]["size"]
    b = d["brain"]
    assert b["populations"]["motor"] == 75 and sum(b["slots"]) == 75 and len(b["slot_names"]) == 11
    run = json.loads((SMOKE / "run.json").read_text())
    assert b["layout"]["retina"]["size"] == run["head"]["size"] and b["layout"]["v1"]["side"] > 0
    assert b["layout"]["map"]["side"] > 0
    m = call(smoke, op="moment", driver="shown")
    assert m["used"] == "shown" and m["mode"] == "shown" and m["taught"] and len(m["frames"]) == 12
    assert m["commands"] == [(-2, -1, 0, 1, 2)[v] for v in m["labels"][:4]] + [m["labels"][4]]  # the caregiver drove
    m = call(smoke, op="moment", driver="brain")
    assert m["mode"] == "alone" and not m["taught"] and (m["own"] is None) == m["refused"]
    assert len(m["commands"]) == 5 and all(c in (-2, -1, 0, 1, 2) for c in m["commands"][:4]) and m["ms"] > 0
    if m["own"] is not None:
        assert m["commands"] == [(-2, -1, 0, 1, 2)[v] for v in m["own"][:4]] + [m["own"][4]]  # the brain drove
    a = call(smoke, op="activity")
    for name, size in b["populations"].items():
        assert len(base64.b64decode(a["populations"][name])) == size
    assert [len(p) for p in a["motor"]["probabilities"]] == b["slots"]
    assert all(abs(sum(p) - 1.0) < 1e-3 for p in a["motor"]["probabilities"])
    assert len(a["motor"]["labels"]) == 11 and a["motor"]["commands"] == m["commands"]
    r = call(smoke, op="retinas")
    assert len(base64.b64decode(r["eyes"][0])) == json.loads((SMOKE / "run.json").read_text())["head"]["size"] ** 2
    assert call(smoke, op="erase_memory")["erased"] is True
    m = call(smoke, op="moment", driver="corrected")
    assert m["mode"] == "corrected" and m["used"] == "corrected"
    f = call(smoke, op="reset")["frame"]
    assert f["decisions"] == 0
    assert call(smoke, op="activity")["populations"] is None  # no settled state right after a reset
