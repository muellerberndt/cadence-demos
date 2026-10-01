"""Two discarded ordinary-layer timing probes; no quality or hyperparameter selection."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

import cadence

WIDTHS = (64, 256)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def modules(app):
    sys.path.insert(0, str(app))
    from drsn_amen import model, train

    return model, train


def source_pins(app):
    return {
        str(p.resolve()): sha(p)
        for p in [
            Path(__file__),
            *sorted((app / "drsn_amen").glob("*.py")),
            *sorted(Path(cadence.__file__).parent.glob("*.py")),
        ]
    }


def build(M, width):
    return M.layout(
        steps=8,
        hearing=width,
        groove=0,
        seed=1103,
        device="cpu",
        dtype="float64",
        parameter_prior=0.4,
        tolerance=1e-6,
        settle_budget=2048,
        initial_scale=0.3,
        state_prior=0.01,
        playing_reads="compose",
        wiring="layered",
    )


def require_ordinary(brain):
    if any(kind not in ("input", "state") for kind, _, _ in brain.graph.edges):
        raise ValueError("unexpected observer or unsupported contact")


def freeze(root, app, base):
    import torch

    root.mkdir(exist_ok=False)
    original = read(base / "protocol.json")
    if (
        sha(base / "protocol.json")
        != "6b04f951dd45372a75f00b693f6fb7fe5288039cf3abddceb8f4dc37729eaffa"
    ):
        raise ValueError("wrong frozen control")
    value = {
        "schema": "amen-ordinary-timing/1",
        "app": str(app),
        "base": str(base),
        "sources": source_pins(app),
        "widths": list(WIDTHS),
        "seed": 1103,
        "threads": 4,
        "outer_seconds": 120,
        "signal_seconds": 115,
        "indices": read(base / "schedules.json")["1103"]["uniform"][0],
        "query": read(base / "heldout.json")[0]["inputs"],
        "query_sha256": sha(base / "heldout.json"),
        "data_pins": original["data_files"],
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "cadence": cadence.__version__,
        },
        "scope": "Only first uniform32 witness batch plus one newborn and one post-admission heldout free-query timing. All outcomes/censors retained; discard both resulting brains. No MAE/audio/quality selection. Plan training runtime from both fixed timing probes, before freezing new six-case endpoints.",
    }
    write(root / "protocol.json", value)
    print(sha(root / "protocol.json"), flush=True)


def alarm(*_):
    raise TimeoutError("discarded probe115second cap")


def arm(root, width):
    import torch

    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 115)
    started = time.monotonic()
    out = root / f"ordinary{width}"
    out.mkdir(exist_ok=False)
    report = {"width": width, "status": "running", "calls": []}
    brain = None
    try:
        torch.set_num_threads(4)
        p = read(root / "protocol.json")
        app = Path(p["app"])
        base = Path(p["base"])
        if p["sources"] != source_pins(app):
            raise ValueError("source drift")
        for name, pin in p["data_pins"].items():
            if sha(base / "data" / name) != pin:
                raise ValueError("row cache changed")
        M, T = modules(app)
        brain = build(M, width)
        info = brain.inspect()
        if len(brain.weights) + len(brain.biases) != {64: 47870, 256: 174014}[width]:
            raise ValueError("topology count")
        require_ordinary(brain)
        report.update(
            patches=info["patches"],
            parameters=len(brain.weights) + len(brain.biases),
            protocol_sha256=sha(root / "protocol.json"),
        )
        (out / "initial.json").write_text(brain.snapshot())
        rows = tuple(
            np.load(base / "data" / f"{n}.npy", mmap_mode="r")
            for n in ("history", "clock", "wake", "targets", "origin")
        )
        examples = [T.example(rows, i, 8) for i in p["indices"]]
        for name, operation in [
            ("newborn-query", lambda: brain.settle(p["query"])),
            (
                "discarded-admission",
                lambda: brain.observe_batch(examples, budget=8192, source="witness"),
            ),
            ("post-query", lambda: brain.settle(p["query"])),
        ]:
            before = brain.snapshot()
            intent = {
                "name": name,
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
            }
            write(out / f"{name}-intent.json", intent)
            begin = time.monotonic()
            try:
                result = operation()
                parameters = {
                    k: result[k] for k in ("weights", "biases") if k in result
                }
                compact = {k: v for k, v in result.items() if k not in parameters}
                compact["parameters_sha256"] = hashlib.sha256(
                    json.dumps(
                        parameters,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode()
                ).hexdigest()
                call = dict(
                    **intent,
                    status="returned",
                    seconds=time.monotonic() - begin,
                    result=compact,
                    after_sha256=hashlib.sha256(brain.snapshot().encode()).hexdigest(),
                )
            except Exception:
                call = dict(
                    **intent,
                    status="interrupted_or_error",
                    seconds=time.monotonic() - begin,
                    unknown_solver_work=True,
                    traceback=traceback.format_exc(),
                )
                report["calls"].append(call)
                write(out / f"{name}-result.json", call)
                raise
            report["calls"].append(call)
            write(out / f"{name}-result.json", call)
            if name == "discarded-admission":
                (out / "discarded-final.json").write_text(brain.snapshot())
        report["status"] = "complete"
    except Exception:  # noqa: BLE001 - preserve every discarded probe failure.
        report.update(status="error_or_time_limit", traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["seconds"] = time.monotonic() - started
        report["sources_unchanged"] = read(root / "protocol.json")[
            "sources"
        ] == source_pins(Path(read(root / "protocol.json")["app"]))
        returned = [r for r in report["calls"] if r["status"] == "returned"]
        report["qualified_calls"] = sum(r["result"]["qualified"] for r in returned)
        report["accepted_admissions"] = sum(
            r["name"] == "discarded-admission" and r["result"]["accepted"]
            for r in returned
        )
        report["timing_usable"] = (
            report["status"] == "complete"
            and report["qualified_calls"] == 3
            and report["accepted_admissions"] == 1
            and report["sources_unchanged"]
        )
        write(out / "report.json", report)
    print(
        json.dumps(
            {"width": width, "status": report["status"], "seconds": report["seconds"]}
        ),
        flush=True,
    )


def launch(root):
    def worker(width):
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "arm",
                    str(root),
                    "--width",
                    str(width),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env={
                    **os.environ,
                    "OMP_NUM_THREADS": "4",
                    "MKL_NUM_THREADS": "4",
                    "OPENBLAS_NUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                },
                check=False,
            )
            return {
                "width": width,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "width": width,
                "status": "outer_timeout",
                "stdout": str(e.stdout),
                "stderr": str(e.stderr),
            }
        except Exception:  # noqa: BLE001 - preserve all planned launch outcomes.
            return {
                "width": width,
                "status": "launch_error",
                "traceback": traceback.format_exc(),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, WIDTHS))
    write(root / "execution.json", outcomes)
    print(json.dumps(outcomes), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "launch", "arm"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--width", type=int, choices=WIDTHS)
    a = parser.parse_args()
    if a.mode == "freeze":
        freeze(a.root.resolve(), a.app.resolve(), a.base.resolve())
    elif a.mode == "launch":
        launch(a.root.resolve())
    else:
        arm(a.root.resolve(), a.width)
