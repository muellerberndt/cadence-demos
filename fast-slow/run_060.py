"""Bounded AWS orchestration for the source-frozen 0.60 development comparisons."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

ROOT = Path("/home/ec2-user/cadence-060-20261001")
PYTHON = "/home/ec2-user/venv-atari/bin/python"


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def run(kind):
    code = ROOT / "code"
    output = ROOT / kind
    output.mkdir(exist_ok=False)
    jobs = []
    if kind == "credit":
        for seed in (2, 7, 11, 19, 29):
            for preferred in (0, 1):
                for delay in (8, 32, 128):
                    name = f"seed{seed}-preferred{preferred}-delay{delay}"
                    jobs.append(
                        (
                            name,
                            [
                                PYTHON,
                                "examples/credit_diagnostic.py",
                                "--seed",
                                str(seed),
                                "--delay",
                                str(delay),
                                "--preferred",
                                str(preferred),
                                "--out",
                                str(output / name),
                            ],
                        )
                    )
        workers = 16
    elif kind == "exposure":
        for seed in (2, 7, 11, 19, 29):
            for preferred in (0, 1):
                name = f"seed{seed}-preferred{preferred}-delay128"
                jobs.append(
                    (
                        name,
                        [
                            PYTHON,
                            "examples/credit_exposure.py",
                            "--collection",
                            str(ROOT / "credit" / name / "collection.json"),
                            "--out",
                            str(output / name),
                        ],
                    )
                )
        workers = 10
    elif kind == "query":
        for fixture in sorted((ROOT / "fixtures").glob("*.json")):
            if fixture.name in {"manifest.json", "protocol.json"}:
                continue
            name = fixture.stem
            jobs.append(
                (
                    name,
                    [
                        PYTHON,
                        str(ROOT / "query_cache.py"),
                        "run",
                        "--fixture",
                        str(fixture),
                        "--baseline",
                        "/home/ec2-user/fast-slow-20261001/code/cadence/_repair.py",
                        "--out",
                        str(output / name),
                    ],
                )
            )
        if len(jobs) != 16:
            raise ValueError(
                f"Expected 16 source-bound model fixtures, got {len(jobs)}"
            )
        workers = 8
    else:
        jobs = [("full-suite", [PYTHON, "-m", "pytest", "-q", "-ra"])]
        workers = 1
    available = sorted(os.sched_getaffinity(0))
    protocol = {
        "kind": kind,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "jobs": [{"name": n, "command": c} for n, c in jobs],
        "workers": workers,
        "timeout_seconds_per_process": 900,
        "cpu_affinity": available,
        "python": PYTHON,
        "statuses": {n: "pending" for n, _ in jobs},
    }
    write(output / "schedule.json", protocol)
    env = dict(
        os.environ,
        PYTHONPATH=str(code / "src"),
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
    )

    def execute(index, name, command):
        started = time.monotonic()
        cpu = (
            available[-1]
            if kind == "tests"
            else available[index % min(32, len(available))]
        )
        with (output / f"{name}.log").open("w") as handle:
            try:
                result = subprocess.run(
                    ["taskset", "-c", str(cpu), *command],
                    cwd=code,
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                    check=False,
                )
                status, returncode = (
                    "complete" if result.returncode == 0 else "failed",
                    result.returncode,
                )
            except subprocess.TimeoutExpired:
                status, returncode = "timeout", None
        return {
            "name": name,
            "status": status,
            "returncode": returncode,
            "seconds": time.monotonic() - started,
            "cpu": cpu,
        }

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(execute, i, name, command)
            for i, (name, command) in enumerate(jobs)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            protocol["statuses"][result["name"]] = result["status"]
            write(output / "schedule.json", protocol)
            write(output / "execution.json", results)
            print(json.dumps(result), flush=True)
    if any(result["status"] != "complete" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind", choices=("setup", "credit", "query", "tests", "exposure")
    )
    args = parser.parse_args()
    if args.kind == "setup":
        ROOT.mkdir(exist_ok=False)
        (ROOT / "code").mkdir()
        with tarfile.open(
            "/home/ec2-user/cadence-060-wave2-source.tar.gz", "r:gz"
        ) as tar:
            tar.extractall(ROOT / "code", filter="data")
        print(ROOT)
    else:
        run(args.kind)
