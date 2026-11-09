"""The arcade's brain: the recipe both editions compose, and the brain's side of a runner.

``build_brain`` is the one ``Brain.compose`` call of the arcade, used by ``server.py`` (the
Python edition) and by the browser edition, which runs this file and the released
``cadence-net`` wheel in Pyodide. ``BrainSide`` is the browser's serial owner of the brain: a
lesson per watched screen, the takeover gate, then one decision per screen it gets to see,
learning from the reward since its last decision. It follows ``server.Runner``'s ``_watch``,
``_play`` and ``_show`` line for line, without the server's threads.

Nothing here imports more than NumPy and Cadence.
"""

from __future__ import annotations

import os
import time

import numpy as np

# One numba thread per process. Each game's brain runs in its own thread (server.py) and numba's
# default threading layer refuses concurrent parallel launches from several threads; with the
# recall memory on, two brains in one process abort without this. Each game takes one core.
os.environ.setdefault("NUMBA_NUM_THREADS", "1")

N_SCREEN = 84 * 84
RETINA_GAIN = 2.0
MIN_LESSONS = 500
MAX_LESSONS = 2000
AGREE_WINDOW = 120
AGREE_TO_PLAY: dict[str, float] = {}
AGREE_DEFAULT = 0.9
RECALL = os.environ.get("ARCADE_RECALL") == "1"


def build_brain(n_actions: int, seed: int = 0, recall: bool | None = None, n_screen: int = N_SCREEN):
    """System 1 on raw pixels with demo learning rates, adaptivity and reward timescales.

    The recall memory is off unless asked for (``ARCADE_RECALL=1``): the screen is the whole
    observation, and the memory triples the brain (21,300 neurons against 7,188) and makes
    each decision about five times slower, so a body that never waits sees far fewer of them.
    """
    from cadence import Brain, LearnerConfig

    return Brain.compose(
        n_screen, n_actions, seed=seed, recall=RECALL if recall is None else bool(recall),
        # the lesson's own steps: each synapse steps on its own running mean over its own
        # running scale, since most pixels are quiet most of the time
        learning=LearnerConfig(
            beta=0.1, temperature=0.2, tolerance=3e-3, free_steps=1024, nudged_steps=12,
            eta_bias=0.02, eta=0.003, momentum=0.9, normalize=0.99, normalize_floor=1e-4),
        # reward learning over a long life at a small actor rate
        actor_gamma=0.97, actor_lam=0.9, actor_eta=0.001, actor_eta_bias=0.0001,
        actor_eta_critic=0.3,
        # one core: the browser has no other backend, and the server keeps the bits it measured
        backend="cpu",
    )


def _round(values, digits: int = 3) -> list[float]:
    return [float(v) for v in np.round(np.asarray(values, dtype=float).ravel(), digits)]


class BrainSide:
    """One brain and its watching and playing, driven one snapshot at a time."""

    def __init__(self, game: str, meanings: list[str], seed: int = 0, life_learn: bool = True,
                 recall: bool | None = None) -> None:
        self.game = game
        self.meanings = list(meanings)
        self.n_actions = len(self.meanings)
        self.seed = int(seed)
        self.life_learn = life_learn
        began = time.perf_counter()
        self.brain = build_brain(self.n_actions, seed=self.seed, recall=recall)
        self.compose_ms = (time.perf_counter() - began) * 1000.0
        graph = self.brain.connectome
        self.assoc = np.asarray(graph.populations["association"])
        self.trace = np.asarray(graph.populations["prefrontal"])
        self.motor = np.asarray(self.brain.motor_index)
        self.phase = "watching"
        self.lessons = 0
        self.agreement: list[int] = []
        self.agree_hist: list[float] = []
        self.sweeps_hist: list[int] = []
        self.last_sweeps: int | None = None
        self.decisions = 0
        self.outcomes = 0
        self.rewarded = 0
        self.refused = 0
        self.faults = 0
        self.last_error: str | None = None
        self.value = 0.0
        self.dopamine = 0.0
        self.pending = False
        self.current_action = 0
        self.takeover: dict | None = None
        self.think_ms: list[float] = []
        self.viz: dict | None = None
        self.viz_t = 0.0
        self._prev = None
        self.born = time.time()

    # ---- what the page draws -----------------------------------------------------------
    def populations(self) -> list[dict]:
        n, t, a = len(self.assoc), len(self.trace), self.n_actions
        return [{"name": "association", "count": n, "start": 0},
                {"name": "trace", "count": t, "start": n},
                {"name": "motor", "count": a, "start": n + t},
                {"name": "memory", "count": a, "start": n + t + a},
                {"name": "value", "count": 1, "start": n + t + 2 * a}]

    def graph_sample(self, per_kind: int = 260) -> list[list]:
        """Synapses as [kind, source, target, weight]; kind 0 starts at a retina pixel, kind 1
        at another node. The strongest of a random tenth, with their current weights."""
        graph = self.brain.connectome
        weights = np.asarray(self.brain.brain.weights)
        node = np.full(graph.n, -1)
        node[self.assoc] = np.arange(len(self.assoc))
        node[self.trace] = len(self.assoc) + np.arange(len(self.trace))
        node[self.motor] = len(self.assoc) + len(self.trace) + np.arange(self.n_actions)
        pixel = np.full(graph.n, -1)
        pixel[np.asarray(self.brain.sensory_index)] = np.arange(len(self.brain.sensory_index))
        rng = np.random.default_rng(7)
        edges = []
        from_pixel = np.flatnonzero(pixel[graph.pre] >= 0)
        inner = np.flatnonzero((node[graph.pre] >= 0) & (node[graph.post] >= 0))
        for members, kind, count in ((from_pixel, 0, per_kind), (inner, 1, 2 * per_kind)):
            if len(members) > count:
                pool = rng.choice(members, min(len(members), 10 * count), replace=False)
                members = pool[np.argsort(-np.abs(weights[pool]))[:count]]
            for i in members:
                source = pixel[graph.pre[i]] if kind == 0 else node[graph.pre[i]]
                edges.append([kind, int(source), int(node[graph.post[i]]), round(float(weights[i]), 3)])
        return edges

    def _show(self, state, sweeps: int, x: np.ndarray, wrong_action: int | None = None) -> None:
        act = np.asarray(state.activation)[0]
        memory = self.brain.hippocampus.recall(x)[0]
        vec = np.concatenate([act[self.assoc], act[self.trace], act[self.motor], memory, [self.value]])
        prev = self._prev
        delta = np.abs(vec - prev) if prev is not None and len(prev) == len(vec) else np.zeros(len(vec))
        self._prev = vec
        errors = np.zeros(len(vec))
        errors[-1] = min(1.0, abs(self.dopamine))
        if wrong_action is not None:
            errors[len(self.assoc) + len(self.trace) + wrong_action] = 1.0
        self.last_sweeps = int(sweeps)
        self.sweeps_hist = (self.sweeps_hist + [int(sweeps)])[-48:]
        self.viz = {"state": _round(vec), "errors": _round(errors), "delta": _round(delta), "q": True}
        self.viz_t = time.time() * 1000.0

    # ---- the brain's two phases ----------------------------------------------------------
    def _watch(self, x: np.ndarray, teacher: int, teacher_games: int) -> dict:
        """One watched screen: the brain's own greedy answer (not executed, no eligibility),
        then the lesson with the teacher's action as this screen's label."""
        brain = self.brain
        drive = brain.stimulus(x)
        try:
            own = int(brain.act(x, greedy=True)[0])
        except RuntimeError as exc:
            own = None
            self.refused += 1
            self.last_error = f"refused: {exc}"
        self.agreement = (self.agreement + [int(own == teacher)])[-AGREE_WINDOW:]
        state = brain.basal_ganglia.state
        if own is not None and self.lessons % 3 == 0:
            self.value = float(brain.basal_ganglia.value(state)[0])
            self._show(state, state.steps, x, wrong_action=None if own == teacher else teacher)
        brain.learner.step(drive, np.array([teacher]))
        self.lessons += 1
        if self.lessons % 10 == 0:
            self.agree_hist = (self.agree_hist + [round(float(np.mean(self.agreement)), 3)])[-60:]
        agree = float(np.mean(self.agreement))
        gate = AGREE_TO_PLAY.get(self.game, AGREE_DEFAULT)
        ready = ((self.lessons >= MIN_LESSONS and len(self.agreement) >= AGREE_WINDOW and agree >= gate)
                 or self.lessons >= MAX_LESSONS)
        # the badge measures the brain against the teacher's own games: it watches one whole game
        if ready and teacher_games >= 1:
            self.takeover = {"lessons": self.lessons, "agreement": round(agree, 3),
                             "seconds": round(time.time() - self.born, 1)}
            self.current_action = teacher
            self.pending = False
            self.phase = "playing"
            return {"takeover": True, "action": teacher, "consumed": True}
        return {}

    def _play(self, x: np.ndarray, teacher: int, reward: float, done: bool) -> dict:
        """One decision at the controls: the outcome of the last action (the reward since then,
        whether an episode ended), then the next action."""
        brain = self.brain
        try:
            if not self.life_learn:
                if done:
                    brain.reset()
                action = int(brain.act(x)[0])
            elif self.pending:
                signal = float(np.sign(reward))
                action = int(brain.step(x, reward=np.array([signal]), done=np.array([bool(done)]))[0])
                self.outcomes += 1
                self.rewarded += int(signal != 0)
                self.dopamine = float(brain.last_learning.get("dopamine", 0.0))
            else:
                action = int(brain.step(x)[0])
        except RuntimeError as exc:
            # no answer settled: no action was issued; the body holds its last one, uncredited
            self.refused += 1
            self.last_error = f"refused: {exc}"
            self.pending = False
            if done:
                brain.reset()
            return {"consumed": True}
        self.current_action = action
        self.pending = True
        self.decisions += 1
        self.agreement = (self.agreement + [int(action == teacher)])[-AGREE_WINDOW:]
        state = brain.basal_ganglia.state
        self.value = float(brain.basal_ganglia.value(state)[0])
        sweeps = state.steps + int(brain.last_learning.get("free_steps", 0))
        if self.decisions % 3 == 0:
            self._show(state, sweeps, x)
        if self.decisions % 10 == 0:
            self.agree_hist = (self.agree_hist + [round(float(np.mean(self.agreement)), 3)])[-60:]
        return {"action": action, "consumed": True}

    def iterate(self, drive, teacher: int, reward: float, done: bool, teacher_games: int) -> dict:
        """One iteration over the latest screen. ``drive`` is the retina's 7,056 values (any
        buffer of float64); ``reward`` and ``done`` cover the time since the last decision."""
        x = np.asarray(drive, dtype=float).reshape(1, -1)
        began = time.perf_counter()
        try:
            out = (self._watch(x, int(teacher), int(teacher_games)) if self.phase == "watching"
                   else self._play(x, int(teacher), float(reward), bool(done)))
        except Exception as exc:  # counted and shown, never swallowed silently
            self.faults += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.pending = False
            out = {"fault": self.last_error}
        self.think_ms = (self.think_ms + [(time.perf_counter() - began) * 1000.0])[-20000:]
        return out

    def state(self) -> dict:
        agree = round(float(np.mean(self.agreement)), 2) if self.agreement else None
        gate = AGREE_TO_PLAY.get(self.game, AGREE_DEFAULT)
        recent = self.think_ms[-200:]
        return {
            "phase": self.phase,
            "watch": {"lessons": self.lessons,
                      "to_takeover": round(min(1.0, self.lessons / MIN_LESSONS) * min(1.0, (agree or 0) / gate), 2),
                      "sweeps": self.last_sweeps, "agreement": agree, "sweeps_hist": self.sweeps_hist,
                      "agree_hist": self.agree_hist, "takeover": self.takeover},
            "brain": {"beat_age": 0.0, "faults": self.faults, "last_error": self.last_error},
            "life": {"decisions": self.decisions, "outcomes": self.outcomes, "refused": self.refused,
                     "rewarded": self.rewarded,
                     "think_ms": round(float(np.median(recent)), 1) if recent else None,
                     "think_ms_scope": "median of the latest 200 brain handlers, watching and play, including refusals",
                     "value": round(self.value, 3), "dopamine": round(self.dopamine, 3)},
        }
