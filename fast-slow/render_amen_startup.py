"""Render every verified fixed output and descriptive stem energies; no selection.

Reads already verified events, never re-admits learning or changes playback gains.
Musical quality requires listening and is not inferred from presence/energy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import amen_startup_curriculum as A
import numpy as np
import soundfile as sf


def rms(signal):
    return float(np.sqrt(np.mean(np.square(np.asarray(signal, dtype=np.float64)))))


def diagnostics(events, full, stems, hop, S):
    bars = []
    for i in range(0, len(events), 8):
        e = events[i : i + 8]
        a = slice(i * hop, (i + 8) * hop)
        bars.append(
            dict(
                bar=i // 8 + 1,
                drum_fraction=float((e[:, S.DRUM_ON] > 0.5).mean()),
                bass_fraction=float((e[:, S.BASS_ON] > 0.5).mean()),
                actual_mean_drum_gain=float(e[:, S.DRUM_GAIN].mean()),
                full_rms=rms(full[a]),
                **{f"{k}_rms": rms(v[a]) for k, v in stems.items()},
            )
        )
    last = {}
    for name, index in (("drum", S.DRUM_ON), ("bass", S.BASS_ON)):
        indices = np.flatnonzero(events[:, index] > 0.5)
        last[name] = int(indices[-1]) if len(indices) else None
    return {
        "per_bar": bars,
        "last_active_half_beat": last,
        "full_rms": rms(full),
        "peak": float(np.max(np.abs(full))),
        "exact_zero_drum_bars": sum(b["drum_rms"] == 0 for b in bars),
        "exact_zero_bass_bars": sum(b["bass_rms"] == 0 for b in bars),
    }


def render(root, verification, texture_source, out):
    p = A.bound(root)
    verified = A.read(verification)
    if not verified["verified"] or verified["protocol_sha256"] != A.sha(
        root / "protocol.json"
    ):
        raise ValueError("verified protocol mismatch")
    out.mkdir(exist_ok=False)
    C, _M, S, _T = A.app_modules(Path(p["app"]))
    sys.path.insert(0, str(texture_source.parent))
    import texture_synth

    if Path(texture_synth.__file__).resolve() != texture_source.resolve():
        raise ValueError("wrong texture renderer import")
    pins = {
        str(Path(__file__).resolve()): A.sha(__file__),
        str(texture_source): A.sha(texture_source),
        str(Path(C.__file__)): A.sha(C.__file__),
    }
    for folder in ("phrase-source-v1", "bass-notes-v1"):
        for name in ("fixture.json", "arrays.npz"):
            path = Path(p["app"]) / "fixtures" / folder / name
            pins[str(path)] = A.sha(path)
    instrument = C.load_instrument()
    hop = instrument[0].shape[1]
    results = []
    for case in verified["results"]:
        d = root / f"{case['arm']}-seed{case['seed']}"
        report = A.read(d / "report.json")
        for mode in ("argmax-0", "sample-1", "sample-2", "sample-3", "sample-4"):
            g = report.get("generation", {}).get(mode, {})
            if not g.get("complete"):
                results.append(
                    {
                        "seed": case["seed"],
                        "arm": case["arm"],
                        "mode": mode,
                        "status": "unavailable",
                    }
                )
                continue
            events = np.asarray(g["events"])
            full = C.render(events, instrument)
            stems = {}
            for name in ("drum", "bass", "texture"):
                e = events.copy()
                if name != "drum":
                    e[:, S.DRUM_ON] = 0
                if name != "bass":
                    e[:, S.BASS_ON] = 0
                if name != "texture":
                    e[:, S.TEXTURE] = 0
                stems[name] = C.render(e, instrument)
            error = float(
                np.max(
                    np.abs(
                        full.astype(np.float64)
                        - sum(v.astype(np.float64) for v in stems.values())
                    )
                )
            )
            if error > 2e-7:
                raise ValueError("rendered stem sum differs")
            name = f"{case['arm']}-seed{case['seed']}-{mode}.wav"
            path = out / name
            sf.write(path, full, 22050, subtype="PCM_16")
            pcm, rate = sf.read(path, dtype="float64", always_2d=True)
            if (
                rate != 22050
                or pcm.shape != full.shape
                or np.max(np.abs(pcm - full)) > 1 / 32768 + 1e-12
            ):
                raise ValueError("PCM roundtrip")
            results.append(
                dict(
                    seed=case["seed"],
                    arm=case["arm"],
                    mode=mode,
                    status="rendered",
                    file=name,
                    sha256=A.sha(path),
                    bytes=path.stat().st_size,
                    frames=len(full),
                    sample_rate=22050,
                    seconds=len(full) / 22050,
                    report_sha256=A.sha(d / "report.json"),
                    snapshot_sha256=A.sha(d / "final.json"),
                    events_sha256=A.digest(g["events"]),
                    stem_sum_max_error=error,
                    **diagnostics(events, full, stems, hop, S),
                )
            )
    if any(A.sha(path) != pin for path, pin in pins.items()):
        raise ValueError("render source/instrument changed")
    A.bound(root)
    receipt = {
        "schema": "amen-startup-audio/1",
        "verification_sha256": A.sha(verification),
        "protocol_sha256": A.sha(root / "protocol.json"),
        "source_and_instrument_pins": pins,
        "render": {
            "sample_rate": 22050,
            "subtype": "PCM_16",
            "drum_gain": 0.6,
            "bass_gain": 0.38,
            "texture_seed": 7,
            "normalization": False,
        },
        "results": results,
        "scope": "All six final brains, argmax and fixed sample seeds1..4, rendered from source-bound verified executed events. Per-bar stem RMS/gain/extinction are post-run diagnostics requested after the original pilot sounded poor; no new gate, output repair, best-seed selection or musical-quality claim. Original pilot was reported by owner to fade to noise and fail the musical task.",
    }
    A.write(out / "receipt.json", receipt)
    print(A.sha(out / "receipt.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--texture-source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    render(
        a.root.resolve(),
        a.verification.resolve(),
        a.texture_source.resolve(),
        a.out.resolve(),
    )
