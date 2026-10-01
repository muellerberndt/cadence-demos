"""Run the five predeclared self-correction cases on an isolated AWS directory."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def run(root):
    output = root / "runs"
    output.mkdir(exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(root / "code/src"))
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        env[key] = "1"
    jobs = [
        [
            sys.executable,
            str(root / "self_correction.py"),
            "--seed",
            str(seed),
            "--out",
            str(output / f"seed{seed}"),
        ]
        for seed in (2, 7, 11, 19, 29)
    ]
    available = sorted(os.sched_getaffinity(0))
    protocol = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commands": jobs,
        "cpus": available[:5],
        "outer_timeout_seconds": 400,
        "workers": 5,
        "scope": "prediction and correction, not autonomous action selection",
    }
    (output / "launch.json").write_text(json.dumps(protocol, indent=2) + "\n")

    def execute(index, command):
        start = time.monotonic()
        with (output / f"case{index}.log").open("w") as log:
            process = subprocess.Popen(
                ["taskset", "-c", str(available[index]), *command],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=400)
                status = "exited"
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
                status = "outer_timeout"
        return {
            "case": index,
            "command": command,
            "status": status,
            "returncode": code,
            "seconds": time.monotonic() - start,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda item: execute(*item), enumerate(jobs)))
    (output / "execution.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root.resolve())
