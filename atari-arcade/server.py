"""Cadence Arcade: System 1 brains of Cadence 0.80.0 learning Atari while you watch.

Every runner composes a fresh brain with ``Brain.compose``: 7,056 sensory
neurons (the 84x84 screen), an association cortex with a working trace, a
motor cortex with one neuron per action, basal ganglia and an associative
memory. Phase one, the scripted teacher plays and the brain watches: each
watched screen is one lesson, the teacher's action as its label. Before the
lesson the brain's own free answer is compared with the teacher's. Once
the free answers agree often enough the brain takes the controls, and from
then on ``brain.step`` learns from the measured reward of its own actions
and chooses the next one. The game never waits for the brain: it runs at
its own pace and holds the brain's last action while the brain thinks. The
page streams the game, the settled brain, the learning numbers and a skill
badge. /pace trades speed for watchability.

    python server.py   ->  http://localhost:8668
"""

from __future__ import annotations

import io
import os
import threading
import time

import numpy as np
from aiohttp import web

GAMES = os.environ.get(
    "ARCADE_GAMES", "Atlantis,Freeway,Carnival,SpaceInvaders").split(",")
PUBLIC = os.environ.get("ARCADE_PUBLIC") == "1"
HOST = os.environ.get("ARCADE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARCADE_PORT", "8668"))
N_SCREEN = 84 * 84
RETINA_FRAMES = 300        # screens of random play averaged into the background
RETINA_GAIN = 2.0
STEPS_PER_SECOND = 60      # the game's pace: four times the console's
MIN_LESSONS = 500
MAX_LESSONS = 2000
TEACHER_EPISODES = 3       # the teacher's own benchmark, played before birth
AGREE_WINDOW = 120
AGREE_TO_PLAY = {}
AGREE_DEFAULT = 0.9
PACE = {"sleep": 0.0}

AGENT_HINTS = {
    "Atlantis": "the brain fires the three gun bases",
    "Freeway": "the brain is the chicken crossing the road",
    "Carnival": "the brain runs the shooter at the bottom",
    "SpaceInvaders": "the brain aims the cannon at the bottom",
}


def teacher_action(game, ram, meanings, tick):
    m = meanings
    if game == "Freeway":
        return m.index("UP")
    if game == "Atlantis":
        return m.index("FIRE")
    if game == "Carnival":
        if tick % 4:
            return m.index("FIRE")
        x = int(ram[2])
        return m.index("RIGHT") if x < 80 else m.index("LEFT")
    if game == "SpaceInvaders":
        x = int(ram[28])
        return (m.index("RIGHTFIRE") if x < 75
                else m.index("LEFTFIRE"))
    raise SystemExit(f"no teacher for {game}")


def build_brain(n_actions, seed=0):
    """System 1 on raw pixels with demo learning rates, adaptivity and reward timescales."""
    from cadence import Brain

    return Brain.compose(
        N_SCREEN, n_actions, seed=seed,
        learning_beta=0.1, temperature=0.2, learning_tolerance=3e-3,
        learning_free_steps=1024, learning_nudged_steps=12, learning_eta_bias=0.02,
        # each synapse steps on its own running mean over its own running
        # scale: most pixels are quiet most of the time
        learning_eta=0.003, learning_momentum=0.9, learning_normalize=0.99,
        learning_normalize_floor=1e-4,
        actor_gamma=0.97, actor_lam=0.9, actor_eta=0.001, actor_eta_bias=0.0001,
        actor_eta_critic=0.3, actor_momentum=0.9, actor_normalize=0.99,
        actor_eligibility_steps=None,
    )


def make_env(game):
    import ale_py
    import gymnasium as gym

    gym.register_envs(ale_py)
    return gym.make(f"ALE/{game}-v5", frameskip=4,
                    repeat_action_probability=0.0,
                    full_action_space=False, obs_type="rgb")


_ROWS = np.linspace(0, 210, 85)[:-1].astype(int)
_COLS = np.linspace(0, 160, 85)[:-1].astype(int)


def grey84(rgb):
    """Screen luminance pooled to 84x84, in [0, 1]."""
    grey = (rgb @ np.array([0.299, 0.587, 0.114])).astype(np.float32)
    rows = np.add.reduceat(grey, _ROWS, axis=0)
    cols = np.add.reduceat(rows, _COLS, axis=1)
    return np.clip(cols / (2.5 * 1.9047), 0, 255) / 255.0


def background(game, seed):
    """Mean luminance per pixel over random play, taken before the brain is
    born and never updated: the retina reports what differs from it."""
    env = make_env(game)
    obs, _ = env.reset(seed=10_000 + seed)
    rng = np.random.default_rng(10_000 + seed)
    total = np.zeros((84, 84))
    for _ in range(RETINA_FRAMES):
        total += grey84(obs)
        obs, _, term, trunc, _ = env.step(int(rng.integers(env.action_space.n)))
        if term or trunc:
            obs, _ = env.reset()
    env.close()
    return total / RETINA_FRAMES


def teacher_benchmark(game, seed):
    """Scores of the scripted teacher alone, on a scratch emulator."""
    env = make_env(game)
    meanings = [str(x) for x in env.unwrapped.get_action_meanings()]
    scores, tick = [], 0
    obs, _ = env.reset(seed=20_000 + seed)
    for _ in range(TEACHER_EPISODES):
        score, done = 0.0, False
        while not done:
            ram = env.unwrapped.ale.getRAM()
            _, r, term, trunc, _ = env.step(
                teacher_action(game, ram, meanings, tick))
            tick += 1
            score += float(r)
            done = term or trunc
        scores.append(score)
        env.reset()
    env.close()
    return scores


class Runner:
    def __init__(self, game: str, seed: int = 0, life_learn: bool = True):
        self.seed = seed
        self.life_learn = life_learn
        self.game = game
        self.env = make_env(game)
        self.meanings = [str(x) for x in
                         self.env.unwrapped.get_action_meanings()]
        self.n_actions = len(self.meanings)
        self.background = background(game, seed)
        self.brain = build_brain(self.n_actions, seed=seed)
        graph = self.brain.connectome
        self.assoc = np.asarray(graph.populations["association"])
        self.trace = np.asarray(graph.populations["prefrontal"])
        self.motor = np.asarray(self.brain.motor_index)
        # the page's nodes: association, working trace, motor, memory, value
        a, n = self.n_actions, len(self.assoc)
        self.populations = [
            {"name": "association", "count": n, "start": 0},
            {"name": "trace", "count": len(self.trace), "start": n},
            {"name": "motor", "count": a, "start": 2 * n},
            {"name": "memory", "count": a, "start": 2 * n + a},
            {"name": "value", "count": 1, "start": 2 * n + 2 * a}]
        self.phase = "watching"
        self.tick = 0
        self.lessons = 0
        self.agreement: list[int] = []
        self.agree_hist: list[float] = []
        self.sweeps_hist: list[int] = []
        self.last_sweeps = None
        self.decisions = 0
        self.outcomes = 0          # outcomes of its own actions learned from
        self.rewarded = 0          # those with a reward in them
        self.refused = 0
        # Whole watching/play handlers, including caught faults and backoff;
        # excludes body preprocessing, emulator steps and waiting for input.
        self.think_seconds: list[float] = []
        self.value = 0.0
        self.dopamine = 0.0
        self.score = 0.0
        self.best_score = None
        self.episode = 0
        self.returns: list[float] = []
        self.teacher_returns: list[float] = teacher_benchmark(game, seed)
        self.takeover = None
        self.badge = "hatchling"
        self.frame = np.zeros((210, 160, 3), np.uint8)
        self.viz_traj: list[dict] = []
        self.viz_t = 0.0
        self.beat = time.time()
        self.faults = 0
        self.last_error = None
        self.exec_action = 0
        self.retina_small: list[int] = []
        self._prev_state = None
        self._pending = False      # an own executed action awaits its outcome
        self.current_action = 0    # what the body holds while the brain thinks
        self.latest = None         # (screen drive, teacher's action, tick)
        self.reward_acc = 0.0      # reward since the brain's last decision
        self.episode_done = False  # an episode ended since that decision
        self._seen_tick = -1
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # ---- wiring sample for the viz --------------------------------
    def sample_graph(self, per_kind=260):
        """Synapses as [kind, source, target, weight]; kind 0 starts at a
        retina pixel, kind 1 at another node. The weights are the current
        ones."""
        graph = self.brain.connectome
        weights = np.asarray(self.brain.brain.weights)
        node = np.full(graph.n, -1)
        node[self.assoc] = np.arange(len(self.assoc))
        node[self.trace] = len(self.assoc) + np.arange(len(self.trace))
        node[self.motor] = 2 * len(self.assoc) + np.arange(self.n_actions)
        pixel = np.full(graph.n, -1)
        pixel[np.asarray(self.brain.sensory_index)] = np.arange(N_SCREEN)
        rng = np.random.default_rng(7)
        edges = []
        from_pixel = np.flatnonzero(pixel[graph.pre] >= 0)
        inner = np.flatnonzero((node[graph.pre] >= 0) & (node[graph.post] >= 0))
        for members, kind, count in ((from_pixel, 0, per_kind),
                                     (inner, 1, 2 * per_kind)):
            if len(members) > count:
                # the strongest of a random tenth, so learned fibers show
                pool = rng.choice(members, min(len(members), 10 * count),
                                  replace=False)
                members = pool[np.argsort(-np.abs(weights[pool]))[:count]]
            for i in members:
                source = pixel[graph.pre[i]] if kind == 0 else node[graph.pre[i]]
                edges.append([kind, int(source), int(node[graph.post[i]]),
                              round(float(weights[i]), 3)])
        return edges

    # ---- perception ------------------------------------------------
    def _drive(self, small):
        return ((small - self.background) * RETINA_GAIN).reshape(1, -1)

    # ---- what the page sees of one settled state -------------------
    def _show(self, state, sweeps, x, wrong_action=None):
        act = np.asarray(state.activation)[0]
        memory = self.brain.hippocampus.recall(x)[0]
        vec = np.concatenate([act[self.assoc], act[self.trace],
                              act[self.motor], memory, [self.value]])
        prev = self._prev_state
        delta = (np.abs(vec - prev) if prev is not None
                 and len(prev) == len(vec) else np.zeros(len(vec)))
        self._prev_state = vec
        errors = np.zeros(len(vec))
        errors[-1] = min(1.0, abs(self.dopamine))
        if wrong_action is not None:
            errors[2 * len(self.assoc) + wrong_action] = 1.0
        self.last_sweeps = int(sweeps)
        self.sweeps_hist.append(int(sweeps))
        self.sweeps_hist = self.sweeps_hist[-48:]
        with self.lock:
            self.viz_traj = [{
                "state": [round(float(v), 3) for v in vec],
                "errors": [round(float(v), 3) for v in errors],
                "delta": [round(float(v), 3) for v in delta],
                "q": True}]
            self.viz_t = time.time()

    # ---- the brain's side: a lesson while watching, a decision afterwards -
    def _watch(self, x, teacher_a):
        """One watched screen. First the brain's own answer, read greedily
        from its settled state: the teacher is at the controls, so that
        answer is not executed and carries no eligibility. Then the lesson:
        the teacher's action as the label of this screen."""
        brain = self.brain
        drive = brain.stimulus(x)        # the screen, the working trace, memory
        try:
            own = int(brain.act(x, greedy=True)[0])
        except RuntimeError as exc:      # no answer settled; the lesson still counts
            own = None
            self.refused += 1
            self.last_error = f"refused: {exc}"
        self.agreement.append(int(own == teacher_a))
        self.agreement = self.agreement[-AGREE_WINDOW:]
        state = brain.basal_ganglia.state
        if own is not None and self.lessons % 3 == 0:
            self.value = float(brain.basal_ganglia.value(state)[0])
            self._show(state, state.steps, x,
                       wrong_action=None if own == teacher_a else teacher_a)
        brain.learner.step(drive, np.array([teacher_a]))
        self.lessons += 1
        if self.lessons % 10 == 0:
            self.agree_hist.append(round(float(np.mean(self.agreement)), 3))
            self.agree_hist = self.agree_hist[-60:]
        agree = float(np.mean(self.agreement))
        gate = AGREE_TO_PLAY.get(self.game, AGREE_DEFAULT)
        if ((self.lessons >= MIN_LESSONS
             and len(self.agreement) >= AGREE_WINDOW and agree >= gate)
                or self.lessons >= MAX_LESSONS):
            print(f"{self.game}: TAKEOVER at {self.lessons} lessons, "
                  f"agreement {agree:.2f}", flush=True)
            self.takeover = {"lessons": self.lessons,
                             "agreement": round(agree, 3),
                             "seconds": round(time.time() - self.born, 1)}
            with self.lock:
                self.current_action = teacher_a
                self.reward_acc, self.episode_done = 0.0, False
                self._pending = False
                self.phase = "playing"

    def _play(self, x, teacher_a, reward, done):
        """One decision of the brain at the controls: the outcome of its last
        action (the reward since then, whether an episode ended), then the
        next action."""
        brain = self.brain
        try:
            if not self.life_learn:        # the frozen twin: no outcome reaches it
                if done:
                    brain.reset()
                action = int(brain.act(x)[0])
            elif self._pending:
                signal = float(np.sign(reward))
                action = int(brain.step(x, reward=np.array([signal]),
                                        done=np.array([bool(done)]))[0])
                self.outcomes += 1
                self.rewarded += int(signal != 0)
                self.dopamine = float(
                    brain.last_learning.get("dopamine", 0.0))
            else:
                action = int(brain.step(x)[0])
        except RuntimeError as exc:
            # the brain did not settle: no action was issued. The body keeps
            # holding its last action and that stretch is never credited.
            self.refused += 1
            self.last_error = f"refused: {exc}"
            self._pending = False
            if done:
                brain.reset()
            return
        self.current_action = action
        self._pending = True
        self.decisions += 1
        self.agreement.append(int(action == teacher_a))
        self.agreement = self.agreement[-AGREE_WINDOW:]
        state = brain.basal_ganglia.state
        self.value = float(brain.basal_ganglia.value(state)[0])
        # sweeps of this screen: settling it after the last outcome was
        # learned, plus any further sweeps the action needed to qualify
        sweeps = state.steps + int(brain.last_learning.get("free_steps", 0))
        if self.decisions % 3 == 0:
            self._show(state, sweeps, x)
        if self.decisions % 10 == 0:
            self.agree_hist.append(round(float(np.mean(self.agreement)), 3))
            self.agree_hist = self.agree_hist[-60:]

    def _brain_loop(self):
        """The sole owner of the brain: always the latest screen, each at
        most once."""
        while not self._stop.is_set():
            self.beat = time.time()
            with self.lock:
                snap = self.latest
                fresh = snap is not None and snap[2] != self._seen_tick
                if fresh:
                    x, teacher_a, self._seen_tick = snap
                    reward, done = self.reward_acc, self.episode_done
                    if self.phase == "playing":
                        self.reward_acc, self.episode_done = 0.0, False
            if not fresh:
                time.sleep(0.002)
                continue
            started = time.perf_counter()
            try:
                if self.phase == "watching":
                    self._watch(x, teacher_a)
                else:
                    self._play(x, teacher_a, reward, done)
            except Exception as exc:
                self.faults += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                print(f"{self.game}: BRAIN FAULT {self.last_error}",
                      flush=True)
                self._pending = False
                time.sleep(0.5)
            self.think_seconds.append(time.perf_counter() - started)
            self.think_seconds = self.think_seconds[-20000:]

    def _update_badge(self):
        if not self.returns or not self.teacher_returns:
            return
        t = max(1e-9, float(np.mean(self.teacher_returns)))
        recent = float(np.mean(self.returns[-5:]))
        frac = recent / t
        self.badge = ("legend" if frac > 1.0 else
                      "expert" if frac >= 0.8 else
                      "intermediate" if frac >= 0.3 else "noob")

    # ---- the body's side: streams the game and never waits for the brain
    def _run(self):
        self.born = time.time()
        threading.Thread(target=self._brain_loop, daemon=True).start()
        first = True
        while not self._stop.is_set():
            if first:
                obs, _ = self.env.reset(seed=self.seed)
                first = False
            else:
                obs, _ = self.env.reset()
            self.episode += 1
            self.score = 0.0
            watched = self.phase == "watching"
            done = False
            while not done and not self._stop.is_set():
                started = time.perf_counter()
                small = grey84(obs)
                ram = self.env.unwrapped.ale.getRAM()
                teacher_a = teacher_action(self.game, ram,
                                           self.meanings, self.tick)
                self.tick += 1
                with self.lock:
                    self.latest = (self._drive(small), teacher_a, self.tick)
                    action = (teacher_a if self.phase == "watching"
                              else self.current_action)
                self.exec_action = int(action)
                obs, r, term, trunc, _ = self.env.step(action)
                done = term or trunc
                self.score += float(r)
                with self.lock:
                    self.reward_acc += float(r)
                    if done:
                        self.episode_done = True
                    self.frame = obs
                    if self.tick % 3 == 0:
                        half = small.reshape(42, 2, 42, 2).mean(axis=(1, 3))
                        self.retina_small = [
                            int(v) for v in (half * 255).reshape(-1)]
                rest = 1.0 / STEPS_PER_SECOND - (time.perf_counter() - started)
                time.sleep(max(0.001, rest) + PACE["sleep"])
            if not done:
                break
            if self.phase == "watching":
                self.teacher_returns.append(self.score)
                self.teacher_returns = self.teacher_returns[-20:]
            elif not watched:          # a whole episode at the brain's controls
                self.returns.append(self.score)
                self.returns = self.returns[-60:]
                if self.best_score is None or self.score > self.best_score:
                    self.best_score = self.score
                self._update_badge()

    def meta_action(self):
        i = self.exec_action
        return self.meanings[i] if 0 <= i < len(self.meanings) else "NOOP"

    def stop(self):
        self._stop.set()


RUNNERS: dict[str, Runner] = {}
routes = web.RouteTableDef()


@routes.get("/")
async def index(_):
    return web.FileResponse("static/index.html")


@routes.get("/pace")
async def pace(request):
    value = request.query.get("sleep")
    if PUBLIC:
        return web.json_response({**PACE, "locked": True})
    if value is not None:
        try:
            PACE["sleep"] = min(0.5, max(0.0, float(value)))
        except ValueError:
            pass
    return web.json_response(PACE)


@routes.get("/state")
async def state(_):
    out = {}
    for name, r in RUNNERS.items():
        agree = (round(float(np.mean(r.agreement)), 2)
                 if r.agreement else None)
        gate = AGREE_TO_PLAY.get(r.game, AGREE_DEFAULT)
        out[name] = {
            "game": r.game, "phase": r.phase, "badge": r.badge,
            "score": r.score, "best": r.best_score,
            "episode": r.episode,
            "teacher": (round(float(np.mean(r.teacher_returns)), 1)
                        if r.teacher_returns else None),
            "agent": AGENT_HINTS.get(r.game, "the brain is the player"),
            "watch": {"lessons": r.lessons,
                      "to_takeover": round(
                          min(1.0, r.lessons / MIN_LESSONS)
                          * min(1.0, (agree or 0) / gate), 2),
                      "sweeps": r.last_sweeps, "agreement": agree,
                      "sweeps_hist": r.sweeps_hist,
                      "agree_hist": r.agree_hist,
                      "takeover": r.takeover},
            "brain": {"alive": r.thread.is_alive()
                              and (time.time() - r.beat) < 25,
                      "beat_age": round(time.time() - r.beat, 1),
                      "faults": r.faults,
                      "last_error": r.last_error},
            "life": {"decisions": r.decisions, "outcomes": r.outcomes,
                     "refused": r.refused,
                     "think_ms_scope": (
                         "median of latest 200 brain handlers; watching and play, "
                         "including refusals/fault backoff"),
                     "think_ms": (round(1000 * float(np.median(
                         r.think_seconds[-200:])), 1)
                                  if r.think_seconds else None),
                     "value": round(r.value, 3),
                     "dopamine": round(r.dopamine, 3),
                     "returns": r.returns}}
    return web.json_response(out)


@routes.get("/brain/{name}")
async def brain_view(request):
    r = RUNNERS.get(request.match_info["name"])
    if r is None:
        raise web.HTTPNotFound()
    with r.lock:
        return web.json_response({
            "traj": r.viz_traj, "t": r.viz_t,
            "retina": r.retina_small,
            "action": r.meta_action(),
            "rewarded": r.rewarded})


@routes.get("/graph/{name}")
async def graph_view(request):
    r = RUNNERS.get(request.match_info["name"])
    if r is None:
        raise web.HTTPNotFound()
    return web.json_response({
        "populations": r.populations, "n_screen": N_SCREEN,
        "n_action": r.n_actions, "meanings": r.meanings,
        "edges": r.sample_graph()})


def render_jpeg(runner) -> bytes:
    from PIL import Image, ImageDraw

    with runner.lock:
        frame = runner.frame.copy()
    img = Image.fromarray(frame).resize((320, 420),
                                        Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 402, 320, 420], fill=(13, 10, 8))
    best = ("·" if runner.best_score is None
            else f"{runner.best_score:+.0f}")
    draw.text((6, 405),
              f"{runner.phase}  ep {runner.episode}  "
              f"score {runner.score:+.0f}  best {best}",
              fill=(216, 203, 184))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@routes.get("/frame/{name}")
async def frame(request):
    runner = RUNNERS.get(request.match_info["name"])
    if runner is None:
        raise web.HTTPNotFound()
    import asyncio
    body = await asyncio.get_event_loop().run_in_executor(
        None, render_jpeg, runner)
    return web.Response(body=body, content_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


def main():
    for game in GAMES:
        name = game.lower()
        try:
            RUNNERS[name] = Runner(game)
            print(f"runner up: {name}", flush=True)
        except Exception as exc:
            print(f"runner failed: {name}: {exc}", flush=True)
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
