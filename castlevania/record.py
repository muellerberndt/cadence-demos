"""Record a video of the brain playing, from the first frame Simon can move: every NES frame at
60 frames a second, the game large on the left, the brain's eye, answer and settled regions on
the right, as the page draws them. Frozen and greedy, no search, no cuts.

    python record.py --idle 1 --out docs/castlevania-run.mp4 --log docs/castlevania-run.json

Needs ffmpeg (H.264) and Pillow, and your ROM imported (``python -m simon.rom``).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from simon.console import Console
from simon.player import BRAIN, Player, load_brain, populations
from simon.pad import readings

W, H = 1280, 720
GAME_X, GAME_Y, SCALE = 16, 10, 3  # the core's 240 x 224 picture at 3x: 720 x 672
PANEL_X = 752
BG, PANEL, LINE, TEXT, DIM, RED, BLUE, GOLD = ((13, 11, 16), (23, 19, 28), (44, 36, 51), (233, 227, 238),
                                               (156, 144, 168), (224, 68, 79), (79, 163, 224), (242, 193, 78))
STATES = ["ground", "jump", "whip", "crouch", "stairs", "knocked back", "onto stairs", "falling", "other", "recovering"]
SLOT_NAMES = [("horizontal", ["left", "-", "right"]), ("vertical", ["up", "-", "down"]),
              ("whip", ["no", "yes"]), ("jump", ["no", "yes"])]


def font(size: int, bold: bool = False):
    for path in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else []) + [
            "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_SMALL, F_TEXT, F_HEAD = font(13), font(15), font(14, bold=True)


def gray_map(values, w, h, scale, lo=-0.6, hi=0.6) -> Image.Image:
    v = np.clip((np.asarray(values, float).reshape(h, w) - lo) / (hi - lo), 0, 1)
    img = (np.repeat(v[:, :, None], 3, axis=2) * 255).astype(np.uint8)
    return Image.fromarray(img).resize((w * scale, h * scale), Image.NEAREST)


def signed_map(values, w, h, scale) -> Image.Image:
    a = np.clip(np.asarray(values, float).reshape(h, w) * 2, -1, 1)
    img = np.stack([40 + 215 * np.clip(a, 0, 1), 40 + 60 * np.abs(a), 40 + 215 * np.clip(-a, 0, 1)], axis=2)
    return Image.fromarray(img.astype(np.uint8)).resize((w * scale, h * scale), Image.NEAREST)


def activity_map(values, w, h, scale) -> Image.Image:
    t = np.clip((np.asarray(values, float)[: w * h].reshape(h, w) + 0.1) / 1.1, 0, 1)
    img = np.stack([30 + 212 * t, 20 + 173 * t * t, 40 + 38 * t], axis=2)
    return Image.fromarray(img.astype(np.uint8)).resize((w * scale, h * scale), Image.NEAREST)


def panel(snap: dict, caption: str) -> Image.Image:
    """The right-hand panel for one decision."""
    img = Image.new("RGB", (W - PANEL_X - 16, 224 * SCALE), BG)
    d = ImageDraw.Draw(img)
    y = 0
    d.text((0, y), "WHAT THE EYE SEES", fill=DIM, font=F_HEAD)
    y += 22
    eye = snap["eye"]
    maps = [("scene", gray_map(eye["scene"], 16, 12, 7)), ("motion", signed_map(eye["motion"], 16, 12, 7)),
            ("fovea ahead", gray_map(eye["ahead"], 16, 12, 7)), ("fovea behind", gray_map(eye["behind"], 16, 12, 7))]
    for k, (name, m) in enumerate(maps):
        x = k * 124
        img.paste(m, (x, y))
        d.text((x, y + 88), name, fill=DIM, font=F_SMALL)
    y += 110
    hot = lambda v: int(np.argmax(v))  # noqa: E731
    d.text((0, y), f"stage {hot(eye['stage'])}   block {hot(eye['block'])}   body {STATES[hot(eye['state'])]}   "
                   f"floor {hot(eye['floor'])}", fill=TEXT, font=F_TEXT)
    y += 34
    d.text((0, y), "THE ANSWER", fill=DIM, font=F_HEAD)
    d.text((110, y), f"{snap.get('sweeps', '?')} sweeps", fill=DIM, font=F_SMALL)
    y += 22
    chosen = [snap["act"][0] + 1, snap["act"][1] + 1, snap["act"][2], snap["act"][3]]
    for k, vals in enumerate(snap["slots"]):
        name, labels = SLOT_NAMES[k]
        d.text((0, y + 3), name, fill=DIM, font=F_SMALL)
        lo, hi = min(min(vals), -0.1), max(max(vals), 1.0)
        width = (img.width - 90 - 6 * (len(vals) - 1)) // len(vals)
        for j, v in enumerate(vals):
            x0 = 90 + j * (width + 6)
            d.rectangle((x0, y, x0 + width, y + 20), fill=(34, 28, 40))
            fill = int(width * (v - lo) / (hi - lo))
            d.rectangle((x0, y, x0 + max(fill, 1), y + 20), fill=RED if j == chosen[k] else (91, 74, 104))
            d.text((x0 + 5, y + 3), labels[j], fill=TEXT, font=F_SMALL)
        y += 26
    y += 12
    d.text((0, y), "THE SETTLED BRAIN", fill=DIM, font=F_HEAD)
    y += 22
    regions = snap["regions"]
    x = 0
    for name, w, h in (("module_0", 16, 16, ), ("association", 16, 8), ("prefrontal", 16, 8)):
        if name in regions:
            m = activity_map(regions[name], w, h, 7)
            img.paste(m, (x, y))
            d.text((x, y + m.height + 3), f"{name.replace('_', ' ')} ({len(regions[name])})", fill=DIM, font=F_SMALL)
            x += m.width + 18
    y += 112 + 26
    mem = snap.get("memory") or {}
    if mem:
        d.text((0, y), f"recall memory: {mem.get('held', 0)} of {mem.get('capacity', 0)} slots hold moments of this game",
               fill=DIM, font=F_SMALL)
        y += 22
    g = snap["game"]
    d.text((0, y), f"stage {g['stage']}   world x {g['world_x']}   health {g['health']}   lives {g['lives']}   "
                   f"decision {snap['decisions']}", fill=TEXT, font=F_TEXT)
    return img


def compose(frame: np.ndarray, snap: dict | None, side: Image.Image | None, caption: str = "") -> bytes:
    canvas = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(canvas).text((GAME_X, GAME_Y + 224 * SCALE + 10), caption, fill=DIM, font=F_TEXT)
    game = Image.fromarray(frame[8:232, 8:248]).resize((240 * SCALE, 224 * SCALE), Image.NEAREST)
    canvas.paste(game, (GAME_X, GAME_Y))
    if snap is not None:
        d = ImageDraw.Draw(canvas)
        f = snap["fovea"]
        box = lambda l, r, c: d.rectangle(  # noqa: E731
            (GAME_X + (l - 8) * SCALE, GAME_Y + (f["top"] - 8) * SCALE, GAME_X + (r - 8) * SCALE,
             GAME_Y + (f["bottom"] - 8) * SCALE), outline=c, width=2)
        shift = -32 if f["facing"] > 0 else 32
        box(f["left"] + shift, f["right"] + shift, BLUE)
        box(f["left"], f["right"], RED)
    if side is not None:
        canvas.paste(side, (PANEL_X, 8))
    return canvas.tobytes()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--idle", type=int, default=1, help="decisions of nothing after the start screen")
    p.add_argument("--decisions", type=int, default=1500)
    p.add_argument("--out", type=Path, default=Path("docs/castlevania-run.mp4"))
    p.add_argument("--log", type=Path, default=None, help="per-decision readings as JSON")
    p.add_argument("--crf", type=int, default=30)
    a = p.parse_args()
    import cadence
    caption = (f"Cadence brain, cadence-net {cadence.__version__}, playing frozen: no search, no cuts. "
               f"Start after {a.idle} idle decision{'s' if a.idle != 1 else ''}. No ROM included.")
    player = Player(load_brain(BRAIN), populations(BRAIN))
    console = Console()
    frame, ram = console.power_on(a.idle)
    player.new_game()
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", "60", "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)], stdin=subprocess.PIPE)
    log, frames, lives = [], 0, readings(ram)["lives"]
    for t in range(a.decisions):
        action = player.decide(frame, ram)
        snap = player.snapshot()
        side = panel(snap, caption)
        done = False
        for frame, done in console.frames(action):
            ffmpeg.stdin.write(compose(frame, snap, side, caption))
            frames += 1
        ram = console.ram()
        g = readings(ram)
        log.append({"decision": t, "frame": frames, "second": round(frames / 60, 2), "stage": g["stage"],
                    "block": g["block"], "world_x": g["world_x"], "y": g["y"], "health": g["health"],
                    "lives": g["lives"], "buttons": snap["buttons"], "died": g["lives"] < lives})
        lives = g["lives"]
        if done or g["lives"] == 0:
            break
    for _ in range(120):  # two seconds on the last frame
        ffmpeg.stdin.write(compose(frame, None, side, caption))
        frames += 1
    ffmpeg.stdin.close()
    ffmpeg.wait()
    if a.log is not None:
        a.log.write_text(json.dumps({"idle": a.idle, "frames": frames, "decisions": len(log), "log": log}) + "\n")
    print(json.dumps({"out": str(a.out), "frames": frames, "seconds": round(frames / 60, 1), "decisions": len(log)}))


if __name__ == "__main__":
    main()
