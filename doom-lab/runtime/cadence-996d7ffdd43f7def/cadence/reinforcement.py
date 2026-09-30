"""Bounded replay and one-step reward credit through the ordinary patch rule.

Action values are settled patch outputs. The orchestration below computes
explicit Q-learning teaching estimates; it is not an additional optimizer,
biological dopamine model, or evidence of planning emerging inside a solve.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter, deque
from importlib.resources import files
from types import MappingProxyType

from ._validation import canonical, integer, number, strict_json
from .brain import MAX_CHECKPOINT_BYTES, Brain
from .ports import _values

_IMPLEMENTATION = hashlib.sha256(
    files(__package__).joinpath("reinforcement.py").read_bytes()
).hexdigest()


class Reinforcement:
    """Learn discrete choices from bounded rewards and observed transitions.

    ``brain`` declares an ``action_input`` vector of length ``actions`` and
    one scalar ``value_output``. Other inputs describe the situation, including
    any explicit history and drives. ``act`` supplies a one-hot action to each
    candidate query and retains the selected qualified activity. ``feedback``
    pairs that action with its actual reward and subsequent observation.

    Alternatively, ``action_input=None`` and a tuple of ``actions`` scalar
    ``value_output`` names expose one distinct patch value per action in a
    single joint query. The same reward rule teaches only the selected output.

    Targets are ``(1-discount)*value_scale*reward/reward_scale +
    discount*clip(max_next_value, -value_scale, value_scale)``; terminal
    transitions omit the second term. ``discount`` is in [0,1), exploration
    in [0,1], and rewards in [-reward_scale,reward_scale]. Target projection
    and reward scaling are explicit parts of this algorithm. Updates use
    ``observe_batch(source='estimate')`` with no separate parameter updater.

    Replay is a bounded FIFO store sampled uniformly, always including the
    latest transition. It mitigates forgetting but does not guarantee retention.
    All calls, including direct access to ``brain``, require one serial owner.
    """

    def __init__(
        self,
        brain,
        *,
        actions,
        action_input="action",
        value_output="value",
        discount=0.95,
        exploration=0.1,
        reward_scale=1.0,
        value_scale=0.9,
        capacity=1024,
        batch_size=16,
        seed=0,
    ):
        if not isinstance(brain, Brain):
            raise ValueError("brain must be a compiled Brain")
        actions = integer(actions, "actions", 2)
        capacity = integer(capacity, "capacity", 1)
        batch_size = integer(batch_size, "batch_size", 1)
        seed = integer(seed, "seed")
        if batch_size > capacity:
            raise ValueError("batch_size must not exceed capacity")
        discount = number(discount, "discount")
        exploration = number(exploration, "exploration")
        reward_scale = number(reward_scale, "reward_scale", positive=True)
        value_scale = number(value_scale, "value_scale", positive=True)
        if not 0 <= discount < 1 or not 0 <= exploration <= 1:
            raise ValueError("discount must be in [0,1); exploration in [0,1]")
        if value_scale >= min(
            1 / (1 + brain.config["state_prior"]), brain.config["state_bound"]
        ):
            raise ValueError("value_scale must be below the attainable output bound")
        inputs = {p.name: p for p in brain._inputs}
        outputs = {p.name: p for p in brain._outputs}
        if action_input is None:
            if (
                not isinstance(value_output, (tuple, list))
                or len(value_output) != actions
            ):
                raise ValueError(
                    "Vector values require one scalar output name per action"
                )
            value_output = tuple(value_output)
            names = value_output
        else:
            if (
                not isinstance(action_input, str)
                or action_input not in inputs
                or inputs[action_input].size != actions
            ):
                raise ValueError(
                    "action_input must name a sensor with one coordinate per action"
                )
            names = (value_output,)
        if any(
            not isinstance(name, str)
            or name not in outputs
            or len(outputs[name].indices) != 1
            for name in names
        ):
            raise ValueError("value_output must name scalar-valued outputs")
        selected = tuple(outputs[name] for name in names)
        if len({(value.reads.name, value.indices[0]) for value in selected}) != len(
            names
        ):
            raise ValueError("Action values must expose distinct patches, not aliases")
        self.brain = brain
        self.config = MappingProxyType(
            dict(
                actions=actions,
                action_input=action_input,
                value_output=value_output,
                discount=discount,
                exploration=exploration,
                reward_scale=reward_scale,
                value_scale=value_scale,
                capacity=capacity,
                batch_size=batch_size,
                seed=seed,
            )
        )
        self._sensors = tuple(p for p in brain._inputs if p.name != action_input)
        self._value_outputs = selected
        self._rng = random.Random(seed)
        try:
            self._records = deque(maxlen=capacity)
        except OverflowError as error:
            raise ValueError("capacity exceeds this platform's index range") from error
        self._pending = None
        self._transitions = 0
        self._updates = 0

    def _context(self, inputs):
        supplied = self.brain._mapping(inputs, self._sensors)
        return {
            p.name: (
                _values(supplied[p.name], p.shape, p.name)[0]
                if not p.shape
                else tuple(_values(supplied[p.name], p.shape, p.name))
            )
            for p in self._sensors
        }

    def _inputs(self, context, action):
        if self.config["action_input"] is None:
            return dict(context)
        return {
            **context,
            self.config["action_input"]: tuple(
                float(i == action) for i in range(self.config["actions"])
            ),
        }

    def _values(self, context, budget):
        if self.config["action_input"] is None:
            result = self.brain.settle(context, budget=budget)
            return [result], tuple(
                result["outputs"][value.name][0] for value in self._value_outputs
            )
        results = [
            self.brain.settle(self._inputs(context, a), budget=budget)
            for a in range(self.config["actions"])
        ]
        return results, tuple(
            r["outputs"][self.config["value_output"]][0] for r in results
        )

    def act(self, inputs, *, explore=True, budget=None):
        """Select and retain a qualified action; call feedback before acting again.

        All candidate queries must qualify, including exploration. Refusal
        changes neither pending experience, RNG, nor brain state. Ties are
        broken uniformly. Returns action index, values and exploration status;
        a refusal has ``action=None``. ``explore=False`` disables epsilon moves.
        ``work`` includes every candidate query and the selected state update;
        ``budget`` bounds each underlying solve separately.
        """
        if type(explore) is not bool:
            raise ValueError("explore must be boolean")
        if self._pending is not None:
            raise ValueError("Supply feedback or reset the pending action first")
        context = self._context(inputs)
        results, values = self._values(context, budget)
        work = Counter()
        for result in results:
            work.update(result["work"])
        if not all(r["qualified"] for r in results):
            return dict(
                accepted=False,
                action=None,
                values=values,
                reason="query_refused",
                work=dict(work),
            )
        before = self._rng.getstate()
        exploratory = explore and self._rng.random() < self.config["exploration"]
        best = max(values)
        choices = (
            list(range(len(values)))
            if exploratory
            else [i for i, v in enumerate(values) if v == best]
        )
        action = self._rng.choice(choices)
        try:
            result = self.brain.step(self._inputs(context, action), budget=budget)
        except Exception:
            self._rng.setstate(before)
            raise
        work.update(result["work"])
        if not result["accepted"]:
            self._rng.setstate(before)
            return dict(
                accepted=False,
                action=None,
                values=values,
                reason="step_refused",
                work=dict(work),
            )
        self._pending = (context, action)
        return dict(
            accepted=True,
            action=action,
            values=values,
            exploratory=exploratory,
            settlement=result,
            work=dict(work),
        )

    def feedback(
        self, reward, next_inputs=None, *, terminal=False, learn=True, budget=None
    ):
        """Record an actual outcome and optionally attempt one replay update.

        Nonterminal outcomes require next_inputs. Terminal outcomes require
        None; terminal means there is no future reward continuation, not just
        that a collector stopped. Invalid arguments change nothing. A valid
        record is retained and consumes the pending action even if the later
        numerical update refuses or raises. Retry learning with replay(), not
        feedback().
        ``learn=False`` records experience without changing learned parameters.
        """
        if self._pending is None:
            raise ValueError("feedback requires a preceding accepted act")
        if type(terminal) is not bool or type(learn) is not bool:
            raise ValueError("terminal and learn must be boolean")
        reward = number(reward, "reward")
        if abs(reward) > self.config["reward_scale"]:
            raise ValueError("reward exceeds reward_scale; scale rewards explicitly")
        if budget is not None:
            integer(budget, "budget")
        if terminal:
            if next_inputs is not None:
                raise ValueError("Terminal feedback requires next_inputs=None")
            following = None
        else:
            following = self._context(next_inputs)
        context, action = self._pending
        self._records.append((context, action, reward, following))
        self._transitions += 1
        self._pending = None
        result = (
            self.replay(budget=budget)
            if learn
            else dict(accepted=False, reason="learning_disabled")
        )
        return {**result, "stored": True, "transitions": self._transitions}

    def replay(self, *, budget=None):
        """Fit one sampled batch of Q estimates, preserving current live activity.

        Compute all targets with the unchanged pre-update brain. Terminal
        samples never bootstrap. Qualification failures commit no parameters;
        replay contents remain available. This is an approximate Q-learning
        algorithm with a nonlinear function approximator, not a convergence
        guarantee. Each call charges ordinary brain work for every next-action
        query as well as the batch fit. The returned ``work`` aggregates all
        those solves; other solve diagnostics describe the fit. ``budget``
        bounds each underlying solve separately.
        """
        if budget is not None:
            integer(budget, "budget")
        if not self._records:
            return dict(accepted=False, reason="empty_replay")
        rng_before = self._rng.getstate()
        count = min(len(self._records), self.config["batch_size"])
        indices = self._rng.sample(range(len(self._records) - 1), count - 1) + [
            len(self._records) - 1
        ]
        examples, targets = [], []
        work = Counter()
        scale, discount = self.config["value_scale"], self.config["discount"]
        try:
            for index in indices:
                context, action, reward, following = self._records[index]
                target = (1 - discount) * scale * (reward / self.config["reward_scale"])
                if following is not None:
                    results, values = self._values(following, budget)
                    for result in results:
                        work.update(result["work"])
                    if not all(r["qualified"] for r in results):
                        self._rng.setstate(rng_before)
                        return dict(
                            accepted=False, reason="bootstrap_refused", work=dict(work)
                        )
                    target += discount * max(-scale, min(scale, max(values)))
                targets.append(target)
                output = self._value_outputs[
                    action if self.config["action_input"] is None else 0
                ]
                examples.append(
                    (
                        self._inputs(context, action),
                        {
                            output.name: target if not output.shape else (target,),
                        },
                    )
                )
            result = self.brain.observe_batch(
                examples, budget=budget, source="estimate"
            )
        except Exception:
            self._rng.setstate(rng_before)
            raise
        if result["accepted"]:
            self._updates += 1
        else:
            self._rng.setstate(rng_before)
        work.update(result["work"])
        return {
            **result,
            "indices": tuple(indices),
            "targets": tuple(targets),
            "updates": self._updates,
            "work": dict(work),
        }

    def reset(self):
        """Discard a pending action without inventing reward or clearing memory."""
        self._pending = None

    def inspect(self):
        """Return configuration and experience counts without exposing owned data."""
        return dict(
            config=dict(self.config),
            records=len(self._records),
            transitions=self._transitions,
            updates=self._updates,
            pending=self._pending is not None,
        )

    def snapshot(self):
        """Save brain, replay, pending action and RNG for exact continuation."""
        text = canonical(
            dict(
                schema="reinforcement/1",
                implementation=_IMPLEMENTATION,
                brain=self.brain.snapshot(),
                config=dict(self.config),
                records=list(self._records),
                pending=self._pending,
                rng=self._rng.getstate(),
                transitions=self._transitions,
                updates=self._updates,
            )
        )
        if len(text.encode()) > MAX_CHECKPOINT_BYTES:
            raise ValueError("Checkpoint exceeds text-size budget")
        return text

    @classmethod
    def from_snapshot(cls, text):
        """Validate a complete checkpoint before constructing a continuation."""
        data = strict_json(text, MAX_CHECKPOINT_BYTES)
        fields = {
            "schema",
            "implementation",
            "brain",
            "config",
            "records",
            "pending",
            "rng",
            "transitions",
            "updates",
        }
        if (
            not isinstance(data, dict)
            or set(data) != fields
            or data["schema"] != "reinforcement/1"
            or data["implementation"] != _IMPLEMENTATION
        ):
            raise ValueError("Unsupported reinforcement checkpoint")
        try:
            obj = cls(Brain.from_snapshot(data["brain"]), **data["config"])
            if set(data["config"]) != set(obj.config):
                raise ValueError("Checkpoint needs complete configuration")
            obj._transitions = integer(data["transitions"], "transitions")
            obj._updates = integer(data["updates"], "updates")
            if not isinstance(data["records"], list) or len(data["records"]) != min(
                obj._transitions, obj.config["capacity"]
            ):
                raise ValueError("Invalid replay length")

            def pending(pair):
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("Invalid pending action")
                action = integer(pair[1], "action")
                if action >= obj.config["actions"]:
                    raise ValueError("Invalid action index")
                return obj._context(pair[0]), action

            for row in data["records"]:
                if not isinstance(row, list) or len(row) != 4:
                    raise ValueError("Invalid transition")
                context, action = pending(row[:2])
                reward = number(row[2], "reward")
                if abs(reward) > obj.config["reward_scale"]:
                    raise ValueError("Invalid reward bound")
                following = None if row[3] is None else obj._context(row[3])
                obj._records.append((context, action, reward, following))
            obj._pending = None if data["pending"] is None else pending(data["pending"])
            rng = data["rng"]
            if (
                not isinstance(rng, list)
                or len(rng) != 3
                or rng[0] != 3
                or type(rng[0]) is not int
                or rng[2] is not None
                or not isinstance(rng[1], list)
                or len(rng[1]) != 625
            ):
                raise ValueError("Invalid RNG state")
            if any(
                type(v) is not int or not 0 <= v <= (624 if i == 624 else 2**32 - 1)
                for i, v in enumerate(rng[1])
            ):
                raise ValueError("Invalid RNG word")
            obj._rng.setstate((3, tuple(rng[1]), None))
            if obj._updates > obj.brain.inspect()["admissions"]:
                raise ValueError("Update count exceeds brain admissions")
            if obj._updates and not obj._transitions:
                raise ValueError("Updates require recorded transitions")
            return obj
        except (TypeError, KeyError, OverflowError, AttributeError) as error:
            raise ValueError("Malformed reinforcement checkpoint") from error
