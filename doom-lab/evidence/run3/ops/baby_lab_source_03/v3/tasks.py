"""Native Doom task contracts. Privileged engine facts never enter actor pixels.

Full-game success is a native single-player level termination while alive and
before the native timeout, on an unmodified IWAD map. Curriculum objectives are
named separately; neither a reward threshold nor an oracle action counts as a
student level completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import importlib
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from .interface import ACTION_BUTTONS, ACTION_NAMES, BUTTON_NAMES, REPEAT_TICS


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    asset: str
    map_name: str = "map01"
    objective: str = "native_exit"
    skill: int = 2
    timeout_tics: int = 21000
    no_monsters: bool = False
    min_kills: int = 0
    split: str = "train"
    scenario: str | None = None

    def __post_init__(self):
        if self.objective not in {"native_exit", "scenario_completion", "survival", "kill"}:
            raise ValueError("Unknown native objective")
        if self.skill not in range(1, 6) or self.timeout_tics <= 0 or self.min_kills < 0:
            raise ValueError("Invalid skill, timeout or kill requirement")
        if self.objective == "native_exit" and self.scenario is not None:
            raise ValueError("Scenario completion must not be called full-game native exit")


MAP_SPLITS = {
    "train": ("E1M1", "E1M2", "E1M3"),
    "development": ("E1M4",),
    "heldout": ("E1M5", "E1M6"),
    "reserved_extension": ("E1M7", "E1M8", "E1M9"),
}


def full_game_tasks(asset="doom1"):
    return tuple(TaskSpec(f"{asset}:{map_name}", asset, map_name, split=split)
                 for split, maps in MAP_SPLITS.items() for map_name in maps)


CURRICULUM = (
    TaskSpec("basic", "freedoom2", objective="kill", timeout_tics=300,
             scenario="basic", min_kills=1),
    TaskSpec("navigation", "freedoom2", objective="scenario_completion",
             timeout_tics=2100, scenario="my_way_home"),
    TaskSpec("doors", "doom1", "E1M1", no_monsters=True),
    TaskSpec("survival", "freedoom2", objective="survival", timeout_tics=1050,
             scenario="take_cover"),
    TaskSpec("health_survival", "freedoom2", objective="survival", timeout_tics=1050,
             scenario="health_gathering"),
    TaskSpec("corridor", "freedoom2", objective="scenario_completion",
             timeout_tics=2100, scenario="deadly_corridor"),
    TaskSpec("combined", "doom1", "E1M1", min_kills=1),
)


def get_task(value):
    if isinstance(value, TaskSpec):
        return value
    if isinstance(value, dict):
        return TaskSpec(**value)
    for spec in CURRICULUM + full_game_tasks("doom1") + full_game_tasks("freedoom1"):
        if spec.task_id == value:
            return spec
    raise KeyError(f"Unknown task: {value}")


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vizdoom_module():
    return importlib.import_module("vizdoom")


def new_game(vzd):
    # Native construction creates this process-working-directory cache using a
    # check-then-mkdir sequence. Concurrent first engines can race. Python's
    # exist_ok operation handles that race before any native constructor runs.
    # Do not chdir here: browser environments can live in different threads.
    (Path.cwd() / "_vizdoom").mkdir(exist_ok=True)
    return vzd.DoomGame()


def asset_path(asset):
    """Explicit environment override first; portable installed assets second."""
    override = os.environ.get("DOOM_V3_" + asset.upper() + "_WAD")
    if override:
        path = Path(override).expanduser().resolve()
    elif asset in {"freedoom1", "freedoom2"}:
        path = Path(vizdoom_module().__file__).parent / f"{asset}.wad"
    elif asset == "doom1":
        lab = Path(__file__).resolve().parents[1]
        candidates = [lab / "wads/doom1.wad", lab.parents[1] / "demos/doom/wads/doom1.wad"]
        path = next((p for p in candidates if p.is_file()), candidates[0])
    else:
        raise ValueError("Unsupported asset name")
    if not path.is_file():
        raise FileNotFoundError(f"Missing {asset}; set DOOM_V3_{asset.upper()}_WAD: {path}")
    return path


def wad_maps(path):
    """Read map marker names only; no trajectory or heldout policy query."""
    data = Path(path).read_bytes()
    ident, count, directory = struct.unpack_from("<4sII", data)
    if ident not in {b"IWAD", b"PWAD"} or directory + count * 16 > len(data):
        raise ValueError("Invalid WAD directory")
    names = [struct.unpack_from("<II8s", data, directory + i * 16)[2].rstrip(b"\0").decode("ascii")
             for i in range(count)]
    return [name for i, name in enumerate(names[:-1]) if names[i + 1] in {"THINGS", "TEXTMAP"}]


def task_identity(spec):
    spec = get_task(spec)
    vzd = vizdoom_module()
    wad = asset_path(spec.asset)
    value = {"task": asdict(spec), "engine_version": vzd.__version__,
             "iwad": {"name": wad.name, "bytes": wad.stat().st_size, "sha256": sha_file(wad)},
             "screen": {"format": "GRAY8", "width": 320, "height": 240, "hud": True,
                        "weapon": True, "crosshair": False, "decals": True, "particles": True,
                        "automap_buffer": False},
             "engine_config": "fresh per-engine temporary vizdoom.ini", "sound": False,
             "action_names": list(ACTION_NAMES), "button_names": list(BUTTON_NAMES),
             "repeat_tics": REPEAT_TICS,
             "episode_start_time": configured_start_time(spec),
             "episode_start_source": "scenario_cfg" if spec.scenario else "explicit_iwad_control"}
    if spec.scenario:
        root = Path(vzd.__file__).parent / "scenarios"
        value["scenario_files"] = {suffix: {"sha256": sha_file(root / f"{spec.scenario}.{suffix}"),
                                            "bytes": (root / f"{spec.scenario}.{suffix}").stat().st_size}
                                   for suffix in ("cfg", "wad")}
    value["boundary"] = "Actor receives visible screen and its own past actions only; all variables/labels/geometry are teacher or evaluator evidence"
    return value


def configured_start_time(spec):
    """Read the engine's parsed setting; never replace scenario warm-up tics."""
    spec = get_task(spec)
    if not spec.scenario:
        return 1
    vzd = vizdoom_module()
    game = new_game(vzd)
    try:
        game.load_config(str(Path(vzd.__file__).parent / "scenarios" / f"{spec.scenario}.cfg"))
        return int(game.get_episode_start_time())
    finally:
        game.close()


def classify_outcome(spec, *, terminal, dead, timeout, kills, elapsed_tics, external_cutoff=None):
    """Pure evidence predicate, independent of rewards and teacher decisions."""
    spec = get_task(spec)
    if external_cutoff:
        return {"success": False, "reason": external_cutoff, "native_exit": False}
    native_exit = bool(terminal and not dead and not timeout and spec.objective == "native_exit")
    if dead:
        reason, success = "dead", False
    elif spec.objective == "survival":
        # Native timeout is checked by the engine against the configured bound;
        # initial engine setup tics are not actor-executed tics.
        success = bool(timeout)
        reason = "survived_declared_horizon" if success else "survival_incomplete"
    elif timeout:
        reason, success = "native_timeout", False
    elif spec.objective == "kill":
        success = bool(terminal and kills >= spec.min_kills)
        reason = "native_kill_objective" if success else "kill_objective_incomplete"
    elif terminal:
        success = bool(kills >= spec.min_kills)
        reason = ("native_level_exit" if native_exit else "native_scenario_completion") if success else "insufficient_native_kills"
    else:
        reason, success = "running", False
    return {"success": success, "reason": reason, "native_exit": native_exit}


class DoomEnv:
    """Owns one native game. observe() is the entire external actor boundary."""
    VARIABLE_NAMES = ("HEALTH", "ARMOR", "KILLCOUNT", "ITEMCOUNT", "SECRETCOUNT", "DEAD",
                      "POSITION_X", "POSITION_Y", "POSITION_Z", "ANGLE", "SELECTED_WEAPON",
                      "SELECTED_WEAPON_AMMO", "DAMAGE_TAKEN", "DAMAGECOUNT")

    def __init__(self, task, seed, *, teacher=False, visible=False):
        self.spec, self.seed, self.teacher_enabled = get_task(task), int(seed), bool(teacher)
        self.vzd = vzd = vizdoom_module()
        self.game = game = new_game(vzd)
        self.tmp = tempfile.TemporaryDirectory(prefix="cadence-doom-v3-")
        try:
            self._initialize(visible)
        except BaseException:
            self.close()
            raise

    def _initialize(self, visible):
        vzd, game, teacher = self.vzd, self.game, self.teacher_enabled
        root = Path(vzd.__file__).parent
        if self.spec.scenario:
            game.load_config(str(root / "scenarios" / f"{self.spec.scenario}.cfg"))
        game.set_doom_config_path(str(Path(self.tmp.name) / "vizdoom.ini"))
        game.set_doom_game_path(str(asset_path(self.spec.asset)))
        game.set_doom_map(self.spec.map_name)
        game.set_doom_skill(self.spec.skill)
        game.set_seed(self.seed)
        game.set_mode(vzd.Mode.PLAYER)
        if not self.spec.scenario:
            game.set_episode_start_time(1)
        self.episode_start_time = int(game.get_episode_start_time())
        game.set_episode_timeout(self.spec.timeout_tics)
        game.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
        game.set_screen_format(vzd.ScreenFormat.GRAY8)
        game.set_render_hud(True)
        game.set_render_weapon(True)
        game.set_render_crosshair(False)
        game.set_render_decals(True)
        game.set_render_particles(True)
        game.set_automap_buffer_enabled(False)
        game.set_sound_enabled(False)
        game.set_window_visible(visible)
        game.set_labels_buffer_enabled(teacher)
        game.set_depth_buffer_enabled(teacher)
        game.set_objects_info_enabled(teacher)
        game.set_sectors_info_enabled(teacher)
        game.set_available_buttons([getattr(vzd.Button, name) for name in BUTTON_NAMES])
        game.set_available_game_variables([getattr(vzd.GameVariable, name) for name in self.VARIABLE_NAMES])
        if self.spec.no_monsters:
            game.add_game_args("-nomonsters")
        game.init()
        self.start_tic = int(game.get_episode_time())
        self.elapsed_tics = 0
        self.total_reward = 0.0
        self.transitions = 0
        self.last_facts = self.facts()

    @property
    def finished(self):
        return bool(self.game.is_episode_finished())

    def observe(self):
        state = self.game.get_state()
        if state is None:
            raise RuntimeError("A terminal game has no actor observation")
        result = np.asarray(state.screen_buffer, dtype=np.uint8).copy()
        if result.shape != (240, 320):
            raise ValueError(f"Unexpected native screen shape {result.shape}")
        return result

    def facts(self):
        game = self.game
        values = {name.lower(): float(game.get_game_variable(getattr(self.vzd.GameVariable, name)))
                  for name in self.VARIABLE_NAMES}
        terminal, dead = self.finished, bool(game.is_player_dead())
        timeout = bool(game.is_episode_timeout_reached())
        return {**values, "terminal": terminal, "dead": dead, "timeout": timeout,
                "episode_tic": int(game.get_episode_time()), "elapsed_tics": self.elapsed_tics,
                "episode_start_time": self.episode_start_time, "initial_episode_tic": self.start_tic,
                "seed": self.seed, "task_id": self.spec.task_id}

    def privileged(self):
        if not self.teacher_enabled:
            raise PermissionError("Privileged observations are disabled for student evaluation")
        state = self.game.get_state()
        if state is None:
            raise RuntimeError("Terminal game")
        return {"facts": self.facts(), "labels": state.labels, "objects": state.objects,
                "sectors": state.sectors, "depth": np.asarray(state.depth_buffer),
                "screen": np.asarray(state.screen_buffer)}

    def step(self, action, *, tics=REPEAT_TICS):
        if isinstance(action, bool) or not isinstance(action, (int, np.integer)) or not 0 <= action < len(ACTION_NAMES):
            raise ValueError("Action must be a legal discrete macro index")
        if not isinstance(tics, int) or not 1 <= tics <= REPEAT_TICS:
            raise ValueError("An actor decision may execute at most the declared macro duration")
        if self.finished:
            raise RuntimeError("Cannot execute after a terminal state")
        before = self.facts()
        buttons = list(ACTION_BUTTONS[int(action)])
        rewards = []
        for _ in range(tics):
            if self.finished:
                break
            rewards.append(float(self.game.make_action(buttons, 1)))
        actual = len(rewards)
        self.elapsed_tics += actual
        self.transitions += 1
        self.total_reward += sum(rewards)
        after = self.facts()
        self.last_facts = after
        return {"action": int(action), "action_name": ACTION_NAMES[int(action)], "buttons": buttons,
                "requested_tics": tics, "tics": actual, "rewards": rewards, "reward": sum(rewards),
                "terminal": after["terminal"], "dead": after["dead"], "timeout": after["timeout"],
                "native_kill_delta": after["killcount"] - before["killcount"],
                "health_delta": after["health"] - before["health"], "episode_tic": after["episode_tic"]}

    def outcome(self, external_cutoff=None):
        facts = self.facts()
        classification = classify_outcome(self.spec, terminal=facts["terminal"], dead=facts["dead"],
                                          timeout=facts["timeout"], kills=int(facts["killcount"]),
                                          elapsed_tics=self.elapsed_tics, external_cutoff=external_cutoff)
        return {"task_id": self.spec.task_id, "seed": self.seed, "skill": self.spec.skill,
                "split": self.spec.split, "return": self.total_reward, "tics": self.elapsed_tics,
                "decisions": self.transitions, **facts, **classification}

    def close(self):
        try:
            self.game.close()
        finally:
            self.tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
