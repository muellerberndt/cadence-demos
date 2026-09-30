"""Explicit temporal context and an error-progress heuristic, outside brain repair."""

from __future__ import annotations

from ._validation import canonical, integer, number, strict_json
from .ports import _values

_MAX_HISTORY_SIZE = 1_000_000
_MAX_CONTEXTS = 4096
_MAX_KEY_BYTES = 256
_MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024


def _checkpoint(text, kind, fields):
    try:
        data = strict_json(text, _MAX_CHECKPOINT_BYTES)
    except UnicodeError as error:
        raise ValueError("Checkpoint must contain valid UTF-8 text") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"kind", "version", *fields}
        or data["kind"] != kind
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError("Invalid memory checkpoint fields or version")
    return data


def _key(value):
    if not isinstance(value, str) or not value:
        raise ValueError("key must be a nonempty string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError("key must contain valid UTF-8 text") from error
    if size > _MAX_KEY_BYTES:
        raise ValueError(f"key must use at most {_MAX_KEY_BYTES} UTF-8 bytes")
    return value


def _error(value):
    value = number(value, "error")
    if value < 0:
        raise ValueError("error must be nonnegative")
    return value


class History:
    """A bounded caller-fed window, not learned neural memory.

    ``size`` is the number of scalars per observation; ``steps`` is the number
    of observations retained. The encoded vector has ``steps * (size + 1)``
    coordinates. Each oldest-to-newest block contains its values followed by
    a validity mask (one for an actual observation, zero for initial padding).
    Missing observations within a real sample need their own caller encoding.
    Encoded width is limited to one million coordinates.
    """

    __slots__ = ("_input_size", "_steps", "_rows")

    def __init__(self, size, *, steps=4):
        self._input_size = integer(size, "size", 1)
        self._steps = integer(steps, "steps", 1)
        if self._steps * (self._input_size + 1) > _MAX_HISTORY_SIZE:
            raise ValueError(
                f"encoded history size must be at most {_MAX_HISTORY_SIZE}"
            )
        self._rows = ()

    @property
    def input_size(self):
        """Number of scalar values required by each push or preview."""
        return self._input_size

    @property
    def steps(self):
        """Maximum number of retained observations."""
        return self._steps

    @property
    def size(self):
        """Encoded width, including one validity mask per observation slot."""
        return self.steps * (self.input_size + 1)

    @property
    def shape(self):
        """Flat input shape suitable for ``Cortex.input(shape=history.shape)``."""
        return (self.size,)

    def _append(self, values):
        row = _values(values, (self.input_size,), "history values")
        return (*self._rows, row)[-self.steps :]

    def _encode(self, rows):
        padding = (0.0,) * (self.size - len(rows) * (self.input_size + 1))
        return padding + tuple(value for row in rows for value in (*row, 1.0))

    def push(self, values):
        """Retain a finite flat sample and return the padded encoded window.

        Drop the oldest sample if full. Invalid samples leave history unchanged.
        """
        rows = self._append(values)
        encoded = self._encode(rows)
        self._rows = rows
        return encoded

    def preview(self, values):
        """Return the encoding after a hypothetical push, without retaining it."""
        return self._encode(self._append(values))

    def reset(self):
        """Forget all observations; the next encoding starts with empty padding."""
        self._rows = ()

    def snapshot(self):
        """Serialize dimensions and retained rows as bounded, finite JSON."""
        return canonical(
            {
                "kind": "cadence.history",
                "version": 1,
                "input_size": self.input_size,
                "steps": self.steps,
                "rows": self._rows,
            }
        )

    @classmethod
    def from_snapshot(cls, text):
        """Restore validated JSON of at most 32 MiB, with exact schema fields."""
        data = _checkpoint(text, "cadence.history", {"input_size", "steps", "rows"})
        result = cls(data["input_size"], steps=data["steps"])
        rows = data["rows"]
        if not isinstance(rows, list) or len(rows) > result.steps:
            raise ValueError("checkpoint rows must fit the history window")
        result._rows = tuple(
            _values(row, (result.input_size,), "checkpoint row") for row in rows
        )
        return result


class LearningProgress:
    """Bounded per-context reduction of a caller-supplied prediction error.

    ``rate`` in (0, 1] updates the error mean as ``m' = m + rate * (error-m)``.
    ``update`` returns ``max(0, m-m') / max(1, m)`` in [0, 1], or zero for a
    new context. Error units therefore matter. This is a heuristic, not
    information gain, a reward learner, or numerical settlement qualification.
    Noisy downward fluctuations can also produce a positive score.

    ``capacity`` bounds context means (1..4096); the least recently updated
    context is evicted when full. Keys are nonempty strings of at most 256
    UTF-8 bytes. Forgetting an evicted context makes its next update a first
    observation again. No brain state or parameters are changed by this helper.
    """

    __slots__ = ("_rate", "_capacity", "_errors")

    def __init__(self, *, rate=0.1, capacity=128):
        self._rate = number(rate, "rate", positive=True)
        if self._rate > 1:
            raise ValueError("rate must be at most one")
        self._capacity = integer(capacity, "capacity", 1)
        if self._capacity > _MAX_CONTEXTS:
            raise ValueError(f"capacity must be at most {_MAX_CONTEXTS}")
        self._errors = {}

    @property
    def rate(self):
        """Moving-error update fraction in (0, 1]."""
        return self._rate

    @property
    def capacity(self):
        """Maximum number of context means retained."""
        return self._capacity

    def update(self, key, error):
        """Record actual predictor error and return its positive mean reduction.

        Error must be finite and nonnegative. Validation occurs before any
        update or eviction. New contexts and constant/increasing errors score
        zero; random fluctuations are not evidence of acquired capability.
        """
        key, error = _key(key), _error(error)
        previous = self._errors.get(key)
        if previous is None:
            current = error
        elif error >= previous:
            current = previous + self.rate * (error - previous)
        else:
            # Add from the smaller endpoint: at rate=1 a large downward jump
            # must retain the new error, not cancel it out of the old mean.
            current = error + (1 - self.rate) * (previous - error)
        progress = (
            0.0
            if previous is None
            else max(0.0, previous - current) / max(1.0, previous)
        )
        self._errors.pop(key, None)
        if len(self._errors) == self.capacity:
            del self._errors[next(iter(self._errors))]
        self._errors[key] = current
        return progress

    def snapshot(self):
        """Serialize means and their eviction order, preserving continuation."""
        return canonical(
            {
                "kind": "cadence.learning-progress",
                "version": 1,
                "rate": self.rate,
                "capacity": self.capacity,
                "errors": list(self._errors.items()),
            }
        )

    @classmethod
    def from_snapshot(cls, text):
        """Restore bounded finite JSON, rejecting duplicate contexts or fields."""
        data = _checkpoint(
            text, "cadence.learning-progress", {"rate", "capacity", "errors"}
        )
        result = cls(rate=data["rate"], capacity=data["capacity"])
        rows = data["errors"]
        if not isinstance(rows, list) or len(rows) > result.capacity:
            raise ValueError("checkpoint errors must fit the context capacity")
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("checkpoint errors must contain [key, error] pairs")
            key, error = _key(row[0]), _error(row[1])
            if key in result._errors:
                raise ValueError("duplicate context in checkpoint")
            result._errors[key] = error
        return result
