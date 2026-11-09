"""Record a video of the brain playing, from the first frame Simon can move: every NES frame at
60 frames a second, the game large on the left and, on the right, the page's own brain view
(``web/brain.js``) settling on each decision. Frozen and greedy, no search, no cuts.

    python record.py --idle 42 --out docs/castlevania-brain-alone-run.mp4 --log evidence/castlevania-brain-alone-run.json
    python record.py --lookahead --idle 21 --out docs/castlevania-run.mp4 --log evidence/castlevania-run.json

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
SWEEP_STRIDE = 2  # the trace keeps every second sweep of the settle (and the last)


def trace_record(snap: dict, x, frame: int, thumb: str) -> dict:
    """One decision for the player page: the first video frame it covers, the exact eye input
    (float64, so live mode can settle on it bit for bit), the snapshot without what the page can
    rebuild from the input, and the frame the decision saw (the recall view's thumbnails)."""
    import numpy as np
    s = dict(snap)
    t = dict(s["trajectory"])
    keep = lambda seq: seq[::SWEEP_STRIDE] + ([seq[-1]] if (len(seq) - 1) % SWEEP_STRIDE else [])  # noqa: E731
    t["regions"] = {k: keep(v) for k, v in t["regions"].items()}
    s["trajectory"] = t
    for key in ("eye", "regions"):
        s.pop(key, None)
    if s.get("memory"):
        s["memory"] = dict(s["memory"])
        s["memory"]["top"] = [{k: v for k, v in top.items() if k != "thumb"} for top in s["memory"]["top"]]
        s["memory"]["weights"] = [round(w, 2) for w in s["memory"]["weights"]]
    return {"frame": frame, "x": base64.b64encode(np.asarray(x, "<f8").tobytes()).decode(), "snap": s, "thumb": thumb}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--idle", type=int, default=49, help="decisions of nothing after the start screen")
    p.add_argument("--decisions", type=int, default=1500)
    p.add_argument("--out", type=Path, default=Path("docs/castlevania-brain-alone-run.mp4"))
    p.add_argument("--log", type=Path, default=None, help="per-decision readings as JSON")
    p.add_argument("--crf", type=int, default=30)
    p.add_argument("--scale", type=int, default=1, help="2: draw the frames natively at 2560 x 1440")
    p.add_argument("--trace", type=Path, default=None, help="the player page's trace (gzip JSON)")
    p.add_argument("--game-video", type=Path, default=None, help="the game alone at 3x, for the player page")
    p.add_argument("--lookahead", action="store_true",
                   help="brain + look-ahead over the emulator's savestates (simon/lookahead.py); overruled decisions amber")
    a = p.parse_args()
    import cadence
    from playwright.sync_api import sync_playwright
    caption = (f"Cadence brain, cadence-net {cadence.__version__}, playing frozen: no search, no cuts. "
               f"Start after {a.idle} idle decision{'s' if a.idle != 1 else ''}. No ROM included.")
    player = Player(load_brain(BRAIN), populations(BRAIN))
    console = Console()
    if a.lookahead:
        from simon.lookahead import LABEL, Lookahead
        player.look, player.console = Lookahead(), console
        caption = (f"{LABEL}, cadence-net {cadence.__version__}\n"
                   f"Amber: look-ahead overruled the brain · teal: route recovery · no cuts · "
                   f"start after {a.idle} idle decision{'s' if a.idle != 1 else ''} · no ROM included")
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
    game_pipe = None
    if a.game_video is not None:
        game_pipe = subprocess.Popen(
            [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "720x672", "-r", "60",
             "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(a.game_video)], stdin=subprocess.PIPE)
    trace = []
    log, frames, lives = [], 0, readings(ram)["lives"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280 * a.scale, "height": 720 * a.scale})
        page.goto((HERE / "web" / "render.html").as_uri() + f"?scale={a.scale}")
        page.wait_for_function("window.ready === true")

        def emit(game, phase, extra):
            nonlocal frames
            url = page.evaluate("([g, p, c, cap, e]) => renderFrame(g, p, c, cap, e)",
                                [base64.b64encode(png(game[8:232, 8:248])).decode(), phase,
                                 frames * 1000 / 60, caption, extra])
            ffmpeg.stdin.write(base64.b64decode(url.split(",", 1)[1]))
            if game_pipe is not None:
                game_pipe.stdin.write(game[8:232, 8:248].repeat(3, axis=0).repeat(3, axis=1).tobytes())
            frames += 1

        for t in range(a.decisions):
            thumb = thumbnail(frame)
            action = player.decide(frame, ram, thumb=thumb)
            snap = player.snapshot()
            if a.trace is not None:
                trace.append(trace_record(snap, player.last["x"], frames, thumb))
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
                        "lives": g["lives"], "buttons": snap["buttons"], "died": g["lives"] < lives,
                        **({"played": snap["look"]["played"], "kind": snap["look"]["kind"]} if snap.get("look") else {})})
            lives = g["lives"]
            if done or g["lives"] == 0:
                break
        for _ in range(120):  # two seconds on the last frame
            emit(frame, None, "game over")
        browser.close()
    ffmpeg.stdin.close()
    ffmpeg.wait()
    if game_pipe is not None:
        game_pipe.stdin.close()
        game_pipe.wait()
    if a.trace is not None:
        import gzip
        import hashlib
        body = {"schema": "cadence-castlevania-trace/1", "cadence": cadence.__version__, "idle": a.idle,
                "brain_sha256": hashlib.sha256(BRAIN.read_bytes()).hexdigest(), "fps": 60,
                "frames_per_decision": 12, "settle_frames": SETTLE_FRAMES, "sweep_stride": SWEEP_STRIDE,
                "frames": frames, "decisions": trace}
        with gzip.open(a.trace, "wt", compresslevel=9) as handle:
            json.dump(body, handle, separators=(",", ":"))
    if a.log is not None:
        looked = {"lookahead": dict(player.look.counts)} if player.look is not None else {}
        a.log.write_text(json.dumps({"idle": a.idle, "frames": frames, "decisions": len(log), **looked, "log": log}) + "\n")
    print(json.dumps({"out": str(a.out), "frames": frames, "seconds": round(frames / 60, 1), "decisions": len(log)}))


if __name__ == "__main__":
    main()
