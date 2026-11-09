"""Record a video of the brain playing, from the first frame Simon can move: every NES frame at
60 frames a second, the game large on the left and, on the right, the page's own brain view
(``web/brain.js``) settling on each decision. Frozen and greedy, no search, no cuts.

    python record.py --idle 49 --out docs/castlevania-run.mp4 --log evidence/castlevania-run.json

Needs your ROM imported (``python -m simon.rom``), ffmpeg (H.264), and Playwright's Chromium
(``pip install playwright && playwright install chromium``): the frames are drawn by
``web/render.html`` in a headless browser, so the video shows exactly what the page draws.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path

from server import png, thumbnail
from simon.console import Console
from simon.player import BRAIN, Player, load_brain, populations
from simon.pad import readings

HERE = Path(__file__).resolve().parent
SETTLE_FRAMES = 9  # the settle is played over the first 9 of a decision's 12 frames


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--idle", type=int, default=49, help="decisions of nothing after the start screen")
    p.add_argument("--decisions", type=int, default=1500)
    p.add_argument("--out", type=Path, default=Path("docs/castlevania-run.mp4"))
    p.add_argument("--log", type=Path, default=None, help="per-decision readings as JSON")
    p.add_argument("--crf", type=int, default=30)
    a = p.parse_args()
    import cadence
    from playwright.sync_api import sync_playwright
    caption = (f"Cadence brain, cadence-net {cadence.__version__}, playing frozen: no search, no cuts. "
               f"Start after {a.idle} idle decision{'s' if a.idle != 1 else ''}. No ROM included.")
    player = Player(load_brain(BRAIN), populations(BRAIN))
    console = Console()
    frame, ram = console.power_on(a.idle)
    player.new_game()
    import shutil
    exe = shutil.which("ffmpeg")
    if exe is None:  # the static ffmpeg of the imageio-ffmpeg wheel, where none is installed
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg = subprocess.Popen(
        [exe, "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-r", "60", "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(a.out)], stdin=subprocess.PIPE)
    log, frames, lives = [], 0, readings(ram)["lives"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto((HERE / "web" / "render.html").as_uri())
        page.wait_for_function("window.ready === true")

        def emit(game, phase, extra):
            nonlocal frames
            url = page.evaluate("([g, p, c, cap, e]) => renderFrame(g, p, c, cap, e)",
                                [base64.b64encode(png(game[8:232, 8:248])).decode(), phase,
                                 frames * 1000 / 60, caption, extra])
            ffmpeg.stdin.write(base64.b64decode(url.split(",", 1)[1]))
            frames += 1

        for t in range(a.decisions):
            action = player.decide(frame, ram, thumb=thumbnail(frame))
            snap = player.snapshot()
            page.evaluate("s => setSnap(s)", snap)
            g = snap["game"]
            extra = (f"stage {g['stage']}   block {g['block']}   world x {g['world_x']}   health {g['health']}   "
                     f"lives {g['lives']}   decision {snap['decisions']}   {snap['sweeps']} sweeps")
            done = False
            for k, (frame, done) in enumerate(console.frames(action)):
                emit(frame, min(1.0, (k + 1) / SETTLE_FRAMES), extra)
            ram = console.ram()
            g = readings(ram)
            log.append({"decision": t, "frame": frames, "second": round(frames / 60, 2), "stage": g["stage"],
                        "block": g["block"], "world_x": g["world_x"], "y": g["y"], "health": g["health"],
                        "lives": g["lives"], "buttons": snap["buttons"], "died": g["lives"] < lives})
            lives = g["lives"]
            if done or g["lives"] == 0:
                break
        for _ in range(120):  # two seconds on the last frame
            emit(frame, None, "game over")
        browser.close()
    ffmpeg.stdin.close()
    ffmpeg.wait()
    if a.log is not None:
        a.log.write_text(json.dumps({"idle": a.idle, "frames": frames, "decisions": len(log), "log": log}) + "\n")
    print(json.dumps({"out": str(a.out), "frames": frames, "seconds": round(frames / 60, 1), "decisions": len(log)}))


if __name__ == "__main__":
    main()
