"""The page's host for the brain trained tonight (cadence#334, the meaning lane's night, its N1
export): the composed host (`parrotbrain.page`: the parrot-brain lane's body, eyes, focus and map,
with the page's hearing layer) and, beside it, the trained brain that answers questions
(`cadence.meaning.host.MeaningParrot`, loaded from `brain.npz`, `brain.records.npz` and
`spec.json`; `version.json` names its stage, founder and export).

The body moves as the composed brain moves it; the page turns its head to the thing in focus. The
trained brain lives only during an exchange, one of its own moments (300 ms) at a time, as its
export protocol says (benchmarks/meaning/export_page.py, COORD 2026-11-13 19:05 and 22:15):

- `begin`: a new exchange (the brain's state reset, the last reply forgotten);
- `moment`: what it sees (each thing's kind, colour, material, direction from the head and
  distance; the focus; during a scan the glimpse on one thing), the word heard (or None) and
  `more` (the trainer has more to say: its voice is held); it returns the word it says, or None;
- `pistachio`: the last reply's moments taught with its own words (the three-factor rule);
- `correct`: the trainer's right word kept as a record under the question's pattern, then heard;
- `over`: the exchange ends with no pistachio;
- `look`: between questions, it sees the room with its focus on a thing, its voice held.

With each moment the reply carries `mind`: the facets of the thing in focus read from its settled
state by the meaning lane's probes (`probes.json` beside the brain, where exported), and the word
its voice neurons are ready to say.

The page sends one of these in `meta["meaning"]` with a moment of the body; the reply carries
`meaning` (what it said, the lessons taken, the record written) and the trained brain's neurons
after the body's in `activity`. Its ear takes the training chamber's word codes, one code a
word. The hearing layer links sounds to these words (one link unit a word of its vocabulary): a
heard sound whose record links to a word sends that word's code to the trained brain's ear, and a
word its voice says recalls the record linked to it (`sound` in the reply), whose audio the page
plays in the parrot's voice.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from cadence.meaning.host import MeaningParrot
from cadence.recording import record_settlements

from .page import Host as Composed

# the trained brain's populations as the brain view draws them: its name in the connectome, the
# page's name, the title, the atlas region, and the scale its activity is drawn at
# (its processing regions, `module_0` up, are found in the connectome: two in the N1 brain, four in
# the deep one)
PISTACHIO = 0.05  # the lesson's amount for a pistachio (the meaning lane's page setting)
ORDINAL = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")
POPULATIONS = [
    ("sensory/eyes", "t_eyes", "Trained brain: what its eyes report (the thing in focus, then each thing)", "rotundus", 1.0),
    ("modules", "", "", "rotundus", 1.0),
    ("sensory/ear", "t_ear", "Trained brain: the code of the word it hears (a stand-in code)", "ncm", 2.2),
    ("association", "t_association", "Trained brain: the association region", "ncl", 1.0),
    ("prefrontal", "t_prefrontal", "Trained brain: its working trace", "trace", 1.0),
    ("history", "t_history", "Trained brain: the words heard before, held", "trace", 4.0),
    ("motor", "t_voice", "Trained brain: its voice, one neuron a word and one for silence", "vocal", 1.0),
]


class Host(Composed):
    def __init__(self, config: dict[str, Any]):
        folder = Path(str(config.get("host_files") or "/home/pyodide/trained"))
        # the hearing layer's sounds stand for the trained brain's words: one link unit a word it hears
        vocab = sorted(w for w in json.loads((folder / "spec.json").read_text())["codes"] if not w.startswith("<"))
        super().__init__({**config, "words": vocab})
        began = time.perf_counter()
        spec = folder / "spec.json"
        self.spec_path = spec
        seed = int(json.loads(spec.read_text()).get("records", {}).get("settings", {}).get("seed", 0))
        self.meaning = MeaningParrot(folder / "brain.npz", spec, seed=seed)
        self.load_s = time.perf_counter() - began
        found = folder / "version.json"
        self.version = json.loads(found.read_text()) if found.exists() else {}
        # the meaning lane's probes (probes.json beside the brain): each facet of the thing in focus
        # read from the settled state; without the file the page shows no facet
        found = folder / "probes.json"
        self.probes: dict[str, Any] | None = None
        if found.exists():
            raw = json.loads(found.read_text())
            pops = self.meaning.brain.connectome.populations
            if "neurons" in raw:  # the lane's format: one population's neurons, a weight matrix (dims x classes) a facet
                units = np.asarray(raw["neurons"], np.int64)
                regions = [str(raw.get("population", "association"))]
            else:
                regions = [r for r in raw.get("code", {}).get("regions", ["association"]) if r in pops]
                units = np.concatenate([np.asarray(list(pops[r]), np.int64) for r in regions])
            self.probes = {"regions": regions, "units": units, "facets": {},
                           "read_at": raw.get("read_at") or raw.get("code", {}).get("read_at") or "a moment of looking: a thing in focus, nothing heard"}
            for name, f in raw.get("facets", {}).items():
                if "weights" in f:
                    W = np.asarray(f["weights"], np.float64).T  # classes x dims
                    b = np.zeros(W.shape[0])
                    mu, sd = f["mean"], f["sd"]
                else:
                    W = np.atleast_2d(np.asarray(f["W"], np.float64))
                    b = np.atleast_1d(np.asarray(f.get("b", 0.0), np.float64))
                    mu, sd = f["mu"], f["sd"]
                self.probes["facets"][name] = {"classes": [str(c) for c in f["classes"]], "W": W, "b": b,
                                               "mu": np.asarray(mu, np.float64), "sd": np.asarray(sd, np.float64),
                                               "accuracy": f.get("accuracy"), "base_rate": f.get("base_rate"), "held_out": f.get("held_out")}
        c = self.meaning.brain.connectome
        self.t_pops: list[tuple[dict[str, Any], np.ndarray, float]] = []
        start = self.neurons
        rows = []
        for name, page_name, title, area, scale in POPULATIONS:
            if name == "modules":
                found = sorted((k for k in c.populations if k.startswith("module_")), key=lambda k: int(k.split("_")[1]))
                rows += [(k, f"t_{k}", f"Trained brain: its {ORDINAL[i] if i < len(ORDINAL) else str(i + 1) + 'th'} processing region", area, scale)
                         for i, k in enumerate(found)]
            elif name in c.populations:
                rows.append((name, page_name, title, area, scale))
        for name, page_name, title, area, scale in rows:
            units = np.asarray(list(c.populations[name]), dtype=np.int64)
            self.t_pops.append(({"name": page_name, "title": title, "region": area, "start": start, "size": int(len(units))}, units, scale))
            start += len(units)
        self.t_start, self.neurons = self.neurons, start
        self.t_activity = np.zeros(start - self.t_start, np.float32)
        # each neuron's population, for the pistachio's change per tract
        owner = np.full(c.n, -1, np.int64)
        for k, (_, units, _) in enumerate(self.t_pops):
            owner[units] = k
        self.pre_pop, self.post_pop = owner[np.asarray(c.pre)], owner[np.asarray(c.post)]
        # the brain view's repairs: each atlas region's neurons, and each tract's synapses (from one
        # region to another), for the settle the library records as it happens
        areas = sorted({p["region"] for p, _, _ in self.t_pops})
        area_of = np.full(c.n, -1, np.int64)
        self.area_units: dict[str, np.ndarray] = {}
        for k, a in enumerate(areas):
            units = np.concatenate([u for p, u, _ in self.t_pops if p["region"] == a])
            self.area_units[a] = units
            area_of[units] = k
        pre_a, post_a = area_of[np.asarray(c.pre)], area_of[np.asarray(c.post)]
        self.pre_index = np.asarray(c.pre, np.int64)
        self.tract_synapses: dict[tuple[str, str], np.ndarray] = {}
        for i, a in enumerate(areas):
            for j, b in enumerate(areas):
                if i != j:
                    found = np.flatnonzero((pre_a == i) & (post_a == j))
                    if len(found):
                        self.tract_synapses[(a, b)] = found
        self.settle: dict[str, Any] | None = None
        self.moments = 0
        self.lessons = 0
        self.records_written = 0

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        m = self.meaning
        d.update(name="trained", populations=d["populations"] + [p for p, _, _ in self.t_pops], neurons=self.neurons,
                 title="The parrot's brain: the composed body, and the brain trained tonight for the words",
                 trained={"words": sorted(w for w in m.codes if not w.startswith("<")), "says": [w for w in m.voice if not w.startswith("<")],  # the words it hears (its codes) and the words its voice has "moment_ms": int(m.spec.get("moment_ms", 300)),
                          "turn_moments": int(m.spec.get("turn_moments", 3)), "kinds": sorted(m.spec["kinds"]),
                          "colours": sorted(m.spec["colours"]), "materials": sorted(m.spec["materials"]),
                          "neurons": int(m.brain.connectome.n), "synapses": int(m.brain.connectome.synapses),
                          "records": 0 if m.records is None else int(m.records.count), "load_s": round(self.load_s, 2),
                          "version": self.version,
                          "probes": None if self.probes is None else {"regions": self.probes["regions"], "read_at": self.probes["read_at"],
                                                                      "facets": {k: {"classes": f["classes"], "accuracy": f["accuracy"], "base_rate": f["base_rate"], "held_out": f["held_out"]}
                                                                                 for k, f in self.probes["facets"].items()}}})
        return d

    # --- the trained brain's moments ---------------------------------------------------------------
    def _activation(self) -> None:
        state = self.meaning.brain.basal_ganglia.state
        out = self.t_activity
        if state is None:  # reset: nothing settled since
            out[:] = 0.0
            return
        a = np.asarray(state.activation, dtype=np.float64)[0]
        for p, units, scale in self.t_pops:
            s = p["start"] - self.t_start
            out[s: s + p["size"]] = np.clip(a[units] * scale, -1.0, 1.0)

    def _mind(self) -> dict[str, Any]:
        """What its settled state holds of the thing in focus, read by the meaning lane's probes;
        and the word its voice is ready to say (its voice neurons, the silence held apart)."""
        m = self.meaning
        state = m.brain.basal_ganglia.state
        out: dict[str, Any] = {"facets": None if self.probes is None else {}, "voice": None}
        if state is None:
            return out
        a = np.asarray(state.activation, dtype=np.float64)[0]
        if self.probes is not None:
            x = a[self.probes["units"]]
            for name, f in self.probes["facets"].items():
                if f["mu"].shape != x.shape:
                    continue
                z = ((x - f["mu"]) / f["sd"]) @ f["W"].T + f["b"]
                if f["W"].shape[0] == 1:  # one logistic row: the second class's chance
                    q = 1.0 / (1.0 + np.exp(-float(z[0])))
                    p = np.array([1.0 - q, q])
                else:
                    e = np.exp(z - z.max())
                    p = e / e.sum()
                order = np.argsort(p)[::-1]
                k = int(order[0])
                out["facets"][name] = {"value": f["classes"][k], "p": round(float(p[k]), 3), "p2": round(float(p[order[1]]), 3) if len(p) > 1 else 0.0}
        voice = a[np.asarray(list(m.brain.connectome.populations["motor"]), np.int64)]
        words = voice[: len(m.voice)]
        k = int(np.argmax(words))
        out["voice"] = {"word": m.voice[k], "level": round(float(words[k]), 3),
                        "silence": round(float(voice[len(m.voice)]), 3) if len(voice) > len(m.voice) else None}
        return out

    def _settle_viz(self, records: list[Any], frames: int = 16) -> dict[str, Any] | None:
        """The moment's settle as the library recorded it (cadence.recording.record_settlements:
        the activations after every sweep): each region's residual (the mean distance of its
        neurons from the settled state) and each tract's message (its synapses' weights times the
        sending neurons' activations, summed) at up to ``frames`` sweeps (VIZ_EVENTS.md)."""
        if not records:
            return None
        rec = max(records, key=lambda r: int(r.steps))
        rows = np.asarray(rec.activation, dtype=np.float64)[:, 0, :]
        if len(rows) < 2:
            return None
        pick = np.linspace(0, len(rows) - 1, min(frames, len(rows))).round().astype(int)
        at, final = rows[pick], rows[-1]
        regions = {a: np.abs(at[:, u] - final[u]).mean(axis=1).round(5).tolist() for a, u in self.area_units.items()}
        w = np.asarray(rec.weights, dtype=np.float64)
        n = rows.shape[1]
        tracts = []
        for (a, b), syn in self.tract_synapses.items():
            out_w = np.bincount(self.pre_index[syn], weights=w[syn], minlength=n)  # each neuron's summed weight into the tract
            tracts.append({"from": a, "to": b, "carried": (at @ out_w).round(5).tolist()})
        return {"frames": int(len(pick)), "sweeps": int(len(rows) - 1), "kind": "residual", "regions": regions, "tracts": tracts,
                "source": "trained", "settlements": len(records)}

    def _recalled(self) -> str | None:
        r = np.asarray(self.meaning.recalled, dtype=np.float64)
        if not np.any(r):
            return None
        best, top = None, 0.0
        for w, code in self.meaning.codes.items():
            cos = float(code @ r) / (np.linalg.norm(code) * np.linalg.norm(r) + 1e-12)
            if cos > top:
                best, top = w, cos
        return best if top > 0.9 else None

    def _paid(self, before: np.ndarray) -> list[dict[str, Any]]:
        """The lesson's change per tract: the summed size of the change of the synapses from one of
        its populations to another, the largest first."""
        after = np.asarray(self.meaning.brain.brain.efficacy, dtype=np.float64)
        d = np.abs(after - before)
        ok = (self.pre_pop >= 0) & (self.post_pop >= 0) & (d > 0)
        n = len(self.t_pops)
        sums = np.bincount(self.pre_pop[ok] * n + self.post_pop[ok], weights=d[ok], minlength=n * n)
        top = float(sums.max()) if sums.size else 0.0
        out = []
        for k in np.argsort(sums)[::-1][:6]:
            if sums[k] <= 0:
                break
            a, b = divmod(int(k), n)
            pa, pb = self.t_pops[a][0], self.t_pops[b][0]
            if pa["region"] != pb["region"]:
                out.append({"from": pa["region"], "to": pb["region"], "from_population": pa["name"], "to_population": pb["name"],
                            "change": round(float(sums[k]) / top, 3)})
        return out

    def meaning_op(self, op: dict[str, Any]) -> dict[str, Any]:
        m = self.meaning
        kind = op.get("op")
        began = time.perf_counter()
        out: dict[str, Any] = {"op": kind, "id": op.get("id")}
        things = [t for t in (op.get("things") or []) if t.get("kind") in m.spec["kinds"]]
        if kind == "begin":
            m.brain.reset()
            m.own = None
            m.turn_over()
        elif kind == "moment":
            g = op.get("glimpse")
            m.see(things, glimpse=things[g] if isinstance(g, int) and 0 <= g < len(things) else None)
            word = op.get("hear")
            m.hear(word if word in m.codes else None)
            in_turn = m.in_turn
            got: list[Any] = []
            with record_settlements(got.append, label="trained moment"):
                out["said"] = m.moment(more=bool(op.get("more")))
            if out["said"]:  # the word said recalls its sound: the record its link reads back from the word
                slot, link = self.hearing.mem.recall(out["said"])
                out["sound"] = None if slot is None else {"id": f"you-{slot}", "slot": int(slot), "link": link}
            self.settle = self._settle_viz(got)
            if m.in_turn and not in_turn:
                out["recalled"] = self._recalled()
            self.moments += 1
        elif kind == "look":  # between questions: it sees the room, its focus on a thing, its voice held
            g = op.get("glimpse")
            m.see(things, glimpse=things[g] if isinstance(g, int) and 0 <= g < len(things) else None)
            m.hear(None)
            got = []
            with record_settlements(got.append, label="trained look"):
                m.moment(more=True)
            self.settle = self._settle_viz(got)
            self.moments += 1
        elif kind == "pistachio":
            before = np.asarray(m.brain.brain.efficacy, dtype=np.float64).copy()
            # the meaning lane's page setting: each word of the reply taught once, at a small amount
            # (with it a paid name leaves the colour answer standing: page_test.py, COORD 02:06)
            taken = m.pistachio(float(op.get("amount", PISTACHIO)), first=True)
            out.update(lessons=taken, paid=self._paid(before) if taken else [])
            self.lessons += taken
            m.turn_over()
        elif kind == "correct":
            word = str(op.get("word") or "")
            wrote = m.correct(word) if word in m.codes else False
            out.update(word=word, known=word in m.codes, wrote=bool(wrote))
            self.records_written += int(bool(wrote))
            if word in m.codes:  # the trainer says the word after the reply: heard, the voice held
                m.see(things)
                m.hear(word)
                m.moment(more=True)
            m.turn_over()
        elif kind == "over":
            m.turn_over()
        else:
            raise ValueError(f"unknown trained-brain step {kind!r}")
        self._activation()
        if kind in ("moment", "look", "correct"):
            out["mind"] = self._mind()
        out["records"] = 0 if m.records is None else int(m.records.count)
        out["ms"] = round(1000.0 * (time.perf_counter() - began), 1)
        return out

    def step(self, meta: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
        op = meta.get("meaning")
        paid = isinstance(op, dict) and op.get("op") == "pistachio"
        out = super().step({**meta, "reward": 0.0} if paid else meta, arrays)
        self.settle = None
        if isinstance(op, dict):
            got = self.meaning_op(op)
            out["meaning"] = got
            if paid:  # the pistachio rewards the trained brain's reply: its lesson is the reward's
                out.update(reward=float(op.get("amount", 1.0)), vta=float(op.get("amount", 1.0)) if got.get("lessons") else 0.0,
                           paid=got.get("paid", []))
        self.buffers["activity"][self.t_start:] = self.t_activity
        out["trained_moments"] = self.moments
        if self.settle is not None:  # the trained brain's settle joins the body's (each of its moments)
            viz = dict(out.get("viz") or {"v": 1})
            body = viz.get("settle") or {}
            regions = dict(body.get("regions") or {})
            for a, v in self.settle["regions"].items():
                regions[a] = [max(x, y) for x, y in zip(regions[a], v)] if a in regions and len(regions[a]) == len(v) else v
            viz["settle"] = {**self.settle, "regions": regions, "tracts": list(body.get("tracts") or []) + self.settle["tracts"],
                             "sweeps": max(int(body.get("sweeps") or 0), self.settle["sweeps"])}
            out["viz"] = viz
        return out
