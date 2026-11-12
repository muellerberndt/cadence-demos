"""Record a short clip of the page for the README: the tutorial's steps, performed with the mouse.

    python tools/record_clip.py --out docs/out-of-sight.mp4      # from out-of-sight/

Serves ``site/``, opens it in headless Chromium at 1280 by 800, performs the six steps of the
tutorial as ``tools/check_page.py`` does (the same pointer input), and saves the browser's own
recording. With ``ffmpeg`` on the path the recording is written as H.264 ``.mp4`` (or as a
``.gif`` where ``--out`` ends so); without it the ``.webm`` is kept.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

import check_page as check

HERE = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, default=Path("docs/out-of-sight.mp4"))
    p.add_argument("--size", default="1280x800")
    p.add_argument("--warm", type=int, default=0, help="moments of free movement in view before the tutorial (a brain raised on the page learns in them)")
    a = p.parse_args()
    width, height = (int(v) for v in a.size.split("x"))
    out = a.out if a.out.is_absolute() else HERE / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    url, server = check.serve(check.SITE)
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=check.GPU)
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1,
                                      record_video_dir=folder, record_video_size={"width": width, "height": height})
        page = context.new_page()
        page.goto(url + "?sound=0", wait_until="domcontentloaded")
        check.ready(page, 240)
        began = page.evaluate("performance.now()")
        if a.warm:
            page.evaluate("document.getElementById('welcome').hidden = true")
            for point in ([-0.3, 1.15], [-0.75, 1.2], [-0.45, 0.9], [-0.8, 1.3], [-0.2, 1.25], [-0.6, 1.0]) * 8:
                page.evaluate("(p) => { window.outOfSight.stage.targets[0] = p; }", point)
                check.wait_moments(page, 24)
                if check.moment(page) >= a.warm:
                    break
            page.evaluate("window.outOfSight.stage.targets[0] = null; document.getElementById('welcome').hidden = false")
            began = page.evaluate("performance.now()")
        home = page.evaluate("window.outOfSight.stage.home.things")
        page.wait_for_timeout(900)
        page.click("#welcome-go")
        check.wait_tour(page, "follow", 5)
        check.drag(page, "hand", [[-0.3, 1.15], [-0.75, 1.2], [-0.45, 0.9], [-0.6, 1.0]])
        check.wait_tour(page, "hide")
        page.wait_for_timeout(700)
        check.drag(page, "hand", [page.evaluate("window.outOfSight.shadowPoint(0.32)")])
        part = page.evaluate("(() => { const p = window.outOfSight.brainView.part('place'), b = document.getElementById('brain-stage').getBoundingClientRect(); return [b.left + p.x + p.w / 2, b.top + p.y + p.h / 2]; })()")
        page.mouse.move(part[0], part[1], steps=12)
        check.wait_tour(page, "return", 20)
        page.wait_for_timeout(1600)
        page.mouse.move(part[0], 70, steps=8)
        check.drag(page, "hand", [home[0]], hold=20)
        check.wait_tour(page, "turn", 20)
        page.wait_for_timeout(600)
        sweep = page.evaluate("""(() => { const o = window.outOfSight, d = o.awayHeading('apple') - o.stage.geometry.camera.heading;
            return Math.atan2(Math.sin(d), Math.cos(d)); })()""")
        check.turn(page, sweep * 1.05)
        check.wait_tour(page, "move", 20)
        page.wait_for_timeout(1800)
        check.drag(page, "cup", [page.evaluate("window.outOfSight.awayPoint('cup', 0.3)")], hold=20)
        check.wait_tour(page, "knock", 20)
        page.wait_for_timeout(600)
        x, y = page.evaluate("window.outOfSight.screenOf('cup')")
        page.mouse.move(x, y, steps=6)
        page.mouse.down()
        page.mouse.up()
        check.wait_tour(page, "free", 20)
        page.wait_for_timeout(2500)
        skip = began / 1000.0
        video = page.video
        context.close()
        browser.close()
        source = Path(video.path())
        if shutil.which("ffmpeg") and out.suffix in (".mp4", ".gif"):
            if out.suffix == ".mp4":
                command = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{skip:.2f}", "-i", str(source), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-crf", "26", "-preset", "slow", "-movflags", "+faststart", str(out)]
            else:
                command = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{skip:.2f}", "-i", str(source), "-vf",
                           "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer", str(out)]
            subprocess.run(command, check=True)
        else:
            out = out.with_suffix(".webm")
            shutil.copyfile(source, out)
    server.shutdown()
    print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
