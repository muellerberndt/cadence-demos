"""The page's placeholder brain host: the joint and eye interface of the parrot page, with a
hand-written controller in place of a brain, so the page runs end to end until the composed brain's
host takes its place in the pack (INTERFACES P6). Nothing here is learned.

Interface (the composed brain's host keeps it):
  describe()                      -> {name, placeholder, joints, eye, rate_hz, populations, groups, neurons}
  step(meta, left, right, proprio) -> {targets, group_activity, readout}, buffers "activity", "targets"
  reset(), silence(group, on)

`left` and `right` are each eye's image, uint8, rows top-down, (h, w, 3), column 0 at the eye's
rear edge (INTERFACES P2). `proprio` is the joints' angles then speeds on [-1, 1] (P3).

The placeholder looks at what stands out: in each eye, the pixels whose colour differs most from
the eye's own mean colour. It looks as a parrot does: its head still, then a quick turn toward the
strongest spot (or elsewhere), a hold of one to three seconds, now and then a slow tilt of the head. Its "distance" units are a stand-in for the units a real brain learns: a population
tuned to the apparent size of what it looks at (a thing near looks large), so the page's tuning
curve, its question mark and its silence switch run end to end; the composed brain names its own.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

JOINTS = ["head_yaw", "head_pitch", "head_roll", "neck_pitch", "beak_open", "wing_l", "wing_r",
          "grip_l", "grip_r", "leg_l", "leg_r"]
RANGE = {"head_yaw": (-170.0, 170.0), "head_pitch": (-50.0, 60.0), "head_roll": (-45.0, 45.0)}
DISTANCE_UNITS = 12


def _unit(name: str, value: float) -> float:
    lo, hi = RANGE[name]
    return float(2.0 * (value - lo) / (hi - lo) - 1.0)


def _value(name: str, unit: float) -> float:
    lo, hi = RANGE[name]
    return float(lo + (unit + 1.0) / 2.0 * (hi - lo))


class Host:
    def __init__(self, config: dict[str, Any]):
        eye = config.get("eye", {})
        self.w, self.h = int(eye.get("w", 64)), int(eye.get("h", 32))
        self.field = math.radians(float(eye.get("field", 87.5)))
        self.vfield = math.radians(float(eye.get("vfield", 60.0)))
        self.fovea = float(eye.get("fovea", 0.4))
        self.axis = math.radians(float(eye.get("axis", 75.0)))
        t = 2.0 * (np.arange(self.w) + 0.5) / self.w - 1.0
        self.az = self.field * t * (self.fovea + (1.0 - self.fovea) * np.abs(t))  # toward the beak
        r = 1.0 - 2.0 * (np.arange(self.h) + 0.5) / self.h
        self.el = self.vfield * r * (self.fovea + (1.0 - self.fovea) * np.abs(r))
        self.silenced: set[str] = set()
        self.buffers: dict[str, Any] = {}
        pops = [("retina_l", "Left eye's retina", self.w * self.h // 4, "retina"),
                ("retina_r", "Right eye's retina", self.w * self.h // 4, "retina"),
                ("salience", "What stands out", 2 * 16, "tectum"),
                ("distance", "Distance units", DISTANCE_UNITS, "distance"),
                ("motor", "Motor: the joints' targets", len(JOINTS), "motor")]
        self.populations = []
        start = 0
        for name, title, size, region in pops:
            self.populations.append({"name": name, "title": title, "start": start, "size": size, "region": region})
            start += size
        self.neurons = start
        self.pop = {p["name"]: p for p in self.populations}
        self.preferred = np.geomspace(0.012, 0.25, DISTANCE_UNITS)  # apparent sizes (fractions of a field) each unit prefers
        self.reset()

    def reset(self) -> dict[str, Any]:
        self.t = 0
        self.rng = np.random.default_rng(7)
        self.target = {"head_yaw": 0.0, "head_pitch": 0.0, "head_roll": 0.0}
        self.hold_until = 10
        self.tilt = None  # a slow tilt in progress: (start roll, end roll, first moment, moments)
        return {"ok": True}

    def describe(self) -> dict[str, Any]:
        return {
            "name": "placeholder", "placeholder": True,
            "title": "Placeholder brain: a hand-written controller",
            "joints": JOINTS, "eye": {"w": self.w, "h": self.h}, "rate_hz": 10,
            "populations": self.populations, "neurons": self.neurons, "synapses": 0,
            "groups": [{
                "name": "distance", "title": "Distance units (placeholder)",
                "explain": ("Stand-ins for the units the parrot's brain learns for distance. Here each unit is "
                            "tuned by hand to how large the thing in view looks: a thing near looks large. "
                            "The composed brain names its own units here, with what they learned."),
                "units": list(range(self.pop["distance"]["start"], self.pop["distance"]["start"] + DISTANCE_UNITS)),
                "variable": "distance", "unit": "m", "range": [0.1, 0.8],
            }],
        }

    def silence(self, group: str, on: bool) -> dict[str, Any]:
        (self.silenced.add if on else self.silenced.discard)(group)
        return {"silenced": sorted(self.silenced)}

    def _salience(self, img: np.ndarray) -> np.ndarray:
        x = img.astype(np.float32) / 255.0
        mean = x.reshape(-1, 3).mean(axis=0)
        d = np.sqrt(((x - mean) ** 2).sum(axis=2))
        sat = x.max(axis=2) - x.min(axis=2)
        return d * (0.5 + sat)

    def step(self, meta: dict[str, Any], left: np.ndarray, right: np.ndarray, proprio: np.ndarray) -> dict[str, Any]:
        self.t += 1
        L = left.reshape(self.h, self.w, 3)
        R = right.reshape(self.h, self.w, 3)
        sl, sr = self._salience(L), self._salience(R)
        yaw = _value("head_yaw", float(proprio[0]))
        pitch = _value("head_pitch", float(proprio[1]))
        # the strongest spot in either eye, and where it lies from the beak (left of the beak positive)
        best = None
        for name, s in (("left", sl), ("right", sr)):
            k = int(np.argmax(s))
            row, col = divmod(k, self.w)
            if best is None or s[row, col] > best[0]:
                side = 1.0 if name == "left" else -1.0
                az_head = side * (self.axis - self.az[col])  # 0 at the beak, + to the parrot's left
                best = (float(s[row, col]), name, row, col, math.degrees(az_head), math.degrees(self.el[row]), s)
        strength, eye, row, col, az, el, smap = best
        # How a parrot looks: the head still, then a quick turn to something (a head saccade; the page
        # moves the joint there in about 0.2 s), a hold of one to three seconds, now and then a slow
        # tilt to look with one eye. The targets change only at a decision, never each moment.
        if self.t >= self.hold_until:
            if strength > 0.35 and self.rng.random() < 0.8:
                # bring the thing to the middle of the eye that sees it (a parrot looks with one eye)
                turn = az - math.copysign(55.0, az) if abs(az) > 55.0 else az * 0.5
                self.target["head_yaw"] = float(np.clip(yaw + turn, -150.0, 150.0))
                self.target["head_pitch"] = float(np.clip(pitch + 0.6 * el, -35.0, 40.0))
            else:
                self.target["head_yaw"] = float(np.clip(yaw + self.rng.choice([-1, 1]) * self.rng.uniform(40, 110), -150.0, 150.0))
                self.target["head_pitch"] = float(self.rng.uniform(-15, 10))
            if self.rng.random() < 0.3:
                end = float(self.rng.choice([-1, 1]) * self.rng.uniform(18, 32))
                self.tilt = (self.target["head_roll"], end, self.t, int(self.rng.integers(10, 16)))
            elif self.target["head_roll"] != 0.0 and self.rng.random() < 0.5:
                self.tilt = (self.target["head_roll"], 0.0, self.t, 8)
            self.hold_until = self.t + int(self.rng.integers(10, 31))
        if self.tilt is not None:  # a slow tilt: the target eases over a second or so
            a, b, t0, n = self.tilt
            x = min(1.0, (self.t - t0) / n)
            self.target["head_roll"] = a + (b - a) * (x * x * (3 - 2 * x))
            if x >= 1.0:
                self.tilt = None
        mask = smap > 0.5 * strength
        apparent = float(mask.sum()) / (self.w * self.h) if strength > 0.35 else 0.0
        # the distance units: tuned to apparent size (log), silent when nothing is in view
        if apparent > 0 and "distance" not in self.silenced:
            dist_units = np.exp(-0.5 * ((np.log(apparent) - np.log(self.preferred)) / 0.35) ** 2).astype(np.float32)
        else:
            dist_units = np.zeros(DISTANCE_UNITS, np.float32)
        if dist_units.sum() > 0.05:
            # the stand-in's own reading of distance: a thing of about 8 cm that looks this large
            est = float(np.sum(dist_units * self.preferred) / dist_units.sum())
            width = math.sqrt(est * 4.0 * self.field * self.vfield)  # the angle it spans, radians
            readout = {"distance": round(float(np.clip(0.08 / (width + 1e-6), 0.05, 2.0)), 3), "eye": eye}
        else:
            readout = {"distance": None, "eye": eye}
        targets = np.full(len(JOINTS), np.nan, np.float32)
        targets[0] = _unit("head_yaw", self.target["head_yaw"])
        targets[1] = _unit("head_pitch", self.target["head_pitch"])
        targets[2] = _unit("head_roll", self.target["head_roll"])
        activity = np.zeros(self.neurons, np.float32)
        lum_l = (L.astype(np.float32).mean(axis=2) / 255.0).reshape(self.h // 2, 2, self.w // 2, 2).mean(axis=(1, 3))
        lum_r = (R.astype(np.float32).mean(axis=2) / 255.0).reshape(self.h // 2, 2, self.w // 2, 2).mean(axis=(1, 3))
        p = self.pop
        activity[p["retina_l"]["start"]:p["retina_l"]["start"] + p["retina_l"]["size"]] = lum_l.ravel()
        activity[p["retina_r"]["start"]:p["retina_r"]["start"] + p["retina_r"]["size"]] = lum_r.ravel()
        sal = np.concatenate([sl.reshape(self.h, 16, self.w // 16).max(axis=(0, 2)), sr.reshape(self.h, 16, self.w // 16).max(axis=(0, 2))])
        activity[p["salience"]["start"]:p["salience"]["start"] + 32] = np.clip(sal / 1.2, 0, 1)
        activity[p["distance"]["start"]:p["distance"]["start"] + DISTANCE_UNITS] = dist_units
        activity[p["motor"]["start"]:p["motor"]["start"] + len(JOINTS)] = np.nan_to_num((targets + 1) / 2, nan=0.5)
        self.buffers = {"activity": activity, "targets": targets}
        return {"buffers": ["activity", "targets"], "group_activity": {"distance": dist_units.tolist()},
                "readout": readout, "looked": {"eye": eye, "row": row, "col": col, "strength": round(strength, 3)}}

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        if cmd == "describe":
            return self.describe()
        if cmd == "reset":
            return self.reset()
        if cmd == "silence":
            return self.silence(str(message.get("group")), bool(message.get("on")))
        raise ValueError(f"unknown command {cmd!r}")
