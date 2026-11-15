"""Prepare a parrot body for the page's rig: one .glb in the parrot's frame, with skin weights on the
rig's bones, and a rig file with the bones and the eye sockets fitted to the body.

    python tools/prepare_look.py --src BODY.glb --name realistic --height 0.30 --grip 0.17 --dz -0.045 [--texture 2048]

The source is a textured mesh of a perched African Grey (one primitive; a decimated copy is fine).
`height`, `grip` (where the feet grip, a fraction of the height from the lowest point) and `dx`/`dz`
place it on the perch as look.html does. The tool then:
  1. finds the dowel the body grips (a cylinder along x under the feet), fits its axis and radius,
     removes its faces, and moves the body so that axis is the perch bar's (the page's bar takes
     the dowel's radius);
  2. finds the beak (dark, in front of the head), the pupils (dark, either side of the head) and the
     tail (red), from the body's colour texture at each vertex;
  3. places the rig's bones on the body and gives every vertex weights on them: head, neck, body,
     upper and lower mandible, tail, the wings (a lift of each wing's side), legs and toes;
  4. writes site/looks/<name>.glb (textures at --texture pixels at most) and site/looks/<name>.rig.json.
Everything is geometry and colour rules, stated here; it reads no labels.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

SITE = Path(__file__).resolve().parents[1]
BAR_Y = 0.13


def read_glb(path: Path):
    b = path.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + n])
    off = 20 + n
    blen = struct.unpack("<I", b[off:off + 4])[0]
    blob = b[off + 8: off + 8 + blen]

    def view(i):
        v = g["bufferViews"][i]
        return blob[v.get("byteOffset", 0): v.get("byteOffset", 0) + v["byteLength"]]

    def acc(i):
        a = g["accessors"][i]
        v = g["bufferViews"][a["bufferView"]]
        comp = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride")
        itemsize = np.dtype(comp).itemsize * width
        if stride and stride != itemsize:
            raw = np.frombuffer(blob, np.uint8, count=stride * a["count"], offset=start).reshape(a["count"], stride)[:, :itemsize]
            return np.frombuffer(raw.tobytes(), comp).reshape(a["count"], width)
        return np.frombuffer(blob, comp, count=a["count"] * width, offset=start).reshape(a["count"], width)

    prim = g["meshes"][0]["primitives"][0]
    at = prim["attributes"]
    pos = acc(at["POSITION"]).astype(np.float64)
    nor = acc(at["NORMAL"]).astype(np.float64) if "NORMAL" in at else None
    uv = acc(at["TEXCOORD_0"]).astype(np.float64)
    idx = acc(prim["indices"]).astype(np.int64).reshape(-1, 3)
    # a node transform on the mesh (gltfpack may leave one)
    for node in g.get("nodes", []):
        if node.get("mesh") == 0:
            s = np.array(node.get("scale", [1, 1, 1]), float)
            t = np.array(node.get("translation", [0, 0, 0]), float)
            if "rotation" in node and np.abs(np.array(node["rotation"]) - [0, 0, 0, 1]).max() > 1e-6:
                raise SystemExit("a rotated mesh node is not handled")
            pos = pos * s + t
    mat = g["materials"][prim.get("material", 0)]
    pbr = mat.get("pbrMetallicRoughness", {})
    images = {}
    for key, ref in (("base", pbr.get("baseColorTexture")), ("mr", pbr.get("metallicRoughnessTexture")), ("normal", mat.get("normalTexture"))):
        if ref is None:
            continue
        img = g["images"][g["textures"][ref["index"]]["source"]]
        images[key] = Image.open(io.BytesIO(view(img["bufferView"]))).convert("RGB")
    return pos, nor, uv, idx, images, mat


def vertex_normals(pos, idx):
    n = np.zeros_like(pos)
    f = np.cross(pos[idx[:, 1]] - pos[idx[:, 0]], pos[idx[:, 2]] - pos[idx[:, 0]])
    for k in range(3):
        np.add.at(n, idx[:, k], f)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def sample(img: Image.Image, uv: np.ndarray) -> np.ndarray:
    a = np.asarray(img, dtype=np.float32) / 255.0
    h, w = a.shape[:2]
    x = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)  # glTF uv: v down from the image's top
    return a[y, x]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def fit_circle(y, z):
    A = np.stack([y, z, np.ones_like(y)], 1)
    rhs = -(y * y + z * z)
    D, E, F = np.linalg.lstsq(A, rhs, rcond=None)[0]
    yc, zc = -D / 2, -E / 2
    return yc, zc, math.sqrt(max(yc * yc + zc * zc - F, 1e-12))


def write_glb(path: Path, pos, nor, uv, joints, weights, idx, images, mat):
    parts, views, accessors = [], [], []

    def add(data: bytes, target=None):
        off = sum(len(p) for p in parts)
        parts.append(data + b"\x00" * ((4 - len(data) % 4) % 4))
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            v["target"] = target
        views.append(v)
        return len(views) - 1

    def accessor(arr, comp, typ, target, minmax=False):
        a = {"bufferView": add(arr.tobytes(), target), "componentType": comp, "count": len(arr), "type": typ}
        if minmax:
            a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        accessors.append(a)
        return len(accessors) - 1

    attrs = {"POSITION": accessor(pos.astype(np.float32), 5126, "VEC3", 34962, True),
             "NORMAL": accessor(nor.astype(np.float32), 5126, "VEC3", 34962),
             "TEXCOORD_0": accessor(uv.astype(np.float32), 5126, "VEC2", 34962),
             "JOINTS_0": accessor(joints.astype(np.uint16), 5123, "VEC4", 34962),
             "WEIGHTS_0": accessor(weights.astype(np.float32), 5126, "VEC4", 34962)}
    ind = accessor(idx.astype(np.uint32).reshape(-1), 5125, "SCALAR", 34963)
    gimages, textures = [], []
    for key, (img, quality) in images.items():
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=quality, optimize=True)
        gimages.append({"bufferView": add(buf.getvalue()), "mimeType": "image/jpeg"})
        textures.append({"source": len(gimages) - 1, "sampler": 0})
    order = list(images)
    material = {"name": mat.get("name", "body"), "pbrMetallicRoughness": {"baseColorTexture": {"index": order.index("base")}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "doubleSided": False}
    if "mr" in images:
        material["pbrMetallicRoughness"]["metallicRoughnessTexture"] = {"index": order.index("mr")}
        material["pbrMetallicRoughness"]["metallicFactor"] = 1.0
    if "normal" in images:
        material["normalTexture"] = {"index": order.index("normal")}
    blob = b"".join(parts)
    gltf = {"asset": {"version": "2.0", "generator": "parrot prepare_look.py"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"name": "parrot_body", "mesh": 0}],
            "meshes": [{"name": "parrot_body", "primitives": [{"attributes": attrs, "indices": ind, "material": 0}]}],
            "materials": [material], "textures": textures, "images": gimages,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * ((4 - len(text) % 4) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + blob
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--height", type=float, default=0.30)
    ap.add_argument("--grip", type=float, default=0.2)
    ap.add_argument("--dx", type=float, default=0.0)
    ap.add_argument("--dz", type=float, default=0.0)
    ap.add_argument("--texture", type=int, default=2048)
    ap.add_argument("--normal-texture", type=int, default=2048)
    args = ap.parse_args()
    rig = json.loads((SITE / "rig.json").read_text())
    pos, nor, uv, idx, images, mat = read_glb(args.src)
    # 1. onto the perch, as look.html places it; the parrot's frame has the bar's axis at the origin
    lo, hi = pos.min(0), pos.max(0)
    size = hi - lo
    k = args.height / size[1]
    c = (lo + hi) / 2
    p = np.empty_like(pos)
    p[:, 0] = (pos[:, 0] - c[0]) * k + args.dx
    p[:, 1] = (pos[:, 1] - lo[1] - args.grip * size[1]) * k
    p[:, 2] = (pos[:, 2] - c[2]) * k + args.dz
    n = vertex_normals(p, idx) if nor is None else nor / np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-12)
    # the dowel: points near the bar's axis, out at the dowel's ends beyond the feet
    near = (np.hypot(p[:, 1], p[:, 2]) < 0.035)
    xmax = np.abs(p[near, 0]).max()
    ends = near & (np.abs(p[:, 0]) > 0.72 * xmax)
    yc, zc, r = fit_circle(p[ends, 1], p[ends, 2])
    radial = np.stack([np.zeros(len(p)), p[:, 1] - yc, p[:, 2] - zc], 1)
    dist = np.linalg.norm(radial[:, 1:], axis=1)
    radial /= np.maximum(dist, 1e-9)[:, None]
    outward = (n * radial).sum(1)
    cap = (np.abs(p[:, 0]) > xmax - 0.012) & (np.abs(n[:, 0]) > 0.6)
    dowel_v = (dist < r * 1.12) & (np.abs(p[:, 0]) <= xmax + 0.002) & ((outward > 0.3) | cap)
    keep_f = ~dowel_v[idx].all(1)
    print(f"dowel: axis y {yc:+.4f} z {zc:+.4f} radius {r:.4f} half-length {xmax:.3f}; removed {(~keep_f).sum()} of {len(idx)} faces")
    idx = idx[keep_f]
    used = np.unique(idx)
    remap = -np.ones(len(p), np.int64); remap[used] = np.arange(len(used))
    p, n, uv, idx = p[used], n[used], uv[used], remap[idx]
    # what is left of the dowel: pieces of the mesh (connected along its edges) that lie wholly in
    # the dowel's box, apart from the body; a flat plank's faces stand off a round fit's surface
    box = (np.abs(p[:, 0]) <= xmax + 0.004) & (np.abs(p[:, 1] - yc) <= 1.6 * r) & (np.abs(p[:, 2] - zc) <= 1.6 * r)
    # vertices at one place are one (a texture's seams split them in the file)
    _, weld = np.unique(np.round(p / 2e-5).astype(np.int64), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    e = weld[np.concatenate([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]])]
    _, wl = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(weld.max() + 1, weld.max() + 1)), directed=False)
    lab = wl[weld]
    inside = np.bincount(lab, weights=box.astype(float), minlength=lab.max() + 1)
    total = np.bincount(lab, minlength=lab.max() + 1)
    drop_piece = (inside >= 0.98 * total)
    # and a plank fused to the feet: its faces have the dowel's own colour, a flat brownish grey
    # (red over blue by more than 0.04, middling light), where the toes are neutral grey and dark
    col0 = sample(images["base"], uv)
    plank = box & (col0[:, 0] - col0[:, 2] > 0.04) & (col0.mean(1) > 0.22) & (col0.mean(1) < 0.5)
    keep_f = ~drop_piece[lab[idx[:, 0]]] & ~(plank[idx].sum(1) >= 2)
    print(f"dowel remnants: {int(drop_piece.sum())} pieces, {(~keep_f).sum()} faces removed; {int((total > 0).sum())} pieces in all")
    idx = idx[keep_f]
    used = np.unique(idx)
    remap = -np.ones(len(p), np.int64); remap[used] = np.arange(len(used))
    p, n, uv, idx = p[used], n[used], uv[used], remap[idx]
    p[:, 1] -= yc; p[:, 2] -= zc
    bar_r = float(np.clip(r, 0.009, 0.02))
    # 2. colour landmarks: dark patches of the head, found as connected pieces of the mesh
    col = sample(images["base"], uv)
    lum = col @ np.array([0.2126, 0.7152, 0.0722])
    top = p[:, 1].max()
    headish = p[:, 1] > top - 0.08

    def pieces(mask):
        """Connected pieces of the masked vertices (along the mesh's edges), largest first."""
        _, wv = np.unique(np.round(p / 2e-5).astype(np.int64), axis=0, return_inverse=True)
        wv = wv.reshape(-1)
        e = np.concatenate([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]])
        e = e[mask[e[:, 0]] & mask[e[:, 1]]]
        m = wv.max() + 1
        g = coo_matrix((np.ones(len(e)), (wv[e[:, 0]], wv[e[:, 1]])), shape=(m, m))
        _, wl = connected_components(g, directed=False)
        lab = wl[wv]
        lab = np.where(mask, lab, -1)
        ids, counts = np.unique(lab[lab >= 0], return_counts=True)
        return [lab == i for i in ids[np.argsort(-counts)]]

    # the eyes: the pale yellow irises, two groups of pieces either side of the head
    yellow = headish & (col[:, :2].mean(1) - col[:, 2] > 0.07) & (col.mean(1) > 0.45)
    irises = [m for m in pieces(yellow) if m.sum() >= 6]
    if len(irises) < 2:
        raise SystemExit("no eyes found")
    cents = np.array([p[m].mean(0) for m in irises]); sizes = np.array([m.sum() for m in irises], float)
    a, b = cents[0], cents[1]
    for _ in range(20):  # two groups (k-means, k = 2), weighted by size
        ga = np.linalg.norm(cents - a, axis=1) <= np.linalg.norm(cents - b, axis=1)
        a = (cents[ga] * sizes[ga, None]).sum(0) / sizes[ga].sum(); b = (cents[~ga] * sizes[~ga, None]).sum(0) / sizes[~ga].sum()
    eye_masks = [np.any([irises[i] for i in np.flatnonzero(ga)], 0), np.any([irises[i] for i in np.flatnonzero(~ga)], 0)]
    em = (a + b) / 2
    ee = (b - a) * [1, 0, 1]; ee /= np.linalg.norm(ee)
    dark = headish & (lum < 0.2)
    dc = p[dark].mean(0) - em
    f = (dc - ee * (dc @ ee)) * [1, 0, 1]; f /= np.linalg.norm(f)
    yaw0 = math.atan2(f[0], f[2])
    # The head as generated is turned by yaw0. Its geometry stays as it is: the head bone takes that
    # turn as its rest (head_rest_yaw in the rig), so head_yaw 0 faces forward through the bone and the
    # whole head and beak turn rigidly. The head's pivot sits under and behind the eyes, placed so that
    # turning the head back by yaw0 about it brings the eyes over the body's middle.
    ang = -yaw0
    pz = float((em - f * 0.022)[2]); py = float(em[1] - 0.027)
    if abs(1 - math.cos(ang)) > 1e-3:
        px = -(math.cos(ang) * em[0] + math.sin(ang) * (em[2] - pz) - math.cos(ang) * 0.0) / (1 - math.cos(ang))
        px = float(np.clip(px, -0.03, 0.03))
    else:
        px = float(em[0])
    pivot = np.array([px, py, pz])

    def turn(v, t, about=pivot):
        """Turn points (or directions, with about=0) about the vertical axis through `about` by t radians."""
        d = v - about
        c, s_ = math.cos(t), math.sin(t)
        out = d.copy()
        out[..., 0] = c * d[..., 0] + s_ * d[..., 2]
        out[..., 2] = -s_ * d[..., 0] + c * d[..., 2]
        return out + about

    # Turn the head back to face forward, rigidly: the whole head and beak by yaw0 (masks found in the
    # head's own frame before the turn), the turn fading out only down the neck, over 4 cm.
    hq = turn(p, -yaw0)
    em_q = turn(em, -yaw0)
    nh0 = np.array([0.0, 1.0, 0.35]); nh0 /= np.linalg.norm(nh0)
    above0 = (hq - pivot) @ nh0 + 0.8 * np.clip(hq[:, 2] - em_q[2], 0, None)
    beak0 = dark & (hq[:, 2] > em_q[2] + 0.004) & (np.abs(hq[:, 0]) < 0.02) & (hq[:, 1] < em_q[1] + 0.012)
    share = smooth(-0.045, -0.004, above0)
    share[beak0] = 1.0
    if abs(yaw0) > math.radians(2):
        c, s_ = np.cos(-yaw0 * share), np.sin(-yaw0 * share)
        d = p - pivot
        p = p.copy(); n = n.copy()
        p[:, 0] = pivot[0] + c * d[:, 0] + s_ * d[:, 2]; p[:, 2] = pivot[2] - s_ * d[:, 0] + c * d[:, 2]
        nx, nz = n[:, 0].copy(), n[:, 2].copy()
        n[:, 0] = c * nx + s_ * nz; n[:, 2] = -s_ * nx + c * nz
    print(f"head turned {math.degrees(yaw0):+.1f} deg as made: turned back rigidly about {np.round(pivot, 4)}, fading down the neck; eyes now at x {em_q[0] * 1000:+.1f} mm")
    yaw0 = 0.0
    hq, nq, em_q = p, n, np.mean([p[m].mean(0) for m in eye_masks], 0)
    pivot = np.array([em_q[0], py, em_q[2] - 0.022])  # the head's pivot, now under the head's middle
    px, pz = float(pivot[0]), float(pivot[2])
    beak = dark & (hq[:, 2] > em_q[2] + 0.004) & (np.abs(hq[:, 0]) < 0.02) & (hq[:, 1] < em_q[1] + 0.012)
    if beak.sum() < 30:
        raise SystemExit("no beak found")
    bz0, bz1 = np.percentile(hq[beak, 2], [3, 99.5]); by0, by1 = np.percentile(hq[beak, 1], [0.5, 99])
    eyes = {}
    for m in eye_masks:
        cen = p[m].mean(0)
        axis = n[m].mean(0); axis /= np.linalg.norm(axis)
        name = "eye_l" if turn(cen, -yaw0)[0] > 0 else "eye_r"
        yaw = math.degrees(math.atan2(axis[0], axis[2]))
        eyes[name] = {"bone": "head", "at": [round(float(v), 5) for v in cen - axis * 0.004], "yaw": round(yaw, 1)}
        print(f"{name}: at {np.round(cen, 4)} axis yaw {yaw:.1f} deg at rest ({yaw - math.degrees(yaw0):+.1f} in the head's frame), {m.sum()} iris vertices")
    if set(eyes) != {"eye_l", "eye_r"}:
        raise SystemExit("both eyes on one side")
    red = (col[:, 0] > 0.45) & (col[:, 1] < 0.28) & (col[:, 2] < 0.28) & (p[:, 1] < 0.03)
    # 3. bones on the body (the head's bones in the head's frame, then turned to its rest)
    head = pivot
    neck = np.array([px, py - 0.036, pz - 0.012])
    body = np.array([0.0, 0.04, neck[2] - 0.02])
    def half_width(y0, band=0.01):
        m = np.abs(p[:, 1] - y0) < band
        return np.percentile(np.abs(p[m, 0]), 98) if m.sum() > 20 else 0.04
    sh_y = neck[1] - 0.012
    shoulder = np.array([0.72 * half_width(sh_y), sh_y, neck[2] - 0.012])
    elbow = shoulder + np.array([0.008, -0.03, -0.03])
    wrist = elbow + np.array([0.0, -0.02, -0.02])
    tail_top = p[red].max(0) if red.sum() > 20 else np.array([0, -0.01, -0.05])
    tail = np.array([0.0, min(0.02, float(tail_top[1])), float(np.median(p[red, 2])) if red.sum() > 20 else -0.05])
    feet = {}
    for side, sgn in (("l", 1), ("r", -1)):
        m = (np.hypot(p[:, 1], p[:, 2]) < bar_r + 0.012) & (np.sign(p[:, 0]) == sgn) & (np.abs(p[:, 0]) < 0.06)
        fx = float(np.median(p[m, 0])) if m.sum() > 20 else 0.016 * sgn
        feet[side] = fx
    lower_hinge = turn(np.array([em_q[0], by0 + 0.38 * (by1 - by0), bz0 + 0.12 * (bz1 - bz0)]), yaw0)
    upper_hinge = turn(np.array([em_q[0], by1 - 0.15 * (by1 - by0), bz0]), yaw0)
    at = {"root": [0, 0, 0], "body": body, "tail": tail, "neck": neck, "head": head, "upper_mandible": upper_hinge, "lower_mandible": lower_hinge,
          "wing_l_shoulder": shoulder, "wing_l_elbow": elbow, "wing_l_wrist": wrist,
          "wing_r_shoulder": shoulder * [-1, 1, 1], "wing_r_elbow": elbow * [-1, 1, 1], "wing_r_wrist": wrist * [-1, 1, 1],
          "leg_l": [feet["l"], 0.034, 0.002], "leg_r": [feet["r"], 0.034, 0.002],
          "foot_l": [feet["l"], bar_r + 0.0015, 0.0], "foot_r": [feet["r"], bar_r + 0.0015, 0.0]}
    bones = [{"name": b["name"], "parent": b["parent"], "at": [round(float(v), 5) for v in np.asarray(at[b["name"]], float)]} for b in rig["bones"]]
    names = [b["name"] for b in rig["bones"]] + [f"toe_{s}_{t['n']}{seg}" for s in "lr" for t in rig["toes"]["toes"] for seg in "abc"]
    B = {nm: i for i, nm in enumerate(names)}
    # weights
    N = len(p)
    W = {}
    def put(name, w):
        W[name] = W.get(name, 0) + w
    # the head and the beak rigid on the head bone: everything above a plane under the eyes that tilts
    # down toward the beak (the beak hangs below the eyes), in the head's own frame; the neck blends below
    nh = np.array([0.0, 1.0, 0.35]); nh /= np.linalg.norm(nh)
    above = (hq - pivot) @ nh + 0.8 * np.clip(hq[:, 2] - em_q[2], 0, None)
    # straight ramps (an even twist down the neck, as its many vertebrae share a turn): the head's bone
    # from 3 cm under the eyes' plane up to it, the neck's from 7.5 cm to 3.5 cm under it
    ramp = lambda a, b, x: np.clip((x - a) / (b - a), 0.0, 1.0)
    # the turn is the neck's, so what lies far from the neck's axis (the shoulders, the chest) keeps out of it
    r_axis = np.hypot(p[:, 0] - pivot[0], p[:, 2] - pivot[2])
    near_axis = ramp(0.05, 0.032, r_axis)
    w_head = ramp(-0.035, -0.004, above)
    w_head[beak] = 1.0
    low = ramp(-0.075, -0.035, above)  # into the neck from the shoulders; what the head leaves above is the neck's
    w_neck = np.where(above >= -0.035, 1.0 - w_head, low * (near_axis + (1 - near_axis) * low))
    w_neck = np.clip(w_neck, 0, 1) * (1 - beak)
    rest = 1.0 - w_head - w_neck
    # the lower mandible (hinged at the beak's corner), rigid: the dark beak below its cutting edge,
    # behind the hook, its faces looking down or sideways; the upper beak stays with the head
    bz = (hq[:, 2] - bz0) / max(bz1 - bz0, 1e-6)
    lower = beak & (hq[:, 1] < by0 + 0.45 * (by1 - by0)) & (bz < 0.75) & (nq[:, 1] < 0.25)
    w_lower = lower.astype(float)
    w_upper = np.zeros(len(p))
    w_head = w_head * (1 - w_lower)
    # the tail: red, behind and below the bar
    w_tail = (red | ((p[:, 1] < -0.01) & (p[:, 2] < -0.025))).astype(float) * smooth(0.0, -0.025, p[:, 1])
    # the wings: each side's outer face from the shoulder down, a lift of the folded wing
    wings = {}
    for side, sgn in (("l", 1), ("r", -1)):
        uniq, inv = np.unique(np.round(p[:, 1] / 0.005).astype(int), return_inverse=True)
        widths = np.array([half_width(u * 0.005, 0.006) for u in uniq])[inv]
        # wide, smooth bands of position only (no normals, which jump across the feathers' relief)
        lateral = smooth(0.2, 0.9, sgn * p[:, 0] / np.maximum(widths, 1e-3))
        vertical = smooth(sh_y + 0.02, sh_y - 0.03, p[:, 1]) * smooth(-0.06, 0.02, p[:, 1])
        behind = smooth(neck[2] + 0.04, neck[2] - 0.02, p[:, 2])
        wings[side] = np.clip(lateral * vertical * behind, 0, 1) * (1 - w_head - w_neck).clip(0, 1)
    # the feet and legs: what lies on the bar is the foot; what wraps under it, the toes
    ang = np.degrees(np.arctan2(np.abs(p[:, 2]), p[:, 1]))  # 0 at the bar's top, 180 under it
    onbar = smooth(bar_r + 0.02, bar_r + 0.008, np.hypot(p[:, 1], p[:, 2]))
    feet_w = {}
    for side, sgn in (("l", 1), ("r", -1)):
        m = onbar * smooth(0.035, 0.02, np.abs(p[:, 0] - feet[side]))
        f = m * smooth(0.035, 0.012, p[:, 1])
        toe = m * smooth(35.0, 70.0, ang)
        front = toe * (p[:, 2] >= 0)
        back = toe * (p[:, 2] < 0)
        feet_w[side] = (f * (1 - toe), front, back)
    # assemble: up to four influences, normalized
    infl = np.zeros((N, len(names)), np.float32)
    infl[:, B["head"]] += w_head; infl[:, B["neck"]] += w_neck
    infl[:, B["lower_mandible"]] += w_lower; infl[:, B["upper_mandible"]] += w_upper
    body_w = np.clip(rest, 0, 1)
    for side in "lr":
        wing = wings[side]
        infl[:, B[f"wing_{side}_shoulder"]] += wing * smooth(sh_y - 0.06, sh_y - 0.02, p[:, 1])
        infl[:, B[f"wing_{side}_wrist"]] += wing * (1 - smooth(sh_y - 0.06, sh_y - 0.02, p[:, 1]))
        body_w = body_w * (1 - wing)
        f, front, back = feet_w[side]
        infl[:, B[f"foot_{side}"]] += f
        infl[:, B[f"toe_{side}_2a"]] += front
        infl[:, B[f"toe_{side}_1a"]] += back
        body_w = body_w * (1 - np.clip(f + front + back, 0, 1))
    infl[:, B["tail"]] += body_w * w_tail
    infl[:, B["body"]] += body_w * (1 - w_tail)
    # vertices at one place (split by the texture's seams) take one set of weights, so no seam opens
    _, weld = np.unique(np.round(p / 2e-5).astype(np.int64), axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    sums = np.zeros((weld.max() + 1, infl.shape[1]), np.float64)
    np.add.at(sums, weld, infl)
    infl = (sums / np.bincount(weld)[:, None])[weld].astype(np.float32)
    # the lower mandible cut free of the upper along the gape: a face is the jaw's when two of its
    # corners are; corners shared with the head's faces are doubled, so the beak opens without
    # stretching a face, and the mouth's dark inside shows (a dark plug in the head, below)
    jaw_face = lower[idx].sum(1) >= 2
    shared = np.zeros(len(p), bool)
    shared[np.unique(idx[jaw_face])] = True
    on_head = np.zeros(len(p), bool); on_head[np.unique(idx[~jaw_face])] = True
    dup = np.flatnonzero(shared & on_head)
    new_index = np.arange(len(p)); new_index[dup] = len(p) + np.arange(len(dup))
    idx = np.where(jaw_face[:, None], new_index[idx], idx)
    p = np.concatenate([p, p[dup]]); n = np.concatenate([n, n[dup]]); uv = np.concatenate([uv, uv[dup]])
    jaw_row = np.zeros(infl.shape[1], np.float32); jaw_row[B["lower_mandible"]] = 1.0
    infl = np.concatenate([infl, np.repeat(jaw_row[None], len(dup), 0)])
    jaw_v = np.zeros(len(p), bool); jaw_v[np.unique(idx[jaw_face])] = True
    infl[jaw_v] = jaw_row
    head_row = np.zeros(infl.shape[1], np.float32); head_row[B["head"]] = 1.0
    stray = ~jaw_v & (infl[:, B["lower_mandible"]] > 0)
    infl[stray] = head_row
    print(f"jaw: {int(jaw_face.sum())} faces cut free along {len(dup)} doubled corners")
    # smooth how the head, the neck and the body share each vertex, along the mesh (so no rule's edge
    # leaves a step from one vertex to the next), holding the skull and beak above the eyes' plane
    # rigid; the jaw's faces and the jaw's vertices take no part
    cols = [B["head"], B["neck"], B["body"]]
    S = infl[:, cols].sum(1)
    F = np.where(S[:, None] > 1e-6, infl[:, cols] / np.maximum(S, 1e-6)[:, None], 0.0)
    _, wv = np.unique(np.round(p / 2e-5).astype(np.int64), axis=0, return_inverse=True)
    wv = wv.reshape(-1).copy()
    wv[jaw_v] = wv.max() + 1 + np.arange(int(jaw_v.sum()))  # the jaw welds to nothing
    m = wv.max() + 1
    e = idx[~jaw_face]
    e = np.concatenate([e[:, [0, 1]], e[:, [1, 2]], e[:, [2, 0]]])
    a, b = wv[e[:, 0]], wv[e[:, 1]]
    A = coo_matrix((np.ones(2 * len(a)), (np.concatenate([a, b]), np.concatenate([b, a]))), shape=(m, m)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    Fm = np.zeros((m, 3)); cnt = np.bincount(wv, minlength=m).astype(float)
    np.add.at(Fm, wv, F); Fm /= np.maximum(cnt, 1)[:, None]
    above_full = np.concatenate([above, above[dup]])
    beak_full = np.concatenate([beak, beak[dup]])
    fixed = np.zeros(m, bool)
    np.logical_or.at(fixed, wv, jaw_v | beak_full | (above_full >= -0.004) | (S < 1e-6))
    held = Fm[fixed].copy()
    for _ in range(30):
        Fm = 0.5 * Fm + 0.5 * (A @ Fm) / np.maximum(deg, 1)[:, None]
        Fm[fixed] = held
    infl[:, cols] = (Fm[wv] * S[:, None]).astype(np.float32)
    order = np.argsort(-infl, axis=1)[:, :4]
    wts = np.take_along_axis(infl, order, 1)
    wts /= np.maximum(wts.sum(1, keepdims=True), 1e-9)
    wts[wts.sum(1) == 0, 0] = 1.0
    counts = {nm: int((order[:, 0] == i).sum()) for nm, i in B.items() if (order[:, 0] == i).any()}
    print("vertices by strongest bone:", counts)
    # 4. write
    out = SITE / "looks"
    out.mkdir(exist_ok=True)
    def scaled(img, size):
        if max(img.size) > size:
            img = img.resize((size, size), Image.LANCZOS)
        return img
    imgs = {"base": (scaled(images["base"], args.texture), 88)}
    if "mr" in images:
        imgs["mr"] = (scaled(images["mr"], 1024), 85)
    if "normal" in images:
        imgs["normal"] = (scaled(images["normal"], args.normal_texture), 90)
    write_glb(out / f"{args.name}.glb", p, n, uv, order, wts, idx, imgs, mat)
    mouth = np.array([em_q[0], by0 + 0.5 * (by1 - by0), bz0 + 0.12 * (bz1 - bz0)])
    eyes["mouth"] = {"bone": "head", "at": [round(float(v), 5) for v in mouth], "yaw": 0.0, "radius": round(float(0.32 * (by1 - by0)), 5)}
    fitted = {"bar_radius": round(bar_r, 5), "bones": bones, "sockets": eyes, "toe_rest": "closed", "wing_mode": "lift", "wing_lift": 0.0, "toe_open": 0.25,
              "head_rest_yaw": 0.0,
              "source": {"glb": args.src.name, "height": args.height, "grip": args.grip, "dx": args.dx, "dz": args.dz}}
    (out / f"{args.name}.rig.json").write_text(json.dumps(fitted, indent=1) + "\n")
    print(f"wrote looks/{args.name}.glb ({(out / f'{args.name}.glb').stat().st_size / 1e6:.2f} MB, {len(p)} vertices, {len(idx)} faces) and looks/{args.name}.rig.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
