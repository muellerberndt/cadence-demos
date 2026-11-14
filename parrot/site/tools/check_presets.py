"""Every candidate question about the demo room's things, asked through the page's own trained-brain host
(parrotbrain.trained.Host.meaning_op, the ops app.js sends: a look at the thing in focus, begin, the words one
a moment with the voice held, the turn), for each candidate brain; several passes in shuffled order. A
question goes on the page as a preset only if a brain answers it right on every pass.

    python tools/check_presets.py WHEEL_DIR ROOM_THINGS.json OUT.json BRAIN_DIR [BRAIN_DIR ...]

WHEEL_DIR: the page's wheel unpacked. ROOM_THINGS.json: the page's things as its trained brain sees them
({id, kind, direction, distance}, read from the page).
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(SITE / "pack" / "py"))
from parrotbrain.trained import Host  # noqa: E402

ROOM, OUT = json.loads(Path(sys.argv[2]).read_text()), Path(sys.argv[3])
BRAINS = [Path(b) for b in sys.argv[4:]]
PASSES = 3
WORLD = {"apple": ("apple", "red", "fruit"), "ball": ("ball", "white", "cloth"), "cup": ("cup", "white", "glass"),
         "banana": ("banana", "yellow", "fruit"), "block": ("block", "blue", "wood"), "key": ("key", "yellow", "metal"),
         "greenball": ("ball", "green", "plastic"), "lemon": ("lemon", "yellow", "fruit")}
ROUND = {"apple", "ball", "cup", "lemon"}
DIRS = ["front", "right", "behind", "left"]
COLOURS = ["red", "green", "blue", "yellow", "white", "black"]


def direction_word(d):  # app.js expected(): a quarter each, front within 45 degrees, positive to its left
    return DIRS[int(((((-d + math.pi / 4) % (2 * math.pi)) + 2 * math.pi) % (2 * math.pi)) // (math.pi / 2))]


def things(focus_id):  # app.js trainedThings(): the focus first, then the nearest, five at most
    rows = []
    for t in ROOM:
        k, c, m = WORLD[t["kind"]]
        rows.append({"id": t["id"], "kind": k, "colour": c, "material": m, "direction": t["direction"], "distance": t["distance"], "focus": t["id"] == focus_id})
    rows.sort(key=lambda r: (not r["focus"], r["distance"]))
    return rows[:5]


def questions():
    out = []
    for t in ROOM:
        kind, colour, material = WORLD[t["kind"]]
        other = COLOURS[(COLOURS.index(colour) + 1) % len(COLOURS)]
        rnd = kind in ROUND
        out += [("what is this", [kind], t["id"], "name"),
                (f"what colour has the {kind}", [colour], t["id"], "colour_of"),
                ("what colour is this", [colour], t["id"], "colour_this"),
                (f"is this {colour}", ["yes"], t["id"], "is_colour"),
                (f"is this {other}", ["no"], t["id"], "is_colour"),
                (f"what shape has the {kind}", ["round" if rnd else "no"], t["id"], "shape_of"),
                ("is this round", ["yes" if rnd else "no"], t["id"], "is_round"),
                ("can you eat this", ["yes" if material == "fruit" else "no"], t["id"], "can_eat"),
                (f"where is the {kind}", [direction_word(t["direction"])], t["id"], "direction"),
                ("what material is this", [material], t["id"], "material")]
    return out


def ask(h, q, focus):
    seen = things(focus)
    op = lambda **kw: h.meaning_op({**kw, "things": seen, "glimpse": None})  # noqa: E731
    op(op="look"); op(op="begin")
    for w in q.split():
        op(op="moment", hear=w, more=True)
    said = []
    for _ in range(3):
        r = op(op="moment", hear=None, more=False)
        if not r.get("said") and said:
            break
        if r.get("said") and (not said or said[-1] != r["said"]):
            said.append(r["said"])
    if not said:
        op(op="over")
    return said


report = {}
for folder in BRAINS:
    began = time.time()
    h = Host({"host_files": str(folder), "files": str(SITE / "pack"), "whole": "page", "genes": {"map_cells": 32}, "eye": {"w": 64, "h": 32}})
    qs, rows, rng = questions(), {}, np.random.default_rng(5)
    for _ in range(PASSES):
        for i in rng.permutation(len(qs)):
            q, want, focus, form = qs[i]
            r = rows.setdefault(f"{q} | {focus}", {"q": q, "focus": focus, "form": form, "want": want, "said": []})
            r["said"].append(ask(h, q, focus))
    for r in rows.values():
        r["right"] = sum(s == r["want"] for s in r["said"])
    by_form = {}
    for r in rows.values():
        f = by_form.setdefault(r["form"], [0, 0]); f[0] += r["right"] == PASSES; f[1] += 1
    score = float(np.mean([r["right"] == PASSES for r in rows.values()]))
    report[folder.name] = {"all_right": round(score, 3), "by_form": by_form, "rows": list(rows.values()), "s": round(time.time() - began)}
    print(folder.name, round(score, 3), json.dumps(by_form), flush=True)
    OUT.write_text(json.dumps(report, indent=1))
