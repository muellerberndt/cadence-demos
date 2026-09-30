"""Best-effort live scheduling and actuator rate limits, not hard real time.

The worker exclusively owns calls to its callback. If that callback uses a
``Brain``, callers must not query or mutate that brain elsewhere until ``close``
reports worker exit. Python scheduling and the GIL still affect latency;
neither a solve deadline nor thread cancellation is provided here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence

from ._validation import number


def _vector(value, name):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a nonempty finite numeric sequence")
    if not value:
        raise ValueError(f"{name} must be a nonempty finite numeric sequence")
    return tuple(number(item, name) for item in value)


def _observation(value):
    """Copy finite JSON-like data, retaining tuples and rejecting cycles."""
    active = set()

    def copy(item):
        if item is None or type(item) in (str, bool):
            return item
        if type(item) in (int, float):
            number(item, "observation number")
            return item
        if type(item) not in (dict, list, tuple):
            raise ValueError("observation must contain only finite JSON-like data")
        identity = id(item)
        if identity in active:
            raise ValueError("observation must not contain cycles")
        active.add(identity)
        try:
            if type(item) is dict:
                if any(type(key) is not str for key in item):
                    raise ValueError("observation object keys must be strings")
                return {key: copy(value) for key, value in item.items()}
            values = [copy(value) for value in item]
            return tuple(values) if type(item) is tuple else values
        finally:
            active.remove(identity)

    try:
        return copy(value)
    except RecursionError as error:
        raise ValueError("observation nesting is too deep") from error


class LiveController:
    """Run one serial callback without waiting for it in ``submit`` or ``read``.

    ``callback(observation)`` returns a mapping with an exact boolean
    ``qualified``. A qualified result must contain a finite ``command`` sequence
    of the same length as ``fallback``. A refused result may omit ``command``;
    its command is never used. Extra fields are ignored. Callback exceptions or
    malformed results become errors and leave the worker available for later
    observations. This protocol deliberately does not interpret ``accepted``.

    ``submit`` copies finite JSON-like data (string-keyed dictionaries, lists,
    tuples, strings, booleans, numbers and None), returning a positive submission
    ID. At most one observation waits behind an in-flight callback; replacement
    drops only that pending observation. A callback already running is allowed
    to finish. Copying and validation take time proportional to the input.

    ``read`` returns an immutable command tuple. It falls back before the first
    qualified completion, after refusal/error, after ``max_age`` seconds from
    that result's sensory submission, or after closure. A prior fresh command
    remains available while newer work is pending. Age includes queue and solve
    time; completing an old observation cannot make its command fresh again.

    ``clock`` must be a fast, finite, nondecreasing clock in seconds. ``max_age``
    is positive. ``close`` drops pending work and allows the active callback to
    finish, waiting at most its finite ``timeout`` (one second by default).
    It returns whether the daemon worker has exited. It never cancels a solve.
    A false return means the worker still owns the callback and its brain.
    """

    def __init__(self, callback, *, fallback, max_age=0.25, clock=time.monotonic):
        if not callable(callback) or not callable(clock):
            raise ValueError("callback and clock must be callable")
        self._fallback = _vector(fallback, "fallback")
        self._max_age = number(max_age, "max_age", positive=True)
        self._callback, self._clock = callback, clock
        self._condition = threading.Condition()
        self._last_clock = number(clock(), "clock value")
        self._pending = self._latest = None
        self._busy = self._closed = False
        self._counts = dict.fromkeys(
            (
                "submitted",
                "dropped",
                "started",
                "completed",
                "qualified",
                "refused",
                "errors",
            ),
            0,
        )
        self._last_solve_seconds = self._last_latency_seconds = None
        self._last_error = None
        self._thread = threading.Thread(
            target=self._run, name="cadence-live", daemon=True
        )
        self._thread.start()

    def _now(self):
        now = number(self._clock(), "clock value")
        if now < self._last_clock:
            raise ValueError("clock must be nondecreasing")
        self._last_clock = now
        return now

    def submit(self, observation):
        """Copy and enqueue observation, returning its ID without awaiting a solve."""
        with self._condition:
            if self._closed:
                raise ValueError("controller is closed")
            submitted_at = self._now()
            copied = _observation(observation)
            self._counts["submitted"] += 1
            identity = self._counts["submitted"]
            if self._pending is not None:
                self._counts["dropped"] += 1
            self._pending = identity, submitted_at, copied
            self._condition.notify()
            return identity

    def _decision(self, now):
        if self._closed:
            return "closed", self._fallback
        if self._latest is None:
            return "waiting", self._fallback
        _, submitted_at, status, command = self._latest
        if status != "qualified":
            return status, self._fallback
        if now - submitted_at > self._max_age:
            return "stale", self._fallback
        return status, command

    def read(self):
        """Return the latest fresh qualified command, or the declared fallback."""
        with self._condition:
            return self._decision(self._now())[1]

    def inspect(self):
        """Return copied counters, decision status and latest completion timings.

        ``last_solve_seconds`` includes callback execution and result validation;
        ``last_latency_seconds`` also includes queue time. ``result_age`` is
        measured from submission. Timings are seconds from the supplied clock.
        Refused and malformed completed results also increment ``completed``.
        ``dropped`` counts overwritten or closed pending observations only.
        """
        with self._condition:
            now = self._now()
            return {
                **self._counts,
                "closed": self._closed,
                "busy": self._busy,
                "pending": self._pending is not None,
                "worker_alive": self._thread.is_alive(),
                "status": self._decision(now)[0],
                "last_result_id": self._latest[0] if self._latest else None,
                "result_age": now - self._latest[1] if self._latest else None,
                "last_solve_seconds": self._last_solve_seconds,
                "last_latency_seconds": self._last_latency_seconds,
                "last_error": self._last_error,
            }

    def close(self, *, wait=True, timeout=1.0):
        """Stop accepting work; wait at most ``timeout`` and report worker exit."""
        if type(wait) is not bool:
            raise ValueError("wait must be a boolean")
        timeout = number(timeout, "timeout")
        if timeout < 0:
            raise ValueError("timeout must be nonnegative")
        if timeout > threading.TIMEOUT_MAX:
            raise ValueError("timeout exceeds the platform thread-wait limit")
        with self._condition:
            self._closed = True
            if self._pending is not None:
                self._counts["dropped"] += 1
                self._pending = None
            self._condition.notify()
        if wait and threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._closed or self._pending is not None
                )
                if self._closed:
                    return
                identity, submitted_at, observation = self._pending
                self._pending = None
                self._busy = True
                self._counts["started"] += 1
                try:
                    started_at = self._now()
                    clock_error = None
                except Exception as error:
                    started_at, clock_error = None, error
            command, error_text = None, None
            try:
                if clock_error is not None:
                    raise clock_error
                result = self._callback(observation)
                if (
                    not isinstance(result, Mapping)
                    or type(result.get("qualified")) is not bool
                ):
                    raise ValueError("callback result requires boolean qualified")
                status = "qualified" if result["qualified"] else "refused"
                if status == "qualified":
                    command = _vector(result.get("command"), "command")
                    if len(command) != len(self._fallback):
                        raise ValueError("command must match fallback length")
            except Exception as error:
                status = "error"
                error_text = f"{type(error).__name__}: {error}"
            with self._condition:
                try:
                    finished_at = self._now()
                except Exception as error:
                    finished_at, status = None, "error"
                    error_text = f"{type(error).__name__}: {error}"
                self._busy = False
                self._counts["completed"] += 1
                self._counts["errors" if status == "error" else status] += 1
                self._latest = identity, submitted_at, status, command
                self._last_error = error_text
                self._last_solve_seconds = (
                    finished_at - started_at
                    if finished_at is not None and started_at is not None
                    else None
                )
                self._last_latency_seconds = (
                    finished_at - submitted_at if finished_at is not None else None
                )


def slew(current, target, *, rate, dt):
    """Move each coordinate toward a supplied target by at most ``rate * dt``.

    Vectors must be nonempty, finite and equal length. ``rate`` is a nonnegative
    scalar or an equal-length vector; ``dt`` is finite nonnegative seconds.
    This actuator helper limits speed without selecting a target or action.
    """
    current, target = _vector(current, "current"), _vector(target, "target")
    if len(current) != len(target):
        raise ValueError("current and target must have equal length")
    if isinstance(rate, Sequence) and not isinstance(rate, (str, bytes)):
        rates = _vector(rate, "rate")
        if len(rates) != len(current):
            raise ValueError("rate must match current length")
    else:
        rates = (number(rate, "rate"),) * len(current)
    dt = number(dt, "dt")
    if dt < 0 or any(value < 0 for value in rates):
        raise ValueError("rate and dt must be nonnegative")
    limits = tuple(number(value * dt, "rate * dt") for value in rates)
    return tuple(
        min(goal, value + limit) if goal >= value else max(goal, value - limit)
        for value, goal, limit in zip(current, target, limits, strict=True)
    )
