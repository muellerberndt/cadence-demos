"""The page's placeholder brain host: the joint and eye interface of the parrot page, with a
hand-written controller in place of a brain, so the page runs end to end until the composed brain's
host takes its place in the pack (INTERFACES P6). Nothing here is learned.

Interface (the composed brain's host keeps it):
  describe()                      -> {name, placeholder, joints, eye, rate_hz, populations, groups, neurons}
  step(meta, arrays) -> {group_activity, readout, focus, voice?}, buffers "activity", "targets"[, "voice"]
  reset(), silence(group, on)

`arrays` holds `left` and `right`, each eye's image (uint8, rows top-down, (h, w, 3), column 0 at
the eye's rear edge), `proprio` (the joints' angles then speeds on [-1, 1]), and the moment's sound:
`audio` (1,600 samples at 16 kHz) and `mel` (ten log-mel frames of 40 bands, frame-major).
`meta` holds `t`, `reward`, `voice_ok` (the page may play sound) and `cue` (the head-frame azimuth
and elevation of a thing the visitor clicked, which draws the focus there).

The placeholder is a newborn, and a hand-written stand-in for what the composed brain learns: it
hears (its ear populations follow the sound's bands); a drive to call rises with quiet time (a call
every two to six seconds or so), faster when a new thing appears or the visitor has just spoken,
and when it is high the parrot calls, never over its own sound, picking from its repertoire
(African Grey calls from a licensed recording, `calls.json`, and its own babble: a random contour
or a replay of a heard snippet), favouring calls a pistachio followed. It cuts what it hears into
sounds (onset to offset) and keeps only voice-like ones (not a fan's steady hiss, not a click, not a
long steady hum), with the background's spectrum taken out. What it hears is told to the library's own memories
(`sounds.py`): each sound is a record in `cadence.LongTermMemory` (told again, a record is
rewritten and deepened; deep records fade far more slowly), and a `cadence.SynapticMemory` links the
sound to the thing in focus. A record deep enough is a sound the parrot can say back ("learned from
you"), the deeper the more often and the more faithfully. The drive and the choice of call are the
placeholder's hand-written stand-in; the composed brain learns them from the pistachio.

The placeholder looks at what stands out: in each eye, the pixels whose colour differs most from
the eye's own mean colour. It looks as a parrot does: its head still, then a quick turn toward the
strongest spot (or elsewhere), a hold of one to three seconds, now and then a slow tilt of the head. Its "distance" units are a stand-in for the units a real brain learns: a population
tuned to the apparent size of what it looks at (a thing near looks large), so the page's tuning
curve, its question mark and its silence switch run end to end; the composed brain names its own.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .sounds import SoundMemory

JOINTS = ["head_yaw", "head_pitch", "head_roll", "neck_pitch", "beak_open", "wing_l", "wing_r",
          "grip_l", "grip_r", "leg_l", "leg_r"]
RANGE = {"head_yaw": (-75.0, 75.0), "head_pitch": (-25.0, 35.0), "head_roll": (-20.0, 20.0)}
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
                ("motor", "Motor: the joints' targets", len(JOINTS), "motor"),
                ("ear", "Ear: the sound's 40 bands", 40, "ear"),
                ("fieldl", "Field L", 40, "fieldl"),
                ("ncm", "NCM and CM: heard sound, held", 40, "ncm"),
                ("voice", "Voice: the bands it says", 40, "voice")]
        self.populations = []
        start = 0
        for name, title, size, region in pops:
            self.populations.append({"name": name, "title": title, "start": start, "size": size, "region": region})
            start += size
        self.neurons = start
        self.pop = {p["name"]: p for p in self.populations}
        self.preferred = np.geomspace(0.012, 0.25, DISTANCE_UNITS)  # apparent sizes (fractions of a field) each unit prefers
        self.revise = float(config.get("revise", 0.85))
        self.focus_kind = None
        self.reset()
        self.load_calls(config.get("files"))

    def reset(self) -> dict[str, Any]:
        self.t = 0
        self.rng = np.random.default_rng(7)
        self.target = {"head_yaw": 0.0, "head_pitch": 0.0, "head_roll": 0.0}
        self.hold_until = 10
        self.tilt = None  # a slow tilt in progress: (start roll, end roll, first moment, moments)
        self.focus = None  # where the last turn went: {"az", "el"} in the head's frame at that moment
        self.heard = np.full((0, 40), math.log(1e-6), np.float32)  # the last 8 s of heard frames
        self.held = np.zeros(40, np.float32)
        self.saying = 0
        self.drive = 0.6
        self.things = None
        self.sound = []          # frames of the sound being heard
        self.quiet = 0           # quiet frames since it ended
        self.floor = math.log(1e-6)
        self.levels = np.zeros(300)  # the last three seconds' frame energies
        self.level_at = 0
        self.mem = SoundMemory(revise=self.revise)
        self.heard_event = None
        self.noise = np.full(40, math.log(1e-6) + 4.0, np.float64)  # the background's spectrum, per band (log)
        self.last_said = None    # (id, moment)
        return {"ok": True}

    # --- the repertoire ------------------------------------------------------------------------
    def load_calls(self, files: str | None) -> None:
        self.repertoire = []
        self.paid = {}
        self.credit = None
        try:
            with open(f"{files}/calls.json") as fh:
                data = json.load(fh)
            for c in data["calls"]:
                self.repertoire.append({"id": c["id"], "tag": c["tag"], "source": "recording", "frames": np.asarray(c["frames"], np.float32)})
            self.credit = data.get("source")
        except (OSError, KeyError, ValueError, TypeError):
            pass
        self.repertoire.append({"id": "babble", "tag": "babble", "source": "newborn", "frames": None})

    def voice_like(self, frames: np.ndarray) -> tuple[bool, str]:
        """Whether a heard sound is voice-like: not too short (a click, under 120 ms), not a
        steady broadband hiss (a fan: a flat spectrum), not a steady tone (a hum: its bands barely
        change from frame to frame)."""
        n = len(frames)
        if n < 12:
            return False, "click"
        if n > 200:
            return False, "too long"
        p = np.exp(frames[:, 2:38].astype(np.float64))
        mean = p.mean(axis=0)
        flatness = float(np.exp(np.log(mean + 1e-12).mean()) / (mean.mean() + 1e-12))
        flux = float(np.abs(np.diff(frames, axis=0)).mean()) if n > 1 else 0.0
        if flatness > 0.55:
            return False, "hiss"
        if flux < 0.35:
            return False, "hum"
        return True, "voice"

    def clean(self, frames: np.ndarray) -> np.ndarray:
        """The background's spectrum taken out of a sound's frames (power subtraction, kept above a
        twentieth of the frame's own power)."""
        p = np.exp(frames.astype(np.float64))
        q = np.maximum(p - 1.5 * np.exp(self.noise)[None, :], 0.05 * p)
        return np.log(q + 1e-6).astype(np.float32)

    def hear_sound(self, frames: np.ndarray) -> dict | None:
        """A voice-like sound the visitor made, cleaned of the background, told to the memories."""
        ok, _ = self.voice_like(frames)
        if not ok:
            return None
        cleaned = self.clean(frames)
        # what stands above the background once its spectrum is out (a sound the background has
        # taken in, such as a hum going on, stands at or below it)
        excess = float(np.mean(np.log(np.exp(cleaned.astype(np.float64)).sum(axis=1))) - np.log(np.exp(self.noise).sum()))
        if excess < 2.0:
            return None
        self.heard_event = self.mem.hear(cleaned, self.focus_kind)
        slot = self.heard_event["write"]["slot"]
        return {"id": f"you-{slot}", "slot": slot, "deep": round(float(self.mem.records.deep[slot]), 2)}

    def you_sounds(self) -> list:
        """Records deep enough to say back: the repertoire's sounds learned from the visitor."""
        out = []
        for slot in self.mem.sayable():
            out.append({"id": f"you-{slot}", "tag": "learned from you", "source": "you", "slot": slot,
                        "frames": self.mem.frames_of(slot), "deep": float(self.mem.records.deep[slot])})
        return out

    def remember(self, saved: dict) -> dict[str, Any]:
        self.mem.load(saved or {})
        return {"repertoire": self.repertoire_list(), "memory": self.mem.view()}

    def forget(self) -> dict[str, Any]:
        self.mem.clear()
        return {"repertoire": self.repertoire_list(), "memory": self.mem.view()}

    def choose(self) -> dict:
        options = self.repertoire + self.you_sounds()
        def weight(r):
            w = (1.0 + 2.0 * self.paid.get(r["id"], 0.0)) * (0.5 if r["id"] == "babble" else 1.0)
            return w * (1.0 + 0.5 * r["deep"]) if "deep" in r else w
        w = np.array([weight(r) for r in options])
        return options[int(self.rng.choice(len(w), p=w / w.sum()))]

    def say(self, pick: dict) -> np.ndarray:
        """The frames it says: a sound it learned comes out the more faithfully the stronger it is."""
        if pick["frames"] is None:
            return self.babble()
        f = pick["frames"].copy()
        if "deep" in pick:
            blur = 1.0 / (1.0 + pick["deep"])
            soft = 0.5 * f + 0.25 * (np.roll(f, 1, axis=1) + np.roll(f, -1, axis=1))
            soft = 0.5 * soft + 0.25 * (np.roll(soft, 1, axis=0) + np.roll(soft, -1, axis=0))
            f = (1 - blur) * f + blur * soft
        return f.astype(np.float32)

    def repertoire_list(self) -> list:
        out = []
        for r in self.repertoire + self.you_sounds():
            row = {"id": r["id"], "tag": r["tag"], "source": r["source"], "paid": round(self.paid.get(r["id"], 0.0), 2),
                   "frames": None if r["frames"] is None else r["frames"].ravel().round(2).tolist()}
            if "deep" in r:
                row.update(deep=round(r["deep"], 2), slot=r["slot"])
            out.append(row)
        return out

    def describe(self) -> dict[str, Any]:
        return {
            "name": "placeholder", "placeholder": True, "newborn": True,
            "title": "Placeholder brain: a newborn, a hand-written controller",
            "joints": JOINTS, "eye": {"w": self.w, "h": self.h}, "rate_hz": 10,
            "populations": self.populations, "neurons": self.neurons, "synapses": 0,
            "repertoire": self.repertoire_list(), "calls_credit": self.credit,
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

    def babble(self) -> np.ndarray:
        """A newborn's sound: a short run of frames, a replay of something heard or a random contour."""
        rng = self.rng
        floor = math.log(1e-6)
        loud = np.flatnonzero(self.heard.max(axis=1) > floor + 9.0) if len(self.heard) else np.array([], int)
        if len(loud) > 20 and rng.random() < 0.5:
            start = int(rng.choice(loud)); n = int(rng.integers(25, 70))
            seg = self.heard[max(0, start - 10): start - 10 + n].copy()
            shift = int(rng.integers(-3, 4))
            seg = np.roll(seg, shift, axis=1)
            seg = 0.5 * seg + 0.25 * (np.roll(seg, 1, axis=1) + np.roll(seg, -1, axis=1))
            return seg.astype(np.float32)
        n = int(rng.integers(25, 80))
        t = np.arange(n) / n
        frames = np.full((n, 40), floor + 2.0, np.float32)
        bands = np.arange(40)[None, :]
        env = np.sin(np.pi * t) ** 0.6 * rng.uniform(0.7, 1.0)
        for _ in range(int(rng.integers(1, 4))):
            c0, c1 = rng.uniform(8, 34, 2)
            wob = rng.uniform(0, 3) * np.sin(2 * np.pi * rng.uniform(2, 7) * t + rng.uniform(0, 6))
            centre = (c0 + (c1 - c0) * t + wob)[:, None]
            frames = np.logaddexp(frames, (floor + 14.0 * env[:, None]) - 0.5 * ((bands - centre) / rng.uniform(0.8, 2.0)) ** 2)
        return frames.astype(np.float32)

    def step(self, meta: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
        self.t += 1
        left, right = arrays["left"], arrays["right"]
        proprio = arrays.get("proprio", np.zeros(22, np.float32))
        L = left.reshape(self.h, self.w, 3)
        R = right.reshape(self.h, self.w, 3)
        floor = math.log(1e-6)
        mel = arrays.get("mel")
        frames = mel.reshape(-1, 40) if mel is not None and mel.size % 40 == 0 and mel.size else np.full((10, 40), floor, np.float32)
        self.heard = np.concatenate([self.heard, frames])[-800:]
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
        cue = meta.get("cue")
        if cue is not None:  # the visitor clicked a thing: the focus goes there at once
            self.target["head_yaw"] = float(np.clip(yaw + float(cue["az"]), -75.0, 75.0))
            self.target["head_pitch"] = float(np.clip(pitch + 0.8 * float(cue["el"]), -25.0, 35.0))
            self.focus = {"az": float(cue["az"]), "el": float(cue["el"]), "why": "you pointed at it"}
            self.hold_until = self.t + int(self.rng.integers(20, 31))
        elif self.t >= self.hold_until:
            if strength > 0.35 and self.rng.random() < 0.8:
                # bring the thing to the middle of the eye that sees it (a parrot looks with one eye)
                turn = az - math.copysign(55.0, az) if abs(az) > 55.0 else az * 0.5
                self.target["head_yaw"] = float(np.clip(yaw + turn, -75.0, 75.0))
                self.target["head_pitch"] = float(np.clip(pitch + 0.6 * el, -25.0, 35.0))
                self.focus = {"az": az, "el": el, "why": "it stood out most"}
            else:
                self.target["head_yaw"] = float(np.clip(yaw + self.rng.choice([-1, 1]) * self.rng.uniform(30, 70), -75.0, 75.0))
                self.target["head_pitch"] = float(self.rng.uniform(-15, 10))
                self.focus = None
            if self.rng.random() < 0.3:
                end = float(self.rng.choice([-1, 1]) * self.rng.uniform(10, 18))
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
        # hearing: the ear follows the bands, Field L their change, NCM holds what was heard
        last = frames[-1]
        ear = np.clip((last - floor) / 18.0, 0, 1)
        change = np.clip(np.abs(frames[-1] - frames[0]) / 6.0, 0, 1)
        self.held = (0.85 * self.held + 0.15 * ear).astype(np.float32)
        # sounds the visitor makes: onset to offset, from the frames' total energy (not while it calls)
        learned, ended = None, False
        for f in frames:
            e = float(np.log(np.exp(f.astype(np.float64)).sum()))
            # the background's level: a low percentile of the last three seconds' frames
            self.levels[self.level_at % len(self.levels)] = e; self.level_at += 1
            seen = self.levels[: min(self.level_at, len(self.levels))]
            self.floor = float(np.percentile(seen, 10)) if len(seen) >= 20 else max(self.floor, e)
            if e < self.floor + 2.0:
                self.noise = np.logaddexp(self.noise + math.log(0.97), f.astype(np.float64) + math.log(0.03))
            if e > self.floor + 4.0 and self.saying <= 0:
                self.sound.append(f); self.quiet = 0
                if len(self.sound) > 250:  # a sound that never ends is the background
                    self.sound = []
                    self.noise = f.astype(np.float64).copy()
            elif self.sound:
                self.quiet += 1
                if self.quiet >= 8:
                    heard = np.asarray(self.sound, np.float32)
                    if self.voice_like(heard)[0]:
                        learned = self.hear_sound(heard) or learned
                        ended = True
                    self.sound = []; self.quiet = 0
        self.mem.moment()
        self.focus_kind = meta.get("focus_kind")
        # the drive to call: quiet time (about a call every two to six seconds), more when a new
        # thing appears or the visitor has just spoken; a call spends it; never over its own sound
        count = meta.get("things")
        if count is not None and self.things is not None and count > self.things:
            self.drive += 0.45
        self.things = count if count is not None else self.things
        self.drive += float(self.rng.uniform(0.012, 0.04)) + (0.4 if ended else 0.0)
        reward = float(meta.get("reward") or 0.0)
        if reward > 0 and self.last_said and self.t - self.last_said[1] < 60:
            self.paid[self.last_said[0]] = self.paid.get(self.last_said[0], 0.0) + reward
        voice, call = None, None
        if meta.get("voice_ok") and self.drive >= 1.0 and self.saying <= 0 and not self.sound:
            pick = self.choose()
            voice = self.say(pick)
            call = {"id": pick["id"], "tag": pick["tag"], "source": pick["source"]}
            self.last_said = (pick["id"], self.t)
            self.saying = int(math.ceil(len(voice) / 10)) + 2
            self.drive = 0.1
        said = np.zeros(40, np.float32)
        if self.saying > 0:
            self.saying -= 1
            said = np.clip(self.rng.random(40).astype(np.float32) * 0.6, 0, 1) if self.saying > 1 else said
        activity[p["ear"]["start"]:p["ear"]["start"] + 40] = ear
        activity[p["fieldl"]["start"]:p["fieldl"]["start"] + 40] = change * ear
        activity[p["ncm"]["start"]:p["ncm"]["start"] + 40] = self.held
        activity[p["voice"]["start"]:p["voice"]["start"] + 40] = said
        self.buffers = {"activity": activity, "targets": targets}
        names = ["activity", "targets"]
        if voice is not None:
            self.buffers["voice"] = voice.ravel()
            names.append("voice")
        return {"buffers": names, "group_activity": {"distance": dist_units.tolist()}, "readout": readout,
                "looked": {"eye": eye, "row": row, "col": col, "strength": round(strength, 3)},
                "focus": self.focus, "heard": bool(ear.max() > 0.35), "newborn": True,
                "drive": round(min(1.0, self.drive), 3), "said": call, "heard_sound": learned,
                "memory": self.mem.view() if (learned is not None or self.t % 10 == 0) else None,
                "repertoire": self.repertoire_list() if learned is not None else None,
                "paid": {k: round(v, 2) for k, v in self.paid.items() if v}}

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        cmd = message.get("command")
        if cmd == "describe":
            return self.describe()
        if cmd == "reset":
            return self.reset()
        if cmd == "silence":
            return self.silence(str(message.get("group")), bool(message.get("on")))
        if cmd == "remember":
            return self.remember(message.get("saved") or {})
        if cmd == "memory":
            return {"memory": self.mem.view(), "saved": self.mem.save()}
        if cmd == "forget":
            return self.forget()
        if cmd == "repertoire":
            return {"repertoire": self.repertoire_list()}
        raise ValueError(f"unknown command {cmd!r}")
