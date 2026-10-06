"""The brain as the standard Cadence brain view draws it: modules as grids and an atlas.

``layout`` describes every population as a grid of feature maps (from the run's declared
anatomy); ``atlas_for`` builds the standard view's atlas with one named region per module.
"""

from __future__ import annotations

import numpy as np
from cadence import Brain

LABELS = {
    "visual/input": "Retina",
    "visual/v1": "V1",
    "visual/v2": "V2",
    "visual/v3": "V4",
    "visual/output": "V1",
    "association": "Superior colliculus map",
    "prefrontal": "Frontal eye field (memory)",
    "motor": "Gaze: horizontal | vertical",
}


def _stage_maps(anatomy: dict | None, size: int) -> dict[str, int]:
    """Feature maps per visual stage from the run's declared anatomy."""
    if not anatomy:
        return {}
    if "stages" in anatomy:
        return {f"visual/v{k + 1}": int(s["features"]) for k, s in enumerate(anatomy["stages"])}
    if "features" in anatomy:
        return {"visual/output": int(anatomy["features"])}
    return {}


def layout(brain: Brain, bins: int, anatomy: dict | None = None) -> list[dict]:
    """Populations as 2D grids for the 3D view: name, label, neuron range, maps and grid side."""
    pops = brain.connectome.populations
    order = [n for n in ("visual/input", "visual/v1", "visual/output", "visual/v2", "visual/v3",
                         "association", "prefrontal", "motor") if n in pops]
    declared = _stage_maps(anatomy, bins)
    out = []
    for name in order:
        idx = np.asarray(pops[name])
        size = idx.size
        if name == "motor":
            maps, side_y, side_x = 2, 1, size // 2
        elif name == "visual/input":
            maps = int((anatomy or {}).get("channels", 1))
            side = int(round(np.sqrt(size // maps)))
            side_y = side_x = side
        elif name in ("association", "prefrontal"):
            side = int(round(np.sqrt(size)))
            maps, side_y, side_x = (1, side, side) if side * side == size else (1, 1, size)
        else:
            maps = declared.get(name, 0)
            if not maps:
                for m in (4, 8, 16, 32, 64):
                    if size % m == 0 and int(round(np.sqrt(size // m))) ** 2 == size // m:
                        maps = m
                        break
            side = int(round(np.sqrt(size // max(maps, 1))))
            side_y = side_x = side
        out.append({"name": name, "label": LABELS.get(name, name), "start": int(idx[0]),
                    "size": int(size), "maps": int(maps), "rows": int(side_y), "cols": int(side_x)})
    return out


REGIONS = {
    "visual/input": ("Retina", "vision"),
    "visual/v1": ("V1 visual cortex", "vision"),
    "visual/output": ("V1 visual cortex", "vision"),
    "visual/v2": ("V2 visual cortex", "vision"),
    "visual/v3": ("V4 visual cortex", "vision"),
    "association": ("Superior colliculus association map", "association"),
    "prefrontal": ("Frontal eye field prefrontal trace", "memory"),
}


def atlas_for(brain: Brain, layout_: list[dict], lines: int = 15000) -> dict:
    """The standard brain view's atlas of this brain: one region per module, sheets as grids,
    feature maps tiled map by map, the gaze slots split into horizontal and vertical."""
    from .atlas import build_atlas

    regions, roles, shapes, positions = {}, {}, {}, {}
    for p in layout_:
        idx = np.arange(p["start"], p["start"] + p["size"])
        if p["name"] == "motor":
            half = p["size"] // 2
            for part, name in ((idx[:half], "Horizontal gaze motor"), (idx[half:], "Vertical gaze motor")):
                regions[name], roles[name], shapes[name] = part, "motor", (1, half)
            continue
        name, role = REGIONS.get(p["name"], (p["name"], "other"))
        regions[name], roles[name] = idx, role
        if p["maps"] == 1 and p["rows"] * p["cols"] == p["size"]:
            shapes[name] = (p["rows"], p["cols"])
        else:
            tiles = int(np.ceil(np.sqrt(p["maps"])))
            k = np.arange(p["size"])
            m, rest = np.divmod(k, p["rows"] * p["cols"])
            r, c = np.divmod(rest, p["cols"])
            x = (m % tiles) * (p["cols"] + 2) + c
            y = (m // tiles) * (p["rows"] + 2) + r
            positions[name] = np.stack([x, -y], axis=1).astype(float)
    atlas = build_atlas(brain.connectome, np.asarray(brain.brain.weights), regions=regions,
                        shapes=shapes, positions=positions, roles=roles, seed=0)
    return atlas.subsample_edges(lines).to_dict()
