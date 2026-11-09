"""Carry a trained brain onto a wider eye whose first inputs are the old eye's (588 -> 827:
the eye v2 appends 239 readings): a brain of the same composition is composed at the new
width, and every learned array of the old checkpoint is copied in by index, neurons by
population and position, synapses by their mapped (pre, post) pair, the memories' feature axes
(inputs, then actions) embedded. Everything the new inputs reach starts at zero (synapses, the
recall maps' rows and columns, the separators' rows), so the widened brain settles and chooses
as the old one does on the old inputs until learning gives the new ones weight. Stream state
starts afresh. ``Brain.grow`` adds memory parts and slots but not inputs; this is that step for
inputs, done on the checkpoint's arrays.

    python training/widen.py --old narrow.brain.npz --inputs 827 --out wide.brain.npz \
        --check runs/pool/validation.npz
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

NEURON_ARRAYS = ("log_gain", "bias", "plastic_neurons", "velocity_bias", "second_moment_bias", "apical_groups")
SYNAPSE_ARRAYS = ("count", "sign", "efficacy", "plastic_synapses", "velocity", "second_moment", "apical_synapses")


def compose_like(meta_old: dict, brain_old: dict, inputs: int, position: int):
    from cadence import Brain
    from cadence.learning import LearnerConfig
    comp = brain_old["composition"]
    config = {k: v for k, v in meta_old["config"].items() if k in LearnerConfig.__slots__}
    rec = brain_old["memories"]["recall"]
    return Brain.compose(
        inputs, comp["actions"], modules=tuple(comp["modules"]), slots=tuple(comp["slots"]),
        seed=comp["seed"], arousal=True, apical=comp["apical"], memory_choice=True, recall=True,
        recall_heads=int(rec.get("heads", 2)), recall_action=bool(rec.get("action", True)),
        recall_boundary=bool(rec.get("boundary", True)), recall_position=position,
        recall_recency=float(rec.get("recency", 0.0)), learning=LearnerConfig(**config), backend="cpu")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--old", type=Path, required=True)
    p.add_argument("--inputs", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--check", type=Path, default=None, help="a validation.npz of the wide eye")
    a = p.parse_args()
    from cadence import Brain
    old = dict(np.load(a.old, allow_pickle=False))
    meta_old, brain_old = json.loads(str(old["meta"])), json.loads(str(old["brain"]))
    n_in_old = brain_old["composition"]["inputs"]
    actions = brain_old["composition"]["actions"]
    print("recall settings", {k: v for k, v in brain_old["memories"]["recall"].items() if not isinstance(v, (list, dict))})
    fresh = compose_like(meta_old, brain_old, a.inputs, int(old["memories/recall/position_x"].shape[1]) - 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = fresh.save(Path(tmp) / "fresh.brain")
        new = dict(np.load(path, allow_pickle=False))
    meta_new, brain_new = json.loads(str(new["meta"])), json.loads(str(new["brain"]))
    # neurons: population by population, position by position
    nmap = np.full(meta_old["n"], -1, np.int64)
    for name, idx in meta_old["populations"].items():
        target = meta_new["populations"].get(name)
        if target is None:
            raise SystemExit(f"population {name} is missing at the new width")
        if len(target) < len(idx):
            raise SystemExit(f"population {name} is narrower at the new width")
        nmap[np.asarray(idx)] = np.asarray(target)[:len(idx)]
    if (nmap < 0).any():
        raise SystemExit("neurons without a place")
    for key in NEURON_ARRAYS:
        if key in old and key in new and len(old[key]):
            new[key] = new[key].copy()
            new[key][nmap] = old[key]
    # synapses: by mapped (pre, post)
    where = {(int(s), int(t)): j for j, (s, t) in enumerate(zip(new["pre"], new["post"]))}
    pick = np.array([where.get((int(nmap[s]), int(nmap[t])), -1) for s, t in zip(old["pre"], old["post"])])
    if (pick < 0).any():
        raise SystemExit(f"{int((pick < 0).sum())} old synapses have no place")
    covered = np.zeros(len(new["pre"]), bool)
    covered[pick] = True
    for key in SYNAPSE_ARRAYS:
        if key in old and key in new:
            new[key] = new[key].copy()
            new[key][pick] = old[key]
    new["efficacy"][~covered] = 0.0  # the new inputs' synapses (and their partners) start at zero
    for key in ("velocity", "second_moment"):
        new[key][~covered] = 0.0
    # memory feature axes: inputs, then actions
    fold = n_in_old + actions
    fmap = np.concatenate([np.arange(n_in_old), a.inputs + np.arange(actions)])

    def embed(key: str, axes: tuple[int, ...]) -> None:
        if key not in old or key not in new:
            return
        src, dst = old[key], np.zeros_like(new[key])
        index = [slice(None)] * src.ndim
        dindex = [slice(None)] * src.ndim
        for ax in axes:
            m = fmap if src.shape[ax] == fold else np.arange(src.shape[ax])
            dindex[ax] = m
        grid = np.ix_(*[np.asarray(d) if not isinstance(d, slice) else np.arange(src.shape[i])
                        for i, d in enumerate(dindex)])
        sgrid = np.ix_(*[np.arange(src.shape[i]) for i in range(src.ndim)])
        dst[grid] = src[sgrid]
        new[key] = dst

    for suffix in ("", "_1"):
        embed(f"memories/recall/w_x{suffix}", (0, 1))
        embed(f"memories/recall/w_c{suffix}", (1,))
        embed(f"memories/recall/b{suffix}", (0,))
        embed(f"memories/recall/position_x{suffix}", (0,))
        embed(f"memories/recall/position_c{suffix}", ())
        embed(f"memories/recall/position_b{suffix}", ())
    for prefix in ("memories/hippocampus", "memories/episodic/context_memory"):
        size = old[f"{prefix}/separator/projection"].shape[0]
        rows = np.arange(size) if size == n_in_old else fmap
        proj = np.zeros_like(new[f"{prefix}/separator/projection"])
        proj[rows] = old[f"{prefix}/separator/projection"]
        new[f"{prefix}/separator/projection"] = proj
        mean = np.zeros_like(new[f"{prefix}/separator/mean"])
        mean[rows] = old[f"{prefix}/separator/mean"]
        new[f"{prefix}/separator/mean"] = mean
        new[f"{prefix}/consolidated"] = old[f"{prefix}/consolidated"]
    new["actor/w_critic"] = old["actor/w_critic"]
    for k in ("b_critic", "actor", "arousal", "updates"):
        if k in brain_old:
            brain_new[k] = brain_old[k]
    for k in ("updates", "contrast_updates"):
        if k in meta_old:
            meta_new[k] = meta_old[k]
    # memory settings the training changed (learned gains, rates): carried where the key matches
    for name, block in brain_old["memories"].items():
        if isinstance(block, dict) and name in brain_new["memories"]:
            for k, v in block.items():
                if (isinstance(v, float) or k == "writes") and k in brain_new["memories"][name] \
                        and k != "neurons":
                    brain_new["memories"][name][k] = v
    new["meta"], new["brain"] = np.array(json.dumps(meta_new)), np.array(json.dumps(brain_new))
    np.savez_compressed(a.out, **new)
    wide = Brain.load(a.out, backend="cpu")
    report = {"old": str(a.old), "inputs": [n_in_old, a.inputs], "synapses": [int(len(old["pre"])), int(len(new["pre"]))],
              "new_synapses_at_zero": int((~covered).sum())}
    if a.check is not None:
        narrow = Brain.load(a.old, backend="cpu")
        v = np.load(a.check)
        x = v["x"][:400].astype(float)
        same = (narrow.predict(x[:, :n_in_old]) == wide.predict(x)).all(axis=1)
        report["predict_same"] = float(same.mean())
        narrow.reset(), wide.reset()
        acts = []
        for row in x[:200]:
            acts.append(bool((narrow.act(row[None, :n_in_old], greedy=True) == wide.act(row[None, :], greedy=True)).all()))
        report["stream_act_same"] = float(np.mean(acts))
    print(json.dumps(report))
    (a.out.parent / (a.out.name.replace(".brain.npz", "") + ".widen.json")).write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
