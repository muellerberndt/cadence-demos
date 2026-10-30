"""Reference trials for the JS port: the real brain in the real (collision-only, identical) cell.
Per decision: the state before, the observation, the brain's command, the q target the IK reflex
computed, the outcome and the state after. The block's physics is fixed (the site's block)."""
import json, sys
import numpy as np, mujoco
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from cadence import Brain
from arm2 import scene
from arm2.scene import PandaWorld, ORDERS
from arm2.senses import observe
from arm2.actions import target_of, BOUND, one_hot

SITE_BLOCK = {"half": 0.025, "mass": 0.08, "friction": 1.0, "timeconst": 0.02, "dampratio": 1.0}

def fix_block(w):
    m, p = w.model, SITE_BLOCK
    m.geom_size[w.block_geom] = (p["half"],) * 3
    m.geom_friction[w.block_geom][0] = p["friction"]
    m.geom_solref[w.block_geom] = (p["timeconst"], p["dampratio"])
    m.body_mass[w.block_body] = p["mass"]
    m.body_inertia[w.block_body] = p["mass"] * (2 * p["half"]) ** 2 / 6.0
    w.half = p["half"]

def move_bin(w, name, xy):
    bx, by = w.bins[name]
    for g in range(w.model.ngeom):
        n = mujoco.mj_id2name(w.model, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if n.startswith(f"bin_{name}_"):
            w.model.geom_pos[g][0] += xy[0] - bx; w.model.geom_pos[g][1] += xy[1] - by
    w.bins[name] = (float(xy[0]), float(xy[1]))

def state(w):
    d = w.data
    return {"qpos": d.qpos.tolist(), "qvel": d.qvel.tolist(), "ctrl": d.ctrl.tolist(), "act": d.act.tolist(), "time": d.time,
            "closed": w.closed, "closed_for": w.closed_for, "releasing": w.releasing, "holding": w.holding,
            "lifted_once": w.lifted_once, "last_command": None if w.last_command is None else np.asarray(w.last_command).tolist()}

brain_path, out, block_xy, bin_name, bin_xy = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4], json.loads(sys.argv[5])
phys = mujoco.MjModel.from_binary_path(sys.argv[6])
scene._MODEL = phys  # the collision-only model (same dynamics), as the browser loads it
w = PandaWorld(0, "nominal")
fix_block(w); move_bin(w, bin_name, bin_xy)
w.home()
q = w.block_qpos; w.data.qpos[q:q + 7] = (block_xy[0], block_xy[1], w.half, 1, 0, 0, 0); w.data.qvel[:] = 0
w.order = ORDERS.index(bin_name); w.last_command = None
mujoco.mj_forward(w.model, w.data)
b = Brain.load(brain_path); b.reset()
rows = []
for d in range(80):
    before = state(w)
    x = observe(w, "cartesian")
    a = np.asarray(b.act(x[None], greedy=True))[0].astype(int)
    tgt = target_of(w, a); qt = w.solve_ik(w.rest(), tgt, bound=BOUND)
    w.last_command = one_hot(a, "cartesian")
    o = w.decide(qt, int(a[3]))
    rows.append({"d": d, "before": before, "x": x.tolist(), "answer": a.tolist(), "target": tgt.tolist(), "q_target": qt.tolist(),
                 "event": o["event"], "after": state(w), "block": w.block_pos().tolist(), "tip": w.tip().tolist()})
    if o["event"] and o["event"].startswith("placed"): break
json.dump({"block_xy": block_xy, "bin": bin_name, "bin_xy": bin_xy, "site_block": SITE_BLOCK, "rows": rows}, open(out, "w"))
print(out, len(rows), "decisions; events:", [r["event"] for r in rows if r["event"]])
