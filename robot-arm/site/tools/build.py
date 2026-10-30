"""Builds the arm page's runtime files from the lane: the physics model and the Panda's decimated
visual meshes (from ``arm2.scene``), the vendored MuJoCo WebAssembly and three.js, and the brain
pack (the released Cadence wheel, the checkpoint, its run.json and the host) with a manifest of
SHA-256 digests that the worker checks before anything runs.

    python site/tools/build.py --brain runs/.../brain_best.npz --run runs/.../run.json \
        --wheel cadence_net-0.91.1-py3-none-any.whl --mujoco node_modules/@mujoco/mujoco \
        --three node_modules/three

Needs mujoco 3.17.0 and fast-simplification (for the visual meshes) in the Python that runs it,
and ``cadence-arm`` on the import path (it is when run from the lane root).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

import mujoco
import numpy as np

SITE = Path(__file__).resolve().parents[1]
LANE = SITE.parent
sys.path.insert(0, str(LANE))

PYODIDE = "314.0.7"
VISUAL_KEEP = 0.35  # share of each large visual mesh's triangles kept


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physics_model() -> mujoco.MjModel:
    """``arm2.scene.build`` without the Panda's visual-only meshes: the same bodies, inertias,
    actuators and collision geometry, so the dynamics are identical (checked here)."""
    from arm2 import scene

    captured = {}
    original = mujoco.MjSpec.from_file

    def grab(path):
        spec = original(path)
        captured["spec"] = spec
        return spec

    mujoco.MjSpec.from_file = staticmethod(grab)
    scene._MODEL = None
    try:
        full = scene.build()
    finally:
        mujoco.MjSpec.from_file = original
        scene._MODEL = None
    spec = captured["spec"]
    for g in list(spec.geoms):
        if g.type == mujoco.mjtGeom.mjGEOM_MESH and g.contype == 0 and g.conaffinity == 0:
            spec.delete(g)
    used = {g.meshname for g in spec.geoms if g.type == mujoco.mjtGeom.mjGEOM_MESH}
    for mesh in list(spec.meshes):
        if mesh.name not in used:
            spec.delete(mesh)
    phys = spec.compile()
    for key in ("body_mass", "body_inertia", "body_ipos", "body_iquat", "jnt_range", "actuator_gainprm", "actuator_biasprm"):
        if not np.array_equal(getattr(full, key), getattr(phys, key)):
            raise SystemExit(f"the physics model differs from the cell in {key}")
    return full, phys


def visuals(full: mujoco.MjModel, out: Path) -> dict:
    import fast_simplification

    verts, idx, entries, voff, ioff = [], [], [], 0, 0
    m = full
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_contype[g] or m.geom_conaffinity[g]:
            continue
        k = int(m.geom_dataid[g])
        va, vn, fa, fn = int(m.mesh_vertadr[k]), int(m.mesh_vertnum[k]), int(m.mesh_faceadr[k]), int(m.mesh_facenum[k])
        v, f = m.mesh_vert[va:va + vn].astype(np.float64), m.mesh_face[fa:fa + fn].astype(np.int64)
        # MuJoCo keeps three unshared vertices per visual triangle; weld them (to 1 micrometre)
        # so the mesh is connected before it is decimated
        _, first, inverse = np.unique(np.round(v * 1e6).astype(np.int64), axis=0, return_index=True, return_inverse=True)
        v, f = v[first], inverse.ravel()[f]
        f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
        if len(f) > 400:
            v, f = fast_simplification.simplify(v, f, target_reduction=1.0 - VISUAL_KEEP)
        rgba = m.mat_rgba[m.geom_matid[g]] if m.geom_matid[g] >= 0 else m.geom_rgba[g]
        entries.append({"body": mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[g])),
                        "pos": m.geom_pos[g].round(6).tolist(), "quat": m.geom_quat[g].round(6).tolist(),
                        "rgba": [round(float(c), 4) for c in rgba], "voff": voff, "vcount": len(v), "ioff": ioff, "icount": int(f.size)})
        verts.append(v.astype(np.float32))
        idx.append(f.astype(np.uint32).ravel())
        voff += len(v)
        ioff += f.size
    V, I = np.concatenate(verts), np.concatenate(idx)
    (out / "panda_visual.bin").write_bytes(V.tobytes() + I.tobytes())
    index = {"vertices": int(len(V)), "indices": int(len(I)), "geoms": entries}
    (out / "panda_visual.json").write_text(json.dumps(index))
    return {"geoms": len(entries), "vertices": int(len(V)), "triangles": int(len(I) // 3)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--brain", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--wheel", required=True)
    p.add_argument("--mujoco", required=True, help="the unpacked @mujoco/mujoco 3.17.0 npm package")
    p.add_argument("--three", required=True, help="the unpacked three 0.160.0 npm package")
    a = p.parse_args()

    assets = SITE / "assets"
    assets.mkdir(exist_ok=True)
    full, phys = physics_model()
    mujoco.mj_saveModel(phys, str(assets / "cell.mjb"), None)
    mesh = visuals(full, assets)
    menagerie = LANE / "arm2" / "menagerie" / "franka_emika_panda"
    shutil.copy(menagerie / "LICENSE", assets / "LICENSE-menagerie-panda")

    vendor = SITE / "vendor"
    (vendor / "mujoco").mkdir(parents=True, exist_ok=True)
    (vendor / "three").mkdir(parents=True, exist_ok=True)
    mj = Path(a.mujoco)
    for name in ("mujoco.js", "mujoco.wasm"):
        shutil.copy(mj / name, vendor / "mujoco" / name)
    (vendor / "mujoco" / "NOTICE").write_text("MuJoCo 3.17.0 WebAssembly bindings (npm @mujoco/mujoco), Copyright DeepMind Technologies Limited, Apache License 2.0.\n")
    three = Path(a.three)
    shutil.copy(three / "build" / "three.module.min.js", vendor / "three" / "three.module.min.js")
    for rel in ("controls/OrbitControls.js", "environments/RoomEnvironment.js", "utils/BufferGeometryUtils.js",
                "postprocessing/EffectComposer.js", "postprocessing/RenderPass.js", "postprocessing/ShaderPass.js",
                "postprocessing/MaskPass.js", "postprocessing/Pass.js", "postprocessing/UnrealBloomPass.js",
                "postprocessing/OutputPass.js", "shaders/CopyShader.js", "shaders/LuminosityHighPassShader.js", "shaders/OutputShader.js"):
        (vendor / "three" / "jsm" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(three / "examples" / "jsm" / rel, vendor / "three" / "jsm" / rel)
    shutil.copy(three / "LICENSE", vendor / "three" / "LICENSE")

    pack = SITE / "pack"
    if pack.exists():
        shutil.rmtree(pack)
    (pack / "py" / "armbrain").mkdir(parents=True)
    wheel = Path(a.wheel)
    shutil.copy(wheel, pack / wheel.name)
    shutil.copy(a.brain, pack / "brain.npz")
    shutil.copy(a.run, pack / "run.json")
    sources = ["__init__.py", "host.py"]
    for name in sources:
        shutil.copy(SITE / "py" / "armbrain" / name, pack / "py" / "armbrain" / name)
    run = json.loads(Path(a.run).read_text())
    cadence = wheel.name.split("-")[1]
    manifest = {
        "schema": "cadence-arm-site-pack/1", "packed": dt.date.today().isoformat(), "pyodide": PYODIDE, "cadence": cadence,
        "wheel": wheel.name, "wheel_sha256": sha256(pack / wheel.name), "wheel_source": "PyPI",
        "sources": sources, "sources_sha256": {n: sha256(pack / "py" / "armbrain" / n) for n in sources},
        "brain": "brain.npz", "brain_sha256": sha256(pack / "brain.npz"), "brain_bytes": (pack / "brain.npz").stat().st_size,
        "run": "run.json", "run_sha256": sha256(pack / "run.json"), "brain_size": run.get("brain"), "arm": run.get("arm"),
        "assets": {n: sha256(assets / n) for n in ("cell.mjb", "panda_visual.bin", "panda_visual.json")},
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({"physics": {"ngeom": phys.ngeom, "nmesh": phys.nmesh, "bytes": (assets / 'cell.mjb').stat().st_size},
                      "visuals": mesh, "pack": {k: manifest[k] for k in ("cadence", "pyodide", "brain_bytes")}}, indent=1))


if __name__ == "__main__":
    main()
