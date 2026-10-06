"""One continuing life: see the frame, answer, witness where the target was, learn by policy.

The brain answers every tick with a greedy ``act``: the whole connectome settles from the
previous free state under the new frame, both memory pathways are read and the working trace
advances. The answer is scored before anything else happens. The world then reveals the target
position (unless the target is hidden) and the declared teaching policy decides whether that
witnessed position becomes a lesson. A lesson is the library's local contrast step on the same
drive the answer used, warm from the answer's own free state.

This is the supervised-only stream of the Cadence guide on continuous interaction. Reward
learning through ``step`` is a separate arm.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from cadence import Brain

from .world import Frame, World

__all__ = ["Life", "Teaching", "copy_state", "region_spans", "repair_work"]


@dataclass(frozen=True)
class Teaching:
    """When a witnessed target becomes a lesson.

    ``always``: every visible tick (a demonstrated object). ``miss``: only after a report
    more than ``miss`` bins away on either axis, or a refused answer (failure-driven repair).
    ``never``: free behaviour only.
    """

    mode: str = "always"
    miss: int = 1

    def wants(self, frame: Frame, answer: tuple[int, int] | None) -> bool:
        if not frame.visible or self.mode == "never":
            return False
        if self.mode == "always" or answer is None:
            return True
        return max(abs(answer[0] - frame.target[0]), abs(answer[1] - frame.target[1])) > self.miss


def copy_state(state):
    """An owned copy of a ``BrainState`` (live states must not be mutated by instruments)."""
    if state is None:
        return None
    return replace(
        state, v=np.array(state.v), activation=np.array(state.activation),
        adaptation=np.array(state.adaptation),
    )


def region_spans(brain: Brain) -> dict[str, np.ndarray]:
    """Neuron indices of the regions whose movement is reported."""
    pops = brain.connectome.populations
    names = [n for n in pops if n.startswith("visual/") or n in ("association", "prefrontal", "motor")]
    return {n: np.asarray(pops[n], dtype=np.int64) for n in names if n != "motor/actions"}


def repair_work(brain: Brain, drive: np.ndarray, state, *, budget: int | None = None) -> dict:
    """Sweeps to qualification at one-sweep resolution, from ``state`` under ``drive``.

    Runs on the brain's current graph with its own tolerance and no damping, on a copy of the
    state. The life never sees this solve.
    """
    cfg = brain.learner.config
    budget = budget if budget is not None else max(cfg.free_steps // 2, 1)
    eq = brain.brain.equilibrate(
        drive, state=copy_state(state), budget=budget, chunk=1, tolerance=cfg.tolerance,
    )
    return {"fine_sweeps": int(eq.steps), "fine_qualified": bool(np.all(eq.qualified))}


class Life:
    """A brain living in a world under a teaching policy, one tick at a time."""

    def __init__(
        self,
        brain: Brain,
        world: World,
        *,
        teaching: Teaching = Teaching(),
        footprint: bool = False,
        instrument: float = 0.0,
        moved: float = 0.01,
        seed: int = 0,
    ) -> None:
        self.brain = brain
        self.world = world
        self.teaching = teaching
        self.footprint = footprint
        self.instrument = instrument
        self.moved = moved
        self.rng = np.random.default_rng(seed)
        self.spans = region_spans(brain)
        self.last_seen: tuple[int, int] | None = None
        self.last_answer: tuple[int, int] | None = None
        self.locked: tuple[int, int] | None = None  # the last answer given while the target was visible
        self.ticks = 0

    def see(self, frame: Frame, phase: str = "") -> dict[str, Any]:
        """One tick on a supplied frame."""
        brain = self.brain
        x = frame.pixels.reshape(1, -1)
        drive = brain.stimulus(x)
        before = brain.basal_ganglia.state
        keep = copy_state(before) if (self.footprint or self.instrument) and before is not None else None
        row: dict[str, Any] = {
            "phase": phase, "tick": self.ticks, "event": frame.event,
            "displacement": round(frame.displacement, 4), "visible": frame.visible,
            "tx": frame.target[0], "ty": frame.target[1],
            "x": round(frame.x, 3), "y": round(frame.y, 3),
        }
        if keep is not None and self.instrument and self.rng.random() < self.instrument:
            row.update(repair_work(brain, drive, keep))
        start = time.perf_counter()
        answer: tuple[int, int] | None
        try:
            chosen = brain.act(x, greedy=True)[0]
            answer = (int(chosen[0]), int(chosen[1]))
        except RuntimeError:
            answer = None
        settled = brain.last_settlement or {}
        row.update({
            "ax": -1 if answer is None else answer[0],
            "ay": -1 if answer is None else answer[1],
            "refused": answer is None,
            "sweeps": int(settled.get("steps", 0)),
            "residual": float(settled.get("max_residual", np.nan)),
            "damped": int(settled.get("damping_halvings", 0)),
        })
        row.update(self._score(frame, answer))
        if keep is not None and answer is not None and self.footprint:
            after = brain.basal_ganglia.state
            delta = np.abs(after.activation[0] - keep.activation[0])
            row["moved"] = {k: int((delta[idx] > self.moved).sum()) for k, idx in self.spans.items()}
        lesson = self.teaching.wants(frame, answer)
        row["lesson"] = lesson
        if lesson:
            labels = np.array([frame.target], dtype=np.int64)
            warm = brain.basal_ganglia.state if answer is not None else None
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                _, report = brain.learner.step(drive, labels, warm=warm)
            row["lesson_sweeps"] = int(report.get("total_steps", 0))
            row["lesson_exhausted"] = bool(report.get("free_budget_exhausted", 0.0))
            row["lesson_warnings"] = len(caught)
        row["ms"] = round((time.perf_counter() - start) * 1000, 2)
        if frame.visible:
            self.last_seen = frame.target
            if answer is not None:
                self.locked = answer
        if answer is not None:
            self.last_answer = answer
        self.ticks += 1
        return row

    def _score(self, frame: Frame, answer: tuple[int, int] | None) -> dict[str, Any]:
        tx, ty = frame.target
        if answer is None:
            return {"hit": False, "exact": False, "err_px": None, "hold": None}
        ax, ay = answer
        cx, cy = self.world.centre_of(ax, ay)
        out = {
            "hit": max(abs(ax - tx), abs(ay - ty)) <= 1,
            "exact": (ax, ay) == (tx, ty),
            "err_px": round(float(np.hypot(cx - frame.x, cy - frame.y)), 3),
            "hold": None,
        }
        if not frame.visible and self.locked is not None:
            lx, ly = self.locked
            out["hold"] = max(abs(ax - lx), abs(ay - ly)) <= 1
        return out

    def run(self, ticks: int, phase: str = "", log=None) -> list[dict[str, Any]]:
        rows = []
        for _ in range(ticks):
            row = self.see(self.world.step(), phase)
            rows.append(row)
            if log is not None:
                log(row)
        return rows
