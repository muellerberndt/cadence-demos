"""Brain + look-ahead: the frozen brain proposes every move; near an enemy, a savestate look-ahead
over the emulator checks the proposal and overrules it only when another move is clearly safer.

Every decision the brain settles and proposes its buttons (``Player.decide``). Where a hostile
object is near (``SAFE_RANGE`` px across, ``SAFE_BAND`` up or down) or Simon stands at one of
two known trouble spots (the stage-2 staircase foot and the ledge past the underground's exit),
the console's state is saved and the brain's proposal and the damage-averse teacher's candidates
(``training/teacher.py``: wait, whip, turn and whip, crouch and whip, jump on, step or jump away)
are each played out ``SAFE_HORIZON`` decisions, the route heuristic after the prefix, and scored
for health and lives lost with a small credit for progress. The state is then restored. The
brain's proposal carries a bonus of ``bonus`` (two health points' worth), so the brain's move is
played unless a candidate loses clearly less; an overruling candidate's first ``commit`` moves
are played. Elsewhere the brain plays alone.

A wait can only postpone a hit the horizon cannot see past (a panther on its ledge leaps only when
Simon walks up), so the look-ahead is patient: when it has overruled within the last
``patience`` decisions and Simon has not moved ``patience_px`` along the route, it stands down for
``rest`` decisions and overrules only to save a life. And where the brain has made no progress
along the route for ``stuck`` decisions (outside the giant bat's fight), the route heuristic's
move stands in for the brain's proposal for ``recover`` decisions, the look-ahead still checking
it; those decisions count as overruled.

The look-ahead reads the console's object table and savestates; the brain sees only through its
eye. Nothing is learned.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))

import teacher as T  # noqa: E402

LABEL = "Cadence brain + look-ahead over the emulator (savestates), frozen brain"


def trouble_spot(ram) -> bool:
    stage, block, wx = int(ram[T.STAGE]), int(ram[T.BLOCK]), T.world_x(ram)
    return stage == 2 and ((block == 1 and wx < 100) or (block == 0 and 300 <= wx <= 520))


class Lookahead:
    def __init__(self, bonus: float = 48.0, commit: int = 2, patience: int = 8, patience_px: int = 8,
                 rest: int = 6, stuck: int = 40, recover: int = 30) -> None:
        self.bonus, self.commit = float(bonus), int(commit)
        self.patience, self.patience_px, self.rest = int(patience), int(patience_px), int(rest)
        self.stuck, self.recover = int(stuck), int(recover)
        self.reset()

    def reset(self) -> None:
        self.memory: dict = {}  # the route heuristic's small state, for the rollouts
        self.plan: list[int] = []
        self.recent: list[tuple[int, int, int, bool]] = []
        self.resting = 0
        self.place, self.best, self.since, self.recovering = None, -10**9, 0, 0
        self.counts = {"decisions": 0, "checked": 0, "brain": 0, "overruled": 0, "recovery": 0}

    def _stalled(self, hd: int) -> bool:
        if len(self.recent) < self.patience:
            return False
        window = self.recent[-self.patience:]
        if not any(o for *_, o in window) or len({(s, b) for s, b, _, _ in window}) > 1:
            return False
        return (window[-1][2] - window[0][2]) * (hd or 1) < self.patience_px

    def decide(self, console, ram, proposal: int) -> tuple[int, dict]:
        """The move to play for the brain's ``proposal`` and what the look-ahead did:
        {"checked", "overruled", "brain", "best"} (scores of the proposal and the best candidate)."""
        ram = np.asarray(ram).astype(int)
        label = int(T.teacher_action(ram, self.memory, None))
        self.counts["decisions"] += 1
        here = (int(ram[T.STAGE]), int(ram[T.BLOCK]), T.world_x(ram))
        hd = T.heading(here[0], here[1], here[2], int(ram[T.OBJ_Y]))
        brain_move = int(proposal)
        recovering = self._track(ram, here, hd)
        if recovering:
            proposal = label  # the route heuristic stands in while the brain is stuck
        act, info = self._decide(console, ram, int(proposal), hd)
        # each decision is one of three: the brain's own move played, the look-ahead overruling the
        # brain, or a stall-recovery stand-in (the route's move, or the look-ahead's over it)
        kind = "brain" if act == brain_move else ("recovery" if recovering else "overruled")
        self.counts[kind] += 1
        info = {**info, "kind": kind, "overruled": kind == "overruled", "recovery": kind == "recovery"}
        T.note_executed(self.memory, label, act)
        self.recent = (self.recent + [here + (bool(info["overruled"]),)])[-self.patience:]
        if not self.resting and self._stalled(hd):
            self.resting, self.plan = self.rest, []
        return act, info

    def _track(self, ram, here, hd: int, memory: dict | None = None) -> bool:
        """True while the route heuristic leads: after ``stuck`` decisions without progress along the
        route in this (stage, block), for ``recover`` decisions."""
        mem = self.memory if memory is None else memory
        if here[2] >= 4000:  # the scroll wraps while a stage or block changes: no reading
            if self.recovering:
                self.recovering -= 1
                return True
            return False
        fight = mem.get("bat_awake") and int(ram[T.BOSS_HP]) > 0
        if (here[0], here[1]) != self.place:
            self.place, self.best, self.since, self.recovering = (here[0], here[1]), here[2] * (hd or 1), 0, 0
        elif here[2] * (hd or 1) > self.best + 4:
            self.best, self.since = here[2] * (hd or 1), 0
            if self.recovering:
                self.recovering = max(0, self.recovering - 1)
        else:
            self.since += 1
        if self.recovering:
            self.recovering -= 1
            return True
        if self.since >= self.stuck and not fight:
            self.since, self.recovering = 0, self.recover
            return True
        return False

    def _decide(self, console, ram, proposal: int, hd: int) -> tuple[int, dict]:
        if self.plan:  # the rest of an overruling candidate
            return int(self.plan.pop(0)), {"checked": False, "overruled": True}
        resting = self.resting > 0
        if resting:
            self.resting -= 1
        near = T.nearest_threat(ram)
        if near is None and not trouble_spot(ram):
            return proposal, {"checked": False, "overruled": False}
        self.counts["checked"] += 1
        saved = console.snapshot()
        side = (1 if near[0] >= 0 else -1) if near is not None else (hd or 1)
        scored = []
        for prefix in ((proposal,),) + tuple(T.SAFE_CANDIDATES):
            console.restore(saved)
            trial = copy.deepcopy(self.memory)
            trial.pop("plan", None)
            score, actions = T.safe_rollout(console, ram, trial, prefix, side, hd or 1)
            if actions:
                scored.append((score, actions))
        console.restore(saved)
        brain_score = scored[0][0] + (0.5 * T.SAFE_LIFE if resting else self.bonus)
        best = max(scored[1:], key=lambda s: s[0])
        info = {"checked": True, "brain": round(scored[0][0], 1), "best": round(best[0], 1)}
        if best[0] > brain_score and best[1][0] != proposal:
            self.plan = list(best[1][1:self.commit])
            return int(best[1][0]), {**info, "overruled": True}
        return proposal, {**info, "overruled": False}
