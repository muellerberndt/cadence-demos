"""Run the predeclared two-seed, four-dataset training screen on the AWS host."""

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root = Path.cwd()
    jobs = [
        (domain, seed)
        for domain in ("amen", "c64", "SpaceInvaders", "Freeway")
        for seed in (2, 7)
    ]
    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }

    def execute(job):
        domain, seed = job
        data = (
            f"cadence-fast-slow-{domain}{'-v2' if domain == 'amen' else ''}.npz"
            if domain in {"amen", "c64"}
            else f"atari-{domain}.npz"
        )
        name = f"wave1-{domain}-seed{seed}"
        command = [
            sys.executable,
            str(Path(__file__).with_name("train.py")),
            "--data",
            str(root / "data" / data),
            "--out",
            str(root / "runs" / name),
            "--seed",
            str(seed),
            "--seconds",
            "900",
        ]
        started = time.time()
        with (root / "logs" / f"{name}.log").open("x") as log:
            try:
                result = subprocess.run(
                    command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800
                )
                status = result.returncode
            except subprocess.TimeoutExpired:
                status = "timeout"
        row = {
            "name": name,
            "command": command,
            "exit": status,
            "seconds": time.time() - started,
        }
        (root / "logs" / f"{name}.exit.json").write_text(
            json.dumps(row, indent=2) + "\n"
        )
        print(json.dumps(row), flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(execute, jobs))
    (root / "runs" / "wave1-batch.json").write_text(
        json.dumps(results, indent=2) + "\n"
    )
    return int(any(row["exit"] != 0 for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
