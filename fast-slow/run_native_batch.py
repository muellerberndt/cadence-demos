"""Bound the four predeclared native-play comparisons on the AWS host."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


def execute(job):
    game, seed = job
    name = f"wave1-{game}-seed{seed}"
    command = [
        sys.executable,
        str(Path(__file__).with_name("native_play.py")),
        "--run",
        f"runs/{name}",
        "--data",
        f"data/atari-{game}.npz",
        "--out",
        f"runs/native-{name}",
    ]
    with Path(f"logs/native-{name}.log").open("x") as log:
        try:
            result = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=1200
            )
            status = result.returncode
        except subprocess.TimeoutExpired:
            status = "timeout"
    row = {"name": name, "command": command, "exit": status}
    Path(f"logs/native-{name}.exit.json").write_text(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)
    return row


if __name__ == "__main__":
    jobs = [(game, seed) for game in ("SpaceInvaders", "Freeway") for seed in (2, 7)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(execute, jobs))
    Path("runs/native-batch.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(int(any(row["exit"] != 0 for row in results)))
