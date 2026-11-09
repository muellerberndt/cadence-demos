"""Cut a highlights video from full recordings (record.py's MP4 and its per-decision log): each clip
is a stretch of one run and one life, played as recorded, with a caption naming the start and the
life, and a card between clips saying that they are cut together.

    python highlights.py --spec highlights.json --scale 2 --out docs/castlevania-brain-alone-highlights.mp4
    python highlights.py --spec lookahead.json --scale 2 --caption-y 662 --note "..." --out docs/castlevania-highlights.mp4

The spec lists clips: {"video": ..., "log": ..., "start": idle decisions, "life": n,
"from": decision, "to": decision, "label": "..."}; decisions map to video time through the log.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 60
SCALE = 1  # set from --scale
NOTE = ("Highlights: separate runs and lives of the same frozen brain, playing alone, cut together; "
        "the full uncut game is castlevania-brain-alone-run.mp4")


def font(size: int, bold: bool = False):
    for path in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else []) + [
            "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def card(path: Path, title: str, line: str) -> None:
    k = SCALE
    img = Image.new("RGB", (W * k, H * k), (13, 11, 16))
    d = ImageDraw.Draw(img)
    d.text((80 * k, 270 * k), "CUT", fill=(224, 68, 79), font=font(40 * k, True))
    d.text((80 * k, 330 * k), title, fill=(233, 227, 238), font=font(34 * k, True))
    d.text((80 * k, 390 * k), line, fill=(156, 144, 168), font=font(22 * k))
    d.text((80 * k, 640 * k), NOTE, fill=(156, 144, 168), font=font(18 * k))
    img.save(path)


def caption(path: Path, text: str, second: str | None = None) -> None:
    k = SCALE
    h = 56 if second else 44
    img = Image.new("RGBA", (640 * k, h * k), (13, 11, 16, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 640 * k - 1, h * k - 1), 6 * k, fill=(23, 19, 28, 235), outline=(242, 193, 78, 255), width=k)
    d.text((14 * k, (8 if second else 12) * k), text, fill=(242, 193, 78), font=font(15 * k))
    if second:
        d.text((14 * k, 30 * k), second, fill=(200, 190, 210), font=font(13 * k))
    img.save(path)


def shares(log: list, first: int, last: int) -> str | None:
    """A brain + look-ahead clip's three shares: the brain's own move, the look-ahead overruling it,
    route recovery (record.py --lookahead logs each decision's kind)."""
    kinds = [e.get("kind") for e in log if first <= e["decision"] <= last]
    if not kinds or kinds[0] is None:
        return None
    n = len(kinds)
    pct = {k: 100 * kinds.count(k) / n for k in ("brain", "overruled", "recovery")}
    return (f'this clip, {n} decisions: brain {pct["brain"]:.0f}% · look-ahead overruled {pct["overruled"]:.0f}% · '
            f'route recovery {pct["recovery"]:.0f}%')


def main() -> None:
    global SCALE, NOTE
    p = argparse.ArgumentParser()
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--crf", type=int, default=33)
    p.add_argument("--card-seconds", type=float, default=2.5)
    p.add_argument("--scale", type=int, default=1, help="2 for a 2560 x 1440 source")
    p.add_argument("--no-cards", action="store_true", help="the clips back to back with their captions (the short loop)")
    p.add_argument("--note", default=NOTE, help="the line on every card")
    p.add_argument("--caption-y", type=int, default=632, help="where the clip caption sits (at 1x)")
    a = p.parse_args()
    SCALE, NOTE = a.scale, a.note
    exe = shutil.which("ffmpeg")
    if exe is None:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    spec = json.loads(a.spec.read_text())
    tmp = Path(tempfile.mkdtemp())
    inputs, filters, parts = [], [], []
    for i, clip in enumerate(spec["clips"]):
        log = json.loads(Path(clip["log"]).read_text())["log"]
        frame_at = {e["decision"]: e["frame"] for e in log}  # the frame count after each decision
        start_frame = frame_at.get(clip["from"] - 1, 0)
        end_frame = frame_at[clip["to"]]
        t0, t1 = start_frame / FPS, end_frame / FPS
        label = f'start {clip["start"]} · life {clip["life"]} · {clip["label"]}'
        caption(tmp / f"cap{i}.png", label, shares(log, clip["from"], clip["to"]))
        if not a.no_cards:
            card(tmp / f"card{i}.png", clip["label"], f'Start after {clip["start"]} idle decisions, life {clip["life"]} '
                 f'(decisions {clip["from"]} to {clip["to"]}), as recorded')
            inputs += ["-loop", "1", "-t", str(a.card_seconds), "-framerate", str(FPS), "-i", str(tmp / f"card{i}.png")]
        inputs += ["-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", clip["video"], "-loop", "1", "-framerate", str(FPS),
                   "-t", f"{t1 - t0:.3f}", "-i", str(tmp / f"cap{i}.png")]
        clip["t0"], clip["t1"] = round(t0, 2), round(t1, 2)
    # build the filter graph: card, then the clip with its caption overlaid
    idx, segs = 0, []
    for i, clip in enumerate(spec["clips"]):
        if not a.no_cards:
            filters.append(f"[{idx}:v]format=yuv420p,setsar=1,fps={FPS}[c{i}]")
            segs.append(f"[c{i}]")
            idx += 1
        filters.append(f"[{idx}:v]fps={FPS},setsar=1[v{i}];[v{i}][{idx + 1}:v]overlay={636 * a.scale}:{a.caption_y * a.scale}:shortest=1,format=yuv420p[o{i}]")
        segs.append(f"[o{i}]")
        idx += 2
    filters.append("".join(segs) + f"concat=n={len(segs)}:v=1:a=0[out]")
    codec = (["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(a.crf), "-row-mt", "1"] if a.out.suffix == ".webm"
             else ["-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"])
    cmd = [exe, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-an", *codec, str(a.out)]
    subprocess.run(cmd, check=True)
    print(json.dumps({"out": str(a.out), "bytes": a.out.stat().st_size,
                      "clips": [{k: c[k] for k in ("start", "life", "from", "to", "t0", "t1", "label")} for c in spec["clips"]]}, indent=1))


if __name__ == "__main__":
    main()
