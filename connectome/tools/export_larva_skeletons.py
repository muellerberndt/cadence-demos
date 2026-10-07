"""The larva's cells for the brain view: skeleton polylines for the neurons and effectors
(CATMAID compact-detail nodes), a single point for every other cell (its root), in the
viewer's payload format and in the order of web/data/larva_brain.json."""
from __future__ import annotations

import gzip, json, os, time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("CONNECTOME_DATA", str(ROOT.parent / "connectome-research" / "data"))) / "platynereis"
CLASSES = ["sensory", "inter", "motor", "muscle", "ciliated", "gland", "other"]
LABELS = {"sensory": "sensory neuron", "inter": "interneuron", "motor": "motor neuron", "muscle": "muscle", "ciliated": "ciliated cell", "gland": "gland", "other": "other cell"}
COLORS = {"sensory": [120, 255, 170], "inter": [0, 255, 65], "motor": [255, 220, 80], "muscle": [255, 120, 80], "ciliated": [90, 200, 255], "gland": [220, 120, 255], "other": [110, 130, 115]}
BUDGET_NODES = 300000


def class_of(kind: str, role: str) -> str:
    k = kind.lower()
    if role in ("sensory", "inter", "motor"):
        return role
    if role == "effector":
        return "ciliated" if any(w in k for w in ("troch", "cilia")) else "gland" if "gland" in k else "muscle"
    return "other"


def main() -> None:
    t0 = time.time()
    brain = json.loads((ROOT / "web" / "data" / "larva_brain.json").read_text())
    ids, kinds, roles = brain["id"], brain["kind"], brain["role"]
    roots = {int(k): v for k, v in json.loads((DATA / "roots.json").read_text()).items() if isinstance(v, dict) and "x" in v}
    cells, nodes_total = [], 0
    for index, (cid, kind, role) in enumerate(zip(ids, kinds, roles)):
        cls = class_of(kind, role)
        path = DATA / "skeletons" / f"{cid}.json"
        if path.exists():
            nodes = json.loads(path.read_text())
            if not nodes:
                continue
            node_index = {n[0]: j for j, n in enumerate(nodes)}
            xyz = np.array([[n[3], n[4], n[5]] for n in nodes], dtype=float)
            parent = np.array([node_index.get(n[1], -1) if n[1] is not None else -1 for n in nodes], dtype=int)
        elif cid in roots:
            r = roots[cid]; xyz = np.array([[r["x"], r["y"], r["z"]]], dtype=float); parent = np.array([-1])
        else:
            continue
        cells.append({"id": int(cid), "class": cls, "index": index, "n": int(len(xyz)), "xyz": xyz, "parent": parent})
        nodes_total += len(xyz)
    # decimate the longest polylines evenly if the node budget is exceeded
    factor = max(1, int(np.ceil(nodes_total / BUDGET_NODES)))
    if factor > 1:
        for c in cells:
            if c["n"] > 2 * factor:
                keep = np.zeros(c["n"], dtype=bool); keep[::factor] = True; keep[0] = True
                old = np.flatnonzero(keep); remap = {o: j for j, o in enumerate(old)}
                parent = c["parent"]
                new_parent = []
                for o in old:
                    p = parent[o]
                    while p >= 0 and p not in remap:
                        p = parent[p]
                    new_parent.append(remap.get(p, -1) if p >= 0 else -1)
                c["xyz"] = c["xyz"][old]; c["parent"] = np.array(new_parent); c["n"] = len(old)
    allxyz = np.concatenate([c["xyz"] for c in cells])
    centre = (allxyz.min(0) + allxyz.max(0)) / 2; extent = allxyz.max(0) - allxyz.min(0); scale = 2.0 / extent.max()
    out_cells = []
    for c in cells:
        p = (c["xyz"] - centre) * scale
        # view axes: x left-right (EM x), y anterior up (EM -y), z toward the viewer (EM -z)
        v = np.stack([p[:, 0], -p[:, 1], -p[:, 2]], axis=1)
        out_cells.append({"id": c["id"], "class": c["class"], "index": c["index"], "syn_in": 0, "syn_out": 0, "root_radius_em": 0.0, "n": c["n"], "xyz": [round(float(x), 4) for x in v.ravel()], "parent": [int(x) for x in c["parent"]]})
    counts = Counter(c["class"] for c in out_cells)
    payload = {"format": "cadence.zebrafish-skeletons/v1", "source": {"order": "web/data/larva_brain.json", "skeletons": "CATMAID project 11 compact-detail nodes, root points for cells without one"},
               "classes": CLASSES, "labels": LABELS, "colors": COLORS,
               "transform": {"note": "centred, longest axis 2.0; view x = EM x, y = -EM y, z = -EM z", "centre_em": [float(x) for x in centre], "scale": float(scale), "extent_em": [float(x) for x in extent]},
               "decimation": {"factor": factor, "nodes_before": nodes_total},
               "counts": {"skeletons": sum(1 for c in out_cells if c["n"] > 1), "points": sum(1 for c in out_cells if c["n"] == 1), "nodes": sum(c["n"] for c in out_cells), "segments": sum(c["n"] - 1 for c in out_cells), "classes": dict(counts), "matrix_neurons": len(ids)},
               "order": [int(i) for i in ids], "cells": out_cells}
    text = json.dumps(payload, separators=(",", ":"))
    (ROOT / "web" / "data" / "larva_skeletons.json").write_text(text)
    with gzip.open(ROOT / "web" / "data" / "larva_skeletons.json.gz", "wb") as f:
        f.write(text.encode())
    print(f"larva view: {payload['counts']['skeletons']} skeletons, {payload['counts']['points']} points, {payload['counts']['nodes']:,} nodes (factor {factor}), classes {dict(counts)}, {len(text)//1024} KB, {time.time()-t0:.1f} s")


if __name__ == "__main__":
    main()
