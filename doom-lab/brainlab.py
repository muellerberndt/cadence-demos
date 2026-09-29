"""The live Cadence student: persistent brain, real-time trainer, shadow.

One learning Brain is owned by the trainer thread; witnesses stream in from
the teacher window and are admitted through atomic ``observe_batch`` calls.
A separate read-only shadow Brain, refreshed from snapshots, answers
prediction requests from the UI and drives the student player mode without
violating the one-serial-owner-per-brain contract.
"""

from __future__ import annotations

import gzip
import json
import os
import queue
import random as _random
import threading
import time

import numpy as np

from cadence import Brain, Cortex
from doomlab import BUTTONS, buttons_from_scores
import norms as nz

CHECKPOINT = "data/live_brain.json.gz"
MODELS_DIR = "data/models"
POINTER = "data/current_model.json"
WITNESS_DIR = "data/sessions"
SETTLE_BUDGET = 16384
LIVE_BUDGET = 384  # per-query ceiling for interactive predictions
MAX_BATCH = 48
NOOP_KEEP = 0.25  # fraction of all-buttons-off human witnesses admitted


def build_layout(seed=7, device="cpu"):
    cortex = Cortex(seed=seed, device=device, settle_budget=SETTLE_BUDGET)
    periphery = cortex.input("periphery", shape=(20, 32))
    fovea = cortex.input("fovea", shape=(6, 64))
    scene = cortex.column("scene", patches=32, inputs=periphery)
    aim = cortex.column("aim", patches=24, inputs=fovea)
    integration = cortex.observer(
        "integration", patches=16, inputs=(periphery, fovea), observes=(scene, aim),
    )
    reflection = cortex.observer(
        "reflection", patches=8, observes=(scene, aim, integration),
    )
    cortex.output("motor", shape=(len(BUTTONS),), reads=reflection)
    return cortex.build()


class Student:
    """Owns the learning brain, its trainer thread and the shadow reader."""

    def __init__(self, device="cpu"):
        self.device = device
        self.norms = nz.ensure_live_norms()
        if os.path.exists(CHECKPOINT) and not os.path.exists(
                nz.sibling_path(CHECKPOINT)):
            # Pre-conditioning checkpoint: incompatible input units. Retire it.
            os.rename(CHECKPOINT, CHECKPOINT + ".preconditioning.bak")
        self.loaded = False
        if os.path.exists(CHECKPOINT):
            with gzip.open(CHECKPOINT, "rt") as f:
                candidate = Brain.from_snapshot(f.read(), device=device)
            if tuple(candidate.inspect()["outputs"][0]["shape"]) == (len(BUTTONS),):
                self.brain = candidate
                self.loaded = True
            else:
                os.rename(CHECKPOINT, CHECKPOINT + ".motorwidth.bak")
        if not self.loaded:
            self.brain = build_layout(device=device)
        self._shadow = Brain.from_snapshot(self.brain.snapshot(), device=device)
        self.model_id = "live"
        if os.path.exists(POINTER):
            try:
                self.model_id = json.load(open(POINTER)).get("id", "live")
            except ValueError:
                pass
        self._analyze()
        self._swap_request = None
        self._last_action = [0] * len(BUTTONS)
        self._teach_prev = [0] * len(BUTTONS)
        self._shadow_lock = threading.Lock()
        self._queue = queue.Queue(maxsize=4096)
        self._log = []
        self._log_lock = threading.Lock()
        self.stats = {
            "admitted": self.brain.inspect()["admissions"],
            "queued": 0,
            "batches": 0,
            "refusals": 0,
            "last_batch_seconds": None,
            "last_batch_size": 0,
            "checkpoint_loaded": self.loaded,
            "training": False,
        }
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._train_loop, daemon=True)
        self._thread.start()

    def _analyze(self):
        """Recompute everything derived from the current brain."""
        info = self.brain.inspect()
        self.layout_meta = [
            {"name": p["name"], "role": p["role"],
             "start": p["indices"][0], "count": p["patches"]}
            for p in info["populations"]
        ]
        self.has_efference = any(
            i["name"] == "efference" for i in info["inputs"])
        self.model_info = {"patches": info["patches"],
                           "edges": info["connections"],
                           "fingerprint": info["fingerprint"][:12]}
        self._graph_sample = self._sample_graph(max_edges=1400)

    # ---- model registry -----------------------------------------------

    def scan_models(self):
        models = []
        if os.path.isdir(MODELS_DIR):
            for name in sorted(os.listdir(MODELS_DIR)):
                if not name.endswith(".json.gz"):
                    continue
                model_id = name[: -len(".json.gz")]
                meta_path = os.path.join(MODELS_DIR, model_id + ".meta.json")
                label = model_id
                if os.path.exists(meta_path):
                    try:
                        label = json.load(open(meta_path)).get("label", model_id)
                    except ValueError:
                        pass
                models.append({"id": model_id, "label": label})
        return models

    def request_swap(self, model_id):
        path = os.path.join(MODELS_DIR, model_id + ".json.gz")
        if not os.path.exists(path) or not os.path.exists(
                nz.sibling_path(path)):
            return False
        self._swap_request = model_id
        return True

    def _apply_swap(self):
        model_id, self._swap_request = self._swap_request, None
        path = os.path.join(MODELS_DIR, model_id + ".json.gz")
        with gzip.open(path, "rt") as f:
            brain = Brain.from_snapshot(f.read(), device=self.device)
        replacement = Brain.from_snapshot(brain.snapshot(), device=self.device)
        self.brain = brain
        self.norms = nz.load(nz.sibling_path(path))
        with self._shadow_lock:
            self._shadow = replacement
        self.model_id = model_id
        self._analyze()
        self._last_action = [0] * len(BUTTONS)
        # Queued witnesses were sampled for the previous brain's boundaries.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self.stats["queued"] = 0
        self.stats["admitted"] = self.brain.inspect()["admissions"]
        json.dump({"id": model_id}, open(POINTER, "w"))

    def _sample_graph(self, max_edges=1400):
        """Stratified edge sample per functional pathway, for the 3D view."""
        graph = self.brain.graph
        def zone(kind, source):
            if kind == "input":
                return "periphery" if source < 640 else "fovea"
            for p in self.layout_meta:
                if p["start"] <= source < p["start"] + p["count"]:
                    return p["name"]
            return "?"
        def pop_of(target):
            return zone("state", target)
        groups = {}
        for index, (kind, source, target) in enumerate(graph.edges):
            groups.setdefault((kind, zone(kind, source), pop_of(target)),
                              []).append(index)
        total = len(graph.edges)
        rng = _random.Random(7)
        kinds = {"input": 0, "state": 1, "residual": 2}
        sample = []
        for (kind, _, _), members in groups.items():
            if kind == "input":
                take = max(6, int(max_edges * len(members) / total))
            else:
                # Recursive readback is the anatomy worth seeing; keep the
                # bundles thick even though they are numerically few.
                take = min(90, len(members))
            for index in (rng.sample(members, take) if take < len(members)
                          else members):
                sample.append(index)
        edges = []
        for index in sorted(sample):
            kind, source, target = graph.edges[index]
            edges.append((kinds[kind], source, target, index))
        return edges

    def graph_payload(self):
        """Static topology sample plus the current weights on those edges."""
        weights = self.brain.weights
        return {
            "n_periphery": 640,
            "n_fovea": 384,
            "populations": self.layout_meta,
            "motor": len(BUTTONS),
            "edges": [[k, s, t, round(weights[i], 3)]
                      for k, s, t, i in self._graph_sample],
        }

    def export_bundle(self):
        """Portable brain file: snapshot + norms + provenance."""
        return {
            "schema": "doomlab-brain/1",
            "model_id": self.model_id,
            "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "norms": self.norms,
            "snapshot": self.brain.snapshot(),
        }

    def import_bundle(self, name, data):
        """Validate an uploaded brain fully, then install it in the registry."""
        if not isinstance(data, dict) or data.get("schema") != "doomlab-brain/1":
            raise ValueError("Not a doomlab brain bundle")
        snapshot = data["snapshot"]
        Brain.from_snapshot(snapshot, device=self.device)  # full validation
        norms = data["norms"]
        for field in ("periphery", "fovea", "clip", "scale"):
            if field not in norms:
                raise ValueError("Bundle norms are incomplete")
        model_id = "".join(c if c.isalnum() or c in "-_" else "-"
                           for c in name)[:48] or "imported"
        os.makedirs(MODELS_DIR, exist_ok=True)
        path = os.path.join(MODELS_DIR, model_id + ".json.gz")
        with gzip.open(path, "wt") as f:
            f.write(snapshot)
        nz.save(norms, nz.sibling_path(path))
        with open(os.path.join(MODELS_DIR, model_id + ".meta.json"), "w") as f:
            json.dump({"label": model_id + " (imported)",
                       "imported": time.strftime("%Y-%m-%d")}, f)
        return model_id

    # ---- teacher side -------------------------------------------------

    def submit_witness(self, periphery, fovea, buttons, rng):
        """Queue one human decision; no-ops are subsampled, never all kept."""
        if not any(buttons) and rng.random() > NOOP_KEEP:
            return False
        periphery, fovea = nz.apply(self.norms, np.asarray(periphery),
                                    np.asarray(fovea))
        efference = tuple(self._teach_prev)
        self._teach_prev = [int(b) for b in buttons]
        record = (
            periphery.astype(np.float32),
            fovea.astype(np.float32),
            tuple(int(b) for b in buttons),
            efference,
        )
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            return False
        with self._log_lock:
            self._log.append(record)
        self.stats["queued"] = self._queue.qsize()
        return True

    def _train_loop(self):
        from doomlab import targets_from_buttons

        while not self._stop.is_set():
            if self._swap_request is not None:
                self._apply_swap()
            batch = []
            try:
                batch.append(self._queue.get(timeout=0.5))
            except queue.Empty:
                self.stats["training"] = False
                continue
            # Ramp batch size on a cold brain: small batches qualify first.
            cap = MAX_BATCH if self.stats["batches"] >= 3 else 8
            while len(batch) < cap:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            self.stats["training"] = True
            examples = []
            for per, fov, buttons, efference in batch:
                inputs = {"periphery": per.tolist(), "fovea": fov.tolist()}
                if self.has_efference:
                    inputs["efference"] = [0.6 if b else -0.6
                                           for b in efference]
                examples.append(
                    (inputs, {"motor": targets_from_buttons(buttons)}))
            started = time.perf_counter()
            try:
                result = self.brain.observe_batch(examples)
                accepted = bool(result["accepted"])
            except ValueError:
                accepted = False
            self.stats["last_batch_seconds"] = round(
                time.perf_counter() - started, 2)
            self.stats["last_batch_size"] = len(batch)
            self.stats["batches"] += 1
            if accepted:
                self.stats["admitted"] += len(batch)
                snapshot = self.brain.snapshot()
                replacement = Brain.from_snapshot(snapshot, device=self.device)
                with self._shadow_lock:
                    self._shadow = replacement
            else:
                self.stats["refusals"] += 1
                if len(batch) > 1:
                    # Split and requeue once rather than losing witnesses.
                    half = len(batch) // 2
                    for part in (batch[:half], batch[half:]):
                        try:
                            for record in part:
                                self._queue.put_nowait(record)
                        except queue.Full:
                            break
            self.stats["queued"] = self._queue.qsize()

    # ---- reader side --------------------------------------------------

    def predict_buttons(self, periphery, fovea):
        """Shadow-brain prediction: scores, decoded buttons, qualification.

        The lock is held through the solve: brains require one serial caller,
        and the trainer may swap in a fresher shadow between predictions.
        """
        periphery, fovea = nz.apply(self.norms, periphery, fovea)
        inputs = {"periphery": periphery.ravel().tolist(),
                  "fovea": fovea.ravel().tolist()}
        if self.has_efference:
            inputs["efference"] = [0.6 if b else -0.6
                                   for b in self._last_action]
        with self._shadow_lock:
            result = self._shadow.step(inputs, budget=LIVE_BUDGET)
        scores = result["outputs"]["motor"]
        decoded = buttons_from_scores(scores)
        if result["qualified"]:
            self._last_action = decoded
        outcome = result["outputs"].get("outcome")
        return {
            "scores": [round(s, 3) for s in scores],
            "outcome": [round(v, 3) for v in outcome] if outcome else None,
            "buttons": decoded,
            "qualified": result["qualified"],
            "sweeps": result["sweeps"],
            "state": [round(x, 3) for x in result["state"]],
            "errors": [round(e, 3) for e in result["errors"]],
            "retina_p": [round(float(v), 2) for v in np.ravel(periphery)],
            "retina_f": [round(float(v), 2) for v in np.ravel(fovea)],
            "energy": round(result["energy"], 5),
            "stationarity": float(f"{result['stationarity']:.2e}"),
        }

    # ---- persistence --------------------------------------------------

    def save(self):
        os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
        with gzip.open(CHECKPOINT, "wt") as f:
            f.write(self.brain.snapshot())
        nz.save(self.norms, nz.sibling_path(CHECKPOINT))
        with self._log_lock:
            log, self._log = self._log, []
        if log:
            os.makedirs(WITNESS_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            np.savez_compressed(
                os.path.join(WITNESS_DIR, f"session_{stamp}.npz"),
                periphery=np.stack([r[0] for r in log]),
                fovea=np.stack([r[1] for r in log]),
                buttons=np.array([r[2] for r in log], np.int8),
            )
        return {"admitted": self.stats["admitted"], "logged": len(log)}

    def close(self):
        self._stop.set()
        self._thread.join(timeout=5)
        return self.save()
