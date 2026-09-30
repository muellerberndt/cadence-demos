"""Privileged demonstration teacher; never imported by the learned actor.

This teacher reads native map geometry, positions, labels and projectile state.
Every chosen action carries its reason and privileged target in an intervention
record. It is an imperfect route/combat expert, not an asserted solved oracle.
Its own native outcomes must pass before its demonstrations count as successful.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from pathlib import Path
import re
import struct

import numpy as np

from .interface import ACTION_NAMES
from .tasks import asset_path, vizdoom_module


EXIT_SPECIALS = {11, 51, 52, 124}
KEY_TYPES = {5: "blue", 6: "yellow", 13: "red", 38: "red", 39: "yellow", 40: "blue"}
ENEMIES = {"Zombieman", "ShotgunGuy", "DoomImp", "Demon", "Spectre", "Cacodemon",
           "BaronOfHell", "HellKnight", "LostSoul", "ChaingunGuy", "Revenant", "Mancubus",
           "Arachnotron", "Archvile", "PainElemental", "Cyberdemon", "SpiderMastermind"}
PROJECTILES = {"DoomImpBall", "CacodemonBall", "BaronBall", "Rocket", "RevenantTracer",
               "FatShot", "ArachnotronPlasma"}


@dataclass(frozen=True)
class TeacherDecision:
    action: int
    reason: str
    evidence: dict

    def record(self):
        return {"action": self.action, "action_name": ACTION_NAMES[self.action], "reason": self.reason,
                "privileged_evidence": self.evidence, "source": "privileged_geometry_teacher",
                "actor_boundary": "Only the chosen action can become a target; privileged_evidence is never a sensory input"}


class WadMap:
    """Doom/Hexen/UDMF map reader and teacher-only floor-aware route grid.

    Keys and doors are potential routes, not claims of native traversability.
    Closed doors remain routeable and need a USE intervention in the engine.
    UDMF geometry is parsed as data, never evaluated as executable text.
    """
    cell = 16

    def __init__(self, path, map_name):
        self.path, self.map_name = str(path), map_name.upper()
        data = Path(path).read_bytes()
        ident, count, directory = struct.unpack_from("<4sII", data)
        if ident not in {b"IWAD", b"PWAD"} or directory + count * 16 > len(data):
            raise ValueError("Invalid WAD")
        entries = []
        for i in range(count):
            offset, size, name = struct.unpack_from("<II8s", data, directory + i * 16)
            if offset + size > len(data):
                raise ValueError("WAD lump outside file")
            entries.append((name.rstrip(b"\0").decode("ascii").upper(), offset, size))
        start = next((i for i, e in enumerate(entries) if e[0] == self.map_name), None)
        if start is None:
            raise ValueError(f"Map {map_name} not found")
        map_entries = entries[start + 1:start + 12]
        names = {e[0] for e in map_entries}
        if "TEXTMAP" in names:
            entry = next(e for e in map_entries if e[0] == "TEXTMAP")
            self._load_udmf(data[entry[1]:entry[1]+entry[2]].decode("utf8"))
            self._grid = None
            return
        self.hexen = "BEHAVIOR" in names

        def records(name, fmt):
            entry = next(e for e in map_entries if e[0] == name)
            chunk = data[entry[1]:entry[1] + entry[2]]
            width = struct.calcsize(fmt)
            if len(chunk) % width:
                raise ValueError(f"Malformed {name}")
            return list(struct.iter_unpack(fmt, chunk))

        self.vertices = records("VERTEXES", "<hh")
        self.sides = records("SIDEDEFS", "<hh8s8s8sh")
        self.sectors = records("SECTORS", "<hh8s8shhh")
        if self.hexen:
            self.things = [dict(x=r[1], y=r[2], angle=r[4], type=r[5], flags=r[6]) for r in records("THINGS", "<7h6B")]
            line_records = [(r[0], r[1], r[2], r[3], r[4], r[9], r[10]) for r in records("LINEDEFS", "<3H6B2h")]
        else:
            self.things = [dict(x=x, y=y, angle=a, type=t, flags=f) for x, y, a, t, f in records("THINGS", "<hhhhh")]
            line_records = records("LINEDEFS", "<HHHHHhh")
        self.lines = []
        for index, (a, b, flags, special, tag, front, back) in enumerate(line_records):
            self.lines.append(dict(index=index, a=self.vertices[a], b=self.vertices[b], flags=flags,
                                   special=special, tag=tag,
                                   front=self.sides[front][-1] if front >= 0 else -1,
                                   back=self.sides[back][-1] if back >= 0 else -1))
        self.exits = []
        for line in self.lines:
            if self.hexen or line["special"] not in EXIT_SPECIALS:
                continue
            ax, ay = line["a"]
            bx, by = line["b"]
            length = math.hypot(bx - ax, by - ay)
            if not length:
                continue
            center = ((ax + bx) / 2, (ay + by) / 2)
            right = ((by - ay) / length, -(bx - ax) / length)
            self.exits.append({"line": line["index"], "special": line["special"], "center": center,
                               "approach": (center[0] + 40 * right[0], center[1] + 40 * right[1]),
                               "cross": (center[0] - 40 * right[0], center[1] - 40 * right[1]),
                               "secret": line["special"] in {51, 124}})
        self._grid = None

    def _load_udmf(self, text):
        self.hexen = True
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        grouped = {}
        for kind, body in re.findall(r"\b(\w+)\s*\{([^{}]*)\}", text):
            value = {}
            for key, token in re.findall(r"\b(\w+)\s*=\s*(\"[^\"]*\"|[^;]+);", body):
                token = token.strip()
                if token in {"true", "false"}:
                    parsed = token == "true"
                elif token.startswith('"'):
                    parsed = token[1:-1]
                else:
                    parsed = float(token) if any(c in token.lower() for c in (".", "e")) else int(token, 0)
                value[key.lower()] = parsed
            grouped.setdefault(kind.lower(), []).append(value)
        self.vertices = [(float(v.get("x", 0)), float(v.get("y", 0))) for v in grouped.get("vertex", [])]
        self.sides = [(0, 0, b"", b"", b"", int(s.get("sector", 0))) for s in grouped.get("sidedef", [])]
        self.sectors = [(int(s.get("heightfloor", 0)), int(s.get("heightceiling", 128)), b"", b"", 0,
                         int(s.get("special", 0)), int(s.get("id", 0))) for s in grouped.get("sector", [])]
        self.things = [dict(x=float(t.get("x", 0)), y=float(t.get("y", 0)), angle=float(t.get("angle", 0)),
                            type=int(t.get("type", 0)), flags=7) for t in grouped.get("thing", [])]
        self.lines = []
        for index, line in enumerate(grouped.get("linedef", [])):
            front, back = int(line.get("sidefront", -1)), int(line.get("sideback", -1))
            self.lines.append(dict(index=index, a=self.vertices[int(line["v1"])], b=self.vertices[int(line["v2"])],
                                   flags=1 if line.get("blocking", False) else 0, special=int(line.get("special", 0)),
                                   tag=int(line.get("arg0", 0)),
                                   front=self.sides[front][-1] if front >= 0 else -1,
                                   back=self.sides[back][-1] if back >= 0 else -1))
        if not self.vertices or not self.sectors or not self.lines:
            raise ValueError("UDMF map lacks required geometry")
        self.exits = []  # Scenario objectives use native ACS completion, not Doom line numbers.

    def _build_grid(self):
        if self._grid is not None:
            return self._grid
        vertices = np.asarray(self.vertices)
        origin = vertices.min(axis=0) - self.cell
        w, h = ((vertices.max(axis=0) - origin) // self.cell + 2).astype(int)
        if h * w > 4_000_000:
            raise ValueError("Teacher route grid exceeds declared 4M-cell bound")
        cx = origin[0] + (np.arange(w) + .5) * self.cell
        cy = origin[1] + (np.arange(h) + .5) * self.cell
        gx, gy = np.broadcast_arrays(cx[None, :], cy[:, None])
        floors = np.full((h, w), -32768, dtype=np.int32)
        damage = np.zeros((h, w), dtype=bool)
        boundaries = [[] for _ in self.sectors]
        for line in self.lines:
            if line["front"] != line["back"]:
                for side in (line["front"], line["back"]):
                    if side >= 0:
                        boundaries[side].append(line)
        for sector in sorted(range(len(self.sectors)), key=lambda i: -len(boundaries[i])):
            inside = np.zeros((h, w), dtype=bool)
            for line in boundaries[sector]:
                ax, ay = line["a"]
                bx, by = line["b"]
                if ay == by:
                    continue
                inside ^= ((ay > gy) != (by > gy)) & (gx < ax + (gy - ay) * (bx - ax) / (by - ay))
            floors[inside] = self.sectors[sector][0]
            damage[inside] = self.sectors[sector][5] in {4, 5, 7, 11, 16}
        blocked = floors == -32768
        margin = np.zeros((h, w), dtype=bool)
        for line in self.lines:
            if line["back"] >= 0 and not line["flags"] & 1:
                continue
            ax, ay = line["a"]
            bx, by = line["b"]
            lo = np.floor((np.minimum(line["a"], line["b"]) - origin - 32) / self.cell).astype(int)
            hi = np.ceil((np.maximum(line["a"], line["b"]) - origin + 32) / self.cell).astype(int)
            x0, y0 = np.maximum(lo, 0)
            x1, y1 = np.minimum(hi + 1, (w, h))
            xs, ys = gx[y0:y1, x0:x1], gy[y0:y1, x0:x1]
            denom = (bx - ax) ** 2 + (by - ay) ** 2
            t = np.clip(((xs - ax) * (bx - ax) + (ys - ay) * (by - ay)) / max(1, denom), 0, 1)
            distance = np.hypot(xs - ax - t * (bx - ax), ys - ay - t * (by - ay))
            blocked[y0:y1, x0:x1] |= distance < 16.1
            margin[y0:y1, x0:x1] |= distance < 28
        self._grid = blocked, floors, damage, margin, origin
        return self._grid

    def route(self, start, goal):
        blocked, floors, damage, margin, origin = self._build_grid()
        h, w = blocked.shape

        def cell(point):
            return int((point[1] - origin[1]) // self.cell), int((point[0] - origin[0]) // self.cell)

        def free(c):
            return 0 <= c[0] < h and 0 <= c[1] < w and not blocked[c]

        def snap(point):
            c = cell(point)
            candidates = [(dy * dy + dx * dx, (c[0] + dy, c[1] + dx))
                          for dy in range(-5, 6) for dx in range(-5, 6) if free((c[0] + dy, c[1] + dx))]
            if not candidates:
                raise ValueError("No walkable route endpoint within80 map units")
            return min(candidates)[1]

        start, goal = snap(start), snap(goal)
        costs, came, heap = {start: 0.0}, {start: None}, [(0.0, start)]
        while heap:
            _, current = heapq.heappop(heap)
            if current == goal:
                break
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                nxt = current[0] + dy, current[1] + dx
                if not free(nxt) or floors[nxt] - floors[current] > 24:
                    continue
                if dy and dx and (not free((current[0] + dy, current[1])) or not free((current[0], current[1] + dx))):
                    continue
                weight = math.hypot(dx, dy) * (60 if damage[nxt] else 3 if margin[nxt] else 1)
                candidate = costs[current] + weight
                if candidate < costs.get(nxt, math.inf):
                    costs[nxt], came[nxt] = candidate, current
                    heapq.heappush(heap, (candidate + math.hypot(nxt[0] - goal[0], nxt[1] - goal[1]), nxt))
        if goal not in came:
            raise ValueError("No static floor-aware path to teacher target")
        cells, current = [], goal
        while current is not None:
            cells.append(current)
            current = came[current]
        cells.reverse()
        return [(float(origin[0] + (x + .5) * self.cell), float(origin[1] + (y + .5) * self.cell)) for y, x in cells]


class GeometryTeacher:
    def __init__(self, spec):
        self.spec = spec
        if not spec.scenario:
            self.map = WadMap(asset_path(spec.asset), spec.map_name)
        elif spec.scenario in {"my_way_home", "deadly_corridor", "health_gathering"}:
            self.map = WadMap(Path(vizdoom_module().__file__).parent / "scenarios" / f"{spec.scenario}.wad", spec.map_name)
        else:
            self.map = None
        self.steps = 0
        self.route, self.goal = [], None
        self.last_position, self.stuck = None, 0
        self.last_action = "noop"
        self.collected_keys = set()
        self.last_reason = None
        self.route_errors = []
        self.exit = None
        self.last_use_step = -100
        self.door_target = None
        self.door_used_step = None

    @staticmethod
    def _decision(name, reason, **evidence):
        return TeacherDecision(ACTION_NAMES.index(name), reason, evidence)

    def acknowledge(self, actual_action, actual_tics):
        """Commit actual motor feedback, including student actions in DAgger.

        Proposed USE cannot advance a door's opening phase if another action
        was executed. Stuck detection also follows executed forward motion.
        """
        if (isinstance(actual_action, bool) or not isinstance(actual_action, (int, np.integer))
                or not 0 <= actual_action < len(ACTION_NAMES) or type(actual_tics) is not int
                or not 1 <= actual_tics <= 4):
            raise ValueError("Invalid teacher motor acknowledgement")
        name = ACTION_NAMES[int(actual_action)]
        if self.door_used_step == self.steps and name != "use":
            self.door_used_step = None
        if self.last_use_step == self.steps and name != "use":
            self.last_use_step = -100
        if name == "use":
            self.last_use_step = self.steps
            if self.door_target is not None:
                self.door_used_step = self.steps
        self.last_action = name

    def _navigation_goal(self, position, objects):
        if self.spec.scenario:
            goals = [o for o in objects if o.name in {"GreenArmor", "BlueArmor", "RedArmor", "HealthBonus", "Medikit"}]
            if goals:
                item = min(goals, key=lambda o: math.hypot(o.position_x - position[0], o.position_y - position[1]))
                return (item.position_x, item.position_y), "scenario_native_item"
            return None, "no_geometry_goal"
        keys = [thing for thing in self.map.things if thing["type"] in KEY_TYPES and
                thing["flags"] & (1 if self.spec.skill <= 2 else 2 if self.spec.skill == 3 else 4)]
        for thing in keys:
            key = (thing["x"], thing["y"], thing["type"])
            if math.hypot(thing["x"] - position[0], thing["y"] - position[1]) < 24:
                self.collected_keys.add(key)
        remaining = [thing for thing in keys if (thing["x"], thing["y"], thing["type"]) not in self.collected_keys]
        if remaining:
            remaining.sort(key=lambda t: math.hypot(t["x"] - position[0], t["y"] - position[1]))
            for thing in remaining:
                try:
                    self.map.route(position, (thing["x"], thing["y"]))
                    return (thing["x"], thing["y"]), "key_pickup_approach"
                except ValueError:
                    continue
        exits = sorted(self.map.exits, key=lambda e: (e["secret"], math.hypot(e["approach"][0] - position[0], e["approach"][1] - position[1])))
        for target in exits:
            try:
                self.map.route(position, target["approach"])
                self.exit = target
                return target["approach"], "native_exit_approach"
            except ValueError:
                continue
        return None, "no_routable_exit"

    def act(self, env):
        view = env.privileged()
        facts, labels = view["facts"], view["labels"]
        position = facts["position_x"], facts["position_y"]
        angle = facts["angle"]
        self.steps += 1
        moved = None if self.last_position is None else math.dist(self.last_position, position)
        if moved is not None and self.last_action.startswith("forward"):
            self.stuck = self.stuck + 1 if moved < 3 else 0
        self.last_position = position

        def choose(name, reason, **evidence):
            self.last_action, self.last_reason = name, reason
            return self._decision(name, reason, position=list(position), angle=angle,
                                  health=facts["health"], native_kills=facts["killcount"], **evidence)

        projectiles = [label for label in labels if label.object_name in PROJECTILES and label.width >= 2]
        if projectiles:
            threat = max(projectiles, key=lambda label: label.width)
            offset = (threat.x + threat.width / 2 - 160) / 160
            if abs(offset) < .55:
                return choose("fire_strafe_right" if offset <= 0 else "fire_strafe_left", "visible_projectile_dodge",
                              projectile=threat.object_name, offset=offset)
        enemies = [label for label in labels if label.object_name in ENEMIES and label.width >= 2]
        if enemies:
            enemy = max(enemies, key=lambda label: label.width)
            offset = (enemy.x + enemy.width / 2 - 160) / 160
            if abs(offset) > .08:
                name = "fire_left" if offset < 0 else "fire_right"
            elif enemy.width < 5:
                name = "forward_fire"
            elif enemy.width > 42:
                name = "backward_fire"
            else:
                name = "fire_strafe_left" if self.steps // 12 % 2 else "fire_strafe_right"
            if facts["selected_weapon_ammo"] <= 0 and facts["selected_weapon"] not in {0, 1}:
                name = "weapon_next"
            return choose(name, "visible_enemy_combat", enemy=enemy.object_name, offset=offset, width=enemy.width)
        if self.spec.objective == "survival":
            depth = view["depth"]
            left, right = np.median(depth[60:180, 20:120]), np.median(depth[60:180, 200:300])
            return choose("strafe_left" if left > right else "strafe_right", "survival_clearance",
                          left_depth=float(left), right_depth=float(right))

        if self.door_target is not None:
            door = self.door_target
            center = ((door["a"][0]+door["b"][0])/2, (door["a"][1]+door["b"][1])/2)
            if self.door_used_step is None:
                bearing = math.degrees(math.atan2(center[1]-position[1], center[0]-position[0]))
                error = (bearing-angle+180) % 360 - 180
                if abs(error) > 8:
                    return choose("turn_left" if error > 0 else "turn_right", "door_center_alignment",
                                  door_line=door["index"], bearing_error=error)
                self.door_used_step = self.steps
                self.last_use_step = self.steps
                return choose("use", "blocked_route_door_use", door_line=door["index"])
            if self.steps - self.door_used_step < 20:
                return choose("forward", "door_opening_committed_advance", door_line=door["index"])
            self.door_target = self.door_used_step = None
            self.route, self.goal, self.stuck = [], None, 0

        if self.goal is None or self.steps % 32 == 1:
            self.goal, goal_kind = self._navigation_goal(position, view["objects"])
            if self.goal is not None and self.map is not None:
                try:
                    self.route = self.map.route(position, self.goal)
                except ValueError as error:
                    self.route_errors.append(str(error))
                    self.route = []
        if (self.exit and self.goal == self.exit["approach"] and math.dist(position, self.goal) < 28
                and math.dist(position, self.exit["center"]) < 62):
            target = self.exit["center"]
            bearing = math.degrees(math.atan2(target[1] - position[1], target[0] - position[0]))
            error = (bearing - angle + 180) % 360 - 180
            if abs(error) > 9:
                return choose("turn_left" if error > 0 else "turn_right", "align_native_exit", exit_line=self.exit["line"], bearing_error=error)
            if self.exit["special"] in {52, 124}:
                return choose("forward", "cross_native_exit", exit_line=self.exit["line"])
            return choose("use", "activate_native_exit", exit_line=self.exit["line"])
        if self.stuck >= 3:
            self.stuck = 0
            doors = [line for line in self.map.lines if line["special"] in {1, 26, 27, 28, 31, 32, 33, 34, 117, 118}] if self.map else []
            doors = [(math.dist(position, ((line["a"][0]+line["b"][0])/2, (line["a"][1]+line["b"][1])/2)), line) for line in doors]
            if doors:
                distance, door = min(doors, key=lambda pair: pair[0])
                if distance < 96:
                    self.door_target = door
                    self.door_used_step = None
                    center = ((door["a"][0]+door["b"][0])/2, (door["a"][1]+door["b"][1])/2)
                    bearing = math.degrees(math.atan2(center[1]-position[1], center[0]-position[0]))
                    error = (bearing-angle+180) % 360 - 180
                    if abs(error) > 8:
                        return choose("turn_left" if error > 0 else "turn_right", "door_center_alignment",
                                      door_line=door["index"], bearing_error=error)
                    self.door_used_step = self.steps
                    self.last_use_step = self.steps
                    return choose("use", "blocked_route_door_use", door_line=door["index"])
            if self.steps - self.last_use_step >= 24:
                self.last_use_step = self.steps
                return choose("use", "blocked_route_door_use", goal=self.goal)
            # Repeated USE can reverse a rising native door before the player's
            # height fits. Keep moving toward it while one activation completes.
            return choose("forward", "door_opening_cooldown", goal=self.goal)
        if self.route:
            # Only skip a contiguous reached prefix; never jump through walls.
            while len(self.route) > 1 and math.dist(position, self.route[0]) < 28:
                self.route.pop(0)
            target = self.route[min(1, len(self.route)-1)]
        else:
            target = self.goal
        if target is not None:
            bearing = math.degrees(math.atan2(target[1] - position[1], target[0] - position[0]))
            error = (bearing - angle + 180) % 360 - 180
            if abs(error) > 12:
                return choose("turn_left" if error > 0 else "turn_right", "route_bearing", target=list(target), bearing_error=error)
            return choose("forward", "route_advance", target=list(target), bearing_error=error)
        depth = view["depth"]
        center = float(np.median(depth[60:180, 140:180]))
        if center < 12:
            return choose("use" if self.steps % 8 == 0 else "turn_right", "unrouted_exploration_blocked", center_depth=center)
        return choose("forward", "unrouted_exploration", center_depth=center)


def probe(task, seed, output, *, wall_seconds=120, max_decisions=5250):
    """Record an oracle episode; never label it student performance."""
    import gzip
    import hashlib
    import json
    import time
    from .tasks import DoomEnv, get_task, task_identity, sha_file
    task = get_task(task)
    if task.split not in {"train", "development"}:
        raise ValueError("Teacher probes may not consume reserved full-map evaluation layouts")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    freeze = {"schema": "doom-v3-teacher-probe/1", "task_identity": task_identity(task), "seed": int(seed),
              "wall_seconds": wall_seconds, "max_decisions": max_decisions,
              "teacher_sha256": sha_file(Path(__file__)), "tasks_sha256": sha_file(Path(__file__).with_name("tasks.py")),
              "interface_sha256": sha_file(Path(__file__).with_name("interface.py")),
              "interpretation": "Privileged teacher feasibility, never a learned actor result", "created_unix": time.time()}
    (output / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
    (output / "sources").mkdir()
    for name in ("teacher.py", "tasks.py", "interface.py"):
        (output / "sources" / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    started = time.monotonic()
    counts, cutoff = {}, None
    with DoomEnv(task, seed, teacher=True) as env, gzip.open(output / "interventions.jsonl.gz", "wt") as stream:
        teacher = GeometryTeacher(task)
        for index in range(max_decisions):
            if env.finished:
                break
            if time.monotonic() - started >= wall_seconds:
                cutoff = "teacher_wall_cap"
                break
            raw = env.observe()
            decision = teacher.act(env)
            transition = env.step(decision.action)
            teacher.acknowledge(decision.action, transition["tics"])
            record = {"step": index, "raw_sha256": hashlib.sha256(raw.tobytes()).hexdigest(),
                      **decision.record(), "transition": transition}
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            counts[decision.reason] = counts.get(decision.reason, 0) + 1
            if index % 100 == 0:
                status = {"event": "teacher_progress", "task": task.task_id, "seed": seed,
                                  "decisions": index + 1, "reason": decision.reason,
                                  "position": decision.evidence["position"], "health": decision.evidence["health"],
                                  "native_kills": decision.evidence["native_kills"], "wall_seconds": time.monotonic() - started}
                (output / "status.json").write_text(json.dumps(status) + "\n")
                print(json.dumps(status), flush=True)
        else:
            if not env.finished:
                cutoff = "teacher_decision_cap"
        result = {"schema": "doom-v3-teacher-result/1", "outcome": env.outcome(cutoff),
                  "wall_seconds": time.monotonic() - started, "action_reasons": counts,
                  "route_errors": teacher.route_errors, "freeze_sha256": sha_file(output / "freeze.json"),
                  "interpretation": "Privileged teacher feasibility, never a learned actor result"}
    result["interventions_sha256"] = sha_file(output / "interventions.jsonl.gz")
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="doom1:E1M1")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wall-seconds", type=float, default=120)
    parser.add_argument("--max-decisions", type=int, default=5250)
    args = parser.parse_args()
    probe(args.task, args.seed, args.out, wall_seconds=args.wall_seconds, max_decisions=args.max_decisions)
