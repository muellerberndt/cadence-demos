"""The page's promise, tried end to end in headless Chromium, with the mouse a visitor uses.

    python tools/check_page.py                 # from out-of-sight/; serves site/ on a free port
    python tools/check_page.py --shots docs    # and saves screenshots there

The promise: hide the hand behind the blind spot, and the brain keeps knowing where it is. The
check performs the tutorial's five steps with real pointer input and reads what the brain did at
each of them from the page's own record of its answers:

1. follow: the hand is dragged across the table in view; the brain's place follows it;
2. hide: the hand is dragged behind the pillar and rests in the shadow; the brain's place stays
   with the hand and its stated area holds the hand; the place part's card, opened while the
   hand is hidden, shows a position and an uncertainty that grows;
3. return: the hand is brought back into view; the place closes on it and the uncertainty falls;
4. move: the cup is dragged into the shadow; its record keeps the place it was last seen at;
5. knock: the cup is tapped; its record moves to the heard place without sight.

Then the parts' cards (each beside its part, never over it) and the eight stages of "follow the
position", undo and reset, the
details switch with a scene file loaded and replayed, the frame times with the brain view on,
a phone-sized touch screen, and the Canvas2D view. Console errors, page errors and failed
requests fail the check. The bounds below were set before the trained brain was read. Evidence
goes to ``evidence/page_check.json``.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import platform
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
SITE = HERE / "site"
GPU = (["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] if platform.system() == "Darwin"
       else ["--enable-gpu", "--ignore-gpu-blocklist"])

# The bounds a step is read against (metres; a hand is about 0.1 m wide).
FOLLOW = 0.05        # in view: the mean distance of the brain's place from the true hand
HIDDEN = 0.10        # out of view: the same, over the moments the hand is hidden
COVER = 0.85         # the share of hidden moments whose stated area holds the true hand
RETURN = 0.05        # 15 moments after the hand is seen again
PIN_KEPT = 0.03      # the record's distance from the place the thing was last seen at
PIN_HEARD = 3.0      # after one knock: the record's distance from the true place, in standard deviations of the cue's own error
FRAME_MEDIAN = 20.0  # milliseconds a frame with the brain view on
FRAME_P95 = 34.0


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *args: None
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


class Check:
    def __init__(self, shots: Path | None) -> None:
        self.rows: list[dict] = []
        self.errors: list[str] = []
        self.shots = shots

    def add(self, name: str, passed: bool, **detail) -> bool:
        self.rows.append({"name": name, "passed": bool(passed), **detail})
        print(("ok    " if passed else "FAIL  ") + name, json.dumps(detail, default=str)[:400], flush=True)
        return bool(passed)

    def watch(self, page, label: str) -> None:
        page.on("console", lambda m: self.errors.append(f"{label}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: self.errors.append(f"{label}: {e}"))
        page.on("requestfailed", lambda r: self.errors.append(f"{label}: failed {r.url}"))

    def shot(self, page, name: str) -> None:
        if self.shots:
            self.shots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(self.shots / name))


# Whether the open card covers none of the named parts (their buttons' boxes on the screen).
CLEAR = """(ids) => { const card = document.getElementById('card'); if (card.hidden) return false; const a = card.getBoundingClientRect();
  return ids.every((id) => { const el = document.querySelector(`.part[data-part="${id}"]`); if (!el) return true; const b = el.getBoundingClientRect();
    return a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1; }); }"""

JS_ROWS = """([from, to]) => window.outOfSight.state.history.filter((r) => r.moment > from && r.moment <= to)
  .map((r) => ({ m: r.moment, seen: r.seen, brain: r.brain, last: r.last, kalman: r.kalman, u: r.uncertainty, inside: r.inside, lesson: r.lesson, cup: r.pins.cup || null }))"""


def mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def ready(page, timeout_s: float) -> float:
    began = time.time()
    page.wait_for_function("document.body.dataset.ready === '1' || document.body.dataset.error", timeout=timeout_s * 1000)
    error = page.evaluate("document.body.dataset.error || null")
    if error:
        raise RuntimeError(error)
    return time.time() - began


def moment(page) -> int:
    return int(page.evaluate("window.outOfSight.state.record ? window.outOfSight.state.record.moment : 0"))


def wait_moments(page, count: int, timeout_s: float = 60.0) -> None:
    """Wait until the brain has answered ``count`` further moments; a page that stopped says why."""
    target = moment(page) + count
    # answered: the page's record of answers holds the moment (the next one may be on its way)
    page.wait_for_function(f"document.body.dataset.error || (window.outOfSight.state.history.length && window.outOfSight.state.history.at(-1).moment >= {target})",
                           timeout=timeout_s * 1000)
    error = page.evaluate("document.body.dataset.error || null")
    if error:
        raise RuntimeError(f"the page stopped: {error}")


def drag(page, name: str, points: list[list[float]], *, hold: int = 0, release: bool = True, pace: float = 0.5) -> None:
    """Press on a thing and bring it through plane points with the mouse, as a visitor drags:
    the pointer runs ahead at ``pace`` metres a second and the thing follows it."""
    x, y = page.evaluate("(n) => window.outOfSight.screenOf(n)", name)
    page.mouse.move(x, y)
    page.mouse.down()
    at = page.evaluate("(n) => window.outOfSight.stage.where(n)", name)
    for target in points:
        span = ((target[0] - at[0]) ** 2 + (target[1] - at[1]) ** 2) ** 0.5
        steps = max(2, int(span / pace * 30))
        for k in range(1, steps + 1):
            p = [at[0] + (target[0] - at[0]) * k / steps, at[1] + (target[1] - at[1]) * k / steps]
            sx, sy = page.evaluate("(p) => window.outOfSight.screenAt(p)", p)
            page.mouse.move(sx, sy)
            page.wait_for_timeout(33)
        at = target
        # the thing itself arrives a little after the pointer
        page.wait_for_function("(a) => { const p = window.outOfSight.stage.where(a[0]); return Math.hypot(p[0] - a[1][0], p[1] - a[1][1]) < 0.01; }",
                               arg=[name, target], timeout=20000)
    if hold:
        wait_moments(page, hold)
    if release:
        page.mouse.up()


def tour_step(page) -> str:
    return page.evaluate("document.body.dataset.tour || ''")


def wait_tour(page, step: str, timeout_s: float = 30.0) -> bool:
    try:
        page.wait_for_function(f"document.body.dataset.tour === '{step}'", timeout=timeout_s * 1000)
        return True
    except Exception:
        return False


def tutorial(page, c: Check) -> dict:
    """The five steps, performed with the mouse; what the brain did at each."""
    out: dict = {}
    home = page.evaluate("window.outOfSight.stage.home.things")
    page.click("#welcome-go")
    c.add("the tutorial starts at its first step", wait_tour(page, "follow", 5), step=tour_step(page))

    # 1. follow: across the table, in view
    start = moment(page)
    drag(page, "hand", [[-0.75, 0.6], [-0.25, 1.15], [-0.7, 1.2], [-0.55, 0.8], [-0.8, 1.0], [-0.6, 0.95]])
    advanced = wait_tour(page, "hide")
    wait_moments(page, 20)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    seen = [r for r in rows if r["seen"]]
    follow = mean([r["brain"] for r in seen[-60:]])
    out["follow"] = {"moments": len(rows), "in_view": len(seen), "brain_m": follow, "kalman_m": mean([r["kalman"] for r in seen[-60:]]),
                     "lessons": sum(1 for r in rows if r["lesson"])}
    c.add("1 follow: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.add("1 follow: the brain's place follows the hand in view", follow is not None and follow <= FOLLOW, bound_m=FOLLOW, **out["follow"])
    c.shot(page, "tour-1-follow.png")

    # 2. hide: behind the pillar, at rest in the shadow, the mouse held
    target = page.evaluate("window.outOfSight.shadowPoint(0.32)")
    start = moment(page)
    drag(page, "hand", [target])
    # the hand rests in the shadow; the visitor points at the place part, and its card is read
    # while the hand stays hidden
    part = page.evaluate("(() => { const p = window.outOfSight.brainView.part('place'), b = document.getElementById('brain-stage').getBoundingClientRect(); return [b.left + p.x + p.w / 2, b.top + p.y + p.h / 2]; })()")
    page.mouse.move(part[0], part[1])
    page.evaluate("""() => { window.__card = [];
        window.__cardTimer = setInterval(() => { const q = (k) => document.querySelector(`#card [data-${k}]`);
          if (document.getElementById('card').hidden || !q('unseen')) return;
          window.__card.push({ unseen: Number(q('unseen').dataset.unseen), uncertainty: Number(q('uncertainty').dataset.uncertainty), place: q('place').dataset.place,
            text: document.getElementById('card').innerText }); }, 30); }""")
    page.wait_for_timeout(400)
    c.shot(page, "tour-2-hidden-card.png")
    page.wait_for_function("window.outOfSight.state.unseen >= 70", timeout=20000)
    samples = page.evaluate("(() => { clearInterval(window.__cardTimer); return window.__card; })()")
    seen_u = page.evaluate("window.outOfSight.state.seenBelief ? window.outOfSight.state.history.filter((r) => r.seen).at(-1).uncertainty : null")
    page.mouse.move(part[0], 60)
    first = samples[0] if samples else {"unseen": None, "uncertainty": None, "place": None, "text": ""}
    later = samples[-1] if samples else first
    advanced = wait_tour(page, "return", 20)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    hidden = [r for r in rows if not r["seen"] and r["brain"] is not None]
    no_answer = sum(1 for r in rows if r["brain"] is None)
    out["hide"] = {"hidden_moments": len(hidden), "no_answer": no_answer, "brain_m": mean([r["brain"] for r in hidden]),
                   "brain_last_m": hidden[-1]["brain"] if hidden else None, "kalman_m": mean([r["kalman"] for r in hidden]),
                   "last_seen_m": mean([r["last"] for r in hidden]), "inside_area": mean([1.0 if r["inside"] else 0.0 for r in hidden]),
                   "uncertainty_first_m": hidden[0]["u"] if hidden else None, "uncertainty_last_m": hidden[-1]["u"] if hidden else None,
                   "lessons_while_hidden": sum(1 for r in hidden if r["lesson"])}
    c.add("2 hide: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.add("2 hide: THE PROMISE, the brain's place stays with the hidden hand", bool(hidden) and out["hide"]["brain_m"] <= HIDDEN,
          bound_m=HIDDEN, **out["hide"])
    c.add("2 hide: the stated area holds the hidden hand", bool(hidden) and out["hide"]["inside_area"] >= COVER, bound=COVER,
          inside_area=out["hide"]["inside_area"])
    c.add("2 hide: the brain learns nothing while the hand is hidden", bool(hidden) and out["hide"]["lessons_while_hidden"] == 0,
          lessons=out["hide"]["lessons_while_hidden"])
    c.add("2 hide: the place part's card shows a position and the moments unseen",
          bool(samples) and bool(later["place"]) and later["unseen"] >= 40 and "plays the role of" in later["text"],
          readings=len(samples), place=later["place"], unseen=later["unseen"], text=later["text"][:300])
    c.add("2 hide: the card's uncertainty grows while the hand is hidden",
          bool(samples) and seen_u is not None and first["uncertainty"] > seen_u and later["uncertainty"] > first["uncertainty"],
          when_last_seen_m=seen_u, first_m=first["uncertainty"], first_unseen=first["unseen"], later_m=later["uncertainty"], later_unseen=later["unseen"])

    # 3. return: back into the light
    start = moment(page)
    drag(page, "hand", [home[0]], hold=25)
    advanced = wait_tour(page, "move", 20)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    seen = [r for r in rows if r["seen"] and r["brain"] is not None]
    back = mean([r["brain"] for r in seen[-10:]])
    out["return"] = {"brain_m": back, "uncertainty_m": seen[-1]["u"] if seen else None,
                     "uncertainty_hidden_m": out["hide"]["uncertainty_last_m"]}
    c.add("3 return: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.add("3 return: the place closes on the hand", back is not None and back <= RETURN, bound_m=RETURN, **out["return"])
    c.add("3 return: the uncertainty falls when the hand is seen", bool(seen) and out["hide"]["uncertainty_last_m"] is not None
          and seen[-1]["u"] < out["hide"]["uncertainty_last_m"], **out["return"])

    # 4. move: the cup into the shadow; its pin keeps the place it was last seen at
    target = page.evaluate("window.outOfSight.shadowPoint(0.5)")
    start = moment(page)
    drag(page, "cup", [target], hold=20)
    advanced = wait_tour(page, "knock", 20)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    last_seen = [r for r in rows if r["cup"] and r["cup"]["seen"]]
    hidden = [r for r in rows if r["cup"] and not r["cup"]["seen"]]
    kept = None
    if last_seen and hidden:
        a, b = last_seen[-1]["cup"]["place"], hidden[-1]["cup"]["place"]
        kept = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    out["move"] = {"hidden_moments": len(hidden), "pin_from_last_seen_m": kept, "pin_from_true_m": hidden[-1]["cup"]["off"] if hidden else None,
                   "pin_source": hidden[-1]["cup"]["from"] if hidden else None}
    c.add("4 move: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.add("4 move: the record keeps the place the cup was last seen at", kept is not None and kept <= PIN_KEPT
          and out["move"]["pin_from_true_m"] >= 0.1, bound_m=PIN_KEPT, **out["move"])
    c.shot(page, "tour-4-moved.png")

    # 5. knock: a tap on the hidden cup
    start = moment(page)
    x, y = page.evaluate("window.outOfSight.screenOf('cup')")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.up()
    finished = wait_tour(page, "free", 20)
    wait_moments(page, 10)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    after = [r for r in rows if r["cup"]]
    out["knock"] = {"pin_from_true_m": after[-1]["cup"]["off"] if after else None, "pin_source": after[-1]["cup"]["from"] if after else None,
                    "cup_in_view": after[-1]["cup"]["seen"] if after else None, "before_m": out["move"]["pin_from_true_m"]}
    c.add("5 knock: the tap completes the tutorial, which leaves the visitor in free play", finished, step=tour_step(page))
    far, noise = page.evaluate("""(() => { const o = window.outOfSight, g = o.stage.geometry, p = o.stage.where('cup');
        return [Math.hypot(p[0] - g.ear[0], p[1] - g.ear[1]), o.stage.world.cueNoise]; })()""")
    bound = PIN_HEARD * far * (noise[0] ** 2 + noise[1] ** 2) ** 0.5
    out["knock"]["cue_error_sd_m"] = far * (noise[0] ** 2 + noise[1] ** 2) ** 0.5
    c.add("5 knock: the record moves to the heard place without sight", bool(after) and after[-1]["cup"]["from"] == "heard"
          and not after[-1]["cup"]["seen"] and after[-1]["cup"]["off"] <= bound and after[-1]["cup"]["off"] < out["move"]["pin_from_true_m"],
          bound_m=bound, **out["knock"])
    c.shot(page, "tour-5-knock.png")
    return out


def cards(page, c: Check) -> None:
    """Every part explains itself; the path of a position is reachable in order."""
    parts = page.evaluate("window.outOfSight.brainView.parts.map((p) => ({ id: p.id, kind: p.kind, x: p.x + p.w / 2, y: p.y + p.h / 2 }))")
    box = page.locator("#brain-stage").bounding_box()
    opened = []
    for part in parts:
        page.mouse.move(box["x"] + part["x"], box["y"] + part["y"])
        page.wait_for_timeout(80)
        text = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
        opened.append({"id": part["id"], "ok": "at this moment" in text.lower() and ("plays the role of" in text or "fibre tract" in text.lower()),
                       "clear": page.evaluate(CLEAR, [part["id"]]), "head": text.split("\n")[0][:60]})
    page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
    page.wait_for_timeout(80)
    c.add("every part of the brain explains itself on hover, with what it does at this moment", all(o["ok"] for o in opened),
          parts=len(opened), missing=[o["id"] for o in opened if not o["ok"]], heads=[o["head"] for o in opened])
    c.add("a card stands beside its part, never over it", all(o["clear"] for o in opened), over=[o["id"] for o in opened if not o["clear"]])
    c.add("no card shows until the visitor points at something", page.evaluate("document.getElementById('card').hidden"))
    # the keyboard reaches the same cards; Escape closes
    page.focus(".part")
    page.keyboard.press("Tab")
    page.wait_for_timeout(80)
    focused = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
    page.keyboard.press("Escape")
    closed = page.evaluate("document.getElementById('card').hidden")
    c.add("a part's card opens on keyboard focus and Escape closes it", "at this moment" in focused.lower() and closed, head=focused.split("\n")[0][:60])
    # follow the position: eight stages in order
    page.click("#follow")
    stages = []
    for _ in range(8):
        page.wait_for_timeout(60)
        stages.append(page.evaluate("""() => ({ kicker: document.querySelector('#card .kicker')?.innerText || '', title: document.querySelector('#card h3')?.innerText || '',
            live: document.querySelector('#card .live')?.innerText || '', marked: !!document.querySelector('#card .mark'),
            spots: [...window.outOfSight.brainView.spot] })"""))
        stages[-1]["clear"] = page.evaluate(CLEAR, stages[-1]["spots"])
        page.click("#card [data-go='1']")
    c.shot(page, "follow-the-position.png")
    page.keyboard.press("Escape")
    order_ok = [s["kicker"].upper().endswith(f"{k + 1} OF 8") for k, s in enumerate(stages)]
    c.add("follow the position: eight stages in order, each with live numbers and its part ringed",
          all(order_ok) and all(s["title"] and "AT THIS MOMENT" in s["live"].upper() and s["spots"] and s["clear"] for s in stages),
          stages=[{"title": s["title"], "ringed": s["spots"], "baseline_mark": s["marked"]} for s in stages])


def manners(page, c: Check, scene_file: Path | None) -> None:
    """Undo, reset, the details switch and a scene file."""
    before = page.evaluate("window.outOfSight.stage.where('box')")
    drag(page, "box", [[0.4, 0.2]])
    moved = page.evaluate("window.outOfSight.stage.where('box')")
    page.click("#undo")
    page.wait_for_timeout(100)
    undone = page.evaluate("window.outOfSight.stage.where('box')")
    c.add("undo takes the last move back in one tap", abs(moved[0] - 0.4) < 0.02 and abs(undone[0] - before[0]) < 1e-9 and abs(undone[1] - before[1]) < 1e-9,
          before=before, moved=moved, undone=undone)
    x, y = page.evaluate("window.outOfSight.screenOf('camera')")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.up()
    wait_moments(page, 5)
    dark = page.evaluate("({ on: window.outOfSight.stage.cameraOn, seen: window.outOfSight.state.record.in_view })")
    c.add("a tap on the camera switches it off: nothing is in view", dark["on"] is False and not any(dark["seen"]), **dark)
    c.shot(page, "camera-off.png")
    page.click("#reset")
    wait_moments(page, 5)
    state = page.evaluate("({ on: window.outOfSight.stage.cameraOn, things: window.outOfSight.stage.world.things, home: window.outOfSight.stage.home.things })")
    c.add("reset puts everything back in one tap", state["on"] is True and state["things"] == state["home"], camera_on=state["on"])
    hidden = page.evaluate("document.getElementById('details-panel').hidden")
    page.click("#details")
    page.wait_for_timeout(400)
    shown = page.evaluate("({ hidden: document.getElementById('details-panel').hidden, chart: document.getElementById('chart').getBoundingClientRect().height, more: document.body.classList.contains('more') })")
    c.add("the comparison, the chart and the settings stay behind one switch, off until asked for", hidden and not shown["hidden"] and shown["chart"] > 50, **shown)
    if scene_file and scene_file.exists():
        page.evaluate("document.body.dataset.run = ''")
        page.set_input_files("#file", str(scene_file))
        page.wait_for_function("document.body.dataset.run && document.body.dataset.run.length > 2", timeout=120000)
        run = json.loads(page.evaluate("document.body.dataset.run"))
        steps = len(json.loads(scene_file.read_text())["truth"])
        c.add("a scene file of the tracking chamber loads and replays", run["moments"] == steps, file=scene_file.name, steps=steps, run=run)
        c.shot(page, "details-scene-file.png")
    page.click("#details")
    page.click("#reset")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", help="a running server for site/ (default: serve it here)")
    p.add_argument("--shots", type=Path, default=None, help="save screenshots in this folder")
    p.add_argument("--scene", type=Path, default=HERE / "tests" / "fixtures" / "example.json", help="a scene file to load and replay")
    p.add_argument("--timeout", type=float, default=240.0)
    a = p.parse_args()
    url, server = (a.url, None) if a.url else serve(SITE)
    c = Check((HERE / a.shots) if a.shots and not a.shots.is_absolute() else a.shots)
    manifest = json.loads((SITE / "pack" / "manifest.json").read_text())
    report: dict = {"schema": "cadence-out-of-sight-page-check/1", "checked": time.strftime("%Y-%m-%d %H:%M"),
                    "cadence": manifest["cadence"], "brain": manifest.get("module") or manifest.get("brain_kind"),
                    "bounds": {"follow_m": FOLLOW, "hidden_m": HIDDEN, "cover": COVER, "return_m": RETURN, "pin_kept_m": PIN_KEPT,
                               "pin_heard_cue_sd": PIN_HEARD, "frame_median_ms": FRAME_MEDIAN, "frame_p95_ms": FRAME_P95}}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=GPU)
            # -- a desktop, with the mouse
            context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page = context.new_page()
            c.watch(page, "desktop")
            page.goto(url + "?sound=0", wait_until="domcontentloaded")
            seconds = ready(page, a.timeout)
            info = page.evaluate("({ cadence: window.outOfSight.state.describe.cadence, brain: window.outOfSight.state.describe.brain, view: window.outOfSight.brainView.stats(), neurons: window.outOfSight.state.describe.neurons, synapses: window.outOfSight.state.describe.synapses })")
            report["page"] = {**info, "seconds_to_ready": round(seconds, 1)}
            c.add("the brain loads in Pyodide with the released wheel", info["cadence"] == manifest["cadence"], seconds=round(seconds, 1),
                  cadence=info["cadence"], brain=info["brain"]["label"], view=info["view"]["mode"])
            fits = page.evaluate("({ w: document.documentElement.scrollWidth <= innerWidth, h: document.documentElement.scrollHeight <= innerHeight + 1, welcome: !document.getElementById('welcome').hidden })")
            c.add("one screen: the scene and the brain, nothing to scroll, the tutorial offered", fits["w"] and fits["h"] and fits["welcome"], **fits)
            c.shot(page, "welcome.png")
            report["tutorial"] = tutorial(page, c)
            frames = page.evaluate("window.outOfSight.frameStats(1500)")
            think = page.evaluate("(() => { const t = window.outOfSight.state.think.slice().sort((a, b) => a - b), r = window.outOfSight.state.roundTrip.slice().sort((a, b) => a - b); return { think_ms: t[t.length >> 1], round_trip_ms: r[r.length >> 1], moments: window.outOfSight.state.moments, no_answer: window.outOfSight.state.refused }; })()")
            report["frames"] = {"desktop_webgl": frames, **think}
            c.add("frame time with the brain view on, over the tutorial", frames["median_ms"] <= FRAME_MEDIAN and frames["p95_ms"] <= FRAME_P95,
                  bound_median_ms=FRAME_MEDIAN, bound_p95_ms=FRAME_P95, **frames, **think)
            cards(page, c)
            manners(page, c, a.scene)
            context.close()

            # -- a phone, with a finger
            context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
            page = context.new_page()
            c.watch(page, "phone")
            page.goto(url + "?sound=0&tour=0", wait_until="domcontentloaded")
            ready(page, a.timeout)
            wait_moments(page, 30)
            fits = page.evaluate("({ w: document.documentElement.scrollWidth <= innerWidth, scene: document.getElementById('scene').getBoundingClientRect().height, brain: document.getElementById('brain-stage').getBoundingClientRect().height })")
            c.add("a phone shows the scene and the brain on one screen", fits["w"] and fits["scene"] > 200 and fits["brain"] > 200, **fits)
            x, y = page.evaluate("window.outOfSight.screenOf('cup')")
            page.touchscreen.tap(x, y)
            wait_moments(page, 6)
            heard = page.evaluate("window.outOfSight.sceneView.rings.length > 0 || (window.outOfSight.state.history.slice(-8).some((r) => r.pins.cup))")
            part = page.evaluate("(() => { const p = window.outOfSight.brainView.part('place'), b = document.getElementById('brain-stage').getBoundingClientRect(); return [b.left + p.x + p.w / 2, b.top + p.y + p.h / 2]; })()")
            page.touchscreen.tap(part[0], part[1])
            page.wait_for_timeout(150)
            text = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
            c.shot(page, "phone.png")
            above = page.evaluate("""(() => { const v = window.outOfSight.brainView, card = document.getElementById('card').getBoundingClientRect(), stage = document.getElementById('brain-stage').getBoundingClientRect();
                return { brain_bottom: stage.top + v.brainBox.y + v.brainBox.h, sheet_top: card.top, brain_height: v.brainBox.h, sheet: document.body.classList.contains('sheet') }; })()""")
            c.add("on a phone the card is a sheet from the bottom and the brain stays visible above it",
                  above["sheet"] and above["brain_bottom"] <= above["sheet_top"] + 2 and above["brain_height"] >= 110, **above)
            page.touchscreen.tap(60, 200)
            page.wait_for_timeout(120)
            closed = page.evaluate("document.getElementById('card').hidden")
            c.add("on a phone a tap knocks, a tap on a part opens its card and a tap elsewhere closes it",
                  bool(heard) and "at this moment" in text.lower() and closed, card=text.split("\n")[0][:60], closed=closed)
            frames = page.evaluate("window.outOfSight.frameStats(300)")
            report["frames"]["phone_viewport"] = frames
            context.close()

            # -- without fast WebGL: the Canvas2D view
            context = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            page = context.new_page()
            c.watch(page, "canvas2d")
            page.goto(url + "?sound=0&tour=0&renderer=2d", wait_until="domcontentloaded")
            ready(page, a.timeout)
            wait_moments(page, 90)
            view = page.evaluate("window.outOfSight.brainView.stats()")
            frames = page.evaluate("window.outOfSight.frameStats(240)")
            report["frames"]["desktop_canvas2d"] = frames
            c.add("the Canvas2D view draws the brain where WebGL2 is missing", view["mode"] == "canvas2d" and view["lit"] > 0 and frames["median_ms"] <= FRAME_P95,
                  view=view, frame_times=frames)
            c.shot(page, "canvas2d.png")
            context.close()
            browser.close()
    finally:
        if server:
            server.shutdown()
    c.add("no console errors, page errors or failed requests", not c.errors, errors=c.errors[:6])
    report["checks"] = c.rows
    report["passed"] = all(row["passed"] for row in c.rows)
    report["failed"] = [row["name"] for row in c.rows if not row["passed"]]
    out = HERE / "evidence" / "page_check.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(("PASS" if report["passed"] else "FAIL") + f": {sum(r['passed'] for r in c.rows)} of {len(c.rows)} checks; evidence in {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
