"""A scripted RAM-reading teacher for NES Castlevania (PRG1), stages 0 to 5.

It reads console RAM (the brain never does) and answers one pad action per decision:

- **Routes.** Stairs, jumps and headings per (stage, block): stages 0 to 2 placed by hand,
  stages 3 to 18 mined from a synced replay of a published no-damage tool-assisted run
  (``routes_mined.py``; places are world x = scroll + ``0x38C`` and y = ``0x354``), with
  recovery rules for places it has walked past.
- **Enemies.** The whip for enemies within reach ahead, a jump or a crouch for some.
- **Savestate lookahead at the giant bat.** Given the console (``teacher_action(ram, memory,
  body)``), when the bat is awake and within ``PLAN_RANGE`` px the teacher saves the emulator
  state, rolls out ``CANDIDATES`` (short action prefixes, the heuristic fight rule after them)
  for ``HORIZON`` decisions each, scores bat health taken (``HIT_GAIN`` per point) against
  Simon's health lost (``HIT_COST`` per point) and lives lost (-500), restores the state and
  commits the first ``COMMIT`` actions of the best rollout (``memory["plan"]``). Without a body
  the heuristic fight rule answers. A caller that executes something else drops the plan
  (``note_executed``).

Run this file to evaluate the teacher alone on ten power-on starts.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simon.pad import ACTIONS, readings  # noqa: E402

# object table: 28 slots, one byte array per attribute; slot 0 is Simon, 1-3 his whip/weapon
SLOTS = 0x1C
OBJ_Y, OBJ_X, OBJ_TYPE, OBJ_LEFT, OBJ_STATE = 0x354, 0x38C, 0x434, 0x450, 0x46C
ON_STAIRS = 4  # Simon's state byte: 0 ground, 1 jump, 2 whip, 4 stairs
STAGE, SCROLL_LO, SCROLL_HI = 0x28, 0x2E, 0x2F

HARMLESS = {0, 40, 47, 48, 49, 50, 51}   # empty, candle, hit/death effects, pickups


def action(h=0, v=0, whip=0, jump=0) -> int:
    return ACTIONS.index((h, v, whip, jump))


def objects(ram):
    """Active non-Simon objects as (slot, type, x, y)."""
    out = []
    for i in range(4, SLOTS):
        kind = int(ram[OBJ_TYPE + i])
        if kind:
            out.append((i, kind, int(ram[OBJ_X + i]), int(ram[OBJ_Y + i])))
    return out


# The route, by (stage, block). World x is the scroll plus Simon's screen x; y is Simon's y.
# Stairs: (x low, x high, y, vertical): standing there, press up (-1) or down (+1); once on the
# stairs keep pressing it until they end. Jumps: (x low, x high, y[, direction]): standing there,
# jump right (direction +1, the default) or left (-1).
# Stages 0-2 were found by hand; stages 3 onward are mined from the TAS (routes_mined.py), the
# windows widened to the 12-px decision phase.
STAIRS = {
    (1, 0): [(1285, 1305, 192, -1)],            # hall end: up to the door floor
    (2, 1): [(30, 58, 192, +1),                 # bottom-left: down into the underground
             (445, 470, 192, -1)],              # after the underground: up towards the exit
    (2, 0): [(434, 456, 112, -1)],              # underground: up and out
}
JUMPS = {
    (2, 0): [(216, 228, 112), (276, 288, 112),   # two gaps over the water
             (470, 500, 144, -1)],                  # off the low ledge past the exit stairs, back up left
    (2, 1): [(395, 412, 128)],                   # stair landing onto the exit ledge
}
# Walking direction overrides (stage, block): list of (x low, x high, y low, y high, direction);
# the default is right (stage-2 rules are in ``heading``).
HEADINGS: dict[tuple[int, int], list[tuple[int, int, int, int, int]]] = {}
BLOCK = 0x46
BOSS_HP = 0x1A9  # the stage boss's health (64 full)

try:  # mined places for stages 4 and on (written by mine_routes.py --write)
    from routes_mined import HEADINGS as _MH, JUMPS as _MJ, STAIRS as _MS  # noqa: E402

    for _k, _v in _MS.items():
        STAIRS.setdefault(_k, []).extend(_v)
    for _k, _v in _MJ.items():
        JUMPS.setdefault(_k, []).extend(_v)
    for _k, _v in _MH.items():
        HEADINGS.setdefault(_k, []).extend(_v)
except ImportError:
    pass


def world_x(ram) -> int:
    return int(ram[SCROLL_LO]) + 256 * int(ram[SCROLL_HI]) + int(ram[OBJ_X])


def heading(stage: int, block: int, wx: int, sy: int) -> int:
    """Walking direction: right, except on the stage-2 ground floor left of the brick wall,
    where the way on is the stairs down at the far left, and back towards a staircase Simon
    has walked past ; mined overrides for later stages."""
    if stage == 2 and block == 1 and wx < 300 and sy >= 150:
        return -1
    if stage == 1 and block == 0 and sy >= 184 and 1305 < wx < 1600:
        return -1  # past the hall-end stairs on the floor: back to their foot
    if stage == 2 and block == 0 and abs(sy - 112) <= 4 and 456 < wx < 487:
        return -1  # past the underground stairs, still on their ledge
    if stage == 2 and block == 1 and sy >= 184 and 470 < wx < 600:
        return -1  # past the stairs towards the exit
    for lo, hi, ylo, yhi, direction in HEADINGS.get((stage, block), ()):
        if lo <= wx <= hi and ylo <= sy <= yhi:
            return direction
    return 1


def route_action(ram, memory: dict) -> int:
    """Movement along the route, ignoring enemies."""
    stage, block, sy = int(ram[STAGE]), int(ram[BLOCK]), int(ram[OBJ_Y])
    state = int(ram[OBJ_STATE])
    if state == ON_STAIRS:
        memory.pop("stair_tries", None)
        return action(0, memory.get("stairs", -1))
    wx = world_x(ram)
    for lo, hi, y, vertical in STAIRS.get((stage, block), ()):
        if lo <= wx <= hi and abs(sy - y) <= 8:
            # Up/Down works only within a few px of the staircase's foot; a window is wider
            # than that (the 12-px decision phase), so after two presses that did nothing
            # Simon steps towards the window's centre and tries again
            centre = (lo + hi) // 2
            tries = memory.get("stair_tries", 0) if memory.get("stair_at") == (stage, block, lo) else 0
            memory["stair_at"] = (stage, block, lo)
            if tries >= 2 and abs(wx - centre) > 3:
                memory["stair_tries"] = 0
                return action(1 if centre > wx else -1)
            memory["stair_tries"] = tries + 1
            memory["stairs"] = vertical
            return action(0, vertical)
    if state == 0:
        for lo, hi, y, *direction in JUMPS.get((stage, block), ()):
            if lo <= wx <= hi and abs(sy - y) <= 8:
                return action(direction[0] if direction else 1, 0, 0, 1)
    if stage in BOSS_STAGES and int(ram[BOSS_HP]) == 0:
        orbs = [x for _, kind, x, _ in objects(ram) if kind == ORB]
        if orbs:
            sx = int(ram[OBJ_X])
            toward = 1 if orbs[0] > sx else -1
            blocked = memory.get("orb_x") == sx and state == 0
            memory["orb_x"] = sx
            return action(toward, 0, 0, int(blocked))  # jump over a step in the way
    return action(heading(stage, block, wx, sy))


# Whip reach: the whip comes out about 13 frames after the press and reaches about 40 px in
# front of Simon, about 8 px above his y. An enemy is engaged when it is within FRONT px ahead
# (it closes in during the wind-up) or BEHIND px behind (turn, then whip), and within the
# vertical band. The giant bat (type 25) swoops about 20 px per decision, so it is engaged on its
# position one decision ahead (from its last move), with a jumping whip when it is high.
FRONT, BEHIND = 60, 40
DEFAULT_BAND = (-28, 28)
BOSS = 25
BOSS_REACH, BOSS_BAND, BOSS_HIGH = (6, 52), (-44, 12), (-76, -44)
SUBWEAPON = True
BOSS_LEAD = 0.5  # decisions of lead on the bat's last move (0.5 beat 1.0 in the arena)
ORB, BOSS_STAGES = 47, {3, 6, 9, 12, 15, 18}  # the orb the dead boss leaves; touching it clears the stage

# the savestate lookahead (bat arena)
PLAN_RANGE = 128     # plan while the awake bat is within this many px horizontally
HORIZON = 10         # decisions per rollout
COMMIT = 2           # decisions of the best rollout executed before the next plan
HIT_COST = 24.0      # score per point of Simon's health lost (a bat hit takes 8); a whip hit on
HIT_GAIN = 8.0       # the bat (8 of its 64) scores this per point: survival before damage
NOOP = action(0)
CANDIDATES: tuple[tuple, ...] = (
    (),                                   # the heuristic fight rule throughout
    (NOOP,), (NOOP, NOOP), (NOOP, NOOP, NOOP),   # wait, then the rule
    (action(0, 0, 1, 0),),                # whip now, facing as is
    ("turn_whip",),                       # whip towards the bat
    (NOOP, "turn_whip"),                  # one beat later
    ("turn_jump_whip",),                  # jump and whip towards the bat
    (action(0, 1, 1, 0),),                # crouch and whip
    (action(0, 1, 0, 0), action(0, 1, 0, 0)),  # crouch (duck under a swoop)
    (action(-1), action(-1)),             # step left
    (action(1), action(1)),               # step right
    (action(0, 0, 0, 1),),                # jump straight up (dodge)
    ("away", "away"), ("away", "away", "away"),  # steps away from the bat
    ("toward", "toward"),                 # steps towards it (under a high swoop)
)


def threat(ram):
    """The nearest hostile object within whip reach as (dx, dy, kind), or None."""
    sx, sy = int(ram[OBJ_X]), int(ram[OBJ_Y])
    best = None
    for _, kind, x, y in objects(ram):
        if kind in HARMLESS or kind == BOSS:
            continue
        dx, dy = x - sx, y - sy
        low, high = DEFAULT_BAND
        if low < dy < high and -BEHIND < dx < FRONT and (best is None or abs(dx) < abs(best[0])):
            best = (dx, dy, kind)
    return best


def bat_position(ram):
    bats = [(x, y) for _, kind, x, y in objects(ram) if kind == BOSS]
    return bats[0] if bats else None


def boss_action(ram, memory: dict):
    """Against the giant bat: hold the ground, face its next position and whip when it will be in
    reach (jumping when it will be high). None when no awake giant bat is on screen."""
    bat = bat_position(ram)
    if bat is None:
        memory.pop("bat", None)
        memory.pop("bat_awake", None)
        memory.pop("perch", None)
        return None
    x, y = bat
    px, py = memory.get("bat", (x, y))
    memory["bat"] = (x, y)
    scroll = int(ram[SCROLL_LO]) + 256 * int(ram[SCROLL_HI])
    perch = memory.setdefault("perch", (x + scroll, y))  # where it was first seen, in the world
    memory["bat_awake"] = memory.get("bat_awake", False) or (x + scroll, y) != perch
    if not memory["bat_awake"]:
        return None  # it sleeps on its perch until Simon walks into the arena
    dx = x + round(BOSS_LEAD * (x - px)) - int(ram[OBJ_X])
    dy = y + round(BOSS_LEAD * (y - py)) - int(ram[OBJ_Y])
    facing = -1 if ram[OBJ_LEFT] else 1
    side = 1 if dx >= 0 else -1
    turn = side if side != facing else 0
    if memory.get("whipped", False) or int(ram[OBJ_STATE]) not in (0, ON_STAIRS):
        return action(0)
    if BOSS_REACH[0] <= abs(dx) <= BOSS_REACH[1]:
        if BOSS_BAND[0] <= dy <= BOSS_BAND[1]:
            return action(turn, 0, 1, 0)
        if BOSS_HIGH[0] <= dy < BOSS_HIGH[1] and int(ram[OBJ_STATE]) == 0:
            return action(turn, 0, 1, 1)
    if SUBWEAPON and BOSS_REACH[1] < abs(dx) <= 100 and dy > BOSS_HIGH[0]:
        return action(turn, -1, 1, 0)  # up + whip throws the carried weapon (if hearts allow)
    return action(0)


def heuristic_action(ram, memory: dict) -> int:
    """The teacher: route, enemies within whip reach, the bat rule; no lookahead."""
    facing = -1 if ram[OBJ_LEFT] else 1
    choice = route_action(ram, memory)
    fight = boss_action(ram, memory) if int(ram[OBJ_STATE]) != ON_STAIRS else None
    target = threat(ram)
    if fight is not None:
        choice = fight
    elif target is not None and not memory.get("whipped", False):
        dx, dy, kind = target
        side = 1 if dx >= 0 else -1
        if int(ram[OBJ_STATE]) == ON_STAIRS:
            side = facing  # on the stairs Simon whips the way he faces
        choice = action(side if side != facing else 0, 0, 1, 0)
    return choice


def resolve(step, ram) -> int:
    """A candidate step: a pad action index, or a name relative to the bat."""
    if not isinstance(step, str):
        return int(step)
    bat = bat_position(ram)
    sx = int(ram[OBJ_X])
    side = 1 if bat is None or bat[0] >= sx else -1
    facing = -1 if ram[OBJ_LEFT] else 1
    turn = side if side != facing else 0
    if step == "turn_whip":
        return action(turn, 0, 1, 0)
    if step == "turn_jump_whip":
        return action(turn, 0, 1, 1)
    if step == "away":
        return action(-side)
    if step == "toward":
        return action(side)
    raise ValueError(step)


def rollout(body, ram, memory: dict, prefix, horizon: int) -> tuple[float, list[int]]:
    """Execute ``prefix`` then the heuristic for ``horizon`` decisions in all; the score and
    the actions taken. The body must be restored by the caller."""
    ram = np.asarray(ram).astype(int)
    hp0, health0, lives0 = int(ram[BOSS_HP]), int(ram[0x44]), int(ram[0x2A])
    actions, score = [], 0.0
    for k in range(horizon):
        if k < len(prefix):
            a = resolve(prefix[k], ram)
            memory["whipped"] = bool(ACTIONS[a][2])
        else:
            a = heuristic_action(ram, memory)
            memory["whipped"] = bool(ACTIONS[a][2])
        actions.append(a)
        _, ram, done = body.step(a)
        ram = np.asarray(ram).astype(int)
        if int(ram[0x2A]) < lives0 or int(ram[0x44]) == 0 or done:
            score -= 500.0
            break
    hp = int(ram[BOSS_HP])
    score += HIT_GAIN * max(hp0 - hp, 0) - HIT_COST * max(health0 - int(ram[0x44]), 0)
    if hp == 0 and hp0 > 0:
        score += 100.0
    return score, actions


def plan_fight(body, ram, memory: dict) -> int:
    """Savestate lookahead: the first action of the best candidate rollout; the next
    ``COMMIT - 1`` actions wait in ``memory["plan"]``."""
    snapshot = body.snapshot()
    best = None
    for prefix in CANDIDATES:
        body.restore(snapshot)
        trial = copy.deepcopy(memory)
        trial.pop("plan", None)
        score, actions = rollout(body, ram, trial, prefix, HORIZON)
        if actions and (best is None or score > best[0]):
            best = (score, actions)
    body.restore(snapshot)
    actions = best[1][:COMMIT]
    memory["plan"] = actions[1:]
    memory["planned"] = memory.get("planned", 0) + 1
    return actions[0]


def teacher_action(ram, memory: dict, body=None) -> int:
    """One pad action for the present RAM; ``memory`` is the teacher's small private state.
    With ``body`` (snapshot/restore/step) the bat arena is played by savestate lookahead."""
    ram = np.asarray(ram).astype(int)
    plan = memory.get("plan")
    if plan:
        choice = int(plan.pop(0))
        memory["whipped"] = bool(ACTIONS[choice][2])
        return choice
    choice = heuristic_action(ram, memory)
    if body is not None and memory.get("bat_awake") and int(ram[BOSS_HP]) > 0:
        bat = bat_position(ram)
        if bat is not None and abs(bat[0] - int(ram[OBJ_X])) <= PLAN_RANGE \
                and int(ram[OBJ_STATE]) not in (ON_STAIRS,):
            choice = plan_fight(body, ram, memory)
    memory["whipped"] = bool(ACTIONS[choice][2])
    return choice


def note_executed(memory: dict, label: int, executed: int) -> None:
    """Record what the body actually did: the whip alternation and, when the executed action
    is not the teacher's, the end of any committed plan (its rollout no longer holds)."""
    memory["whipped"] = bool(ACTIONS[executed][2])
    if executed != label:
        memory.pop("plan", None)


# ----------------------------------------------------------------------------- evaluation

def progress_of(ram) -> int:
    return int(ram[SCROLL_LO]) + 256 * int(ram[SCROLL_HI]) + int(ram[OBJ_X])


def run_teacher(decisions: int, noops: int, *, lookahead: bool = True, body=None) -> dict:
    """The teacher alone for ``decisions`` decisions after ``noops`` idle decisions; progress as
    100000*stage + world x (``0x38C``), counted on stable alive frames; deaths per stage and the
    bat health taken."""
    from common import Body  # noqa: PLC0415 (common imports this module)

    own = body is None
    body = body or Body()
    frame, ram = body.power_on(noops)
    memory: dict = {}
    progress = furthest = lives_lost = 0
    previous = None
    deaths, recent, stage_first = [], [], {}
    bat_hp_min = 64
    for step in range(decisions):
        choice = teacher_action(ram, memory, body if lookahead else None)
        before = readings(ram)
        frame, ram, done = body.step(choice)
        after = readings(ram)
        place = progress_of(ram)
        if (after["stage"] == before["stage"] and after["stage"] != 20 and after["lives"] == before["lives"]
                and after["health"] > 0 and previous is not None and abs(place - previous) <= 64):
            progress = max(progress, 100_000 * after["stage"] + place)
        previous = place if after["stage"] == before["stage"] else None
        furthest = max(furthest, after["stage"]) if after["stage"] != 20 else furthest
        stage_first.setdefault(int(after["stage"]), step)
        if after["stage"] == 3 and bat_position(ram) is not None:
            bat_hp_min = min(bat_hp_min, int(ram[BOSS_HP]))
        if after["lives"] < before["lives"]:
            lives_lost += 1
        if after["health"] == 0 and before["health"] > 0:  # one count per death
            deaths.append({"step": step, "stage": before["stage"], "place": progress_of(ram)})
        if done:
            break
    end = readings(ram)
    if own:
        body.close()
    by_stage: dict[str, int] = {}
    for d in deaths:
        by_stage[str(d["stage"])] = by_stage.get(str(d["stage"]), 0) + 1
    return {"noops": noops, "decisions": step + 1, "furthest_stage": furthest, "progress": progress,
            "lives_lost": lives_lost, "score": end["score"], "end": end, "deaths": deaths,
            "deaths_by_stage": by_stage, "bat_hp_dealt": 64 - bat_hp_min,
            "stage_first_decision": stage_first, "plans": memory.get("planned", 0),
            "lookahead": lookahead}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--decisions", type=int, default=3000)
    p.add_argument("--noops", type=int, nargs="+", default=list(range(10)))
    p.add_argument("--no-lookahead", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import Body  # noqa: PLC0415

    body = Body()
    t0 = time.time()
    rows = []
    for n in a.noops:
        t1 = time.time()
        r = run_teacher(a.decisions, n, lookahead=not a.no_lookahead, body=body)
        r["seconds"] = round(time.time() - t1, 1)
        rows.append(r)
        print(json.dumps({k: r[k] for k in ("noops", "decisions", "furthest_stage", "progress",
                                            "lives_lost", "deaths_by_stage", "bat_hp_dealt", "score",
                                            "stage_first_decision", "plans", "seconds")}), flush=True)
    body.close()
    reached4 = sum(r["furthest_stage"] >= 4 for r in rows)
    print(json.dumps({"starts": len(rows), "stage4": reached4, "gate_9_of_10": reached4 >= 9,
                      "seconds": round(time.time() - t0, 1)}))
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"rows": rows, "stage4": reached4,
                                     "seconds": round(time.time() - t0, 1)}, indent=1) + "\n")


if __name__ == "__main__":
    main()
