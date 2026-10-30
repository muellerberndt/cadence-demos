"""Does the arm brain follow a bin moved away from where it trained? Order fixed to the moved bin,
block spawned randomly in the trained area, 20 trials per (brain, bin position)."""
import json, sys
import numpy as np, mujoco
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from arm2 import job
from arm2.inspect import load_policy
from arm2.scene import PandaWorld, BIN_HOME, ORDERS

def move_bin(world, name, xy):
    bx, by = world.bins[name]
    dx, dy = xy[0] - bx, xy[1] - by
    m = world.model
    for g in range(m.ngeom):
        n = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if n.startswith(f"bin_{name}_"):
            m.geom_pos[g][0] += dx; m.geom_pos[g][1] += dy
    world.bins[name] = (float(xy[0]), float(xy[1]))
    mujoco.mj_forward(m, world.data)

ckpt, label, name, x, y, trials, seed, physics = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), sys.argv[8]
policy = load_policy(ckpt, "cartesian", velocity=True, slip=False)
world = PandaWorld(seed, physics)
move_bin(world, name, (x, y))
res = {"right": 0, "wrong": 0, "dropped": 0, "none": 0}
for k in range(trials):
    job.prepare(world)
    world.order = ORDERS.index(name)
    for kk, gid in world.lamps.items():
        world.model.geom_rgba[gid] = (1.0, 0.95, 0.4, 1.0) if kk == name else (0.3, 0.3, 0.3, 1.0)
    policy.reset()
    r = job.run_trial(world, policy, "cartesian", 80, None)
    p = r["passed"]
    res["right" if "right" in p else "wrong" if "wrong" in p else "dropped" if "dropped" in p else "none"] += 1
print(json.dumps({"brain": label, "bin": name, "xy": [x, y], **res, "trials": trials}))
