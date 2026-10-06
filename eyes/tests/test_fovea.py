import json

import numpy as np
import pytest

from tracker.anatomy import Anatomy, Stage, build
from tracker.eye_host import Host
from tracker.fovea import Fovea, FovealConfig, FovealEyes, FovealWorld, fovea_dart
from tracker.shapes import Thing, render


def small_fovea_brain(seed=0):
    return build(Anatomy(size=25, bins=13, channels=2, stages=(Stage(4, 5, 2),), kernels="tied",
                         sheet=13, sheet_input="topographic", readout="topographic", memory=None),
                 seed=seed, trace=None, tie_rate="sum")


def test_fovea_is_fine_at_the_centre_and_coarse_outside():
    fv = Fovea()
    assert list(fv.offsets[12:19]) == [0, 1, 2, 3, 4, 5, 6] and fv.offsets[-1] == pytest.approx(40.0)
    widths = fv.hi - fv.lo
    assert widths[12] == 1 and widths[-1] > 5 and (fv.lo[1:] == fv.hi[:-1]).all()
    assert fv.bin_of(0.0) == fv.bin_of(1.4) == 6 and fv.bin_of(1.6) == 7 and fv.bin_of(-30.0) == 1
    assert fv.bin_of(60.0) is None
    assert fv.saccade(50, 50, (6, 6), 160, 100) == (50, 50)
    assert fv.saccade(50, 50, (11, 1), 160, 100) == (75, 25)
    with pytest.raises(ValueError):
        Fovea(receptors=24)


def test_receptors_average_their_patch_and_see_past_the_edge():
    fv = Fovea()
    surface = np.zeros((200, 200))
    surface[100, 100] = 1.0
    seen = fv.sample(fv.integral(surface), 100, 100)
    assert seen[12, 12] == 1.0 and seen.sum() == pytest.approx(1.0)
    edge = fv.sample(fv.integral(np.zeros((60, 80))), 0, 0)
    assert edge[0, 0] == pytest.approx(0.1) and edge[24, 24] == pytest.approx(0.0)


def test_world_labels_the_eyes_own_shape():
    world = FovealWorld(FovealConfig(), seed=0)
    for _ in range(120):
        f = world.step()
        assert f.pixels.shape == (2 * 25 * 25,) and np.isfinite(f.pixels).all()
        t = world.things[world.mine]
        if f.visible:
            assert f.target == world.fovea.bins_of(t.x - world.gx, t.y - world.gy)


def test_still_scene_needs_no_settling_and_change_reaches_the_eye():
    brain = small_fovea_brain()
    eyes = FovealEyes(brain, Fovea(), 160, 100)
    things = [Thing("face", 40.0, 30.0, 9, 0.9), Thing("star", 120.0, 70.0, 8, 0.8, 0.4)]
    eyes.open(1, 40, 30)
    eyes.open(2, 120, 70)
    surface = render(100, 160, things, 0.1)
    out = [eyes.see(surface) for _ in range(6)]
    assert out[-1]["sweeps"] == 0
    assert np.abs(out[-1]["x"][:, 625:]).max() == 0.0
    moved = render(100, 160, [things[0], Thing("star", 126.0, 70.0, 8, 0.8, 0.4)], 0.1)
    assert np.abs(eyes.see(moved)["x"][:, 625:]).max() > 0.0


def test_host_runs_the_foveated_eye(tmp_path):
    path = small_fovea_brain().save(tmp_path / "fovea.npz")
    host = Host(str(path), 0, 13, 160, 100, eye="fovea",
                fovea={"receptors": 25, "inner": 6, "reach": 40.0, "bins": 13, "change_gain": 1.0})
    info = json.loads(host.handle_json(json.dumps({"op": "describe"})))
    assert info["eye"] == "fovea" and info["receptors"] == 25 and len(info["bin_lo"]) == 13
    host.handle_json(json.dumps({"op": "open", "id": 3, "x": 40, "y": 30}))
    pixels = render(100, 160, [Thing("disc", 40.0, 30.0, 8, 0.9)], 0.1).astype(np.float32)
    frames = [json.loads(host.see(pixels)) for _ in range(8)]
    assert len(frames[0]["windows"]) == 1 and len(frames[0]["changes"]) == 1
    assert frames[-1]["sweeps"] == 0 and frames[-1].get("held")


def test_dart_assay_runs(tmp_path):
    path = small_fovea_brain().save(tmp_path / "fovea.npz")
    out = fovea_dart(path, FovealConfig(), 2, seed=1, jumps=(10.0,), others=2)
    assert set(out["10.0"]) == {"1", "2", "3"}
