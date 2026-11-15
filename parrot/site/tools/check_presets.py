"""Every question phrase of the parrot's starting memory, asked of the demo room's things through the page's own
trained-brain host (parrotbrain.trained.Host.meaning_op, the ops app.js sends: a look at the thing in focus,
begin, the words of the phrase's meaning one a moment with the voice held, the turn), several passes in
shuffled order. A phrase's meaning is the question its brain was taught ("What colour?" and "What colour is
this?" both mean "what colour is this"; "Where is it?" means "where is the <thing in focus>"). A phrase goes on
the page as a preset, with its thing in focus, only if the brain answers it right on every pass.

    python tools/check_presets.py WHEEL_DIR ROOM_THINGS.json PHRASES.json OUT.json [--passes N] [--presets] [BRAIN_DIR ...]

WHEEL_DIR: the page's wheel unpacked. ROOM_THINGS.json: the page's things as its trained brain sees them
({id, kind, direction, distance}, read from the page). PHRASES.json: {"phrases": {key: {text, meaning}},
"presets": [{key, focus}]}. --presets: the presets alone (each with its thing in focus).
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1]
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
PASSES = int(sys.argv[sys.argv.index("--passes") + 1]) if "--passes" in sys.argv else 3
if "--passes" in sys.argv:
    argv.remove(str(PASSES))
sys.path.insert(0, argv[0]); sys.path.insert(0, str(SITE / "pack" / "py"))
from parrotbrain.trained import Host  # noqa: E402

ROOM, SPEC, OUT = json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()), Path(argv[3])
BRAINS = [Path(b) for b in argv[4:]] or [SITE / "pack" / "trained"]
WORLD = {"apple": ("apple", "red", "fruit"), "ball": ("ball", "white", "cloth"), "cup": ("cup", "white", "glass"),
         "banana": ("banana", "yellow", "fruit"), "block": ("block", "blue", "wood"), "key": ("key", "yellow", "metal"),
         "greenball": ("ball", "green", "plastic"), "lemon": ("lemon", "yellow", "fruit")}
ROUND = {"apple", "ball", "cup", "lemon"}
DIRS = ["front", "right", "behind", "left"]


def direction_word(d):  # app.js expected(): a quarter each, front within 45 degrees, positive to its left
    return DIRS[int(((((-d + math.pi / 4) % (2 * math.pi)) + 2 * math.pi) % (2 * math.pi)) // (math.pi / 2))]


def things(focus_id):  # app.js trainedThings(): the focus first, then the nearest, five at most
    rows = []
    for t in ROOM:
        k, c, m = WORLD[t["kind"]]
        rows.append({"id": t["id"], "kind": k, "colour": c, "material": m, "direction": t["direction"], "distance": t["distance"], "focus": t["id"] == focus_id})
    rows.sort(key=lambda r: (not r["focus"], r["distance"]))
    return rows[:5]


def expected(words, t):
    kind, colour, material = WORLD[t["kind"]]
    if words[:3] == ["what", "is", "this"]: return kind
    if words[:2] == ["what", "colour"]: return colour
    if words[:2] == ["what", "shape"]: return "round" if kind in ROUND else "no"  # its voice has no word for another shape
    if words[0] == "where": return direction_word(t["direction"])
    if words[:3] == ["can", "you", "eat"]: return "yes" if material == "fruit" else "no"
    if words[:2] == ["is", "this"]: return "yes" if (words[2] == "round" and kind in ROUND) or words[2] == colour else "no"
    if words[:2] == ["what", "material"]: return material
    return None


def questions():
    out = []
    if "--presets" in sys.argv:
        pairs = [(p["key"], p.get("focus")) for p in SPEC["presets"]]
    else:
        pairs = [(k, None) for k in SPEC["phrases"]]
    for key, focus in pairs:
        meaning = SPEC["phrases"][key]["meaning"]
        for t in ROOM:
            kind = WORLD[t["kind"]][0]
            words = meaning.replace("<this>", kind).split()
            named = [w for w in words[3:] if w in {v[0] for v in WORLD.values()}]  # a question that names its thing
            if (named and named[0] != kind) or (focus and t["kind"] != focus):
                continue
            want = expected(words, t)
            if want is not None:
                out.append((key, " ".join(words), want, t["id"]))
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
    return " ".join(said)


report = {}
for folder in BRAINS:
    began = time.time()
    h = Host({"host_files": str(folder), "files": str(SITE / "pack"), "whole": "page", "genes": {"map_cells": 32}, "eye": {"w": 64, "h": 32}})
    qs, rows, rng = questions(), {}, np.random.default_rng(5)
    for _ in range(PASSES):
        for i in rng.permutation(len(qs)):
            key, q, want, focus = qs[i]
            r = rows.setdefault(f"{key} | {focus}", {"phrase": key, "text": SPEC["phrases"][key]["text"], "meaning": q, "focus": focus, "want": want, "said": []})
            r["said"].append(ask(h, q, focus))
    for r in rows.values():
        r["right"] = sum(s == r["want"] for s in r["said"])
    score = float(np.mean([r["right"] == PASSES for r in rows.values()]))
    report[folder.name] = {"passes": PASSES, "all_right": round(score, 3), "rows": list(rows.values()), "s": round(time.time() - began)}
    print(folder.name, "right on every pass:", sum(r["right"] == PASSES for r in rows.values()), "of", len(rows), flush=True)
    for r in rows.values():
        if r["right"] < PASSES:
            print("  ", r["text"], "|", r["focus"], "| want", r["want"], "| said", r["said"], flush=True)
    OUT.write_text(json.dumps(report, indent=1))
