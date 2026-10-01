"""Experimental ordinary-graph proposals for the frozen Amen first-batch energy.

No Brain admission is fabricated. Both candidate methods are fixed in advance;
all points are independently checked against the frozen scalar reference.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

import amen_architecture_calibrate as A
import numpy as np

from cadence import Brain, _repair

METHODS = ("diagonal_spectral", "gauss_newton_cg")


def plain(value):
    """Receipt encoding only: do not alter any numerical solve value."""
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def write(path, value):
    A.write(path, plain(value))


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Energy:
    """Dense ordinary contacts, exact mean energy and analytic derivatives."""

    def __init__(self, brain, examples):
        self.graph = brain.graph
        self.B = len(examples)
        self.N = brain.graph.n_patches
        self.I = brain.graph.n_inputs
        self.E = len(brain.weights)
        self.alpha = brain.config["state_prior"]
        self.beta = brain.config["parameter_prior"]
        self.state_bound = brain.config["state_bound"]
        self.parameter_bound = brain.config["parameter_bound"]
        inputs = []
        fixed = {}
        for r, (v, t) in enumerate(examples):
            flat, clamps = brain._arguments(v, t)
            inputs.append(flat)
            fixed.update({r * self.N + i: y for i, y in clamps.items()})
        self.X = np.asarray(inputs)
        self.sample_digest = digest({"inputs": inputs, "clamps": sorted(fixed.items())})
        self.fixed = fixed
        self.mask = np.ones(self.B * self.N, dtype=bool)
        self.mask[list(fixed)] = False
        self.ei = np.asarray(
            [i for i, e in enumerate(self.graph.edges) if e[0] == "input"], dtype=int
        )
        self.es = np.asarray(
            [i for i, e in enumerate(self.graph.edges) if e[0] == "state"], dtype=int
        )
        if len(self.ei) + len(self.es) != self.E:
            raise ValueError("ordinary contacts only")
        if any(k == "state" and s == t for k, s, t in self.graph.edges):
            raise ValueError("this diagonal formula excludes self contacts")
        if len(set(self.graph.edges)) != self.E:
            raise ValueError("parallel identical contacts unsupported")
        self.si = np.asarray([self.graph.edges[i][1] for i in self.ei], dtype=int)
        self.ti = np.asarray([self.graph.edges[i][2] for i in self.ei], dtype=int)
        self.ss = np.asarray([self.graph.edges[i][1] for i in self.es], dtype=int)
        self.ts = np.asarray([self.graph.edges[i][2] for i in self.es], dtype=int)
        self.w0 = np.asarray(brain.weights)
        self.b0 = np.asarray(brain.biases)
        self.anchor = np.r_[self.w0, self.b0]
        self.initial = np.r_[np.tile(brain.state, self.B), self.anchor]
        self.initial = self.project(self.initial)
        self.evaluations = 0
        self.returned_evaluations = 0
        self.jv_calls = 0
        self.jt_calls = 0
        self.seconds = 0.0

    def split(self, x):
        return (
            x[: self.B * self.N].reshape(self.B, self.N),
            x[self.B * self.N : self.B * self.N + self.E],
            x[-self.N :],
        )

    def matrices(self, w):
        wi = np.zeros((self.N, self.I))
        ws = np.zeros((self.N, self.N))
        wi[self.ti, self.si] = w[self.ei]
        ws[self.ts, self.ss] = w[self.es]
        return wi, ws

    def gather(self, wi, ws):
        result = np.empty(self.E)
        result[self.ei] = wi[self.ti, self.si]
        result[self.es] = ws[self.ts, self.ss]
        return result

    def project(self, x):
        out = x.copy()
        n = self.B * self.N
        out[:n] = np.clip(out[:n], -self.state_bound, self.state_bound)
        out[n:] = np.clip(out[n:], -self.parameter_bound, self.parameter_bound)
        for i, v in self.fixed.items():
            out[i] = v
        return out

    def free(self, x):
        out = x.copy()
        out[: self.B * self.N][~self.mask] = 0
        return out

    def evaluate(self, x):
        start = time.perf_counter()
        self.evaluations += 1
        z, w, b = self.split(x)
        wi, ws = self.matrices(w)
        pred = np.tanh(self.X @ wi.T + z @ ws.T + b)
        error = z - pred
        slope = 1 - pred**2
        energy = float(
            (np.sum(error**2) + self.alpha * np.sum(z**2)) / (2 * self.B)
            + self.beta * (np.sum((w - self.w0) ** 2) + np.sum((b - self.b0) ** 2)) / 2
        )
        h = -error * slope
        gz = (error + self.alpha * z + h @ ws) / self.B
        gw = self.gather(h.T @ self.X / self.B, h.T @ z / self.B) + self.beta * (
            w - self.w0
        )
        gb = h.sum(axis=0) / self.B + self.beta * (b - self.b0)
        g = self.free(np.r_[gz.reshape(-1), gw, gb])
        aux = (z, w, b, wi, ws, pred, error, slope)
        if not np.isfinite(energy) or not np.isfinite(g).all():
            raise ValueError("nonfinite objective")
        self.seconds += time.perf_counter() - start
        self.returned_evaluations += 1
        return energy, g, aux

    def diagonal(self, aux):
        z, _, _, _, ws, _, _, slope = aux
        squared = slope**2
        dz = (1 + self.alpha + squared @ (ws**2)) / self.B
        dw = (
            self.gather(squared.T @ (self.X**2) / self.B, squared.T @ (z**2) / self.B)
            + self.beta
        )
        db = squared.mean(axis=0) + self.beta
        d = np.r_[dz.reshape(-1), dw, db]
        if not np.all(d > 0):
            raise ValueError("nonpositive GN diagonal")
        return d

    def residual(self, x, aux):
        z, w, b, _, _, _, error, _ = aux
        return np.r_[
            error.reshape(-1) / math.sqrt(self.B),
            math.sqrt(self.alpha / self.B) * z.reshape(-1),
            math.sqrt(self.beta) * (w - self.w0),
            math.sqrt(self.beta) * (b - self.b0),
        ]

    def jv(self, v, aux):
        self.jv_calls += 1
        v = self.free(v)
        dz, dw, db = self.split(v)
        z, _, _, _, ws, _, _, slope = aux
        dwi, dws = self.matrices(dw)
        de = dz - slope * (self.X @ dwi.T + z @ dws.T + dz @ ws.T + db)
        return np.r_[
            de.reshape(-1) / math.sqrt(self.B),
            math.sqrt(self.alpha / self.B) * dz.reshape(-1),
            math.sqrt(self.beta) * dw,
            math.sqrt(self.beta) * db,
        ]

    def jt(self, v, aux):
        self.jt_calls += 1
        n = self.B * self.N
        ve = v[:n].reshape(self.B, self.N)
        vz = v[n : 2 * n].reshape(self.B, self.N)
        vw = v[2 * n : 2 * n + self.E]
        vb = v[-self.N :]
        z, _, _, _, ws, _, _, slope = aux
        h = -slope * ve / math.sqrt(self.B)
        gz = ve / math.sqrt(self.B) + h @ ws + math.sqrt(self.alpha / self.B) * vz
        gw = self.gather(h.T @ self.X, h.T @ z) + math.sqrt(self.beta) * vw
        gb = h.sum(axis=0) + math.sqrt(self.beta) * vb
        return self.free(np.r_[gz.reshape(-1), gw, gb])

    def stationarity(self, x, g):
        scaled = g.copy()
        scaled[: self.B * self.N] *= self.B
        proposed = self.project(x - scaled)
        return float(np.max(np.abs(x - proposed)))

    def reference(self, x):
        z, w, b = self.split(x)
        r = _repair._evaluate_batch(
            self.graph,
            tuple(self.X.reshape(-1)),
            tuple(z.reshape(-1)),
            tuple(w),
            tuple(b),
            self.alpha,
            tuple(self.w0),
            tuple(self.b0),
            self.beta,
            batch_size=self.B,
        )
        g = self.free(
            np.r_[r["gradient_state"], r["gradient_weights"], r["gradient_biases"]]
        )
        residual = _repair._stationarity(
            tuple(z.reshape(-1)),
            tuple(w),
            tuple(b),
            r,
            self.fixed,
            True,
            self.state_bound,
            self.parameter_bound,
            state_scale=self.B,
        )
        return r, g, residual


def checks(energy, baseline):
    rng = np.random.default_rng(20261012)
    points = [("initial", energy.initial.copy()), ("public_baseline", baseline.copy())]
    perturbed = energy.project(
        energy.initial + rng.normal(0, 0.025, len(energy.initial))
    )
    points.append(("seeded_interior", perturbed))
    bound = perturbed.copy()
    free = np.flatnonzero(energy.mask)
    bound[free[0]] = energy.state_bound
    bound[energy.B * energy.N] = energy.parameter_bound
    bound[-1] = -energy.parameter_bound
    points.append(("active_bounds", bound))
    records = []
    for label, x in points:
        f, g, aux = energy.evaluate(x)
        r, rg, rs = energy.reference(x)
        v = energy.free(rng.normal(size=len(x)))
        v /= np.linalg.norm(v)
        jv = energy.jv(v, aux)
        probe = rng.normal(size=len(jv))
        jt = energy.jt(probe, aux)
        eps = 1e-6
        fp, _, ap = energy.evaluate(x + eps * v)
        fm, _, am = energy.evaluate(x - eps * v)
        fd = (energy.residual(x + eps * v, ap) - energy.residual(x - eps * v, am)) / (
            2 * eps
        )
        item = {
            "point": label,
            "energy_difference": abs(f - r["energy"]),
            "gradient_max_difference": float(np.max(np.abs(g - rg))),
            "jt_residual_gradient_difference": float(
                np.max(np.abs(energy.jt(energy.residual(x, aux), aux) - g))
            ),
            "jv_fd_max_difference": float(np.max(np.abs(fd - jv))),
            "adjoint_dot_difference": abs(float(np.dot(jv, probe) - np.dot(v, jt))),
            "energy_directional_difference": abs((fp - fm) / (2 * eps) - np.dot(g, v)),
            "projected_stationarity_difference": abs(energy.stationarity(x, g) - rs),
            "reference_stationarity": rs,
        }
        if not (
            item["energy_difference"] <= 1e-10 * (1 + abs(f))
            and item["gradient_max_difference"] <= 1e-10
            and item["jt_residual_gradient_difference"] <= 1e-10
            and item["jv_fd_max_difference"] <= 1e-7
            and item["adjoint_dot_difference"] <= 1e-9
            and item["energy_directional_difference"] <= 1e-6
            and item["projected_stationarity_difference"] <= 1e-10
        ):
            raise ValueError(f"objective/derivative check failed: {item}")
        records.append(item)
    return records


def cg(energy, g, diagonal, aux):
    b = -g
    p = np.zeros_like(b)
    r = b.copy()
    z = r / diagonal
    d = z.copy()
    rz = float(r @ z)
    initial = float(np.linalg.norm(r))
    ratio = 1.0
    if initial == 0:
        return p, 0, 0.0
    for k in range(32):
        hd = energy.jt(energy.jv(d, aux), aux)
        curvature = float(d @ hd)
        if not np.isfinite(curvature) or curvature <= 0:
            raise ValueError("nonpositive CG curvature")
        step = rz / curvature
        p += step * d
        r -= step * hd
        ratio = float(np.linalg.norm(r) / initial)
        if ratio <= 1e-3:
            return p, k + 1, ratio
        z = r / diagonal
        newrz = float(r @ z)
        d = z + (newrz / rz) * d
        rz = newrz
    return p, 32, ratio


def solve(energy, method, out, trace):
    x = energy.initial.copy()
    f, g, aux = energy.evaluate(x)
    next_step = 1.0
    for iteration in range(8192):
        stationarity = energy.stationarity(x, g)
        if stationarity <= 1e-6:
            return x, "dense_stationary"
        diagonal = energy.diagonal(aux)
        inner = 0
        inner_ratio = None
        if method == "diagonal_spectral":
            direction = -g / diagonal
            step = next_step
        else:
            direction, inner, inner_ratio = cg(energy, g, diagonal, aux)
            step = 1.0
        accepted = False
        for backtrack in range(32):
            candidate = energy.project(x + step * direction)
            delta = candidate - x
            slope = float(g @ delta)
            if slope >= 0:
                step *= 0.5
                continue
            nf, ng, naux = energy.evaluate(candidate)
            ulps = 8 * max(abs(f), np.finfo(float).tiny) * np.finfo(float).eps
            if nf <= f + 1e-4 * slope or (
                abs(nf - f) <= ulps and energy.stationarity(candidate, ng) <= 1e-6
            ):
                accepted = True
                break
            step *= 0.5
        row = {
            "iteration": iteration,
            "energy": f,
            "stationarity": stationarity,
            "accepted": accepted,
            "backtracks": backtrack,
            "step": step,
            "cg_iterations": inner,
            "cg_relative_residual": inner_ratio,
        }
        trace.append(row)
        with (out / "iterations.jsonl").open("a") as log:
            log.write(json.dumps(plain(row), allow_nan=False) + "\n")
        if not accepted:
            return x, "line_search_refused"
        curvature = float(delta @ (ng - g))
        next_step = 1.0
        if method == "diagonal_spectral" and curvature > 0:
            next_step = min(float(np.dot(delta * diagonal, delta)) / curvature, 2.0**31)
        x, f, g, aux = candidate, nf, ng, naux
        # Last accepted numerical point is independent of any public admission.
        if (iteration + 1) % 100 == 0:
            np.save(out / "latest-point.npy", x)
    return x, "iteration_limit"


def environment(root):
    p = A.read(root / "runtime600/protocol.json")
    old = A.read(Path(p["prior_protocol"]))
    if A.sha(p["prior_protocol"]) != p["prior_sha256"]:
        raise ValueError("inherited protocol drift")
    if any(A.sha(k) != v for k, v in p["sources"].items()):
        raise ValueError("inherited source drift")
    for name, pin in old["data_pins"].items():
        if A.sha(Path(old["base"]) / "data" / name) != pin:
            raise ValueError("frozen row cache changed")
    initial = Brain.from_snapshot((root / "runtime600/plain/initial.json").read_text())
    _, T = A.modules(Path(old["app"]))
    base = Path(old["base"])
    rows = tuple(
        np.load(base / "data" / f"{n}.npy", mmap_mode="r")
        for n in ("history", "clock", "wake", "targets", "origin")
    )
    examples = [T.example(rows, i, 8) for i in old["indices"]]
    final = Brain.from_snapshot(
        (root / "runtime600/plain/discarded-final.json").read_text()
    )
    result = A.read(root / "runtime600/plain/discarded-admission-result.json")["result"]
    baseline = np.r_[
        np.asarray(result["states"]).reshape(-1), final.weights, final.biases
    ]
    return p, Energy(initial, examples), baseline


def bound(root, out):
    p = A.read(out / "protocol.json")
    for name, expected in p["artifacts"].items():
        if A.sha(name) != expected:
            raise ValueError(f"artifact drift: {name}")
    if any(A.sha(k) != v for k, v in p["sources"].items()):
        raise ValueError("source drift")
    if p["numpy"] != np.__version__ or p["methods"] != list(METHODS):
        raise ValueError("runtime/method drift")
    return p


def freeze(root, out):
    p, energy, _ = environment(root)
    if (energy.B, energy.N, energy.I, energy.E) != (32, 135, 585, 47735):
        raise ValueError("wrong fixed ordinary64 graph/batch dimensions")
    if (energy.alpha, energy.beta, energy.state_bound, energy.parameter_bound) != (
        0.01,
        0.4,
        1.0,
        4.0,
    ):
        raise ValueError("wrong fixed objective/bounds")
    out.mkdir(exist_ok=False)
    value = {
        "schema": "amen-same-energy-solvers/1",
        "receipt_encoding": "Python scalar JSON v2; preserved v1 failed final serialization, numerical methods unchanged",
        "sources": {
            **p["sources"],
            **{
                str(path.resolve()): A.sha(path)
                for path in (
                    Path(__file__),
                    Path(__file__).with_name("test_amen_solver_candidates.py"),
                )
            },
        },
        "parent_runtime_protocol_sha256": A.sha(root / "runtime600/protocol.json"),
        "initial_sha256": A.sha(root / "runtime600/plain/initial.json"),
        "baseline_result_sha256": A.sha(
            root / "runtime600/plain/discarded-admission-result.json"
        ),
        "artifacts": {
            str(path.resolve()): A.sha(path)
            for path in (
                root / "runtime600/protocol.json",
                root / "runtime600/plain/initial.json",
                root / "runtime600/plain/discarded-final.json",
                root / "runtime600/plain/discarded-admission-result.json",
                Path(p["prior_protocol"]),
            )
        },
        "methods": list(METHODS),
        "numpy": np.__version__,
        "backend": "NumPy float64 dense blocks; OPENBLAS_NUM_THREADS=1, OMP/MKL=4; at most4 CPUthreads percase. Existing nativeTorch4 baseline retained. Wall-time comparison combines backend/kernel and iteration changes; no method-only speed claim.",
        "batch": energy.B,
        "patches": energy.N,
        "inputs": energy.I,
        "weights": energy.E,
        "selected_inputs_and_clamps_sha256": energy.sample_digest,
        "alpha": energy.alpha,
        "beta": energy.beta,
        "state_bound": energy.state_bound,
        "parameter_bound": energy.parameter_bound,
        "tolerance": 1e-6,
        "outer_seconds": 600,
        "signal_seconds": 590,
        "iterations": 8192,
        "line_search_backtracks": 32,
        "armijo": 1e-4,
        "cg_max": 32,
        "cg_relative_residual": 1e-3,
        "validation_points": [
            "initial",
            "public_baseline",
            "seeded_interior",
            "active_bounds",
        ],
        "validation_seed": 20261012,
        "finite_difference_epsilon": 1e-6,
        "scope": "Two predeclared raw proposal solvers for EXACTsame meanresidual/stateprior + ONCEparameteranchor energy and actualclamps. No fabricated Brain admission or trainingquality claim; ordinary input/state contacts only, no residual/self contacts. Densekernel speed and proposalcounts separated. Allfailures retained; final original scalar reference qualification mandatory.",
    }
    predecessor = root / "acceleration"
    if predecessor != out and (predecessor / "execution.json").exists():
        value["prior_failed_attempt"] = str(predecessor)
        original = A.read(predecessor / "protocol.json")
        value["sources"].update(original["sources"])
        value["artifacts"].update(
            {
                str(path.resolve()): A.sha(path)
                for path in predecessor.rglob("*")
                if path.is_file()
            }
        )
    write(out / "protocol.json", value)
    print(A.sha(out / "protocol.json"), flush=True)


def alarm(*_):
    raise TimeoutError("candidate590second cap")


def arm(root, out, method):
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 590)
    started = time.monotonic()
    case = out / method
    case.mkdir(exist_ok=False)
    report = {"method": method, "status": "running", "public_admissions": 0}
    trace = []
    energy = None
    try:
        protocol = bound(root, out)
        report["protocol_sha256"] = A.sha(out / "protocol.json")
        _, energy, baseline = environment(root)
        if energy.sample_digest != protocol["selected_inputs_and_clamps_sha256"] or (
            energy.B,
            energy.N,
            energy.I,
            energy.E,
        ) != tuple(protocol[k] for k in ("batch", "patches", "inputs", "weights")):
            raise ValueError("selected rows or graph dimensions changed")
        np.save(case / "latest-point.npy", energy.initial)
        validation = checks(energy, baseline)
        write(case / "validation.json", validation)
        # Equal-point kernel timing, not extra optimization or quality selection.
        begins = time.perf_counter()
        for _ in range(20):
            energy.evaluate(energy.initial)
        dense_seconds = (time.perf_counter() - begins) / 20
        begins = time.perf_counter()
        energy.reference(energy.initial)
        reference_seconds = time.perf_counter() - begins
        report["kernel_seconds_per_evaluation"] = {
            "dense": dense_seconds,
            "frozen_reference": reference_seconds,
        }
        before = (energy.evaluations, energy.jv_calls, energy.jt_calls, energy.seconds)
        solve_start = time.perf_counter()
        x, status = solve(energy, method, case, trace)
        report["solve_seconds"] = time.perf_counter() - solve_start
        np.save(case / "candidate.npy", x)
        r, _rg, residual = energy.reference(x)
        report.update(
            status=status,
            reference_energy=r["energy"],
            reference_stationarity=residual,
            qualified=residual <= 1e-6,
            all_clamps_exact=all(x[i] == v for i, v in energy.fixed.items()),
            iterations=len(trace),
            evaluations=energy.evaluations - before[0],
            jv_calls=energy.jv_calls - before[1],
            jt_calls=energy.jt_calls - before[2],
            dense_evaluation_seconds=energy.seconds - before[3],
            candidate_sha256=A.sha(case / "candidate.npy"),
        )
        if report["qualified"] and not report["all_clamps_exact"]:
            raise ValueError("qualification with changed clamp")
    except Exception:  # noqa: BLE001 - retain every candidate/check failure.
        report.update(
            status="failed_or_time_limit",
            traceback=traceback.format_exc(),
            qualified=False,
            unknown_interrupted_solver_work=True,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["seconds"] = time.monotonic() - started
        report["completed_iterations"] = len(trace)
        try:
            bound(root, out)
            inherited = A.read(
                A.read(root / "runtime600/protocol.json")["prior_protocol"]
            )
            report["sources_and_artifacts_unchanged"] = all(
                A.sha(Path(inherited["base"]) / "data" / name) == pin
                for name, pin in inherited["data_pins"].items()
            )
        except Exception:  # noqa: BLE001 - mutation veto, preserving numeric record.
            report["sources_and_artifacts_unchanged"] = False
            report["custody_error"] = traceback.format_exc()
        if not report["sources_and_artifacts_unchanged"]:
            report["qualified"] = False
        if energy:
            report["all_phase_evaluations"] = energy.evaluations
            report["all_phase_returned_evaluations"] = energy.returned_evaluations
            report["unknown_incomplete_evaluations"] = (
                energy.evaluations - energy.returned_evaluations
            )
        report["public_admissions"] = 0
        write(case / "report.json", report)
    print(json.dumps(plain(report)), flush=True)


def launch(root, out):
    bound(root, out)

    def worker(method):
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "arm",
                    str(root),
                    "--out",
                    str(out),
                    "--method",
                    method,
                ],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
                env={
                    **os.environ,
                    "OMP_NUM_THREADS": "4",
                    "MKL_NUM_THREADS": "4",
                    "OPENBLAS_NUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                },
            )
            return {
                "method": method,
                "exit_code": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "method": method,
                "status": "outer_timeout",
                "stdout": str(e.stdout),
                "stderr": str(e.stderr),
            }
        except Exception:  # noqa: BLE001 - keep full case inventory.
            return {
                "method": method,
                "status": "launch_error",
                "traceback": traceback.format_exc(),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, METHODS))
    write(out / "execution.json", results)
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("freeze", "launch", "arm"))
    p.add_argument("root", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--method", choices=METHODS)
    a = p.parse_args()
    if a.mode == "freeze":
        freeze(a.root.resolve(), a.out.resolve())
    elif a.mode == "launch":
        launch(a.root.resolve(), a.out.resolve())
    else:
        arm(a.root.resolve(), a.out.resolve(), a.method)
