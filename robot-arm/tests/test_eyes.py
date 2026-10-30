import numpy as np

from arm.eyes import BRIGHT, Camera, Eyes, HeadSpec, render
from arm.world import BODY_SENSES, ArmSpec, World


def test_block_is_visible_and_the_eyes_disagree_by_a_disparity():
    w = World(ArmSpec(), seed=0)
    w.move_block(0.0, 0.25)
    eyes = Eyes(HeadSpec(size=32, eyes=2))
    frames = eyes.see(w)
    assert frames.shape == (2, 32, 32)
    for frame in frames:
        assert (frame == BRIGHT["block"]).sum() >= 2  # the block covers some pixels
        assert (frame == BRIGHT["table"]).sum() > 200  # on a visible table
        assert (frame == BRIGHT["hand"]).sum() >= 1  # and the hand is in view
    cols = [np.argwhere(f == BRIGHT["block"])[:, 1].mean() for f in frames]
    assert cols[0] != cols[1]


def test_inputs_concatenate_retina_and_body():
    w = World(ArmSpec(), seed=0)
    eyes = Eyes(HeadSpec(size=24, eyes=2, change=True))
    x = eyes.inputs(w)
    assert x.shape == (4 * 24 * 24 + BODY_SENSES,)
    assert np.all(x[2 * 24 * 24: 4 * 24 * 24] == 0.0)  # no change on the first frame
    w.decide([0, 1, 0, 0], 0)
    y = eyes.inputs(w)
    assert y[2 * 24 * 24: 4 * 24 * 24].max() > 0.0


def test_camera_projects_the_target_to_the_centre():
    cam = Camera((0, -0.1, 0.5), (0, 0.3, 0), 75.0, 32)
    px, z = cam.project(np.array([[0.0, 0.3, 0.0]]))
    assert np.allclose(px[0], [16, 16]) and z[0] > 0.5


def test_lamp_shows_the_order():
    w = World(ArmSpec(), seed=0)
    cam = Eyes(HeadSpec()).cameras[0]
    w.order = 1
    a = render(w, cam)
    w.order = 2
    b = render(w, cam)
    assert (a == BRIGHT["lamp_on"]).any() and (b == BRIGHT["lamp_on"]).any()
    assert not np.array_equal(a, b)


def test_eye_labels_follow_the_image():
    w = World(ArmSpec(), seed=0)
    eyes = Eyes(HeadSpec())
    labels = eyes.labels(w)
    assert len(labels) == 6 and all(0 <= v < 12 for v in labels[:4])
    frame = eyes.see(w)[0]
    rows, cols = np.nonzero(frame == BRIGHT["block"])
    col_bin, row_bin = int(np.floor(cols.mean() / 40 * 12)), int(np.floor(rows.mean() / 40 * 12))
    assert abs(labels[0] - col_bin) <= 1 and abs(labels[1] - row_bin) <= 1
    assert eyes.block_visible(w)
