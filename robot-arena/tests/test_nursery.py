from dataclasses import replace

import numpy as np
import pytest

from arena import nursery
from arena.brain import RobotBrain, compose
from arena.league import League
from arena.parts import stock_designs


@pytest.fixture
def exact_rewards(monkeypatch):
    """Known unrounded physical outcomes, independent of a newborn's commands."""
    rewards = []
    step = nursery.Arena.step

    def observed_step(world, commands):
        outcome = step(world, commands)
        reward = 0.123456789 + len(rewards) / 10000
        rewards.append(reward)
        outcome[0]["dealt"], outcome[0]["taken"] = reward, 0.0
        return outcome

    monkeypatch.setattr(nursery, "PROGRESS_PAY", 0.0)
    monkeypatch.setattr(nursery, "DAMAGE_SCALE", 1.0)
    monkeypatch.setattr(nursery.Arena, "step", observed_step)
    return rewards


@pytest.mark.parametrize("youth", [0, 300])
def test_nursery_rewards_survive_repeated_training_and_fights(
    tmp_path, monkeypatch, exact_rewards, youth
):
    blueprint = replace(stock_designs()[0], genes={"arousal": {
        "youth": youth, "need": 0.0, "value_surprise": 0.0,
    }})
    baseline = replace(stock_designs()[1], name="Random", policy="random")
    league = League(tmp_path / "league")
    league.create([blueprint, baseline])
    delivered = []
    moment = RobotBrain.moment

    def record(life, observation, reward, done=False):
        before = life.brain.arousal.rewards
        answer = moment(life, observation, reward, done)
        delivered.append((reward, done, before, life.brain.arousal.rewards))
        return answer

    monkeypatch.setattr(RobotBrain, "moment", record)
    first = league.nursery([blueprint.name], moments=4, seed=2)[0]
    assert first["owed"] == [exact_rewards[-1], True]
    assert first["owed"][0] != round(first["owed"][0], 3)
    assert first["brain"]["age"] == 4
    assert delivered[0] == (None, False, 0, 0)
    assert [(r, done) for r, done, _, _ in delivered[1:]] == [
        (reward, False) for reward in exact_rewards[:-1]
    ]

    # Reload both the league ledger and its brain, then train in another physical world.
    league = League(league.root)
    assert league.data["robots"][blueprint.name]["owed"] == first["owed"]
    delivered.clear()
    second = league.nursery([blueprint.name], moments=4, seed=3)[0]
    assert delivered[0] == (*first["owed"], 3, 4)
    assert all(not done for _, done, _, _ in delivered[1:])
    assert second["brain"]["age"] == 8
    assert second["owed"] == [exact_rewards[-1], True]

    # The same ledger also transfers a nursery outcome into a fight and back again.
    delivered.clear()
    league = League(league.root)
    league.royale(seed=4, duration=3, zone_moments=30, workers=0, record=False)
    assert delivered[0] == (*second["owed"], 7, 8)
    owed = league.data["robots"][blueprint.name]["owed"]
    assert owed is not None and owed[1] is True
    delivered.clear()
    league = League(league.root)
    third = league.nursery([blueprint.name], moments=1, seed=5)[0]
    assert delivered[0][:2] == tuple(owed)
    assert delivered[0][3] == delivered[0][2] + 1
    assert third["brain"]["age"] == 12


def test_final_refusal_keeps_carried_feedback_with_the_checkpoint(
    tmp_path, monkeypatch, exact_rewards
):
    blueprint = stock_designs()[0]
    factory = nursery.make_policy
    lives = []

    def make_policy(*args, **kwargs):
        life = factory(*args, **kwargs)
        if not lives:
            live = life.brain.live

            def refuse_feedback(observations, **feedback):
                if "reward" in feedback:
                    raise RuntimeError("refuse before accepting the preceding outcome")
                return live(observations, **feedback)

            monkeypatch.setattr(life.brain, "live", refuse_feedback)
        lives.append(life)
        return life

    monkeypatch.setattr(nursery, "make_policy", make_policy)
    checkpoint = tmp_path / "life.npz"
    first = nursery.run_nursery(blueprint, moments=2, block=1, save_to=checkpoint)
    assert first["total"]["refused"] == 1
    assert lives[0].owed == exact_rewards[0]
    assert first["owed"] == [sum(exact_rewards), True]
    assert lives[0].brain.arousal.rewards == 0

    nursery.run_nursery(
        blueprint, moments=1, block=1, brain_path=checkpoint, owed=tuple(first["owed"]),
    )
    assert lives[1].brain.arousal.rewards == 1
    assert lives[1].brain.arousal.recent == pytest.approx(sum(exact_rewards[:2]), abs=1e-15)
    assert lives[1].owed == 0.0


def test_refused_incoming_terminal_outcome_stays_terminal_on_retry(
    tmp_path, monkeypatch, exact_rewards
):
    blueprint = stock_designs()[0]
    checkpoint = tmp_path / "life.npz"
    first = nursery.run_nursery(blueprint, moments=1, block=1, save_to=checkpoint)
    factory = nursery.make_policy
    feedbacks = []

    def make_policy(*args, **kwargs):
        life = factory(*args, **kwargs)
        live = life.brain.live

        def refuse_once(observations, **feedback):
            feedbacks.append(feedback)
            if len(feedbacks) == 1:
                raise RuntimeError("refuse the first terminal forecast")
            return live(observations, **feedback)

        monkeypatch.setattr(life.brain, "live", refuse_once)
        return life

    monkeypatch.setattr(nursery, "make_policy", make_policy)
    second = nursery.run_nursery(
        blueprint, moments=2, block=1, brain_path=checkpoint, owed=tuple(first["owed"]),
    )
    assert feedbacks == [
        {"reward": [exact_rewards[0]], "done": [True]},
        {"reward": [sum(exact_rewards[:2])], "done": [True]},
    ]
    assert second["total"]["refused"] == 1
    assert second["owed"] == [exact_rewards[-1], True]


def test_repeated_nursery_frozen_control_is_a_real_newborn(tmp_path, monkeypatch):
    blueprint = stock_designs()[0]
    league = League(tmp_path / "league")
    league.create([blueprint])
    league.nursery(moments=4)
    initial = compose(blueprint)
    controls = []
    factory = nursery.make_policy

    def make_policy(bp, policy, path):
        life = factory(bp, policy, path)
        if policy == "frozen":
            controls.append(life)
        return life

    monkeypatch.setattr(nursery, "make_policy", make_policy)
    reports = league.nursery(moments=4, controls=True)
    assert len(controls) == 1
    frozen = controls[0].brain
    assert frozen.arousal.age == 0 and frozen.arousal.rewards == 0
    for name in ("efficacy", "bias", "log_gain"):
        np.testing.assert_array_equal(getattr(frozen.brain, name), getattr(initial.brain, name))
    assert next(r for r in reports if r["policy"] == "brain")["brain"]["age"] == 8
    assert all(r["owed"] is None for r in reports if r["policy"] != "brain")
