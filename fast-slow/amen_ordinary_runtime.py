"""Two discarded, identical ordinary64 first-batch runtime diagnostics.

Plain versus cProfile instrumentation, both four threads, capped600seconds.
No quality selection, learning-rule changes, or campaign continuation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import cProfile
import faulthandler
import hashlib
import json
import os
import pstats
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

import amen_architecture_calibrate as A
import numpy as np


def compact(result):
    parameters = {k: result[k] for k in ("weights", "biases") if k in result}
    return {
        **{k: v for k, v in result.items() if k not in parameters},
        "parameters_sha256": hashlib.sha256(
            json.dumps(
                parameters, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest(),
    }


def freeze(root, base):
    root.mkdir(exist_ok=False)
    p = A.read(base / "protocol.json")
    if (
        A.sha(base / "protocol.json")
        != "855e21f1be991700b7b9c731fa9fc9188ac5f342c9e87da6198ddb99204233a7"
    ):
        raise ValueError("wrong timing baseline")
    if p["sources"] != A.source_pins(Path(p["app"])):
        raise ValueError("timing source drift")
    protocol = {
        "schema": "amen-ordinary64-runtime/1",
        "prior_protocol": str(base / "protocol.json"),
        "prior_sha256": A.sha(base / "protocol.json"),
        "sources": {**p["sources"], str(Path(__file__).resolve()): A.sha(__file__)},
        "cases": ["plain", "profiled"],
        "width": 64,
        "threads": 4,
        "outer_seconds": 600,
        "signal_seconds": 595,
        "call": "samefirst32uniformseed1103witnessbatch after samepure newbornquery",
        "instrumentation": "profiled arm enablescProfile ONLY aroundadmission; bothfaulthandlerstacks every60seconds; no numericalcore edits; timing difference includesprofileroverhead",
        "scope": "Both brains discarded. No MAE/audio/gate/modelselection. Return actualpublicwork ifsolve returns; unknownwork oninterruption. Do notextrapolatefastrefusal toaccepted trainingtime.",
    }
    A.write(root / "protocol.json", protocol)
    print(A.sha(root / "protocol.json"), flush=True)


def alarm(*_):
    raise TimeoutError("runtime diagnostic595second deadline")


def summarize(profile):
    stats = pstats.Stats(profile)
    rows = [
        {
            "file": k[0],
            "line": k[1],
            "function": k[2],
            "primitive_calls": v[0],
            "calls": v[1],
            "own_seconds": v[2],
            "cumulative_seconds": v[3],
        }
        for k, v in stats.stats.items()
    ]
    return {
        "total_calls": stats.total_calls,
        "primitive_calls": stats.prim_calls,
        "total_profile_seconds": stats.total_tt,
        "top_cumulative": sorted(
            rows, key=lambda r: r["cumulative_seconds"], reverse=True
        )[:80],
        "top_own": sorted(rows, key=lambda r: r["own_seconds"], reverse=True)[:80],
        "cadence_functions": [r for r in rows if "/cadence/" in r["file"]],
    }


def arm(root, case):
    import torch

    started = time.monotonic()
    signal.signal(signal.SIGALRM, alarm)
    signal.signal(signal.SIGTERM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 595)
    out = root / case
    out.mkdir(exist_ok=False)
    report = {"case": case, "status": "running", "calls": [], "threads": 4}
    profile = cProfile.Profile() if case == "profiled" else None
    stacks = (out / "progress-stacks.log").open("w")
    faulthandler.dump_traceback_later(60, repeat=True, file=stacks)
    try:
        torch.set_num_threads(4)
        p = A.read(root / "protocol.json")
        old = A.read(Path(p["prior_protocol"]))
        if any(A.sha(k) != v for k, v in p["sources"].items()):
            raise ValueError("frozen source drift")
        if A.sha(Path(p["prior_protocol"])) != p["prior_sha256"]:
            raise ValueError("protocol drift")
        M, T = A.modules(Path(old["app"]))
        brain = A.build(M, 64)
        A.require_ordinary(brain)
        (out / "initial.json").write_text(brain.snapshot())
        report["initial_sha256"] = A.sha(out / "initial.json")
        base = Path(old["base"])
        for name, pin in old["data_pins"].items():
            if A.sha(base / "data" / name) != pin:
                raise ValueError("data changed")
        rows = tuple(
            np.load(base / "data" / f"{n}.npy", mmap_mode="r")
            for n in ("history", "clock", "wake", "targets", "origin")
        )
        examples = [T.example(rows, i, 8) for i in old["indices"]]
        for name, op in [
            ("newborn-query", lambda: brain.settle(old["query"])),
            (
                "discarded-admission",
                lambda: brain.observe_batch(examples, budget=8192, source="witness"),
            ),
        ]:
            before = brain.snapshot()
            intent = {
                "name": name,
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "indices": old["indices"] if name == "discarded-admission" else None,
            }
            A.write(out / f"{name}-intent.json", intent)
            begin = time.monotonic()
            try:
                if profile and name == "discarded-admission":
                    profile.enable()
                result = op()
            except Exception:
                if profile:
                    profile.disable()
                call = dict(
                    **intent,
                    status="interrupted_or_error",
                    seconds=time.monotonic() - begin,
                    unknown_solver_work=True,
                    traceback=traceback.format_exc(),
                )
                report["calls"].append(call)
                A.write(out / f"{name}-result.json", call)
                raise
            finally:
                if profile:
                    profile.disable()
            call = dict(
                **intent,
                status="returned",
                seconds=time.monotonic() - begin,
                result=compact(result),
                after_sha256=hashlib.sha256(brain.snapshot().encode()).hexdigest(),
            )
            report["calls"].append(call)
            A.write(out / f"{name}-result.json", call)
            if name == "discarded-admission":
                (out / "discarded-final.json").write_text(brain.snapshot())
        report["status"] = "complete"
    except Exception:  # noqa: BLE001 - preserve every discarded outcome.
        report.update(status="error_or_time_limit", traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        faulthandler.cancel_dump_traceback_later()
        stacks.close()
        if profile:
            profile.disable()
            profile.dump_stats(str(out / "profile.pstats"))
            A.write(out / "profile-summary.json", summarize(profile))
        returned = [r for r in report["calls"] if r["status"] == "returned"]
        report["accepted_admissions"] = sum(
            r["name"] == "discarded-admission" and r["result"]["accepted"]
            for r in returned
        )
        report["qualified_calls"] = sum(r["result"]["qualified"] for r in returned)
        report["timing_usable"] = (
            report["status"] == "complete"
            and report["accepted_admissions"] == 1
            and report["qualified_calls"] == 2
        )
        report["seconds"] = time.monotonic() - started
        report["sources_unchanged"] = all(
            A.sha(k) == v for k, v in A.read(root / "protocol.json")["sources"].items()
        )
        A.write(out / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "case",
                    "status",
                    "seconds",
                    "accepted_admissions",
                    "timing_usable",
                )
            }
        ),
        flush=True,
    )


def launch(root):
    def worker(case):
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "arm",
                    str(root),
                    "--case",
                    case,
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
                "case": case,
                "exit_code": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "case": case,
                "status": "outer_timeout",
                "stdout": str(e.stdout),
                "stderr": str(e.stderr),
            }
        except Exception:  # noqa: BLE001 - preserve launch failures.
            return {
                "case": case,
                "status": "launch_error",
                "traceback": traceback.format_exc(),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, ("plain", "profiled")))
    A.write(root / "execution.json", outcomes)
    print(json.dumps(outcomes), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("freeze", "launch", "arm"))
    p.add_argument("root", type=Path)
    p.add_argument("--base", type=Path)
    p.add_argument("--case", choices=("plain", "profiled"))
    a = p.parse_args()
    if a.mode == "freeze":
        freeze(a.root.resolve(), a.base.resolve())
    elif a.mode == "launch":
        launch(a.root.resolve())
    else:
        arm(a.root.resolve(), a.case)
