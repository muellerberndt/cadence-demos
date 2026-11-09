"""Routes A and B: raise a deep brain, one run per process, resumable.

    # route A: Mako 1.0 grafted into a deep layout, distilled back to Mako's play
    python scripts/deep_raise.py --init graft --layout deep2w --teacher mako --out runs/r3/c/deepA-2w-mako
    # route B: a deep brain from scratch, corpus school then ab5 DAgger
    python scripts/deep_raise.py --init scratch --genome '{"layout": "deep3", ...}' --watch 15000 \
        --teacher ab5 --out runs/r3/c/deepB-3

The brain (`field` sense, recall off):
- `graft`: `r3.compose` of the layout with no apical compartment (`graft` refuses a different
  neuron model or apical role, and Mako has none), Mako's genes otherwise (normalized teaching,
  lateral -0.5, trace off), then `graft(mako, {"sensory": "sensory", "association": "module_0"},
  joints="kept")`: Mako's trained 256-neuron association region and its sensory synapses become
  the first module; the modules above keep this brain's construction.
- `scratch`: `r3.compose(genome)`, then `--watch` corpus lessons (`voronoi3` games replayed
  through the sense, `r3.watch`), saved as `brain-school.npz`.
- `load`: `--start` as it is.

Lessons: the brain rides its own games against the labelling opponents (`phasec.LABEL_OPPS`) in
`--rows` rows; the teacher labels every position it reaches and the label is the lesson
(DAgger). Teachers: `mako` (the donor's greedy move; `--mako` names the donor, Mako 1.0 by
default), `ab5` (alpha-beta, `--depth` rounds, the Voronoi leaf), `exit` (the same search with
+`--prior` units on the brain's own greedy move: expert iteration without a gate), `mix` (the
donor's move, and on a `--ab5-share` of the rows the `ab5` move).

`--l1-rate r` (graft): the grafted synapses (sense to `module_0`) step at r times the rate
(`learner.synapse_rate`; 0 freezes them), so the lessons train the new layers and the joints;
`final.npz` is saved with every synapse at the full rate again, for selection on the whole brain.

Every `--every` moments: the brain saved as `brain-m<N>.npz`; 128 mirror pairs against
`voronoi` on the checkpoint seeds (2,200,000+, `r3eval`); agreement with `ab5` (all, turns,
critical) and with Mako on the fixed held-out set `runs/r3/turnset.npz`; one line in
report.jsonl (the expert-iteration format); optional S3 sync (`--s3`). Stops at `--moments`, or once the reading reaches
`--stop-at` (route A: Mako's level); the last checkpoint is copied to `final.npz`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from multiprocessing import get_context

# Process pools fork on Linux; on macOS a fork after NumPy or Numba threads have run can hang,
# so pools spawn there. TRON_MP=fork|spawn|forkserver overrides.
MP = os.environ.get("TRON_MP") or ("spawn" if sys.platform == "darwin" else "fork")
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tron import r3  # noqa: E402
from tron.field import make_sense3  # noqa: E402
from tron.world import Arena, mulberry32  # noqa: E402
from phasec import OPP, LABEL_OPPS, _label  # noqa: E402
import r3eval  # noqa: E402

MAKO = "runs/r3/best/exit-s32-m40000.npz"
MAKO_GENES = {"sense": "field", "apical": 0, "teaching": "normalized", "eta_scale": 0.3, "temperature": 0.1,
              "lateral": -0.5, "trace_amp": 0.0, "trace_decay": 0.5, "sensory": 1.0, "rows": 32, "watch": 0, "dagger": 0}


def to_backend(brain, backend):
    from cadence import Brain
    with tempfile.TemporaryDirectory() as d:
        return Brain.load(brain.save(os.path.join(d, "b.npz")), backend=backend)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--init", required=True, choices=["graft", "scratch", "load"])
    p.add_argument("--layout", default="deep2w")
    p.add_argument("--genome", default=None, help="scratch: JSON genome (r3.SPACE keys)")
    p.add_argument("--start", default=None, help="load: the brain to raise")
    p.add_argument("--mako", default=MAKO)
    p.add_argument("--teacher", default="mako", choices=["mako", "ab5", "exit", "mix"])
    p.add_argument("--ab5-share", type=float, default=0.25, help="mix: share of rows labelled by ab5")
    p.add_argument("--l1-rate", type=float, default=None, help="graft: rate multiplier of the grafted synapses")
    p.add_argument("--skip-rate", type=float, default=None,
                   help="fresh start: rate multiplier of the module_0 <-> motor skip; with it --l1-rate applies to any start")
    p.add_argument("--eta", type=float, default=None,
                   help="set the learner rate to this value on every start (bias rate a tenth of it)")
    p.add_argument("--turn-boost", action="store_true",
                   help="a second lesson on this moment's rows whose label is a turn (live rows, no replay)")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--prior", type=int, default=8)
    p.add_argument("--eta-scale", type=float, default=None, help="graft: the learner rate scale (default Mako's 0.3)")
    p.add_argument("--watch", type=int, default=15000)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=61)
    p.add_argument("--rows", type=int, default=32)
    p.add_argument("--moments", type=int, default=60000)
    p.add_argument("--every", type=int, default=5000)
    p.add_argument("--stop-at", type=float, default=0.0)
    p.add_argument("--workers", type=int, default=4, help="label processes (ab5, exit)")
    p.add_argument("--eval-workers", type=int, default=12)
    p.add_argument("--backend", default="torch")
    p.add_argument("--s3", default=None)
    a = p.parse_args()
    from cadence import Brain
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    see = make_sense3("field")[0]

    def sync():
        if a.s3:
            subprocess.run(["aws", "s3", "sync", str(out), a.s3, "--only-show-errors"], check=False)

    saved = sorted(out.glob("brain-m*.npz"), key=lambda q: int(q.stem[7:]))
    meta_path = out / "meta.json"
    if saved:
        brain = Brain.load(str(saved[-1]), backend=a.backend)
        moments = int(saved[-1].stem[7:])
    elif (out / "brain-school.npz").exists():
        brain = Brain.load(str(out / "brain-school.npz"), backend=a.backend)
        moments = 0
    else:
        moments = 0
        if a.init == "graft":
            g = dict(MAKO_GENES, layout=a.layout)
            if a.eta_scale is not None:
                g["eta_scale"] = a.eta_scale
            body = r3.compose(g, a.seed, backend="cpu")
            mako_cpu = Brain.load(a.mako, backend="cpu")
            brain = body.graft(mako_cpu, {"sensory": "sensory", "association": "module_0"}, joints="kept")
            if a.l1_rate is not None:
                c, pops = brain.connectome, brain.connectome.populations
                sens, m0 = np.zeros(c.n, bool), np.zeros(c.n, bool)
                sens[list(pops["sensory"])] = True
                m0[list(pops["module_0"])] = True
                rate = np.ones(len(c.pre))
                rate[sens[c.pre] & m0[c.post]] = a.l1_rate
                brain.learner.synapse_rate = rate
            brain = to_backend(brain, a.backend) if a.backend != "cpu" else brain
        elif a.init == "scratch":
            g = json.loads(a.genome)
            g["sense"] = "field"
            brain = r3.compose(g, a.seed, backend=a.backend)
        else:
            g = None
            brain = Brain.load(a.start, backend=a.backend)
        if a.skip_rate is not None:
            # train the deep pathway alone; the input layer and the skip keep their weights
            c, pops = brain.connectome, brain.connectome.populations

            def m(x, y):
                px, py = np.zeros(c.n, bool), np.zeros(c.n, bool)
                px[list(pops[x])] = True
                py[list(pops[y])] = True
                return px[c.pre] & py[c.post]
            rate = np.ones(len(c.pre))
            rate[m("sensory", "module_0")] = a.l1_rate if a.l1_rate is not None else 1.0
            rate[m("module_0", "motor") | m("motor", "module_0")] = a.skip_rate
            if a.backend != "cpu":
                brain = Brain.load(brain.save(str(out / "start.npz")), backend="cpu")
            brain.learner.synapse_rate = rate
            brain = to_backend(brain, a.backend) if a.backend != "cpu" else brain
        meta_path.write_text(json.dumps({"arm": f"deep-{a.init}-{a.teacher}", "sense": "field", "genome": g,
                                         "layout": r3.LAYOUTS[g["layout"]] if g else None, "args": vars(a)}, indent=1))
        if a.init == "scratch" and a.watch:
            t0 = time.time()
            w = r3.watch(brain, "field", a.watch, a.rows, a.seed)
            w["wall_s"] = round(time.time() - t0)
            (out / "school.json").write_text(json.dumps(w))
            brain.save(str(out / "brain-school.npz"))
            print(json.dumps({"school": w}), flush=True)
    if a.eta is not None:
        from dataclasses import replace as _replace
        c = brain.learner.config
        brain.retune(learning=_replace(c, eta=a.eta, eta_bias=a.eta / 10))
    mako = Brain.load(a.mako, backend="cpu")
    mako.reset()
    turnset = np.load("runs/r3/turnset.npz")
    tx = turnset["x"].astype(np.float64)
    mako_moves = np.array([int(mako.act(x[None, :], greedy=True)[0]) for x in tx])
    mako.reset()
    pool = get_context(MP).Pool(a.workers) if a.teacher != "mako" else None
    mix_rng = np.random.default_rng(a.seed + moments)
    rng = random.Random(a.seed * 31 + moments)

    def fresh():
        s = rng.randrange(1 << 30)
        return {"arena": Arena(24, seed=s), "draw": mulberry32(s), "opp": LABEL_OPPS[rng.randrange(len(LABEL_OPPS))]}

    def checkpoint():
        path = out / f"brain-m{moments}.npz"
        brain.save(str(path))
        t0 = time.time()
        r = r3eval.reading(str(path), "voronoi", 128, r3eval.CHECKPOINT, a.eval_workers)
        t = Brain.load(str(path), backend="cpu")
        t.reset()
        mine = np.array([int(t.act(x[None, :], greedy=True)[0]) for x in tx])
        y, turn, crit = turnset["y"], turnset["turn"].astype(bool), turnset["crit"].astype(bool)
        line = {"moments": moments, "brain": {"voronoi": r}, "agree_with_mako": float((mine == mako_moves).mean()),
                "ab5_agreement": {"all": float((mine == y).mean()), "turns": float((mine == y)[turn].mean()),
                                  "critical": float((mine == y)[crit].mean())},
                "eval_s": round(time.time() - t0)}
        with open(out / "report.jsonl", "a") as f:
            f.write(json.dumps(line) + "\n")
        print(json.dumps({"moments": moments, "vs_voronoi": r["score"], "agree_with_mako": line["agree_with_mako"],
                          "ab5_turns": line["ab5_agreement"]["turns"]}), flush=True)
        brain.reset()
        sync()
        return r["score"]

    if not saved:
        sc = checkpoint()
        if a.stop_at and sc >= a.stop_at:
            moments = a.moments
    games = [fresh() for _ in range(a.rows)]
    brain.reset()
    t0 = time.time()
    while moments < a.moments:
        x = np.stack([see(gm["arena"], 0) for gm in games])
        try:
            brain.reset()  # play from rest, as the lessons train
            own = np.asarray(brain.act(x, greedy=True)).reshape(-1)
            if a.teacher in ("mako", "mix"):
                mako.reset()
                y = np.asarray(mako.act(x, greedy=True)).reshape(-1)  # the donor's trace amplitude is 0
                if a.teacher == "mix":
                    pick = np.flatnonzero(mix_rng.random(a.rows) < a.ab5_share)
                    if len(pick):
                        got = pool.map(_label, [(games[i]["arena"], a.depth, -1, 0) for i in pick])
                        y[pick] = [m for m, _ in got]
            else:
                prior = a.prior if a.teacher == "exit" else 0
                jobs = [(gm["arena"], a.depth, int(own[i]) if prior else -1, prior) for i, gm in enumerate(games)]
                y = np.array([m for m, _ in pool.map(_label, jobs)])
            brain.lesson(x, y)
            if a.turn_boost:
                sel = np.flatnonzero(y != 1)
                if len(sel):
                    brain.reset()  # the rows are a subset of the streams (grafted brains: trace amplitude 0)
                    brain.lesson(x[sel], y[sel])
                    brain.reset()
        except RuntimeError:
            brain.reset()
            own = np.ones(a.rows, int)
        for i, gm in enumerate(games):
            ar = gm["arena"]
            ar.step((int(own[i]), OPP[gm["opp"]](ar, 1, gm["draw"])))
            if ar.over:
                games[i] = fresh()
        moments += 1
        if moments % 1000 == 0:
            print(json.dumps({"progress": moments, "wall_h": round((time.time() - t0) / 3600, 3)}), flush=True)
        if moments % a.every == 0:
            sc = checkpoint()
            if a.stop_at and sc >= a.stop_at:
                break
    if pool:
        pool.close()
    final = sorted(out.glob("brain-m*.npz"), key=lambda q: int(q.stem[7:]))[-1]
    whole = Brain.load(str(final), backend="cpu")
    if whole.learner.synapse_rate is not None:
        whole.learner.synapse_rate = None  # every synapse at the full rate for selection
        whole.save(str(out / "final.npz"))
    else:
        shutil.copyfile(final, out / "final.npz")
    (out / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + f" {final.name}\n")
    sync()


if __name__ == "__main__":
    main()
