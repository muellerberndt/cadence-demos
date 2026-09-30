"""Doom shareware E1M1 harness for a Cadence pixel-only player.

The DoomLab wrapper owns the ViZDoom game. The Teacher is a scripted policy
with privileged access to the labels and depth buffers; it exists only to
supply demonstrated actions. The Cadence brain never sees labels, depth or
game variables: its sensory boundary is the downsampled grayscale frame from
``brain_view``. This is a disclosed supervised curriculum, not reward learning.
"""

from __future__ import annotations

import math

import numpy as np
import vizdoom as vzd

# Decision-level action set. One score per button; combinations are allowed.
BUTTONS = ("forward", "turn_left", "turn_right", "attack", "use",
           "move_left", "move_right", "move_backward")
FRAME_SKIP = 4  # 35 tics/s -> ~8.75 decisions/s
VIEW_W, VIEW_H = 32, 20  # peripheral retina; 640 gray samples
FOVEA_W, FOVEA_H = 64, 6  # high-res aiming band; 384 gray samples
FOVEA_ROWS = (78, 120)  # weapon-height band of the 200-row frame (7px cells)
FOVEA_COLS = (32, 288)  # central 256 columns (4px cells)
TARGET_ON, TARGET_OFF = 0.6, -0.6  # witness encoding inside tanh/state range

ENEMIES = {"Zombieman", "ShotgunGuy", "DoomImp", "Demon", "Spectre"}
PROJECTILES = {"DoomImpBall", "CacodemonBall", "BaronBall", "Rocket"}


def _block_mean(gray: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    h, w = gray.shape
    bh, bw = h // out_h, w // out_w
    small = gray[: out_h * bh, : out_w * bw].reshape(out_h, bh, out_w, bw)
    return small.mean(axis=(1, 3))


def _scale(values: np.ndarray) -> np.ndarray:
    return (values / 255.0) * (2 * TARGET_ON) - TARGET_ON


def brain_view(screen_rgb: np.ndarray):
    """320x200 RGB -> (periphery, fovea) float arrays in [-0.6, 0.6].

    Periphery: full-frame 32x20 block-mean gray. Fovea: 64x6 block-mean gray
    of the central weapon-height band, giving ~4px horizontal cells where
    aiming precision matters. Both are raw luminance; no learned features.
    """
    gray = screen_rgb.astype(np.float32).mean(axis=2)  # (200, 320)
    periphery = _scale(_block_mean(gray, VIEW_H, VIEW_W))
    r0, r1 = FOVEA_ROWS
    c0, c1 = FOVEA_COLS
    fovea = _scale(_block_mean(gray[r0:r1, c0:c1], FOVEA_H, FOVEA_W))
    return periphery, fovea


class DoomLab:
    """Headless doom1.wad E1M1 with screen, depth and label buffers."""

    def __init__(self, *, wad="wads/doom1.wad", doom_map="E1M1", skill=1,
                 timeout_tics=35 * 120, seed=None, visible=False):
        game = vzd.DoomGame()
        game.set_doom_game_path(wad)
        game.set_doom_map(doom_map)
        game.set_screen_resolution(vzd.ScreenResolution.RES_320X200)
        game.set_screen_format(vzd.ScreenFormat.RGB24)
        game.set_depth_buffer_enabled(True)
        game.set_labels_buffer_enabled(True)
        game.set_render_hud(True)
        game.set_window_visible(visible)
        game.set_mode(vzd.Mode.PLAYER)
        game.set_episode_timeout(timeout_tics)
        game.set_doom_skill(skill)
        if seed is not None:
            game.set_seed(seed)
        game.set_available_buttons([
            vzd.Button.MOVE_FORWARD, vzd.Button.TURN_LEFT, vzd.Button.TURN_RIGHT,
            vzd.Button.ATTACK, vzd.Button.USE,
            vzd.Button.MOVE_LEFT, vzd.Button.MOVE_RIGHT,
            vzd.Button.MOVE_BACKWARD,
        ])
        game.set_available_game_variables([
            vzd.GameVariable.HEALTH, vzd.GameVariable.KILLCOUNT,
            vzd.GameVariable.AMMO2, vzd.GameVariable.POSITION_X,
            vzd.GameVariable.POSITION_Y, vzd.GameVariable.ANGLE,
        ])
        game.init()
        self.game = game

    def new_episode(self):
        self.game.new_episode()

    @property
    def finished(self):
        return self.game.is_episode_finished()

    def state(self):
        return self.game.get_state()

    def act(self, buttons, skip=FRAME_SKIP):
        """Apply one decision for ``skip`` tics; buttons is a 5-int list."""
        return self.game.make_action(list(buttons), skip)

    def variables(self):
        v = self.game.get_state().game_variables
        return {"health": v[0], "kills": v[1], "ammo": v[2],
                "x": v[3], "y": v[4], "angle": v[5]}

    def close(self):
        self.game.close()


# E1M1 patrol stops (map units, from the WAD THINGS lump): zombie room,
# zombie overlook, shotgun platform, southern imp, eastern imp, then home.
# The dense waypoint chain between stops comes from the WAD walk grid.
E1M1_STOPS = ((1056, -3616), (2272, -2432), (2912, -2816), (3264, -3936),
              (3008, -4416), (3440, -3472), (1056, -3616))


def load_route(path="e1m1_route.json"):
    import json
    return [tuple(p) for p in json.load(open(path))]


class Teacher:
    """Privileged scripted policy: fight, follow waypoints, avoid walls, unstick.

    Uses labels (enemy screen positions), the depth buffer, and map
    position/angle for waypoint bearings. The student never receives these
    inputs; only the teacher's chosen buttons become witnesses paired with
    the student's grayscale view.
    """

    AIM_DEADZONE = 0.10   # fraction of half-width; inside -> fire
    TURN_ZONE = 0.06      # outside -> turn toward target
    NEAR_WALL = 12        # depth units (smaller = nearer); start turning
    CLEAR_WALL = 18       # keep turning until the way ahead reads at least this
    STUCK_DIST = 8.0      # map units per forward decision considered progress
    WAYPOINT_RADIUS = 60.0
    BEARING_ZONE = 20.0   # degrees; inside -> forward instead of turning

    def __init__(self, route=None):
        self.serpentine = 0  # combat strafe phase counter
        self.last_pos = None
        self.prev_forward = False
        self.stuck = 0
        self.unstick = 0
        self.turning = 0  # 0 none, 1 left, 2 right (wander hysteresis)
        self.route = list(route) if route is not None else load_route()
        self.target = 0
        self.commit = 0  # forward decisions owed after a wall-avoid turn
        self.unstick_cycles = 0  # since the last waypoint advance

    def _threat(self, state):
        """Widest visible incoming projectile: (center offset, width) or None."""
        best = None
        for lab in state.labels:
            if lab.object_name in PROJECTILES and lab.width >= 2:
                if best is None or lab.width > best.width:
                    best = lab
        if best is None:
            return None
        return (best.x + best.width / 2.0 - 160.0) / 160.0, best.width

    def _enemy(self, state):
        """(center offset in [-1, 1], pixel width) of the widest visible enemy."""
        best = None
        for lab in state.labels:
            if lab.object_name in ENEMIES and lab.width >= 3:
                if best is None or lab.width > best.width:
                    best = lab
        if best is None:
            return None
        center = best.x + best.width / 2.0
        return (center - 160.0) / 160.0, best.width

    def act(self, state, pos_xy, angle=None):
        atk = 0
        depth = state.depth_buffer  # smaller = nearer
        center = float(np.median(depth[80:130, 140:180]))
        left = float(np.median(depth[80:130, 20:120]))
        right = float(np.median(depth[80:130, 200:300]))

        # Stuck only counts failed *forward* attempts; turning in place is fine.
        if self.last_pos is not None and self.prev_forward:
            moved = float(np.hypot(pos_xy[0] - self.last_pos[0],
                                   pos_xy[1] - self.last_pos[1]))
            self.stuck = self.stuck + 1 if moved < self.STUCK_DIST else 0
        self.last_pos = pos_xy
        self.prev_forward = False

        # Waypoint capture, including skipping ahead past nearby later ones.
        for ahead in range(min(6, len(self.route)), 0, -1):
            idx = (self.target + ahead - 1) % len(self.route)
            wx, wy = self.route[idx]
            if np.hypot(wx - pos_xy[0], wy - pos_xy[1]) < self.WAYPOINT_RADIUS:
                self.target = (idx + 1) % len(self.route)
                self.unstick_cycles = 0
                break
        wx, wy = self.route[self.target]

        # 0. Reactive dodge: an incoming fireball beats everything else.
        # Strafe hard away from its screen side while still fighting.
        threat = self._threat(state)
        target = self._enemy(state)
        if threat is not None and abs(threat[0]) < 0.55:
            offset = target[0] if target is not None else None
            l = 1 if offset is not None and offset < -self.TURN_ZONE else 0
            r = 1 if offset is not None and offset > self.TURN_ZONE else 0
            atk = 1 if offset is not None and abs(offset) <= self.AIM_DEADZONE else 0
            ml, mr = (0, 1) if threat[0] <= 0 else (1, 0)
            self.prev_forward = False
            return [0, l, r, atk, 0, ml, mr, 0]

        # 1. Combat: track the widest visible enemy, fire when centered,
        # serpentine sideways so hitscan and fireballs miss, close when far.
        if target is not None:
            offset, width = target
            l = 1 if offset < -self.TURN_ZONE else 0
            r = 1 if offset > self.TURN_ZONE else 0
            atk = 1 if abs(offset) <= self.AIM_DEADZONE else 0
            self.serpentine += 1
            side = (self.serpentine // 4) % 2  # swap strafe side each 4
            ml, mr = (1, 0) if side else (0, 1)
            f = 1 if width < 8 else 0  # close distance on far targets
            back = 1 if width >= 24 else 0  # kite when it fills the fovea
            return [f, l, r, atk, 0, ml, mr, back]

        # 2. Unstick: one USE for doors, then a committed turn away.
        if self.unstick > 0:
            self.unstick -= 1
            use = 1 if self.unstick == 5 else 0
            turn = self.turning or 2
            return [0, 1 if turn == 1 else 0, 1 if turn == 2 else 0, 0, use, 0, 0, 0]
        if self.stuck >= 4:
            self.stuck = 0
            self.unstick = 6
            self.unstick_cycles += 1
            if self.unstick_cycles >= 3:
                # The grid was too optimistic here; give up on this waypoint.
                self.target = (self.target + 1) % len(self.route)
                self.unstick_cycles = 0
            self.turning = 1 if left >= right else 2
            return [0, 0, 0, 0, 1, 0, 0, 0]

        # 3. Owe forward motion after an avoidance turn (leave the corner).
        if self.commit > 0:
            self.commit -= 1
            self.prev_forward = True
            return [1, 0, 0, 0, 0, 0, 0, 0]

        # 4. Misaligned: turn toward the waypoint bearing; no depth veto.
        if angle is not None:
            bearing = math.degrees(math.atan2(wy - pos_xy[1], wx - pos_xy[0]))
            error = (bearing - angle + 180.0) % 360.0 - 180.0
            if abs(error) > self.BEARING_ZONE:
                self.turning = 0
                return ([0, 1, 0, 0, 0, 0, 0, 0] if error > 0
                        else [0, 0, 1, 0, 0, 0, 0, 0])

        # 5. Aligned: advance while the way ahead is passable; Doom climbs
        # low sills and steps on contact, so press close before avoiding.
        if center > 5:
            self.turning = 0
            self.prev_forward = True
            return [1, 0, 0, 0, 0, 0, 0, 0]

        # 6. Aligned but blocked: avoidance turn toward the deeper side,
        # then owe a few forward decisions so steering cannot livelock.
        if not self.turning:
            self.turning = 1 if left >= right else 2
        self.commit = 4
        return ([0, 1, 0, 0, 0, 0, 0, 0] if self.turning == 1
                else [0, 0, 1, 0, 0, 0, 0, 0])


def targets_from_buttons(buttons):
    """5 binary buttons -> witness vector in {-0.6, +0.6}."""
    return [TARGET_ON if b else TARGET_OFF for b in buttons]


def buttons_from_scores(scores):
    """Motor scores -> 8 binary buttons; opposed pairs stay exclusive."""
    b = [1 if s > 0.0 else 0 for s in scores]
    for i, j in ((0, 7), (1, 2), (5, 6)):
        if b[i] and b[j]:
            keep = i if scores[i] >= scores[j] else j
            b[i] = 1 if keep == i else 0
            b[j] = 1 if keep == j else 0
    return b
