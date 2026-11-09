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
AGREE_TO_PLAY: dict[str, float] = {}
CHANGE = 1e-4  # a synapse counts as changed in the view when its weight moved by more than this

# The arcade's recipe. ``ARCADE_RECIPE`` (a JSON object, or a path to one) patches it for a run;
# ``ARCADE_RECALL=1`` turns the recall memory on.
RECIPE: dict = {
    "modules": [64],                 # one association region (System 1, no observers)
    "teaching": "custom",            # "custom": the learning settings below; "deep": the library's deep point
    "apical": 0.25,                  # read only with teaching "deep" and several modules
    "learning": {"beta": 0.1, "temperature": 0.2, "tolerance": 3e-3, "free_steps": 1024,
                 "nudged_steps": 12, "eta_bias": 0.02, "eta": 0.003, "momentum": 0.9,
                 "normalize": 0.99, "normalize_floor": 1e-4},
    "actor": {"gamma": 0.97, "lam": 0.9, "eta": 0.001, "eta_bias": 0.0001, "eta_critic": 0.3},
    "recall": False,
    "arousal": None,                 # None, true, or a mapping of arousal genes (life "live")
    "efference_amplitude": 0.0,
    "life": "step",                  # "step": learn from every outcome; "live": calm or aroused
    "min_lessons": 500,
    "max_lessons": 2000,
    "agree": 0.9,
    "agree_window": 120,
}


def recipe(patch: dict | None = None) -> dict:
    """The recipe with ``ARCADE_RECIPE`` and ``patch`` applied (nested dicts are merged)."""
    import json

    out = json.loads(json.dumps(RECIPE))
    env = os.environ.get("ARCADE_RECIPE")
    layers = []
    if env:
        layers.append(json.loads(open(env).read() if os.path.exists(env) else env))
    if os.environ.get("ARCADE_RECALL") == "1":
        layers.append({"recall": True})
    if patch:
        layers.append(patch)
    for layer in layers:
        for key, value in layer.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = {**out[key], **value}
            else:
                out[key] = value
    return out


RECALL = recipe()["recall"]
MIN_LESSONS = RECIPE["min_lessons"]
MAX_LESSONS = RECIPE["max_lessons"]
AGREE_WINDOW = RECIPE["agree_window"]
AGREE_DEFAULT = RECIPE["agree"]


def build_brain(n_actions: int, seed: int = 0, recall: bool | None = None, n_screen: int = N_SCREEN,
                rec: dict | None = None):
    """System 1 on raw pixels with the recipe's learning rates, adaptivity and reward timescales.

    The recall memory is off unless asked for: the screen is the whole observation, and the
    memory triples the brain (21,300 neurons against 7,188) and makes each decision about six
    times slower, so a body that never waits sees far fewer of them.
    """
    from cadence import Brain, LearnerConfig

    r = rec if rec is not None else recipe()
    if recall is not None:
        r = {**r, "recall": bool(recall)}
    options: dict = dict(seed=seed, recall=bool(r["recall"]), modules=tuple(r["modules"]),
                         backend="cpu")  # one core: the browser has no other backend
    options.update({f"actor_{k}": v for k, v in r["actor"].items()})
    if r["teaching"] == "deep":
        options["teaching"] = "deep"
        if len(r["modules"]) > 1:
            options["apical"] = r["apical"]
        # the deep point sets its own steps and constants; the recipe keeps its temperature
        if "temperature" in r["learning"]:
            options["temperature"] = r["learning"]["temperature"]
    else:
        # the lesson's own steps: each synapse steps on its own running mean over its own
        # running scale, since most pixels are quiet most of the time
        options["learning"] = LearnerConfig(**r["learning"])
    if r.get("arousal") is not None or r["life"] == "live":
        options["arousal"] = r.get("arousal") if r.get("arousal") is not None else True
    if r.get("efference_amplitude"):
        options["efference_amplitude"] = r["efference_amplitude"]
    return Brain.compose(n_screen, n_actions, **options)


def _round(values, digits: int = 3) -> list[float]:
    return [float(v) for v in np.round(np.asarray(values, dtype=float).ravel(), digits)]


class BrainSide:
    """One brain and its watching and playing, driven one snapshot at a time."""

    def __init__(self, game: str, meanings: list[str], seed: int = 0, life_learn: bool = True,
                 recall: bool | None = None, rec: dict | None = None, replay_every: int = 0) -> None:
        self.rec = rec if rec is not None else recipe()
        if recall is not None:
            self.rec = {**self.rec, "recall": bool(recall)}
        self.game = game
        self.meanings = list(meanings)
        self.n_actions = len(self.meanings)
        self.seed = int(seed)
        self.life_learn = life_learn
        began = time.perf_counter()
        self.brain = build_brain(self.n_actions, seed=self.seed, rec=self.rec)
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
        self.calm = 0
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
        self._drawn = None         # the synapses the page draws (graph_sample)
        self._weights = None       # every weight at the previous view, to count changes
        self.shows = 0
        self._seen_reward = 0.0    # the sum of reward signs since the last view
        self._seen_dopamine = 0.0  # the largest dopamine (by size) since the last view
        self.replay_every = replay_every  # a sweep-by-sweep replay every this many views; 0: none
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
        drawn = []
        for members, kind, count in ((from_pixel, 0, per_kind), (inner, 1, 2 * per_kind)):
            if len(members) > count:
                pool = rng.choice(members, min(len(members), 10 * count), replace=False)
                members = pool[np.argsort(-np.abs(weights[pool]))[:count]]
            drawn.extend(int(i) for i in members)
            for i in members:
                source = pixel[graph.pre[i]] if kind == 0 else node[graph.pre[i]]
                edges.append([kind, int(source), int(node[graph.post[i]]), round(float(weights[i]), 3)])
        self._drawn = np.asarray(drawn, dtype=np.int64)  # the page's synapses, re-read at each view
        return edges

    def _replay(self, x: np.ndarray) -> dict:
        """The settle of this screen replayed from rest, sweep by sweep, for the view: the same
        drive, budget and tolerance the brain's own free settle uses. The page plays it as the
        wave of activity; the brain's own settle started from its previous state."""
        brain = self.brain
        cfg = brain.learner.config
        out = brain.brain.settle_batch(brain.stimulus(x), steps=int(cfg.free_steps),
                                       tolerance=cfg.tolerance, trajectory=True)
        frames = np.asarray(out.trajectory)[:, 0, :]
        keep = np.concatenate([self.assoc, self.trace, self.motor])
        moved = np.abs(np.diff(frames, axis=0)).max(axis=1) if len(frames) > 1 else np.zeros(0)
        step = max(1, len(frames) // 40)  # at most about 40 frames go to the page
        picked = list(range(0, len(frames), step))
        if picked[-1] != len(frames) - 1:
            picked.append(len(frames) - 1)
        return {"frames": [_round(frames[k][keep], 2) for k in picked], "sweep_of_frame": picked,
                "movement": _round(moved, 5), "tolerance": cfg.tolerance, "sweeps": int(len(frames))}

    def _show(self, state, sweeps: int, x: np.ndarray, wrong_action: int | None = None, *,
              own: int | None = None, teacher: int | None = None) -> None:
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
        weights = np.asarray(self.brain.brain.weights)
        moved = None if self._weights is None else np.abs(weights - self._weights)
        changed = 0 if moved is None else int(np.count_nonzero(moved > CHANGE))
        self._weights = weights.copy()
        moment = getattr(self.brain, "last_arousal", None) or {}
        self.shows += 1
        self.viz = {"state": _round(vec), "errors": _round(errors), "delta": _round(delta), "q": True,
                    "phase": self.phase, "sweeps": int(sweeps), "own": own, "teacher": teacher,
                    "action": self.current_action if self.phase == "playing" else teacher,
                    "reward": self._seen_reward, "dopamine": round(self._seen_dopamine, 4),
                    "value": round(self.value, 4),
                    "changed": changed, "change_threshold": CHANGE, "lessons": self.lessons, "decisions": self.decisions,
                    "drawn_weights": _round(weights[self._drawn], 3) if self._drawn is not None else None,
                    "mode": moment.get("mode") if self.rec["life"] == "live" else None,
                    "arousal": round(float(moment.get("level", 0.0)), 3) if self.rec["life"] == "live" else None}
        self._seen_reward, self._seen_dopamine = 0.0, 0.0  # the outcomes since the last view
        if self.replay_every and self.shows % self.replay_every == 0:
            self.viz["replay"] = self._replay(x)
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
        self.agreement = (self.agreement + [int(own == teacher)])[-self.rec["agree_window"]:]
        state = brain.basal_ganglia.state
        if own is not None and self.lessons % 3 == 0:
            self.value = float(brain.basal_ganglia.value(state)[0])
            self._show(state, state.steps, x, wrong_action=None if own == teacher else teacher,
                       own=own, teacher=teacher)
        brain.learner.step(drive, np.array([teacher]))
        self.lessons += 1
        if self.lessons % 10 == 0:
            self.agree_hist = (self.agree_hist + [round(float(np.mean(self.agreement)), 3)])[-60:]
        agree = float(np.mean(self.agreement))
        r = self.rec
        gate = AGREE_TO_PLAY.get(self.game, r["agree"])
        ready = ((self.lessons >= r["min_lessons"] and len(self.agreement) >= r["agree_window"] and agree >= gate)
                 or self.lessons >= r["max_lessons"])
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
            elif self.rec["life"] == "live":
                # calm while outcomes match (a greedy settle, nothing learned), aroused by surprise
                if self.pending:
                    signal = float(np.sign(reward))
                    action = int(brain.live(x, reward=np.array([signal]), done=np.array([bool(done)]))[0])
                    self.outcomes += 1
                    self.rewarded += int(signal != 0)
                    self._seen_reward += signal
                else:
                    action = int(brain.live(x)[0])
                moment = brain.last_arousal or {}
                self.calm += int(moment.get("mode") in ("calm", "routine"))
                self.dopamine = float((brain.last_learning or {}).get("dopamine", 0.0))
            elif self.pending:
                signal = float(np.sign(reward))
                action = int(brain.step(x, reward=np.array([signal]), done=np.array([bool(done)]))[0])
                self.outcomes += 1
                self.rewarded += int(signal != 0)
                self._seen_reward += signal
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
        self.agreement = (self.agreement + [int(action == teacher)])[-self.rec["agree_window"]:]
        state = brain.basal_ganglia.state
        self.value = float(brain.basal_ganglia.value(state)[0])
        sweeps = state.steps + int(brain.last_learning.get("free_steps", 0))
        if abs(self.dopamine) > abs(self._seen_dopamine):
            self._seen_dopamine = self.dopamine
        # every third decision, and every decision whose outcome paid or cost
        if self.decisions % 3 == 0 or self._seen_reward != 0:
            self._show(state, sweeps, x, own=action, teacher=teacher)
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
        gate = AGREE_TO_PLAY.get(self.game, self.rec["agree"])
        recent = self.think_ms[-200:]
        return {
            "phase": self.phase,
            "watch": {"lessons": self.lessons,
                      "to_takeover": round(min(1.0, self.lessons / self.rec["min_lessons"]) * min(1.0, (agree or 0) / gate), 2),
                      "sweeps": self.last_sweeps, "agreement": agree, "sweeps_hist": self.sweeps_hist,
                      "agree_hist": self.agree_hist, "takeover": self.takeover},
            "brain": {"beat_age": 0.0, "faults": self.faults, "last_error": self.last_error},
            "life": {"decisions": self.decisions, "outcomes": self.outcomes, "refused": self.refused,
                     "rewarded": self.rewarded, "calm": self.calm,
                     "think_ms": round(float(np.median(recent)), 1) if recent else None,
                     "think_ms_scope": "median of the latest 200 brain handlers, watching and play, including refusals",
                     "value": round(self.value, 3), "dopamine": round(self.dopamine, 3)},
        }
