"""Cadence Arcade: System 1 brains of Cadence 0.95.2 learning Atari while you watch.

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

from arcade_brain import RECALL, BrainSide, build_brain  # noqa: F401
from arcade_brain import recipe as arcade_brain_recipe

GAMES = os.environ.get(
    "ARCADE_GAMES", "Atlantis,Freeway,Carnival,SpaceInvaders").split(",")
PUBLIC = os.environ.get("ARCADE_PUBLIC") == "1"
HOST = os.environ.get("ARCADE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARCADE_PORT", "8668"))
N_SCREEN = 84 * 84
RETINA_FRAMES = 300        # screens of random play averaged into the background
RETINA_GAIN = 2.0
STEPS_PER_SECOND = 60      # the game's pace: four times the console's
TEACHER_EPISODES = 3       # the teacher's own benchmark, played before birth
AGREE_TO_PLAY: dict = {}  # per-game agreement gates; the default is the recipe's
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
    """One game: the body's thread steps the emulator and never waits; the brain's thread is the
    sole owner of the brain (``arcade_brain.BrainSide``: watching, the takeover, living)."""

    # the brain side's numbers, read through the runner by the page and the headless report
    _SIDE = ("phase", "lessons", "agreement", "agree_hist", "sweeps_hist", "last_sweeps",
             "decisions", "outcomes", "rewarded", "refused", "calm", "faults", "last_error",
             "value", "dopamine", "takeover", "n_actions", "rec")

    def __init__(self, game: str, seed: int = 0, life_learn: bool = True, rec: dict | None = None):
        self.seed = seed
        self.life_learn = life_learn
        self.game = game
        self.env = make_env(game)
        self.meanings = [str(x) for x in
                         self.env.unwrapped.get_action_meanings()]
        self.background = background(game, seed)
        self.side = BrainSide(game, self.meanings, seed=seed, life_learn=life_learn, rec=rec)
        self.brain = self.side.brain
        self.populations = self.side.populations()
        self.think_seconds: list[float] = []
        self.score = 0.0
        self.best_score = None
        self.episode = 0
        self.tick = 0
        self.returns: list[float] = []
        self.teacher_returns: list[float] = teacher_benchmark(game, seed)
        self.badge = "hatchling"
        self.frame = np.zeros((210, 160, 3), np.uint8)
        self.viz_traj: list[dict] = []
        self.viz_t = 0.0
        self.beat = time.time()
        self.exec_action = 0
        self.retina_small: list[int] = []
        self.current_action = 0    # what the body holds while the brain thinks
        self.latest = None         # (screen drive, teacher's action, tick)
        self.reward_acc = 0.0      # reward since the brain's last decision
        self.episode_done = False  # an episode ended since that decision
        self._seen_tick = -1
        self._phase = "watching"   # the body's copy, switched by the brain's thread
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def __getattr__(self, name):
        if name in Runner._SIDE and "side" in self.__dict__:
            return getattr(self.__dict__["side"], name)
        raise AttributeError(name)

    def sample_graph(self, per_kind=260):
        return self.side.graph_sample(per_kind)

    # ---- perception ------------------------------------------------
    def _drive(self, small):
        return ((small - self.background) * RETINA_GAIN).reshape(1, -1)

    def _brain_loop(self):
        """The sole owner of the brain: always the latest screen, each at most once."""
        while not self._stop.is_set():
            self.beat = time.time()
            with self.lock:
                snap = self.latest
                fresh = snap is not None and snap[2] != self._seen_tick
                if fresh:
                    x, teacher_a, self._seen_tick = snap
                    reward, done = self.reward_acc, self.episode_done
                    if self._phase == "playing":
                        self.reward_acc, self.episode_done = 0.0, False
            if not fresh:
                time.sleep(0.002)
                continue
            started = time.perf_counter()
            out = self.side.iterate(x, teacher_a, reward, done, len(self.teacher_returns))
            if "fault" in out:
                print(f"{self.game}: BRAIN FAULT {out['fault']}", flush=True)
                time.sleep(0.5)
            if out.get("takeover"):
                print(f"{self.game}: TAKEOVER at {self.side.lessons} lessons, "
                      f"agreement {self.side.takeover['agreement']:.2f}", flush=True)
            with self.lock:
                if out.get("takeover"):
                    self.reward_acc, self.episode_done = 0.0, False
                    self._phase = "playing"
                if "action" in out:
                    self.current_action = out["action"]
                if self.side.viz is not None and self.side.viz_t != self.viz_t:
                    self.viz_traj, self.viz_t = [self.side.viz], self.side.viz_t
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
            watched = self._phase == "watching"
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
                    action = (teacher_a if self._phase == "watching"
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
            if self._phase == "watching":
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
        gate = AGREE_TO_PLAY.get(r.game, r.rec["agree"])
        out[name] = {
            "game": r.game, "phase": r.phase, "badge": r.badge,
            "score": r.score, "best": r.best_score,
            "episode": r.episode,
            "teacher": (round(float(np.mean(r.teacher_returns)), 1)
                        if r.teacher_returns else None),
            "agent": AGENT_HINTS.get(r.game, "the brain is the player"),
            "watch": {"lessons": r.lessons,
                      "to_takeover": round(
                          min(1.0, r.lessons / r.rec["min_lessons"])
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
