"""The brain view: what the brain sees and how it settles, beside the game.

Every decision the brain answers with `Brain.predict` as it plays. For the view, the same
observation is settled a second time inside `cadence.recording.record_settlements`, which records
every neuron at every sweep of the settle. The recorder runs the library's NumPy path, which can
differ from the played settle at round-off, so the played answer never comes from the recording;
the view counts how often the two agree (`agree`, shown on the panel).

The panel, top to bottom:
- **Eye**: the two grey maps the brain gets (this decision and the last), 26 x 32 blocks each.
- **Body**: the 42 body readings (speeds, float state, facing, power, timers, held buttons).
- **Association**: the 256 neurons of the one module, settled, 16 x 16; warm = active.
- **Prefrontal**: the composed working-memory region; `predict` does not read it, so it stays dark.
- **Buttons**: the 7 motor neurons at the end of the settle, the pressed one marked; the settle's
  sweep count.
"""
from __future__ import annotations

import numpy as np

from .eye import ACTION_NAMES, COLS, N_BODY, ROWS

W, H = 400, 520  # panel size (the game is drawn 512 x 480 beside it)
BG, INK, DIM, MARK = (16, 18, 22), (225, 228, 232), (120, 126, 134), (255, 196, 0)


def _heat(v: np.ndarray, lo: float = -0.1, hi: float = 1.0) -> np.ndarray:
    """Activations -> RGB: dark blue (quiet) through teal to warm yellow (active)."""
    t = np.clip((np.asarray(v, np.float32) - lo) / (hi - lo), 0, 1)[..., None]
    a, b, c = np.array([18, 22, 48]), np.array([0, 150, 160]), np.array([255, 210, 60])
    return np.where(t < 0.5, a + (b - a) * (t / 0.5), b + (c - b) * ((t - 0.5) / 0.5)).astype(np.uint8)


class BrainView:
    def __init__(self, brain):
        from PIL import ImageFont
        self.brain = brain
        self.idx = {k: np.asarray(getattr(brain, f"{k}_index")) for k in ("sensory", "association", "prefrontal", "motor")}
        self.decisions = self.agree = 0
        try:
            self.font = ImageFont.load_default(size=13)
        except TypeError:
            self.font = ImageFont.load_default()

    def settle(self, obs: np.ndarray, played: int) -> dict:
        """Settle obs again under the recorder; return the final state and the sweep count."""
        from cadence.recording import record_settlements
        recs = []
        with record_settlements(recs.append, label="view"):
            seen = int(np.asarray(self.brain.predict(obs[None])).reshape(-1)[0])
        r = max(recs, key=lambda r: r.steps)  # the real settle (a zero-step check comes first)
        final = np.asarray(r.activation)[-1, 0, :]
        self.decisions += 1
        self.agree += seen == played
        return dict(final=final, steps=int(r.steps), played=played, obs=obs)

    def draw(self, s: dict):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        f, i, y = self.font, self.idx, 8
        # eye: the two grey maps as the brain gets them
        d.text((10, y), "eye: now | last decision", fill=DIM, font=f); y += 18
        n = ROWS * COLS
        for k, x0 in ((0, 10), (1, 205)):
            m = (np.clip(2 * s["obs"][k * n:(k + 1) * n].reshape(ROWS, COLS), 0, 1) * 255).astype(np.uint8)
            img.paste(Image.fromarray(m).resize((COLS * 5, ROWS * 5), Image.NEAREST), (x0, y))
        y += ROWS * 5 + 10
        # body readings (first copy of the 42)
        d.text((10, y), "body: speed, air, facing, power, timers, held", fill=DIM, font=f); y += 18
        body = s["obs"][2 * n:2 * n + N_BODY]
        for k, v in enumerate(body):
            c = _heat(v, 0, 1)
            d.rectangle([10 + k * 9, y, 10 + k * 9 + 7, y + 14], fill=tuple(int(u) for u in c))
        y += 26
        # association and prefrontal, 16 x 16 each
        d.text((10, y), "association (256)", fill=DIM, font=f)
        d.text((205, y), "prefrontal (not read)", fill=DIM, font=f); y += 18
        for k, x0 in (("association", 10), ("prefrontal", 205)):
            g = _heat(s["final"][i[k]].reshape(16, 16))
            img.paste(Image.fromarray(g).resize((128, 128), Image.NEAREST), (x0, y))
        y += 138
        # buttons
        d.text((10, y), f"buttons (settled in {s['steps']} sweeps)", fill=DIM, font=f); y += 18
        motor = s["final"][i["motor"]]  # activations in [-0.1, 1], drawn on that scale
        for k, name in enumerate(ACTION_NAMES):
            yy = y + k * 16
            on = k == s["played"]
            d.text((10, yy), name, fill=MARK if on else INK, font=f)
            w = int(220 * np.clip((float(motor[k]) + 0.1) / 1.1, 0, 1))
            d.rectangle([100, yy + 2, 100 + w, yy + 12], fill=MARK if on else (70, 110, 150))
        y += 7 * 16 + 6
        d.text((10, y), f"view agrees with play: {self.agree} of {self.decisions}", fill=DIM, font=f)
        return img
