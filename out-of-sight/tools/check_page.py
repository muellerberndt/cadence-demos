"""The page's promise, tried end to end in headless Chromium, with the mouse a visitor uses.

    python tools/check_page.py                 # from out-of-sight/; serves site/ on a free port
    python tools/check_page.py --shots docs    # and saves screenshots there

The page runs the what-where map (``cadence.space.map.Map``): the brain's map of things, held in
its own carried activity. The promise: hide the hand, and the brain knows where it is.

What is checked, in order:

1. The promise on the two scene files of the tracking chamber (``tests/fixtures/``: a hand goes
   behind the pillar at 0.5 m/s, rests there for 70 moments and comes back; once with the arm
   folded, once with the arm's shadow joined to the pillar's), replayed on the page: in view the
   hand's place on the map within 3 cm; out of view the mean distance at or under last seen's on
   the same rows, and the hand's cells holding the true hand on at least .85 of the hidden
   moments; back in view within 3 cm.
2. Nothing is announced: a thing is absent from the map until the camera first sees it.
3. The tutorial, performed with the mouse: hide the hand, bring it back, turn away from the
   apple (it keeps its place on the map, behind the body, within one cell for 300 moments), and
   the arm's own hand, placed on the map by its joint readings while the camera cannot see it,
   within 1.5 cm.
4. A thing moved while the camera looks away keeps its old place until the camera sees that
   place; it is then near there, out of sight, or not known where; seen again, it is found
   within 3 cm.
5. Questions both ways: a tap on a thing asks where it is, a tap on the floor what is there.
6. With the camera off nothing on the map changes. An emptied map reports no thing.
7. The parts' cards, the stages of "follow the position", undo, reset, the details switch, a
   scene file, the frame time, a phone and the Canvas2D view. Console errors, page errors and
   failed requests fail the check.

The bounds. They were set on 12 November 2026 from the gates of cadence#320 (S1: in view within
the camera's own error, here 3 cm; S3 and S14: a thing unseen keeps its place within the map's
resolution, one cell; S11: a change unseen is found when seen; the area out of view holds the
true place on .85 of the steps, from S5's bound), from last seen on the same rows, and from the
owner's word on the arm's own hand ("within about a centimetre"). The model's native readings on
the two scene files were known when they were set (the map with ``reach`` 0.15 m: 11.8 cm and
11.8 cm hidden against last seen's 15.5 cm, its cells holding the hand on 1.00 of the hidden
moments, 1.2 cm in view); the page's own numbers were not. A bound changes only by an amendment
recorded here.

One change was made after the checks were first committed (74f1cc2) and before the page first
ran the map, and changed no bound: "what is there" was first asked by a tap on the bread, which
lands on the bread itself and asks where it is; it is asked at the apple's old place after the
apple was moved unseen, where the map holds the apple and no apple stands.

Amendment of 13 November 2026, made when the page took the guide of 824c9ae9 and before any page
run on it: the check of "follow the position" read eight stages, the steps of "How a position
travels" in the guide the cards took. The guide of 824c9ae9 has nine (it adds "Sight only takes
away"), and the cards take its steps word for word, so the check reads the guide's number of
steps (``GUIDE_STEPS``). Every other condition of that check stands as it was.

The earlier models (a plain composed brain, and the place module of a program beside the brain)
are not hosts of this page; their checks left with them. Their readings are in the
repository's history (evidence/page_check.json at a8b35eb). Each run's evidence goes to a file of
its own, ``evidence/page_check-<date>-<time>-<wheel>.json`` (the wheel's SHA-256, its first 8
characters), so that no run replaces another; ``--out`` names another file.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import math
import platform
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PageTimeout
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
SITE = HERE / "site"
FIXTURES = HERE / "tests" / "fixtures"
SCENES = {"default": "promise-scene.json", "merged": "promise-merged-shadows-scene.json"}
GPU = (["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] if platform.system() == "Darwin"
       else ["--enable-gpu", "--ignore-gpu-blocklist"])

# The bounds (metres). Set before the page's numbers were read; see the docstring.
IN_VIEW = 0.03       # a thing in view: the map's place within 3 cm of the true place
COVER = 0.85         # the share of hidden moments at which the hand's cells hold the true hand
RETURN = 0.03        # back in view: the last 10 moments' mean distance
OWN = 0.015          # the arm's own hand out of view, placed by its joint readings
KEEP_MOMENTS = 300   # a thing unseen keeps its place this long ...
# ... within one cell of the map (its widest side; the page reads it from the map's description)
FOUND = 0.03         # a thing moved unseen, seen again: its place within 3 cm
FRAME_MEDIAN = 20.0  # milliseconds a frame with the brain view on
FRAME_P95 = 34.0
GUIDE_STEPS = 9      # the steps of "How a position travels" in the guide the cards take (824c9ae9); eight before it


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # the check's own lines are the log
        pass


def serve(directory: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(Quiet, directory=str(directory))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/", server


class Check:
    def __init__(self, shots: Path | None) -> None:
        self.rows: list[dict] = []
        self.readings: list[dict] = []
        self.errors: list[str] = []
        self.shots = shots

    def add(self, name: str, passed: bool, **detail) -> bool:
        self.rows.append({"name": name, "passed": bool(passed), **detail})
        print(("ok    " if passed else "FAIL  ") + name, json.dumps(detail, default=str)[:420], flush=True)
        return bool(passed)

    def note(self, name: str, within: bool | None, **detail) -> None:
        """A reading that is recorded and decides nothing."""
        self.readings.append({"name": name, "within_bound": within, **detail})
        print("read  " + name, json.dumps({"within_bound": within, **detail}, default=str)[:420], flush=True)

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

JS_ROWS = "([from, to]) => window.outOfSight.state.history.filter((r) => r.moment > from && r.moment <= to)"


def mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def dist(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def ready(page, timeout_s: float) -> float:
    began = time.time()
    page.wait_for_function("document.body.dataset.ready === '1' || document.body.dataset.error", timeout=timeout_s * 1000)
    error = page.evaluate("document.body.dataset.error || null")
    if error:
        raise RuntimeError(error)
    return time.time() - began


def moment(page) -> int:
    return int(page.evaluate("window.outOfSight.state.record ? window.outOfSight.state.record.moment : 0"))


def wait_moments(page, count: int, timeout_s: float = 90.0) -> None:
    """Wait until the brain has answered ``count`` further moments; a page that stopped says why."""
    target = moment(page) + count
    page.wait_for_function(f"document.body.dataset.error || (window.outOfSight.state.history.length && window.outOfSight.state.history.at(-1).moment >= {target})",
                           timeout=timeout_s * 1000)
    error = page.evaluate("document.body.dataset.error || null")
    if error:
        raise RuntimeError(f"the page stopped: {error}")


def drag(page, name: str, points: list[list[float]], *, hold: int = 0, pace: float = 0.5) -> None:
    """Press on a thing and bring it through plane points with the mouse, as a visitor drags."""
    x, y = page.evaluate("(n) => window.outOfSight.screenOf(n)", name)
    page.mouse.move(x, y)
    page.mouse.down()
    at = page.evaluate("(n) => window.outOfSight.stage.where(n)", name)
    for target in points:
        span = dist(target, at)
        steps = max(2, int(span / pace * 30))
        for k in range(1, steps + 1):
            p = [at[0] + (target[0] - at[0]) * k / steps, at[1] + (target[1] - at[1]) * k / steps]
            page.mouse.move(*page.evaluate("(p) => window.outOfSight.screenAt(p)", p))
            page.wait_for_timeout(33)
        at = target
        page.wait_for_function("(a) => { const p = window.outOfSight.stage.where(a[0]); return Math.hypot(p[0] - a[1][0], p[1] - a[1][1]) < 0.01; }",
                               arg=[name, target], timeout=30000)
    if hold:
        wait_moments(page, hold)
    page.mouse.up()


def turn(page, sweep: float, radius: float = 0.3) -> None:
    """Drag the floor around the body through ``sweep`` radians (counter-clockwise where
    positive), as a visitor turns the camera."""
    eye, heading = page.evaluate("[window.outOfSight.stage.geometry.camera.position, window.outOfSight.stage.geometry.camera.heading]")
    at = lambda a: page.evaluate("(p) => window.outOfSight.screenAt(p)", [eye[0] + radius * math.cos(a), eye[1] + radius * math.sin(a)])
    page.mouse.move(*at(heading))
    page.mouse.down()
    steps = max(8, int(abs(sweep) / 0.06))
    for k in range(1, steps + 1):
        page.mouse.move(*at(heading + sweep * k / steps))
        page.wait_for_timeout(33)
    page.wait_for_timeout(400)
    page.mouse.up()


def turn_to(page, heading: float) -> None:
    now = page.evaluate("window.outOfSight.stage.geometry.camera.heading")
    turn(page, math.atan2(math.sin(heading - now), math.cos(heading - now)))
    page.wait_for_function("(h) => Math.abs(Math.atan2(Math.sin(window.outOfSight.stage.geometry.camera.heading - h), Math.cos(window.outOfSight.stage.geometry.camera.heading - h))) < 0.08",
                           arg=heading, timeout=20000)


def entry(page, name: str) -> dict | None:
    return page.evaluate("(n) => window.outOfSight.state.things[n] || null", name)


def promise(page, scene: str) -> dict:
    """A scene file of the chamber replayed on the page: the brain is given exactly the file's
    reports, and the page's own rule for what the camera sees gives the cells in sight."""
    data = json.loads((FIXTURES / SCENES[scene]).read_text())
    summary = page.evaluate("(d) => window.outOfSight.loadScene(d)", data)
    rows = summary["rows"]
    first = next(k for k, r in enumerate(rows) if not r["seen"])
    hidden = [r for r in rows if not r["seen"]]
    seen = [r for r in rows[:first] if r["seen"]]
    back = rows[-10:]
    states: dict[str, int] = {}
    for r in hidden:
        states[str(r["state"])] = states.get(str(r["state"]), 0) + 1
    return {"scene": scene, "file": SCENES[scene], "moments": len(rows), "hidden_moments": len(hidden),
            "in_view_m": mean([r["brain"] for r in seen]), "hidden_m": mean([r["brain"] for r in hidden]),
            "last_seen_hidden_m": mean([r["last"] for r in hidden]), "kalman_hidden_m": mean([r["kalman"] for r in hidden]),
            "hidden_last_m": hidden[-1]["brain"], "cells_hold": mean([1.0 if r["inside"] else 0.0 for r in hidden]),
            "cells_mean": mean([r["cells"] for r in hidden]), "states_hidden": states, "return_m": mean([r["brain"] for r in back]),
            "think_ms": summary.get("think_ms")}


def tour_step(page) -> str:
    return page.evaluate("document.body.dataset.tour || ''")


def wait_tour(page, step: str, timeout_s: float = 40.0) -> bool:
    try:
        page.wait_for_function(f"document.body.dataset.tour === '{step}'", timeout=timeout_s * 1000)
        return True
    except PageTimeout:
        return False


def tutorial(page, c: Check, cell: float) -> dict:
    """The tutorial's steps, performed with the mouse; what the brain did at each."""
    out: dict = {}
    page.click("#welcome-go")
    c.add("the tutorial starts at its first step", wait_tour(page, "hide", 5), step=tour_step(page))
    wait_moments(page, 10)
    # nothing is announced: the bread stands behind the body and has not been seen
    have = page.evaluate("Object.keys(window.outOfSight.state.things)")
    out["first_sight"] = {"on_the_map_at_start": have}
    bread_unseen = "bread" not in have
    c.shot(page, "tour-0-start.png")

    # 1. hide: the hand into the pillar's shadow, held there
    target = page.evaluate("window.outOfSight.shadowPoint(0.32)")
    start = moment(page)
    drag(page, "hand", [target])
    part = page.evaluate("(() => { const p = window.outOfSight.brainView.part('map'), b = document.getElementById('brain-stage').getBoundingClientRect(); return [b.left + p.x + p.w / 2, b.top + p.y + p.h / 2]; })()")
    page.mouse.move(part[0], part[1])
    page.wait_for_timeout(500)
    card = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
    c.shot(page, "tour-1-hidden-card.png")
    advanced = wait_tour(page, "return", 30)
    page.mouse.move(part[0], 40)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    hidden = [r for r in rows if not r["seen"]]
    out["hide"] = {"hidden_moments": len(hidden), "brain_m": mean([r["brain"] for r in hidden]), "last_seen_m": mean([r["last"] for r in hidden]),
                   "cells_hold": mean([1.0 if r["inside"] else 0.0 for r in hidden]), "states": sorted({str(r["state"]) for r in hidden})}
    c.add("1 hide: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.note("1 hide: the hand's place on the map while hidden (a drag's timing differs from run to run)",
           bool(hidden) and out["hide"]["brain_m"] <= out["hide"]["last_seen_m"] + 1e-9 and out["hide"]["cells_hold"] >= COVER, **out["hide"])
    c.add("1 hide: the map's card, opened while the hand is hidden, says where the map holds it and plays the role of a part",
          "plays the role of" in card and "hand" in card.lower() and ("near" in card.lower() or "last seen" in card.lower()), text=card[:400])

    # 2. return: back into the light
    start = moment(page)
    home = page.evaluate("window.outOfSight.stage.home.things[0]")
    drag(page, "hand", [home], hold=20)
    advanced = wait_tour(page, "turn", 30)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    seen = [r for r in rows if r["seen"]]
    out["return"] = {"brain_m": mean([r["brain"] for r in seen[-10:]]), "state": seen[-1]["state"] if seen else None}
    c.add("2 return: the visitor's drag completes the step", advanced, step=tour_step(page))
    c.add("2 return: back in view the map has the hand within 3 cm, as seen", out["return"]["brain_m"] is not None and out["return"]["brain_m"] <= IN_VIEW
          and out["return"]["state"] == "seen", bound_m=IN_VIEW, **out["return"])

    # 3. turn: the camera away from the apple
    apple_seen = entry(page, "apple")
    start = moment(page)
    sweep = page.evaluate("(() => { const o = window.outOfSight, h = o.stage.geometry.camera.heading, d = o.awayHeading('apple') - h; return Math.atan2(Math.sin(d), Math.cos(d)); })()")
    turn(page, sweep * 1.05)
    advanced = wait_tour(page, "own", 30)
    page.wait_for_function("(document.body.dataset.said || '').includes('apple')", timeout=15000)
    said = page.evaluate("document.body.dataset.said")
    apple = entry(page, "apple")
    rel = page.evaluate("(p) => window.outOfSight.aroundBody(p)", apple["place"]) if apple and apple.get("place") else None
    out["turn"] = {"apple_when_seen": apple_seen and apple_seen.get("place"), "apple": apple, "around": rel, "said": said,
                   "on_the_map": page.evaluate("Object.keys(window.outOfSight.state.things)")}
    c.add("3 turn: the visitor's drag of the floor completes the step", advanced, step=tour_step(page))
    c.add("3 turn: the apple, out of view behind the body, keeps its place on the map", bool(apple) and bool(apple_seen) and apple["state"] == "held"
          and dist(apple["place"], apple_seen["place"]) <= cell and rel is not None and abs(rel["bearing"]) >= math.radians(110),
          bound_m=cell, apple=apple, when_seen=apple_seen and apple_seen.get("place"), bearing_degrees=rel and round(math.degrees(rel["bearing"]), 1))
    c.add("3 turn: the page says the apple is behind the body, in one sentence", "apple" in said and "behind you" in said, said=said)
    c.add("nothing is announced: the bread is absent from the map until the camera first sees it, and present after",
          bread_unseen and "bread" in out["turn"]["on_the_map"], at_start=out["first_sight"]["on_the_map_at_start"], after_turn=out["turn"]["on_the_map"])
    c.shot(page, "tour-3-turned.png")

    # 4. the arm's own hand: the step hands the hand to the arm; a tap on the floor sends it there
    page.wait_for_function("window.outOfSight.stage.own === true", timeout=10000)
    start = moment(page)
    goal = page.evaluate("window.outOfSight.tour.current()?.guide()?.target || null")
    if goal:
        page.mouse.click(*page.evaluate("(p) => window.outOfSight.screenAt(p)", goal))
    finished = wait_tour(page, "free", 40)
    wait_moments(page, 5)
    rows = page.evaluate(JS_ROWS, [start, moment(page)])
    hidden = [r for r in rows if not r["seen"] and r["brain"] is not None]
    out["own"] = {"goal": goal, "hidden_moments": len(hidden), "brain_m": mean([r["brain"] for r in hidden]),
                  "worst_m": max([r["brain"] for r in hidden], default=None), "last_seen_m": mean([r["last"] for r in hidden]),
                  "states": sorted({str(r["state"]) for r in hidden})}
    c.add("4 own: the tap completes the tutorial, which leaves the visitor in free play", finished, step=tour_step(page))
    c.add("4 own: out of view the arm's own hand is placed by its joint readings within 1.5 cm", len(hidden) >= 20 and out["own"]["brain_m"] <= OWN,
          bound_m=OWN, **out["own"])
    c.shot(page, "tour-4-own.png")
    return out


def kept_and_moved(page, c: Check, cell: float) -> dict:
    """The apple unseen for 300 moments; then moved while the camera looks away, the camera
    turned to its old place, and the apple brought into view."""
    out: dict = {}
    page.evaluate("window.outOfSight.setCase('other')")
    apple0 = entry(page, "apple")
    wait_moments(page, KEEP_MOMENTS)
    apple1 = entry(page, "apple")
    seen = page.evaluate(f"window.outOfSight.state.history.slice(-{KEEP_MOMENTS}).some((r) => r.pins.apple && r.pins.apple.seen)")
    out["kept"] = {"before": apple0, "after": apple1, "moments": KEEP_MOMENTS, "seen_between": seen}
    c.add(f"a thing unseen keeps its place on the map within one cell for {KEEP_MOMENTS} moments", bool(apple0) and bool(apple1) and not seen
          and dist(apple0["place"], apple1["place"]) <= cell and apple1["since"] >= KEEP_MOMENTS, bound_m=cell,
          moved_m=dist(apple0["place"], apple1["place"]) if apple0 and apple1 else None, since=apple1 and apple1["since"])

    # moved while the camera looks away: into the pillar's shadow
    old = apple1["place"]
    hide = page.evaluate("window.outOfSight.shadowPoint(0.3)")
    drag(page, "apple", [hide], hold=15)
    moved = entry(page, "apple")
    c.add("a thing moved while the camera looks away keeps its old place on the map", bool(moved) and moved["state"] == "held"
          and dist(moved["place"], old) <= cell, bound_m=cell, entry=moved, old=old, true=page.evaluate("window.outOfSight.stage.where('apple')"))
    # the map answers "what is there" with the apple at its old place, where no apple stands
    page.evaluate("document.body.dataset.said = ''")
    page.mouse.click(*page.evaluate("(p) => window.outOfSight.screenAt(p)", old))
    page.wait_for_function("(document.body.dataset.said || '').length > 3", timeout=10000)
    out["what"] = page.evaluate("document.body.dataset.said")
    c.add("a tap on the floor asks the map what is there: the apple at its old place, where it was moved from unseen",
          "apple" in out["what"], said=out["what"], point=old)
    # the camera turned to the old place: seen empty
    eye = page.evaluate("window.outOfSight.stage.geometry.camera.position")
    turn_to(page, math.atan2(old[1] - eye[1], old[0] - eye[0]))
    wait_moments(page, 12)
    looked = entry(page, "apple")
    sees_old = page.evaluate("(p) => window.outOfSight.visibleAt(p)", old)
    hidden_now = not page.evaluate("window.outOfSight.state.record.in_view[window.outOfSight.stage.names.indexOf('apple')]")
    out["looked"] = {"entry": looked, "camera_sees_old_place": sees_old, "apple_out_of_view": hidden_now}
    c.add("its old place seen empty, it is near there out of sight, or not known where", sees_old and hidden_now and bool(looked)
          and (looked["state"] == "not known where" or (looked["state"] == "near" and dist(looked["place"], old) > cell)), **out["looked"])
    c.shot(page, "apple-seen-empty.png")
    # into view: found
    light = page.evaluate("(p) => window.outOfSight.litNear(p)", old)
    drag(page, "apple", [light], hold=10)
    found = entry(page, "apple")
    truth = page.evaluate("window.outOfSight.stage.where('apple')")
    entries = page.evaluate("window.outOfSight.state.inventory.filter((e) => e.name === 'apple').length")
    out["found"] = {"entry": found, "true": truth, "apple_entries": entries}
    c.add("seen again, it is found within 3 cm, one thing on the map", bool(found) and found["state"] == "seen" and dist(found["place"], truth) <= FOUND
          and entries == 1, bound_m=FOUND, off_m=dist(found["place"], truth) if found else None, **out["found"])
    return out


def questions(page, c: Check) -> dict:
    """A tap on a thing asks the map where it is; a tap on the floor where the map holds nothing
    asks what is there (the other way, where the map holds a thing, is tried with the apple moved
    unseen, in ``kept_and_moved``)."""
    out: dict = {}
    page.evaluate("window.outOfSight.setCase('other')")
    wait_moments(page, 3)
    x, y = page.evaluate("window.outOfSight.screenOf('apple')")
    page.evaluate("document.body.dataset.said = ''")
    page.mouse.click(x, y)
    page.wait_for_function("(document.body.dataset.said || '').includes('apple')", timeout=10000)
    out["where"] = page.evaluate("document.body.dataset.said")
    c.add("a tap on a thing asks the map where it is, and the page answers in one sentence", "apple" in out["where"] and "m away" in out["where"], said=out["where"])
    empty = page.evaluate("window.outOfSight.emptyFloor()")
    page.evaluate("document.body.dataset.said = ''")
    page.mouse.click(*page.evaluate("(p) => window.outOfSight.screenAt(p)", empty))
    page.wait_for_function("(document.body.dataset.said || '').length > 3", timeout=10000)
    out["nothing"] = page.evaluate("document.body.dataset.said")
    c.add("a tap on the floor where the map holds nothing: the map says nothing is there", "nothing" in out["nothing"], said=out["nothing"], point=empty)
    return out


def cards(page, c: Check) -> None:
    """Every part explains itself; the path of a position is reachable in order."""
    parts = page.evaluate("window.outOfSight.brainView.parts.map((p) => ({ id: p.id, kind: p.kind, x: p.x + p.w / 2, y: p.y + p.h / 2 }))")
    box = page.locator("#brain-stage").bounding_box()
    opened = []
    for part in parts:
        page.mouse.move(box["x"] + part["x"], box["y"] + part["y"])
        page.wait_for_timeout(90)
        text = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
        opened.append({"id": part["id"], "ok": "at this moment" in text.lower() and ("plays the role of" in text or "fibre tract" in text.lower()),
                       "clear": page.evaluate(CLEAR, [part["id"]]), "head": text.split("\n")[0][:60]})
    page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
    page.wait_for_timeout(90)
    c.add("every part of the brain explains itself on hover, with what it does at this moment", bool(opened) and all(o["ok"] for o in opened),
          parts=len(opened), missing=[o["id"] for o in opened if not o["ok"]], heads=[o["head"] for o in opened])
    c.add("a card stands beside its part, never over it", all(o["clear"] for o in opened), over=[o["id"] for o in opened if not o["clear"]])
    c.add("no card shows until the visitor points at something", page.evaluate("document.getElementById('card').hidden"))
    page.focus(".part")
    page.keyboard.press("Tab")
    page.wait_for_timeout(90)
    focused = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
    page.keyboard.press("Escape")
    closed = page.evaluate("document.getElementById('card').hidden")
    c.add("a part's card opens on keyboard focus and Escape closes it", "at this moment" in focused.lower() and closed, head=focused.split("\n")[0][:60])
    page.click("#follow")
    count = page.evaluate("window.outOfSight.stageCount()")
    stages = []
    for _ in range(count):
        page.wait_for_timeout(70)
        stages.append(page.evaluate("""() => ({ kicker: document.querySelector('#card .kicker')?.innerText || '', title: document.querySelector('#card h3')?.innerText || '',
            live: document.querySelector('#card .live')?.innerText || '', text: document.getElementById('card').innerText, spots: [...window.outOfSight.brainView.spot] })"""))
        stages[-1]["clear"] = page.evaluate(CLEAR, stages[-1]["spots"])
        if len(stages) == 3:
            c.shot(page, "follow-the-position.png")
        page.click("#card [data-go='1']")
    page.keyboard.press("Escape")
    order = [s["kicker"].upper().endswith(f"{k + 1} OF {count}") for k, s in enumerate(stages)]
    every = " ".join(s["text"] for s in stages)
    c.add(f"follow the position: {count} stages in order, each with live numbers and its part ringed beside it",
          count == GUIDE_STEPS and all(order) and all(s["title"] and "AT THIS MOMENT" in s["live"].upper() and s["spots"] and s["clear"] for s in stages),
          stages=[{"title": s["title"], "ringed": s["spots"], "beside_its_parts": s["clear"]} for s in stages])
    c.add("the stages say what the program does and what the brain does, and that the map's graph has no taught synapse",
          "The program" in every and "The brain" in every and "no taught synapse" in every)


def manners(page, c: Check, scene_file: Path | None) -> None:
    """The camera off, an emptied map, undo, reset, the details switch and a scene file."""
    # with the camera off nothing on the map changes
    x, y = page.evaluate("window.outOfSight.screenOf('camera')")
    page.mouse.click(x, y)
    wait_moments(page, 3)
    before = page.evaluate("window.outOfSight.state.inventory")
    wait_moments(page, 30)
    after = page.evaluate("window.outOfSight.state.inventory")
    dark = page.evaluate("({ on: window.outOfSight.stage.cameraOn, seen: window.outOfSight.state.record.in_view })")
    same = len(before) == len(after) and all(a["name"] == b["name"] and a["state"] in ("held", "near", "not known where") and b["state"] == a["state"]
                                             and ((a["place"] is None and b["place"] is None) or (a["place"] and b["place"] and dist(a["place"], b["place"]) == 0.0))
                                             for a, b in zip(before, after))
    c.add("with the camera off nothing on the map changes: every place stays to the bit", dark["on"] is False and not any(dark["seen"]) and bool(before) and same,
          things=len(before), before=[(e["name"], e["state"]) for e in before], after=[(e["name"], e["state"]) for e in after])
    c.shot(page, "camera-off.png")
    page.click("#reset")
    wait_moments(page, 5)
    emptied = page.evaluate("window.outOfSight.state.emptied")
    state = page.evaluate("({ on: window.outOfSight.stage.cameraOn, things: window.outOfSight.stage.world.things, home: window.outOfSight.stage.home.things })")
    c.add("reset puts everything back in one tap, and the emptied map reports no thing", state["on"] is True and state["things"] == state["home"] and emptied == [],
          camera_on=state["on"], inventory_after_reset=emptied)
    before = page.evaluate("window.outOfSight.stage.where('apple')")
    drag(page, "apple", [[before[0] + 0.15, before[1] - 0.1]])
    moved = page.evaluate("window.outOfSight.stage.where('apple')")
    page.click("#undo")
    page.wait_for_timeout(120)
    undone = page.evaluate("window.outOfSight.stage.where('apple')")
    c.add("undo takes the last move back in one tap", dist(moved, before) > 0.1 and dist(undone, before) < 1e-9, before=before, moved=moved, undone=undone)
    facing = page.evaluate("window.outOfSight.stage.where('heading')")
    turn(page, -0.9)
    wait_moments(page, 8)
    turned = page.evaluate("window.outOfSight.stage.where('heading')")
    page.click("#undo")
    wait_moments(page, 3)
    back = page.evaluate("window.outOfSight.stage.where('heading')")
    c.add("a drag of the floor turns the camera, and undo takes the turn back", abs(abs(turned - facing) - 0.9) < 0.12 and abs(back - facing) < 1e-9,
          facing=facing, turned=turned, undone=back)
    hidden = page.evaluate("document.getElementById('details-panel').hidden")
    page.click("#details")
    page.wait_for_timeout(400)
    shown = page.evaluate("({ hidden: document.getElementById('details-panel').hidden, chart: document.getElementById('chart').getBoundingClientRect().height })")
    c.add("the comparison with last seen and the Kalman filter stays behind one switch, off until asked for", hidden and not shown["hidden"] and shown["chart"] > 50, **shown)
    if scene_file and scene_file.exists():
        data = json.loads(scene_file.read_text())
        run = page.evaluate("(d) => window.outOfSight.loadScene(d)", data)
        c.add("a scene file of the tracking chamber loads and replays", run["moments"] == len(data["truth"]), file=scene_file.name, moments=run["moments"])
        c.shot(page, "details-scene-file.png")
    page.click("#details")
    page.click("#reset")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", help="a running server for site/ (default: serve it here)")
    p.add_argument("--shots", type=Path, default=None, help="save screenshots in this folder")
    p.add_argument("--scene", type=Path, default=FIXTURES / "example.json", help="a scene file to load and replay")
    p.add_argument("--timeout", type=float, default=240.0)
    p.add_argument("--out", type=Path, default=None, help="the evidence file (default: one of its own for this run)")
    a = p.parse_args()
    url, server = (a.url, None) if a.url else serve(SITE)
    c = Check((HERE / a.shots) if a.shots and not a.shots.is_absolute() else a.shots)
    manifest = json.loads((SITE / "pack" / "manifest.json").read_text())
    report: dict = {"schema": "cadence-out-of-sight-page-check/2", "checked": time.strftime("%Y-%m-%d %H:%M"), "cadence": manifest["cadence"],
                    "map": manifest.get("map"), "bounds": {"in_view_m": IN_VIEW, "hidden": "at or under last seen on the same rows", "cover": COVER,
                    "return_m": RETURN, "own_m": OWN, "keep_moments": KEEP_MOMENTS, "keep": "one cell", "found_m": FOUND,
                    "frame_median_ms": FRAME_MEDIAN, "frame_p95_ms": FRAME_P95}}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=GPU)
            # -- a desktop, with the mouse
            context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page = context.new_page()
            c.watch(page, "desktop")
            page.goto(url + "?sound=0", wait_until="domcontentloaded")
            seconds = ready(page, a.timeout)
            info = page.evaluate("({ cadence: window.outOfSight.state.describe.cadence, brain: window.outOfSight.state.describe.brain, view: window.outOfSight.brainView.stats(), neurons: window.outOfSight.state.describe.neurons, synapses: window.outOfSight.state.describe.synapses, cell: window.outOfSight.state.describe.cell })")
            report["page"] = {**info, "seconds_to_ready": round(seconds, 1)}
            cell = float(max(info["cell"]))
            c.add("the map loads in Pyodide with the pack's wheel and map file", info["cadence"] == manifest["cadence"] and info["brain"]["kind"] == "map",
                  seconds=round(seconds, 1), cadence=info["cadence"], wheel=manifest.get("wheel_source"), brain=info["brain"]["label"], view=info["view"]["mode"],
                  neurons=info["neurons"], synapses=info["synapses"], cell_m=info["cell"])
            fits = page.evaluate("({ w: document.documentElement.scrollWidth <= innerWidth, h: document.documentElement.scrollHeight <= innerHeight + 1, welcome: !document.getElementById('welcome').hidden })")
            c.add("one screen: the scene and the brain, nothing to scroll, the tutorial offered", fits["w"] and fits["h"] and fits["welcome"], **fits)
            c.shot(page, "welcome.png")
            page.evaluate("document.getElementById('welcome').hidden = true")
            # the promise on the two scene files
            report["promise"] = {}
            for scene in SCENES:
                r = promise(page, scene)
                report["promise"][scene] = r
                label = "the arm folded" if scene == "default" else "the arm's shadow joined to the pillar's"
                c.add(f"THE PROMISE ({label}): in view the map has the hand within 3 cm", r["in_view_m"] is not None and r["in_view_m"] <= IN_VIEW, bound_m=IN_VIEW, in_view_m=r["in_view_m"])
                c.add(f"THE PROMISE ({label}): hidden, the hand's place on the map at or under last seen's distance", r["hidden_m"] <= r["last_seen_hidden_m"] + 1e-9,
                      hidden_m=r["hidden_m"], last_seen_m=r["last_seen_hidden_m"], kalman_m=r["kalman_hidden_m"], states=r["states_hidden"])
                c.add(f"THE PROMISE ({label}): hidden, the hand's cells hold the true hand", r["cells_hold"] >= COVER, bound=COVER, cells_hold=r["cells_hold"], cells_mean=r["cells_mean"])
                c.add(f"THE PROMISE ({label}): back in view the map has the hand within 3 cm", r["return_m"] <= RETURN, bound_m=RETURN, return_m=r["return_m"])
            c.shot(page, "promise-replayed.png")
            page.click("#reset")
            wait_moments(page, 5)
            page.evaluate("try { localStorage.removeItem('out-of-sight-tour'); } catch (e) {}; document.getElementById('welcome').hidden = false")
            report["tutorial"] = tutorial(page, c, cell)
            frames = page.evaluate("window.outOfSight.frameStats(1500)")
            think = page.evaluate("(() => { const t = window.outOfSight.state.think.slice().sort((a, b) => a - b), r = window.outOfSight.state.roundTrip.slice().sort((a, b) => a - b); return { think_ms: t[t.length >> 1], round_trip_ms: r[r.length >> 1], moments: window.outOfSight.state.moments }; })()")
            report["frames"] = {"desktop_webgl": frames, **think}
            c.add("frame time with the brain view on, over the tutorial", frames["median_ms"] <= FRAME_MEDIAN and frames["p95_ms"] <= FRAME_P95,
                  bound_median_ms=FRAME_MEDIAN, bound_p95_ms=FRAME_P95, **frames, **think)
            report["questions"] = questions(page, c)
            report["kept_and_moved"] = kept_and_moved(page, c, cell)
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
            before = page.evaluate("window.outOfSight.stage.where('heading')")
            page.evaluate("""async () => { const el = document.getElementById('scene'), b = el.getBoundingClientRect(), cx = b.left + b.width * 0.5, cy = b.top + b.height * 0.3, r = 50;
                const fire = (type, id, a) => el.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', isPrimary: id === 31, bubbles: true,
                  clientX: cx + r * Math.cos(a), clientY: cy - r * Math.sin(a) }));
                fire('pointerdown', 31, Math.PI); fire('pointerdown', 32, 0);
                for (let k = 1; k <= 20; k++) { const a = (k / 20) * (Math.PI / 3); fire('pointermove', 31, Math.PI + a); fire('pointermove', 32, a); await new Promise((r2) => setTimeout(r2, 30)); }
                fire('pointerup', 31, Math.PI + Math.PI / 3); fire('pointerup', 32, Math.PI / 3); }""")
            wait_moments(page, 12)
            after = page.evaluate("window.outOfSight.stage.where('heading')")
            twisted = math.atan2(math.sin(after - before), math.cos(after - before))
            c.add("on a phone two fingers twist the camera", abs(twisted - math.pi / 3) < 0.1, turned_degrees=round(math.degrees(twisted), 1))
            page.click("#reset")
            wait_moments(page, 6)
            part = page.evaluate("(() => { const p = window.outOfSight.brainView.part('map'), b = document.getElementById('brain-stage').getBoundingClientRect(); return [b.left + p.x + p.w / 2, b.top + p.y + p.h / 2]; })()")
            page.touchscreen.tap(part[0], part[1])
            page.wait_for_timeout(200)
            text = page.evaluate("document.getElementById('card').hidden ? '' : document.getElementById('card').innerText")
            c.shot(page, "phone.png")
            above = page.evaluate("""(() => { const v = window.outOfSight.brainView, card = document.getElementById('card').getBoundingClientRect(), stage = document.getElementById('brain-stage').getBoundingClientRect();
                return { brain_bottom: stage.top + v.brainBox.y + v.brainBox.h, sheet_top: card.top, brain_height: v.brainBox.h, sheet: document.body.classList.contains('sheet') }; })()""")
            c.add("on a phone the card is a sheet from the bottom and the brain stays visible above it",
                  above["sheet"] and above["brain_bottom"] <= above["sheet_top"] + 2 and above["brain_height"] >= 110, **above)
            page.touchscreen.tap(60, 200)
            page.wait_for_timeout(150)
            closed = page.evaluate("document.getElementById('card').hidden")
            c.add("on a phone a tap on a part opens its card and a tap elsewhere closes it", "at this moment" in text.lower() and closed, card=text.split("\n")[0][:60], closed=closed)
            report["frames"]["phone_viewport"] = page.evaluate("window.outOfSight.frameStats(300)")
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
    report["readings"] = c.readings
    report["checks"] = c.rows
    report["passed"] = all(row["passed"] for row in c.rows)
    report["failed"] = [row["name"] for row in c.rows if not row["passed"]]
    out = a.out or HERE / "evidence" / f"page_check-{time.strftime('%Y%m%d-%H%M')}-{manifest['wheel_sha256'][:8]}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(("PASS" if report["passed"] else "FAIL") + f": {sum(r['passed'] for r in c.rows)} of {len(c.rows)} checks; evidence in {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
