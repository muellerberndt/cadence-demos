"""Watch the brain play, beside its brain view: the five-life gauntlet from 1-1, or one level.

    python play.py                          # the gauntlet in a window, at the game's speed
    python play.py --level 1-3 --idle 110   # one attempt
    python play.py --video gauntlet.mp4     # write a video instead (needs imageio-ffmpeg)
    python play.py --speed 4                # 1 = the game's speed, 0 = as fast as the brain answers
    python play.py --no-view                # the game alone

Every button is the brain's. It plays frozen: nothing is learned while you watch. Run
`python -m smb.rom <your dump>` first.
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message=".*Gym has been unmaintained.*")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from smb.eye import ACTION_NAMES  # noqa: E402
from smb.player import attempt, gauntlet  # noqa: E402
from smb.rom import ROM  # noqa: E402

BRAIN = HERE / "brain" / "brain.npz"
GAME_W, GAME_H, BAR = 512, 480, 40


class Screen:
    """Composes each frame: a status bar and the game on the left, the brain view on the right."""

    def __init__(self, view):
        from PIL import ImageFont
        self.view, self.panel, self.status = view, None, "loading the brain"
        try:
            self.font = ImageFont.load_default(size=15)
        except TypeError:
            self.font = ImageFont.load_default()

    def on_attempt(self, level, tries, lives):
        self.status = f"{level}   try {tries}   lives {lives}"

    def on_decision(self, obs, action):
        if self.view:
            self.panel = self.view.draw(self.view.settle(obs, action))

    def frame(self, screen, action) -> np.ndarray:
        from PIL import Image, ImageDraw
        from smb.view import W
        width = GAME_W + (W if self.view else 0)
        img = Image.new("RGB", (width, GAME_H + BAR), (16, 18, 22))
        img.paste(Image.fromarray(screen).resize((GAME_W, GAME_H), Image.NEAREST), (0, BAR))
        ImageDraw.Draw(img).text((10, 12), f"{self.status}   brain: {ACTION_NAMES[action]}", fill=(235, 235, 235), font=self.font)
        if self.panel is not None:
            img.paste(self.panel, (GAME_W, 0))
        return np.asarray(img)


def run(a, screen_cb, scr: Screen):
    from cadence import Brain
    brain = Brain.load(str(BRAIN), backend="cpu")
    if not a.no_view:
        from smb.view import BrainView
        scr.view = BrainView(brain)
    if a.level:
        scr.on_attempt(a.level, 1, 1)
        log = [attempt(brain, ROM, a.level, a.idle, on_frame=screen_cb, on_decision=scr.on_decision)]
    else:
        log = gauntlet(brain, ROM, on_frame=screen_cb, on_attempt=scr.on_attempt, on_decision=scr.on_decision)
    for e in log:
        print(f"{e['level']} idle {e['idle']}: {e['end']} at x {e['x']} after {e['decisions']} decisions", flush=True)
    if scr.view:
        print(f"brain view agreed with the played answer on {scr.view.agree} of {scr.view.decisions} decisions", flush=True)
    if a.log:
        Path(a.log).write_text(json.dumps(log, indent=1))
    return log


def video(a, scr: Screen):
    import imageio_ffmpeg
    w = None

    def on_frame(screen, action):
        nonlocal w
        f = np.ascontiguousarray(scr.frame(screen, action))
        if w is None:
            w = imageio_ffmpeg.write_frames(a.video, (f.shape[1], f.shape[0]), fps=60, codec="libx264",
                                            pix_fmt_out="yuv420p", output_params=["-crf", "26", "-movflags", "+faststart"],
                                            macro_block_size=8)
            w.send(None)
        w.send(f)

    run(a, on_frame, scr)
    if w is not None:
        w.close()


def window(a, scr: Screen):
    import tkinter as tk
    q: queue.Queue = queue.Queue(maxsize=4)
    period = 0 if a.speed == 0 else 1 / (60 * a.speed)
    last = [time.perf_counter()]

    def on_frame(screen, action):
        q.put(scr.frame(screen, action))
        if period:  # hold the game's pace: sleep only what is left of this frame's time
            last[0] = max(last[0] + period, time.perf_counter() - period)
            time.sleep(max(0.0, last[0] - time.perf_counter()))

    def worker():
        run(a, on_frame, scr)
        q.put(None)

    root = tk.Tk(); root.title("Cadence plays Super Mario Bros.")
    label = tk.Label(root); label.pack()
    keep = {}

    def poll():
        try:
            item = q.get_nowait()
        except queue.Empty:
            root.after(5, poll); return
        if item is None:
            root.title("Cadence plays Super Mario Bros. (done)"); return
        h, w = item.shape[:2]
        img = tk.PhotoImage(data=f"P6 {w} {h} 255 ".encode() + item.tobytes(), format="PPM")
        keep["img"] = img; label.config(image=img)
        root.after(1, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(5, poll); root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", help="one attempt at this level (e.g. 1-3) instead of the gauntlet")
    ap.add_argument("--idle", type=int, default=0, help="idle frames before the first decision (with --level)")
    ap.add_argument("--video", help="write an mp4 here instead of opening a window")
    ap.add_argument("--speed", type=float, default=1.0, help="1 = the game's speed, 0 = as fast as possible")
    ap.add_argument("--no-view", action="store_true", help="the game alone, without the brain view")
    ap.add_argument("--log", help="write the attempts as JSON here")
    a = ap.parse_args()
    if not ROM.exists():
        sys.exit("No ROM yet: run `python -m smb.rom <your Super Mario Bros. dump or a folder>` first.")
    scr = Screen(None)
    video(a, scr) if a.video else window(a, scr)


if __name__ == "__main__":
    main()
