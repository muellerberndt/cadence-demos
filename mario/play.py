"""Watch the brain play: the five-life gauntlet from 1-1, or one level.

    python play.py                          # the gauntlet in a window, at the game's speed
    python play.py --level 1-3 --idle 110   # one attempt
    python play.py --video gauntlet.mp4     # write a video instead (needs imageio-ffmpeg and Pillow)
    python play.py --speed 4                # 1 = the game's speed, 0 = as fast as the brain answers

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

warnings.filterwarnings("ignore", message=".*Gym has been unmaintained.*")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from smb.eye import ACTION_NAMES  # noqa: E402
from smb.player import attempt, gauntlet  # noqa: E402
from smb.rom import ROM  # noqa: E402

BRAIN = HERE / "brain" / "brain.npz"


def run(a, on_frame, on_attempt):
    from cadence import Brain
    brain = Brain.load(str(BRAIN), backend="cpu")
    if a.level:
        if on_attempt:
            on_attempt(a.level, 1, 1)
        log = [attempt(brain, ROM, a.level, a.idle, on_frame=on_frame)]
    else:
        log = gauntlet(brain, ROM, on_frame=on_frame, on_attempt=on_attempt)
    for e in log:
        print(f"{e['level']} idle {e['idle']}: {e['end']} at x {e['x']} after {e['decisions']} decisions", flush=True)
    if a.log:
        Path(a.log).write_text(json.dumps(log, indent=1))
    return log


def video(a):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw
    w = imageio_ffmpeg.write_frames(a.video, (512, 520), fps=60, codec="libx264", pix_fmt_out="yuv420p",
                                    output_params=["-crf", "26", "-movflags", "+faststart"], macro_block_size=8)
    w.send(None)
    status = {"text": ""}

    def on_attempt(level, tries, lives):
        status["text"] = f"{level}  try {tries}  lives {lives}"

    def on_frame(screen, action):
        img = Image.new("RGB", (512, 520), (20, 20, 20))
        img.paste(Image.fromarray(screen).resize((512, 480), Image.NEAREST), (0, 40))
        ImageDraw.Draw(img).text((8, 12), f"{status['text']}   brain: {ACTION_NAMES[action]}", fill=(255, 255, 255))
        w.send(np.ascontiguousarray(np.asarray(img)))

    run(a, on_frame, on_attempt)
    w.close()


def window(a):
    import tkinter as tk
    q: queue.Queue = queue.Queue(maxsize=4)
    status = {"text": "loading the brain"}
    period = 0 if a.speed == 0 else 1 / (60 * a.speed)

    def on_attempt(level, tries, lives):
        status["text"] = f"{level}  try {tries}  lives {lives}"

    def on_frame(screen, action):
        q.put((screen, f"{status['text']}   brain: {ACTION_NAMES[action]}"))
        if period:
            time.sleep(period)

    def worker():
        run(a, on_frame, on_attempt)
        q.put(None)

    root = tk.Tk(); root.title("Cadence plays Super Mario Bros.")
    label = tk.Label(root, font=("Courier", 12), anchor="w"); label.pack(fill="x")
    canvas = tk.Label(root); canvas.pack()
    keep = {}

    def poll():
        try:
            item = q.get_nowait()
        except queue.Empty:
            root.after(5, poll); return
        if item is None:
            label.config(text=label.cget("text") + "   (done)"); return
        screen, text = item
        img = tk.PhotoImage(data=b"P6 256 240 255 " + screen.tobytes(), format="PPM").zoom(2)
        keep["img"] = img; canvas.config(image=img); label.config(text=text)
        root.after(1, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(5, poll); root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", help="one attempt at this level (e.g. 1-3) instead of the gauntlet")
    ap.add_argument("--idle", type=int, default=0, help="idle frames before the first decision (with --level)")
    ap.add_argument("--video", help="write an mp4 here instead of opening a window")
    ap.add_argument("--speed", type=float, default=1.0, help="1 = the game's speed, 0 = as fast as possible")
    ap.add_argument("--log", help="write the attempts as JSON here")
    a = ap.parse_args()
    if not ROM.exists():
        sys.exit("No ROM yet: run `python -m smb.rom <your Super Mario Bros. dump or a folder>` first.")
    video(a) if a.video else window(a)


if __name__ == "__main__":
    main()
