import numpy as np

from attention import SurpriseAttention, threshold_from_training


def test_surprise_wakes_observer_then_quiet_restores_passive_duty():
    monitor = SurpriseAttention(
        0.1, width=1, period=2, passive_blocks=4, burst_blocks=2
    )
    assert monitor.due(0, [0])
    assert not monitor.due(1, [0])
    assert not monitor.due(2, [0])
    assert not monitor.due(3, [1])  # wakes, preserves trained block alignment
    assert monitor.due(4, [1])
    assert monitor.due(6, [1])
    assert monitor.due(8, [1])  # periodic passive check
    assert not monitor.due(10, [1])


def test_calibration_does_not_look_at_validation():
    sequences = [
        {"split": 0, "x": np.array([[0], [0.1], [0.2]])},
        {"split": 1, "x": np.array([[100], [-100]])},
    ]
    assert np.isclose(threshold_from_training(sequences, 1), 0.1)
