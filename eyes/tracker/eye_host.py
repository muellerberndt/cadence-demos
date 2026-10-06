"""The brain host of the in-browser page: pixels in, answers out.

The page draws the surface and hands this host its pixels every frame; the host keeps the
brain and the eyes. Nothing else reaches the brain: an eye is opened where the player points,
and from then on it sees only its window of the page's pixels. The same class runs natively in
the tests and in Pyodide in the page's worker.

Messages are JSON: ``{"op": "open", "id", "x", "y"}``, ``{"op": "close", "id"}``,
``{"op": "reset"}``, ``{"op": "select", "id"}``, ``{"op": "describe"}``. ``see`` takes the
pixels (a float32 buffer of height × width) and returns a JSON string.

The eye is a window eye (``tracker.eyes``) or a foveated eye (``tracker.fovea``), as the pack
declares. A frame in which no eye's input changed is not settled again: from its qualified
state the brain would pass the residual check at zero sweeps with the same answers.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import numpy as np
from cadence import Brain

from .eyes import Eyes
from .fovea import Fovea, FovealEyes


def fit_32_bit_numpy() -> bool:
    """Pyodide's numpy is 32-bit: its index type is int32. Cadence 0.74.0 sets up a learner
    with several slots by ``np.repeat(..., slot_sizes)`` on int64 sizes, which a 32-bit numpy
    refuses to cast. The library's learning module gets a numpy whose ``repeat`` casts the
    counts to the index type; every other call is numpy's own. Nothing changes on 64 bits."""
    if np.dtype(np.intp).itemsize >= 8:
        return False
    import types

    import cadence.learning as learning

    shim = types.ModuleType("numpy")
    shim.__dict__.update(np.__dict__)
    shim.repeat = lambda a, repeats, axis=None: np.repeat(
        a, np.asarray(repeats).astype(np.intp), axis=axis)
    learning.np = shim
    return True


class Host:
    def __init__(self, path: str, window: int, bins: int, width: int, height: int,
                 eye: str = "window", fovea: dict | None = None) -> None:
        self.shimmed = fit_32_bit_numpy()
        self.brain = Brain.load(path)
        self.brain.reset()
        if eye == "fovea":
            f = dict(fovea or {})
            gain = float(f.pop("change_gain", 1.0))
            self.eyes = FovealEyes(self.brain, Fovea(**f), width, height, gain)
        else:
            self.eyes = Eyes(self.brain, window, bins, width, height)
        self.eye = eye
        self.width, self.height = width, height
        self.selected: int | None = None
        self.frames = 0
        self.last_inputs: np.ndarray | None = None
        self.last_out: dict[str, Any] | None = None

    def handle_json(self, text: str) -> str:
        msg = json.loads(text)
        op = msg.get("op")
        if op == "open":
            self.eyes.open(int(msg["id"]), float(msg["x"]), float(msg["y"]))
            if self.selected is None:
                self.selected = int(msg["id"])
        elif op == "close":
            self.eyes.close(int(msg["id"]))
            if self.selected == int(msg["id"]):
                self.selected = next(iter(self.eyes.gaze), None)
        elif op == "select":
            self.selected = int(msg["id"])
        elif op == "reset":
            for eid in list(self.eyes.gaze):
                self.eyes.close(eid)
            self.brain.reset()
            self.eyes.streams = []
            self.selected = None
            self.last_out = self.last_inputs = None
        elif op == "describe":
            c = self.brain.connectome
            out = {"neurons": int(c.n), "synapses": int(c.synapses), "eye": self.eye}
            if self.eye == "fovea":
                fv = self.eyes.fovea
                out.update(receptors=fv.receptors, bins=fv.bins, middle=fv.middle, reach=fv.reach,
                           edges=[float(v) for v in fv.edges],
                           bin_of_receptor=[int(v) for v in fv.bin_of_receptor],
                           bin_offset=[float(v) for v in fv.bin_offset],
                           bin_lo=[float(v) for v in fv.bin_lo], bin_hi=[float(v) for v in fv.bin_hi])
            else:
                out.update(window=self.eyes.retina.window, bins=self.eyes.retina.bins)
            return json.dumps(out)
        else:
            return json.dumps({"error": f"unknown op {op!r}"})
        return json.dumps({"ok": True, "eyes": len(self.eyes.gaze)})

    def settle(self, surface: np.ndarray) -> dict[str, Any]:
        """Every eye's frame; an unchanged input keeps its equilibrium and its answers."""
        eyes = self.eyes
        ids = list(eyes.gaze)
        if self.last_out is not None and ids == eyes.streams and ids:
            if self.eye == "fovea":
                fv = eyes.fovea
                change = np.zeros_like(surface) if eyes.previous is None or eyes.previous.shape != surface.shape \
                    else np.abs(surface - eyes.previous)
                bright, moved = fv.integral(surface), fv.integral(eyes.change_gain * change, 0.0)
                x = np.stack([fv.see(bright, moved, *eyes.gaze[i]) for i in ids])
            else:
                x = np.stack([eyes.window(surface, *eyes.gaze[i]) for i in ids]).reshape(len(ids), -1)
            if self.last_inputs is not None and x.shape == self.last_inputs.shape \
                    and np.array_equal(x, self.last_inputs):
                if self.eye == "fovea":
                    eyes.previous = surface.copy()
                held = dict(self.last_out)
                held["eyes"] = [{**e, "gaze": list(eyes.gaze[e["id"]]), "next": list(eyes.gaze[e["id"]])}
                                for e in self.last_out["eyes"]]
                held.update(sweeps=0, ms=0.0, held=True)
                return held
        seen = eyes.see(surface)
        self.last_inputs = None if seen["x"] is None else np.array(seen["x"])
        self.last_out = seen
        return seen

    def see(self, pixels: Any) -> str:
        """One frame: the page's pixels in, every eye's answer and next gaze out."""
        if isinstance(pixels, np.ndarray):
            surface = pixels.astype(np.float32)
        elif hasattr(pixels, "to_bytes"):  # a JavaScript Float32Array inside Pyodide
            surface = np.frombuffer(pixels.to_bytes(), dtype=np.float32)
        else:
            surface = np.frombuffer(bytes(pixels), dtype=np.float32)
        surface = surface.reshape(self.height, self.width).astype(float)
        seen = self.settle(surface)
        self.frames += 1
        out: dict[str, Any] = {"frame": self.frames, "sweeps": seen["sweeps"], "ms": seen["ms"],
                               "eyes": seen["eyes"]}
        state = seen["state"]
        ids = [e["id"] for e in seen["eyes"]]
        if state is not None and ids:
            sel = ids.index(self.selected) if self.selected in ids else 0
            a = np.asarray(state.activation)[sel]
            act8 = np.clip(np.round((np.clip(a, -0.1, 1.0) + 0.1) / 1.1 * 255), 0, 255).astype(np.uint8)
            out["selected"] = ids[sel]
            out["activity"] = base64.b64encode(act8.tobytes()).decode()
            if self.eye == "fovea":
                r = self.eyes.fovea.receptors
                x = np.asarray(seen["x"]).reshape(len(ids), 2, r, r)
                win, change = x[:, 0], x[:, 1]
                out["changes"] = [base64.b64encode((np.clip(c, 0, 1) * 255).astype(np.uint8).tobytes()).decode()
                                  for c in change]
            else:
                win = np.asarray(seen["inputs"])
            win = (np.clip(win, 0, 1) * 255).astype(np.uint8)
            out["windows"] = [base64.b64encode(w.tobytes()).decode() for w in win]
        if seen.get("held"):
            out["held"] = True
        return json.dumps(out)
