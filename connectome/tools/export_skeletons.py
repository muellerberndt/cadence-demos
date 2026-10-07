#!/usr/bin/env python3
"""Export the zebrafish brainstem skeletons as the brain view's payload.

Reads the resampled SWC skeletons of the Zfish_recon release and the MATLAB files that
name the 609 classified cells (ZConnectome) and the 2,884-cell order of the synapse count
matrix (AllCells, ConnMatrixPre_cleaned as [post, pre]), and writes

    web/data/skeletons.json (+ skeletons.json.gz)   every cell that has a skeleton
    web/data/neuron_order.json                      the matrix order on its own

Each cell carries its id, class (one of the six, or "periphery"), its index in the matrix
order (-1 when the matrix does not hold it), its synapse totals, and its nodes as a flat
list of coordinates with a parent index per node (-1 for the root, which is node 0): every
node with a parent is one line segment. A live activity vector, one float per neuron in
the matrix order, maps to skeletons through ``index``.

The frame: the whole set centred at the origin and scaled uniformly so the longest axis
spans 2.0. The axes are permuted into the anatomical view that a least-squares fit of the
classified cells' root positions against their Zbrain atlas positions gives: x from left to
right, y from posterior to anterior (anterior up), z from ventral to dorsal (dorsal toward
the viewer, assuming the atlas z grows ventrally). The payload records the transform.

Nodes are kept as the files give them unless the JSON would exceed the budget; then every
unbranched run keeps only every k-th node (roots, branch points and tips always stay) with
the smallest k that fits, and the payload records the decimation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io as sio

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "connectome-research" / "data" / "zebrafish_brainstem"
SKELETONS = DATA / "Zfish_recon" / "skeletons" / "combinedConsensus-resampled"
ZCONNECTOME = DATA / "Zfish_recon" / "matFiles" / "ZConnectome_04292021.mat"
ALL_CELLS = DATA / "Connectome-Model" / "data" / "AllCells.mat"
MATRIX = DATA / "Connectome-Model" / "data" / "ConnMatrixPre_cleaned.mat"
OUT_PATH = ROOT / "web" / "data" / "skeletons.json"
ORDER_PATH = ROOT / "web" / "data" / "neuron_order.json"
FORMAT = "cadence.zebrafish-skeletons/v1"
BUDGET_MB = 15.0
DECIMALS = 4
SPAN = 2.0  # the longest axis in the viewer's frame
FILE_PATTERN = re.compile(r"^(\d+)_reRoot_reSample_5000\.swc$")

CLASSES = ["_Int_", "_Axl_", "_DOs_", "ABD_m", "ABD_i", "vSPNs", "periphery"]
LABELS = {
    "_Int_": "integrator", "_Axl_": "axial", "_DOs_": "DO", "ABD_m": "abducens motor",
    "ABD_i": "abducens internuclear", "vSPNs": "vSPN", "periphery": "periphery",
}
# EM (x, y, z) to the view frame: x = EM y (left to right), y = EM x (anterior up), z = -EM z (dorsal toward the viewer)
VIEW_AXES = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def read_swc(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One skeleton: node coordinates, parents as 0-based positions (-1 for the root) and
    radii, in an order with the root first and every parent before its children."""
    a = np.loadtxt(path, comments="#", ndmin=2)
    ids = a[:, 0].astype(np.int64)
    position = {int(i): k for k, i in enumerate(ids)}
    parent = np.array([-1 if p < 0 else position[int(p)] for p in a[:, 6]], dtype=np.int64)
    xyz = a[:, 2:5].astype(np.float64)
    radius = a[:, 5].astype(np.float64)
    roots = np.flatnonzero(parent < 0)
    if len(roots) != 1:
        raise ValueError(f"{path.name}: {len(roots)} roots")
    ordered = all(parent[k] < k for k in range(len(parent)))
    if not ordered:
        order = topological(parent, int(roots[0]))
        rank = np.empty(len(order), dtype=np.int64)
        rank[order] = np.arange(len(order))
        parent = np.array([-1 if parent[i] < 0 else rank[parent[i]] for i in order], dtype=np.int64)
        xyz, radius = xyz[order], radius[order]
    return xyz, parent, radius


def topological(parent: np.ndarray, root: int) -> np.ndarray:
    """Breadth-first order from the root, so every parent precedes its children."""
    children: dict[int, list[int]] = {}
    for i, p in enumerate(parent):
        if p >= 0:
            children.setdefault(int(p), []).append(i)
    order = [root]
    at = 0
    while at < len(order):
        order.extend(children.get(order[at], []))
        at += 1
    if len(order) != len(parent):
        raise ValueError("skeleton is not one tree")
    return np.array(order, dtype=np.int64)


def decimate(parent: np.ndarray, factor: int) -> np.ndarray:
    """Which nodes to keep: the root, every branch point and tip, and every ``factor``-th
    node along an unbranched run. Needs parents before children."""
    n = len(parent)
    keep = np.ones(n, dtype=bool)
    if factor <= 1:
        return keep
    children = np.zeros(n, dtype=np.int64)
    for p in parent:
        if p >= 0:
            children[p] += 1
    keep = (parent < 0) | (children != 1)
    steps = np.zeros(n, dtype=np.int64)
    for i in range(n):
        p = parent[i]
        if p < 0 or keep[i]:
            continue
        d = steps[p] + 1
        if d >= factor:
            keep[i] = True
            d = 0
        steps[i] = d
    return keep


def apply_keep(xyz: np.ndarray, parent: np.ndarray, keep: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The kept nodes with parents remapped to the nearest kept ancestor."""
    n = len(parent)
    ancestor = np.empty(n, dtype=np.int64)
    for i in range(n):
        ancestor[i] = i if keep[i] else ancestor[parent[i]]
    new_index = np.cumsum(keep) - 1
    kept = np.flatnonzero(keep)
    new_parent = np.array([-1 if parent[i] < 0 else new_index[ancestor[parent[i]]] for i in kept], dtype=np.int64)
    return xyz[kept], new_parent


def atlas_fit(roots: dict[int, np.ndarray], z: Any) -> dict[str, Any]:
    """A least-squares affine map from EM root positions to the Zbrain positions of the
    classified cells: the evidence for the view frame's axis assignment."""
    have = [k for k, c in enumerate(z.cellID) if int(c) in roots]
    X = np.array([roots[int(z.cellID[k])] for k in have])
    Y = np.asarray(z.origin)[have]
    A = np.c_[X, np.ones(len(X))]
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = np.sqrt(((A @ coef - Y) ** 2).sum(axis=1))
    linear = coef[:3]
    strongest = [int(np.argmax(np.abs(linear[:, j]))) for j in range(3)]
    sign = [float(np.sign(linear[strongest[j], j])) for j in range(3)]
    return {
        "cells": int(len(have)),
        "em_to_atlas": [[round(float(v), 8) for v in row] for row in coef.T.tolist()],
        "median_residual_um": round(float(np.median(resid)), 3),
        "p90_residual_um": round(float(np.percentile(resid, 90)), 3),
        "em_axis_of_atlas_axis": {"x (left-right)": "xyz"[strongest[0]] + ("+" if sign[0] > 0 else "-"),
                                   "y (anterior-posterior)": "xyz"[strongest[1]] + ("+" if sign[1] > 0 else "-"),
                                   "z (dorsal-ventral)": "xyz"[strongest[2]] + ("+" if sign[2] > 0 else "-")},
        "note": "atlas (x, y, z) = em @ em_to_atlas[:3].T + em_to_atlas[3], in Zbrain micrometres; the strongest coefficient per atlas axis names the EM axis",
    }


def build(budget_mb: float = BUDGET_MB, decimals: int = DECIMALS, skeletons: Path = SKELETONS) -> tuple[dict[str, Any], dict[str, Any], str]:
    t0 = time.time()
    z = sio.loadmat(ZCONNECTOME, squeeze_me=True, struct_as_record=False)["ZConnectome"]
    all_cells = sio.loadmat(ALL_CELLS, squeeze_me=True)["AllCells"].astype(np.int64)
    matrix = sio.loadmat(MATRIX, squeeze_me=True)["ConnMatrixPre_cleaned"]
    if matrix.shape != (len(all_cells), len(all_cells)):
        raise ValueError(f"matrix {matrix.shape} does not match {len(all_cells)} cells")
    class_of = {int(c): str(t) for c, t in zip(z.cellID, z.cellType)}
    unknown = sorted(set(class_of.values()) - set(CLASSES))
    if unknown:
        raise ValueError(f"unknown classes {unknown}")
    index_of = {int(c): k for k, c in enumerate(all_cells)}
    syn_in = matrix.sum(axis=1).astype(np.int64)  # synapses received, over every presynaptic cell
    syn_out = matrix.sum(axis=0).astype(np.int64)  # synapses given, over every postsynaptic cell

    # 1. every skeleton, in cell id order
    files = []
    for path in sorted(skeletons.iterdir()):
        m = FILE_PATTERN.match(path.name)
        if m:
            files.append((int(m.group(1)), path))
    files.sort()
    raw = []
    for cell_id, path in files:
        xyz, parent, radius = read_swc(path)
        raw.append((cell_id, xyz, parent, radius))
    nodes_before = sum(len(xyz) for _, xyz, _, _ in raw)

    # 2. the frame: centre, uniform scale, anatomical axes
    stacked = np.concatenate([xyz for _, xyz, _, _ in raw])
    lo, hi = stacked.min(axis=0), stacked.max(axis=0)
    centre = (lo + hi) / 2
    scale = SPAN / float((hi - lo).max())
    longest = "xyz"[int(np.argmax(hi - lo))]
    to_view = lambda xyz: ((xyz - centre) * scale) @ VIEW_AXES.T  # noqa: E731
    roots_em = {cell_id: xyz[0] for cell_id, xyz, _, _ in raw}

    # 3. the cells, decimated only if the JSON would exceed the budget; the loop stops at the
    # floor (roots, branch points and tips) when even that does not fit
    factor = 0
    previous_nodes = None
    while True:
        factor += 1
        cells = []
        nodes_after = 0
        for cell_id, xyz, parent, radius in raw:
            keep = decimate(parent, factor)
            kept_xyz, kept_parent = apply_keep(xyz, parent, keep)
            view = np.round(to_view(kept_xyz), decimals)
            nodes_after += len(view)
            k = index_of.get(cell_id, -1)
            cells.append({
                "id": cell_id,
                "class": class_of.get(cell_id, "periphery"),
                "index": k,
                "syn_in": int(syn_in[k]) if k >= 0 else 0,
                "syn_out": int(syn_out[k]) if k >= 0 else 0,
                "root_radius_em": round(float(radius[0]), 1),
                "n": int(len(view)),
                "xyz": [float(v) for v in view.reshape(-1)],
                "parent": [int(p) for p in kept_parent],
            })
        counts = Counter(c["class"] for c in cells)
        payload = {
            "format": FORMAT,
            "source": {
                "skeletons": str(skeletons.relative_to(DATA)) if skeletons.is_relative_to(DATA) else str(skeletons),
                "classes": str(ZCONNECTOME.relative_to(DATA)),
                "order": str(ALL_CELLS.relative_to(DATA)),
                "matrix": str(MATRIX.relative_to(DATA)) + " [post, pre]",
            },
            "classes": CLASSES,
            "labels": LABELS,
            "transform": {
                "note": "view = ((em - centre_em) * scale) @ axes.T; em in the SWC units; the longest axis spans 2.0",
                "centre_em": [float(v) for v in centre],
                "scale": scale,
                "axes": VIEW_AXES.tolist(),
                "view_axes": {"x": "EM y, left to right", "y": "EM x, posterior to anterior (anterior up)", "z": "EM -z, ventral to dorsal (dorsal toward the viewer)"},
                "bbox_em": [[float(v) for v in lo], [float(v) for v in hi]],
                "extent_em": [float(v) for v in hi - lo],
                "longest_axis_em": longest,
                "decimals": decimals,
            },
            "atlas_fit": atlas_fit(roots_em, z),
            "decimation": {"factor": factor, "nodes_before": nodes_before, "nodes_after": nodes_after,
                           "rule": "every factor-th node along unbranched runs; roots, branch points and tips stay"},
            "counts": {
                "skeletons": len(cells), "nodes": nodes_after, "segments": nodes_after - len(cells),
                "classes": {c: int(counts.get(c, 0)) for c in CLASSES},
                "classified": sum(1 for c in cells if c["class"] != "periphery"),
                "classified_without_skeleton": int(sum(1 for c in z.cellID if int(c) not in roots_em)),
                "in_matrix": sum(1 for c in cells if c["index"] >= 0),
                "unmatched": sum(1 for c in cells if c["index"] < 0),
                "matrix_neurons": int(len(all_cells)),
            },
            "order": [int(c) for c in all_cells],
            "cells": cells,
        }
        text = json.dumps(payload, separators=(",", ":"))
        payload["decimation"]["budget_mb"] = budget_mb
        payload["decimation"]["budget_met"] = len(text) <= budget_mb * 1e6
        if payload["decimation"]["budget_met"]:
            break
        if previous_nodes is not None and nodes_after >= previous_nodes:
            print(f"warning: {len(text) / 1e6:.2f} MB at the decimation floor (factor {factor}) exceeds the {budget_mb} MB budget", file=sys.stderr)
            break
        previous_nodes = nodes_after
    payload["counts"]["json_bytes"] = len(text)
    payload["counts"]["seconds"] = round(time.time() - t0, 1)
    text = json.dumps(payload, separators=(",", ":"))

    # 4. the matrix order on its own, with the skeleton and class of every neuron
    skeleton_of = {c["index"]: k for k, c in enumerate(cells) if c["index"] >= 0}
    order = {
        "format": "cadence.zebrafish-order/v1",
        "n": int(len(all_cells)),
        "source": payload["source"]["order"] + "; " + payload["source"]["matrix"],
        "note": "activity[i] belongs to cell_ids[i]; skeleton[i] is its position in skeletons.json's cells, or -1",
        "cell_ids": [int(c) for c in all_cells],
        "class": [class_of.get(int(c), "periphery") for c in all_cells],
        "skeleton": [skeleton_of.get(k, -1) for k in range(len(all_cells))],
    }
    return payload, order, text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--order", type=Path, default=ORDER_PATH)
    ap.add_argument("--skeletons", type=Path, default=SKELETONS)
    ap.add_argument("--budget-mb", type=float, default=BUDGET_MB)
    ap.add_argument("--decimals", type=int, default=DECIMALS)
    args = ap.parse_args()
    if not args.skeletons.is_dir():
        sys.exit(f"no skeleton folder at {args.skeletons}")
    payload, order, text = build(args.budget_mb, args.decimals, args.skeletons)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    gz_path = args.out.with_suffix(args.out.suffix + ".gz")
    with gzip.GzipFile(gz_path, "wb", compresslevel=9, mtime=0) as f:
        f.write(text.encode("utf-8"))
    order_text = json.dumps(order, separators=(",", ":"))
    args.order.write_text(order_text)

    c, d, t = payload["counts"], payload["decimation"], payload["transform"]
    print(f"{'class':<10} {'label':<22} {'skeletons':>9}")
    for name in CLASSES:
        print(f"{name:<10} {LABELS[name]:<22} {c['classes'][name]:>9,}")
    print(f"\nskeletons {c['skeletons']:,} ({c['classified']:,} classified, {c['classified_without_skeleton']} classified cells have no skeleton); "
          f"{c['in_matrix']:,} in the {c['matrix_neurons']:,}-cell matrix order, {c['unmatched']} not")
    print(f"nodes {d['nodes_before']:,} before decimation, {d['nodes_after']:,} after (factor {d['factor']}); segments {c['segments']:,}")
    print(f"frame: extent em {[round(v) for v in t['extent_em']]}, longest {t['longest_axis_em']}, scale {t['scale']:.3e}, {t['decimals']} decimals")
    fit = payload["atlas_fit"]
    print(f"atlas fit over {fit['cells']} cells: median residual {fit['median_residual_um']} um, p90 {fit['p90_residual_um']} um; EM axis per atlas axis {fit['em_axis_of_atlas_axis']}")
    print(f"wrote {args.out} ({len(text) / 1e6:.2f} MB), {gz_path} ({gz_path.stat().st_size / 1e6:.2f} MB), "
          f"{args.order} ({len(order_text) / 1e3:.0f} kB) in {c['seconds']} s")


if __name__ == "__main__":
    main()
