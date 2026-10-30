from dataclasses import replace

import numpy as np
from cadence import Brain

from arm import caregiver
from arm.anatomy import EYE_SLOTS, MOTOR_SLOTS, Anatomy, Stage, build, connectome_of, describe, freeze, raising_config
from arm.eyes import Eyes, HeadSpec
from arm.world import ArmSpec, World


def small():
    head = HeadSpec(size=16, eyes=2)
    anatomy = Anatomy(size=16, channels=head.channels, hidden=32, stages=(Stage(4, 5, 2),), sheet=6)
    return head, anatomy


def test_connectome_populations_and_tie_groups():
    head, anatomy = small()
    c, groups = connectome_of(anatomy, seed=0)
    pops = {k: len(v) for k, v in c.populations.items()}
    assert pops["sensory"] == anatomy.retina + anatomy.body
    assert pops["visual/v1"] == 4 * 6 * 6 and pops["visual/map"] == 36
    assert pops["association"] == 32 and pops["prefrontal"] == 32
    assert pops["motor"] == sum(EYE_SLOTS + MOTOR_SLOTS)
    assert groups is not None and (groups >= 0).sum() > 0


def test_brain_answers_one_index_per_slot_and_learns_one_lesson(tmp_path):
    head, anatomy = small()
    brain = build(anatomy, seed=0, memory_choice=True, memory_context=0.5, memory_rate=0.5,
                  memory_replay=8, memory_demonstrations=1.0, memory_expansion=256, memory_winners=8, arousal=True)
    raising_config(brain)
    world, eyes = World(ArmSpec(), seed=0), Eyes(head)
    world.randomize()
    x = eyes.inputs(world)[None]
    answer = brain.act(x, greedy=True)[0]
    assert answer.shape == (len(anatomy.slots),)
    for k, size in enumerate(anatomy.slots):
        assert 0 <= answer[k] < size
    labels = np.array([world.labels() + caregiver.labels(world)])
    before = brain.brain.efficacy.copy() if hasattr(brain.brain, "efficacy") else None
    drive = brain.stimulus(x)
    _, report = brain.learner.step(drive, labels, warm=brain.basal_ganglia.state)
    assert report.get("total_steps", 0) > 0
    # Cadence 0.91 saves and loads only a learner with the cross-entropy nudge; the nursery's
    # pools phase sets it (``--pool-nudge cross_entropy``) before a brain is saved
    brain.learner.config = replace(brain.learner.config, nudge="cross_entropy")
    path = brain.save(tmp_path / "b.npz")
    again = Brain.load(path)
    assert list(again.learner.slot_sizes) == list(anatomy.slots)
    d = describe(again)
    assert d["neurons"] == brain.connectome.n


def test_freeze_keeps_the_visual_pathway_fixed():
    head, anatomy = small()
    brain = build(anatomy, seed=0)
    raising_config(brain)
    freeze(brain, (("sensory", "visual/v1"),))
    c = brain.connectome
    fixed = np.isin(c.pre, np.asarray(c.populations["sensory"])) & np.isin(c.post, np.asarray(c.populations["visual/v1"]))
    assert not brain.learner.plastic_synapses[fixed].any()
    assert brain.learner.plastic_synapses[~fixed].all()


def test_three_maps_with_topographic_readouts():
    head = HeadSpec(size=16, eyes=2)
    anatomy = Anatomy(size=16, channels=head.channels, hidden=32, stages=(Stage(4, 5, 2),), sheet=6,
                      sheets=3, readout="topographic")
    c, groups = connectome_of(anatomy, seed=0)
    pops = {k: len(v) for k, v in c.populations.items()}
    assert pops["visual/map"] == 36 and pops["visual/map1"] == 36 and pops["visual/map2"] == 36
    motor = np.asarray(c.populations["motor"])
    block_x = motor[:12]
    from_map = np.isin(c.pre, np.asarray(c.populations["visual/map"])) & np.isin(c.post, block_x)
    from_assoc = np.isin(c.pre, np.asarray(c.populations["association"])) & np.isin(c.post, block_x)
    assert from_map.sum() == 36 * 12 and from_assoc.sum() == 0  # positions read their map, not the association
    gripper = motor[-2:]
    assert (np.isin(c.pre, np.asarray(c.populations["association"])) & np.isin(c.post, gripper)).sum() == 32 * 2
    brain = build(anatomy, seed=0)
    raising_config(brain)
    world, eyes = World(ArmSpec(), seed=0), Eyes(head)
    world.randomize()
    x = eyes.inputs(world)[None]
    assert brain.act(x, greedy=True)[0].shape == (len(anatomy.slots),)


def test_eye_phase_moves_only_the_visual_pathway():
    from arm.anatomy import eye_learner, pathway_masks, pool_phase, share_graph
    head = HeadSpec(size=16, eyes=2)
    anatomy = Anatomy(size=16, channels=head.channels, hidden=32, stages=(Stage(4, 5, 2),), sheet=6,
                      sheets=2, readout="topographic", map_reciprocal=False)
    brain = build(anatomy, seed=0)
    raising_config(brain)
    pathway, rest = pathway_masks(brain)
    c = brain.connectome
    assert pathway.sum() + rest.sum() == c.synapses and pathway.sum() > 0 and rest.sum() > 0
    maps_to_assoc = np.isin(c.pre, np.asarray(c.populations["visual/map"])) & np.isin(c.post, np.asarray(c.populations["association"]))
    assert rest[maps_to_assoc].all()  # the association learns to read the maps in the pools phase
    world, eyes = World(ArmSpec(), seed=0), Eyes(head)
    world.randomize()
    x = eyes.inputs(world)[None]
    before = brain.brain.efficacy.copy()
    learner = eye_learner(brain)
    drive = brain.stimulus(x)
    brain.act(x, greedy=True)
    learner.step(drive, np.array([eyes.labels(world)]), warm=brain.basal_ganglia.state)
    share_graph(brain, learner)
    moved = brain.brain.efficacy != before
    assert moved[pathway].any() and not moved[rest].any()
    pool_phase(brain)
    before = brain.brain.efficacy.copy()
    drive = brain.stimulus(x)
    brain.act(x, greedy=True)
    brain.learner.step(drive, np.array([eyes.labels(world) + caregiver.labels(world)]), warm=brain.basal_ganglia.state)
    moved = brain.brain.efficacy != before
    assert moved[rest].any() and not moved[pathway].any()


def test_eye_streams_keep_the_maps_on_the_first_eye():
    head = HeadSpec(size=16, eyes=2, colour=True)
    anatomy = Anatomy(size=16, channels=head.channels, eyes=2, eye_streams=True, hidden=32,
                      stages=(Stage(4, 5, 2),), sheet=6, sheets=2, readout="topographic", map_reciprocal=False)
    c, _ = connectome_of(anatomy, seed=0)
    pops = {k: np.asarray(v) for k, v in c.populations.items()}
    assert len(pops["visual/v1"]) == 4 * 36 and len(pops["visual/v1r"]) == 4 * 36
    to_map = np.isin(c.post, pops["visual/map"])
    assert np.isin(c.pre[to_map], pops["visual/v1"]).sum() > 0
    assert not np.isin(c.pre[to_map], pops["visual/v1r"]).any()  # the right eye never reaches the maps
    to_assoc = np.isin(c.post, pops["association"])
    assert np.isin(c.pre[to_assoc], pops["visual/v1r"]).any()  # but it reaches the association
    retina = pops["sensory"][: anatomy.retina]
    left = np.isin(c.pre, retina[: 16 * 16]) & np.isin(c.post, pops["visual/v1r"])
    assert not left.any()  # the right stream reads only the right eye's channels
    brain = build(anatomy, seed=0)
    world, eyes = World(ArmSpec(), seed=0), Eyes(head)
    assert brain.act(eyes.inputs(world)[None], greedy=True)[0].shape == (len(anatomy.slots),)


def test_map_teaching_labels_and_learner():
    from arm.anatomy import eye_learner, map_cells, share_graph
    head = HeadSpec(size=16, eyes=1)
    anatomy = Anatomy(size=16, channels=head.channels, hidden=32, stages=(Stage(4, 5, 2),), sheet=6,
                      sheets=3, readout="topographic", map_reciprocal=False)
    brain = build(anatomy, seed=0)
    raising_config(brain)
    cells = map_cells(brain)
    assert len(cells) == 3 and all(len(c) == 36 for c in cells)
    world, eyes = World(ArmSpec(), seed=0), Eyes(head)
    labels = eyes.map_labels(world, 6)
    assert len(labels) == 3 and all(0 <= v < 36 for v in labels)
    learner = eye_learner(brain, teach_maps=True)
    assert list(learner.slot_sizes) == [36, 36, 36, 12, 12, 12, 12, 2, 3]
    x = eyes.inputs(world)[None]
    drive = brain.stimulus(x)
    brain.act(x, greedy=True)
    taught = np.array([labels + eyes.labels(world)], dtype=np.int64)
    _, report = learner.step(drive, taught, warm=brain.basal_ganglia.state)
    share_graph(brain, learner)
    assert report.get("total_steps", 0) > 0


def test_innate_colour_wiring_sees_the_block_and_the_hand_at_birth():
    from arm.anatomy import map_cells
    head = HeadSpec(size=28, eyes=1, colour=True)
    anatomy = Anatomy(size=28, channels=head.channels, eyes=1, hidden=32, stages=(Stage(8, 5, 2),), sheet=12,
                      sheets=3, readout="topographic", map_reciprocal=False, map_density=0.5, priors=True,
                      readout_reciprocal=False, map_input_reciprocal=False)
    brain = build(anatomy, seed=0)
    world, eyes = World(ArmSpec(), seed=3), Eyes(head)
    maps = map_cells(brain)
    hits = 0
    for _ in range(6):
        world.randomize(holding_rate=0.0)
        if not eyes.block_visible(world):
            continue
        x = eyes.inputs(world)[None]
        brain.reset()
        answer = brain.act(x, greedy=True)[0]
        act = np.asarray(brain.basal_ganglia.state.activation)[0]
        cell_block, cell_hand, _ = eyes.map_labels(world, 12)
        peak = int(np.argmax(act[maps[0]]))
        assert abs(peak // 12 - cell_block // 12) <= 1 and abs(peak % 12 - cell_block % 12) <= 1
        labels = eyes.labels(world)
        hits += int(abs(int(answer[0]) - labels[0]) <= 1 and abs(int(answer[1]) - labels[1]) <= 1)
    assert hits >= 4
