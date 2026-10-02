"""Cadence Arcade v3: deep tiled DRSNs born in the browser, learning live.

Every runner builds a fresh brain: nine 28x28 receptive-field columns
over the whole 84x84 screen, dense self-reflection observers above,
motor and value heads. Phase one, the brain watches its scripted
teacher play and admits witness batches in real time; once its decoded
actions agree with the teacher often enough it takes the controls, and
every reward feeds the same brain through the library's Reinforcement
learner. The page streams the game, the live wiring, the learning
stats and a skill badge. /pace trades speed for watchability.

    python server.py   ->  http://localhost:8668
"""

from __future__ import annotations

import io
import json
import threading
import time

import numpy as np
from aiohttp import web

import torch

torch.set_num_threads(3)

import os

GAMES = os.environ.get(
    "ARCADE_GAMES", "Atlantis,Freeway,Carnival,SpaceInvaders").split(",")
PUBLIC = os.environ.get("ARCADE_PUBLIC") == "1"
HOST = os.environ.get("ARCADE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARCADE_PORT", "8668"))
TILE, GRID = 28, 3
N_SCREEN = 84 * 84
BATCH = 24
WATCH_MIN_WITNESSES = 240
WATCH_MAX_WITNESSES = 720
AGREE_TO_PLAY = {}
AGREE_DEFAULT = 0.6
RF_EVERY = 1
REPLAY_EVERY = 6
BUDGET = 256
PACE = {"sleep": 0.0}
COLD_LOCK = threading.Semaphore(1)

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
    from cadence import Cortex
    c = Cortex(seed=seed, device="cpu", settle_budget=4096,
               parameter_prior=0.4)
    tiles = [c.input(f"tile{i}", shape=(TILE, TILE))
             for i in range(GRID * GRID)]
    act = c.input("action", shape=(n_actions,))
    cols = [c.column(f"t{i}", patches=8, inputs=tiles[i])
            for i in range(GRID * GRID)]
    r = c.observer("r", patches=12, observes=tuple(cols))
    p = c.observer("p", patches=16, observes=tuple(cols) + (r,))
    v = c.observer("v", patches=8, inputs=(act,), observes=(r, p))
    c.output("motor", shape=(n_actions,), reads=p)
    c.output("value", shape=(1,), reads=v)
    return c.build()


class Runner:
    def __init__(self, game: str, seed: int = 0, life_learn: bool = True):
        self.seed = seed
        self.life_learn = life_learn
        import gymnasium as gym
        import ale_py

        gym.register_envs(ale_py)
        self.game = game
        self.env = gym.make(f"ALE/{game}-v5", frameskip=4,
                            repeat_action_probability=0.0,
                            full_action_space=False, obs_type="rgb")
        self.meanings = [str(x) for x in
                         self.env.unwrapped.get_action_meanings()]
        self.n_actions = len(self.meanings)
        self.zero_act = [0.0] * self.n_actions
        self.brain = build_brain(self.n_actions, seed=seed)
        info = self.brain.inspect()
        self.populations = [
            {"name": p["name"], "count": p["patches"],
             "start": p["indices"][0]}
            for p in info["populations"]]
        self.graph_sample = self._sample_graph()
        self.rf = None
        self.phase = "watching"
        self.tick = 0
        self.witnesses = 0
        self.batches = 0
        self.admissions = 0
        self.last_sweeps = None
        self.sweeps_hist: list[int] = []
        self.agree_hist: list[float] = []
        self.coherence = 0.0
        self.first_sweeps = None
        self.agreement: list[int] = []
        self.transitions = 0
        self.life_admissions = 0
        self.score = 0.0
        self.best_score = None
        self.episode = 0
        self.returns: list[float] = []
        self.teacher_returns: list[float] = []
        self.badge = "hatchling"
        self.frame = np.zeros((210, 160, 3), np.uint8)
        self.viz_traj: list[dict] = []
        self.viz_t = 0.0
        self.beat = time.time()
        self.faults = 0
        self.last_error = None
        self.exec_action = 0
        self.retina_small: list[int] = []
        self.score_sums = np.zeros(self.n_actions)
        self.score_n = 0
        self.norm_mean = None
        self.norm_std = None
        self._norm_buf: list[np.ndarray] = []
        self._batch_buf: list[tuple] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # ---- wiring sample for the viz --------------------------------
    def _sample_graph(self, max_edges=520):
        import random as _random
        rng = _random.Random(7)
        graph = self.brain.graph
        weights = self.brain.weights
        by_kind: dict[str, list[int]] = {}
        for index, (kind, _s, _t) in enumerate(graph.edges):
            by_kind.setdefault(kind, []).append(index)
        picked = []
        for kind, members in by_kind.items():
            if kind == "input":
                picked.extend(rng.sample(members,
                                         min(len(members), 260)))
            else:
                picked.extend(members if len(members) <= 300
                              else rng.sample(members, 300))
        kinds = {"input": 0, "state": 1, "residual": 2}
        return [[kinds.get(k, 2), s, t, round(float(weights[i]), 3)]
                for i in sorted(picked)[:max_edges]
                for k, s, t in [graph.edges[i]]]

    # ---- perception ------------------------------------------------
    def _grey84(self, rgb):
        grey = rgb @ np.array([0.299, 0.587, 0.114])
        g = grey.astype(np.float32)
        rows = np.add.reduceat(g, np.linspace(0, 210, 85)[:-1].astype(int),
                               axis=0)
        cols = np.add.reduceat(rows, np.linspace(0, 160, 85)[:-1].astype(int),
                               axis=1)
        return np.clip(cols / (2.5 * 1.9047), 0, 255) / 255.0

    def _tiles(self, small):
        if self.norm_mean is not None:
            flat = np.clip((small.reshape(-1) - self.norm_mean)
                           / self.norm_std, -3, 3) * 0.2
            small = flat.reshape(84, 84)
        else:
            small = (small - 0.35) * 0.5
        out = {}
        for i in range(GRID * GRID):
            r0, c0 = (i // GRID) * TILE, (i % GRID) * TILE
            out[f"tile{i}"] = small[r0:r0 + TILE,
                                    c0:c0 + TILE].reshape(-1).tolist()
        return out

    # ---- learning steps -------------------------------------------
    def _admit(self):
        size = min(len(self._batch_buf),
                   8 if self.batches == 0 else 16 if self.batches == 1
                   else BATCH)
        batch = self._batch_buf[-size:]
        self._batch_buf = []
        cold = self.batches < 3
        if cold:
            COLD_LOCK.acquire()
        try:
            res = self.brain.observe_batch(batch)
        except ValueError as exc:
            print(f"{self.game}: admission refused: {exc}", flush=True)
            return
        finally:
            if cold:
                COLD_LOCK.release()
        self.batches += 1
        self.last_sweeps = res["sweeps"]
        self.sweeps_hist.append(int(res["sweeps"]))
        self.sweeps_hist = self.sweeps_hist[-48:]
        if res["accepted"]:
            per_witness = int(res["sweeps"]) / max(1, len(batch))
            if self.first_sweeps is None:
                self.first_sweeps = max(0.01, per_witness)
            self.coherence = round(max(0.0, min(1.0,
                1.0 - per_witness / self.first_sweeps)), 3)
        if res["accepted"]:
            self.admissions += 1
            self.witnesses += len(batch)

    def _settle_viz(self, inputs):
        """One real settle; the viz streams the new equilibrium and how
        far every patch moved to reach it."""
        result = self.brain.settle(inputs, budget=64)
        state = [round(float(x), 3) for x in result.get("state", [])]
        prev = getattr(self, "_prev_state", None)
        delta = ([round(abs(a - b), 3) for a, b in zip(state, prev)]
                 if prev and len(prev) == len(state)
                 else [0.0] * len(state))
        self._prev_state = state
        with self.lock:
            self.viz_traj = [{
                "state": state,
                "errors": [round(float(e), 3)
                           for e in result.get("errors", [])],
                "delta": delta,
                "energy": round(float(result.get("energy", 0.0)), 5),
                "q": bool(result.get("qualified"))}]
            self.viz_t = time.time()
        return result

    def _probe(self, tiles, teacher_a):
        result = self._settle_viz({**tiles, "action": self.zero_act})
        motor = np.array(result["outputs"]["motor"])
        self.score_sums += motor
        self.score_n += 1
        decoded = int(np.argmax(motor - self.score_sums
                                / max(1, self.score_n)))
        self.agreement.append(int(decoded == teacher_a))
        self.agreement = self.agreement[-120:]
        if len(self.agreement) >= 10:
            self.agree_hist.append(
                round(float(np.mean(self.agreement)), 3))
            self.agree_hist = self.agree_hist[-60:]
        return decoded

    def _decode_playing(self, motor):
        return int(np.argmax(np.array(motor)
                             - self.score_sums / max(1, self.score_n)))

    def _update_badge(self):
        if not self.returns or not self.teacher_returns:
            return
        t = max(1e-9, float(np.mean(self.teacher_returns)))
        recent = float(np.mean(self.returns[-5:]))
        frac = recent / t
        self.badge = ("legend" if frac > 1.0 else
                      "expert" if frac >= 0.8 else
                      "intermediate" if frac >= 0.3 else "noob")

    # ---- env loop: streams frames, never blocks on the brain -------
    def _run(self):
        self.current_action = 0
        self.latest = None          # (tiles, teacher_action, episode)
        self.reward_acc = 0.0
        self.episode_done = False
        brain_thread = threading.Thread(target=self._brain_loop,
                                        daemon=True)
        brain_thread.start()
        while not self._stop.is_set():
            obs, _ = self.env.reset()
            self.episode += 1
            self.score = 0.0
            done = False
            while not done and not self._stop.is_set():
                small = self._grey84(obs)
                if self.norm_mean is None:
                    self._norm_buf.append(small.reshape(-1))
                    if len(self._norm_buf) >= 300:
                        arr = np.stack(self._norm_buf)
                        self.norm_mean = arr.mean(0)
                        self.norm_std = arr.std(0) + 1e-6
                        self._norm_buf = []
                ram = self.env.unwrapped.ale.getRAM()
                teacher_a = teacher_action(self.game, ram,
                                           self.meanings, self.tick)
                self.tick += 1
                with self.lock:
                    self.latest = (self._tiles(small), teacher_a,
                                   self.episode)
                    if self.tick % 3 == 0:
                        half = small.reshape(42, 2, 42, 2).mean(axis=(1, 3))
                        self.retina_small = [
                            int(x) for x in (half * 255).reshape(-1)]
                action = (teacher_a if self.phase == "watching"
                          else self.current_action)
                self.exec_action = int(action)
                obs, r, term, trunc, _ = self.env.step(action)
                self.score += float(r)
                self.reward_acc += float(r)
                done = term or trunc
                with self.lock:
                    self.frame = obs
                    if done:
                        self.episode_done = True
                time.sleep(max(0.01, PACE["sleep"]))
            if self.phase == "watching":
                self.teacher_returns.append(self.score)
                self.teacher_returns = self.teacher_returns[-20:]
            else:
                self.returns.append(self.score)
                self.returns = self.returns[-60:]
                if self.best_score is None or self.score > self.best_score:
                    self.best_score = self.score
                self._update_badge()

    # ---- brain loop: sole owner of brain and learner ----------------
    def _brain_loop(self):
        pending = False
        while not self._stop.is_set():
            try:
                pending = self._brain_iteration(pending)
            except Exception as exc:
                self.faults += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                print(f"{self.game}: BRAIN FAULT {self.last_error}",
                      flush=True)
                time.sleep(0.5)

    def _brain_iteration(self, pending):
        from cadence import Reinforcement
        self.beat = time.time()
        if True:
            with self.lock:
                snap = self.latest
                done = self.episode_done
                self.episode_done = False
            if snap is None:
                time.sleep(0.02)
                return pending
            tiles, teacher_a, _ep = snap
            if self.phase == "watching":
                target = [0.6 if j == teacher_a else -0.6
                          for j in range(self.n_actions)]
                self._batch_buf.append(
                    ({**tiles, "action": self.zero_act},
                     {"motor": target}))
                if len(self._batch_buf) >= BATCH:
                    self._admit()
                if len(self._batch_buf) % 5 == 0:
                    self._probe(tiles, teacher_a)
                agree = (np.mean(self.agreement)
                         if len(self.agreement) >= 30 else 0.0)
                gate = AGREE_TO_PLAY.get(self.game, AGREE_DEFAULT)
                if (self.witnesses >= WATCH_MIN_WITNESSES
                        and agree >= gate) \
                        or self.witnesses >= WATCH_MAX_WITNESSES:
                    print(f"{self.game}: TAKEOVER at {self.witnesses} "
                          f"witnesses, agreement {agree:.2f}", flush=True)
                    self.rf = Reinforcement(
                        self.brain, actions=self.n_actions,
                        action_input="action", value_output="value",
                        discount=0.95, exploration=0.05,
                        reward_scale=1.0, capacity=2048,
                        batch_size=16, seed=0)
                    self.phase = "playing"
            else:
                if pending:
                    reward = float(np.clip(
                        self.reward_acc / self._rscale(), -1, 1))
                    self.reward_acc = 0.0
                    try:
                        fb = self.rf.feedback(
                            reward, None if done else tiles,
                            terminal=done, learn=False)
                        self.transitions = fb.get(
                            "transitions", self.transitions)
                        if self.life_learn \
                                and self.transitions % REPLAY_EVERY == 0:
                            rp = self.rf.replay(budget=2048)
                            if rp.get("accepted"):
                                self.life_admissions += 1
                    except ValueError:
                        self.rf.reset()
                    pending = False
                    if done:
                        return pending
                try:
                    picked = self.rf.act(tiles, budget=BUDGET)
                except ValueError:
                    self.rf.reset()
                    return pending
                if picked["action"] is not None:
                    self.current_action = int(picked["action"])
                    pending = True
                    if self.transitions % 4 == 0:
                        self._settle_viz({**tiles, "action": self.zero_act})
                else:
                    result = self._settle_viz(
                        {**tiles, "action": self.zero_act})
                    self.current_action = self._decode_playing(
                        result["outputs"]["motor"])

    def meta_action(self):
        i = self.exec_action
        return self.meanings[i] if 0 <= i < len(self.meanings) else "NOOP"

    def stop(self):
        self._stop.set()

    def _rscale(self):
        return {"Atlantis": 500.0, "Freeway": 1.0, "Carnival": 120.0,
                "SpaceInvaders": 200.0}.get(self.game, 100.0)


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
        out[name] = {
            "game": r.game, "phase": r.phase, "badge": r.badge,
            "score": r.score, "best": r.best_score,
            "episode": r.episode,
            "teacher": (round(float(np.mean(r.teacher_returns)), 1)
                        if r.teacher_returns else None),
            "agent": AGENT_HINTS.get(r.game, "the brain is the player"),
            "watch": {"witnesses": r.witnesses, "batches": r.batches,
                      "to_takeover": round(min(
                          1.0,
                          min(1.0, r.witnesses / WATCH_MIN_WITNESSES)
                          * (min(1.0, (agree or 0)
                                 / AGREE_TO_PLAY.get(r.game, AGREE_DEFAULT))
                             if len(r.agreement) >= 30 else
                             len(r.agreement) / 60)), 2),
                      "admissions": r.admissions,
                      "sweeps": r.last_sweeps, "agreement": agree,
                      "sweeps_hist": r.sweeps_hist,
                      "agree_hist": r.agree_hist,
                      "coherence": r.coherence},
            "brain": {"alive": r.thread.is_alive()
                              and (time.time() - r.beat) < 25,
                      "beat_age": round(time.time() - r.beat, 1),
                      "faults": r.faults,
                      "last_error": r.last_error},
            "life": {"transitions": r.transitions,
                     "admissions": r.life_admissions,
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
            "admissions": r.admissions + r.life_admissions})


@routes.get("/graph/{name}")
async def graph_view(request):
    r = RUNNERS.get(request.match_info["name"])
    if r is None:
        raise web.HTTPNotFound()
    return web.json_response({
        "populations": r.populations, "n_screen": N_SCREEN,
        "grid": GRID, "tile": TILE,
        "n_action": r.n_actions, "meanings": r.meanings,
        "edges": r.graph_sample})


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
