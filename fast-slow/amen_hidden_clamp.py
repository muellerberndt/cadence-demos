"""Four-row, no-learning audit of hidden features under the teaching clamp."""

from __future__ import annotations

import argparse
import hashlib
import signal
import time
import traceback
from pathlib import Path

import amen_architecture_calibrate as A
import numpy as np

from cadence import Brain


def alarm(*_):
    raise TimeoutError("hidden-clamp diagnostic30second cap")


def rms(v):
    return float(np.sqrt(np.mean(np.asarray(v, dtype=float) ** 2)))


def run(root):
    import torch

    torch.set_num_threads(4)
    out = root / "hidden-clamp-diagnostic"
    out.mkdir(exist_ok=False)
    p = A.read(root / "timing/protocol.json")
    _, T = A.modules(Path(p["app"]))
    base = Path(p["base"])
    source = root / "timing/ordinary64/initial.json"
    brain = Brain.from_snapshot(source.read_text())
    A.require_ordinary(brain)
    before = brain.snapshot()
    data = tuple(
        np.load(base / "data" / f"{n}.npy", mmap_mode="r")
        for n in ("history", "clock", "wake", "targets", "origin")
    )
    protocol = {
        "source_snapshot": str(source),
        "snapshot_sha256": A.sha(source),
        "indices": p["indices"][:4],
        "scope": "Only paired hypothetical purequeries: freefuturehead versus actualrecordedtargetclamp. Nolearning; clampedresult isNOTforecast. Retainedbrainmustnotchange.",
        "sources": {**p["sources"], str(Path(__file__).resolve()): A.sha(__file__)},
        "seconds_cap": 30,
    }
    A.write(out / "protocol.json", protocol)
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 30)
    started = time.monotonic()
    report = {
        "status": "running",
        "rows": [],
        "attempted_queries": 0,
        "returned_queries": 0,
        "qualified_queries": 0,
    }
    try:
        for rowid in protocol["indices"]:
            values, targets = T.example(data, rowid, 8)
            pair = {}
            for label, t in [("free", None), ("teacher", targets)]:
                A.write(
                    out / f"row{rowid}-{label}-intent.json",
                    {"row": rowid, "phase": label, "targets": t},
                )
                report["attempted_queries"] += 1
                result = brain.settle(values, targets=t)
                report["returned_queries"] += 1
                report["qualified_queries"] += int(result["qualified"])
                item = {
                    k: v for k, v in result.items() if k not in ("weights", "biases")
                }
                A.write(out / f"row{rowid}-{label}.json", item)
                if not result["qualified"]:
                    raise ValueError("unqualified diagnostic")
                pair[label] = result
            v = {}
            for label, r in pair.items():
                v[label] = {
                    name: {
                        "state_rms": rms(r["state"][sl]),
                        "error_rms": rms(r["errors"][sl]),
                        "prediction_rms": rms(r["predictions"][sl]),
                    }
                    for name, sl in [
                        ("hearing", slice(0, 64)),
                        ("playing", slice(64, 135)),
                    ]
                }
            report["rows"].append(
                {
                    "row": rowid,
                    "populations": v,
                    "hearing_state_rms_shift": rms(
                        np.asarray(pair["teacher"]["state"][:64])
                        - pair["free"]["state"][:64]
                    ),
                    "hearing_max_shift": float(
                        np.max(
                            np.abs(
                                np.asarray(pair["teacher"]["state"][:64])
                                - pair["free"]["state"][:64]
                            )
                        )
                    ),
                    "qualified": True,
                }
            )
        report["status"] = "complete"
    except Exception:  # noqa: BLE001 - preserve no-learning diagnostic failures.
        report.update(status="failed", traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["seconds"] = time.monotonic() - started
        report["unknown_work_queries"] = (
            report["attempted_queries"] - report["returned_queries"]
        )
        report["snapshot_unchanged"] = brain.snapshot() == before
        report["admissions"] = brain.inspect()["admissions"]
        report["protocol_sha256"] = A.sha(out / "protocol.json")
        report["sources_unchanged"] = all(
            A.sha(k) == v for k, v in protocol["sources"].items()
        )
        report["retained_snapshot_sha256"] = hashlib.sha256(
            brain.snapshot().encode()
        ).hexdigest()
        A.write(out / "receipt.json", report)
    print(report, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    a = p.parse_args()
    run(a.root.resolve())
