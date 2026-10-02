"""Bounded-memory, offline raw drum/bass diagnostics of saved Amen events.

This reproduces drsn_amen.compose.render's two recorded-sample stems at its
fixed gains, including finite bass voices and the 220-sample endpoint fade.
It does not reproduce browser pad synthesis, normalization, or musical quality.
Looking ahead to an acknowledged hold's end matches that offline renderer; this
is not a causal streaming audio-device implementation. No Brain is imported.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np

PORTS, CROPS, NOTES = 71, 32, 24
DRUM_ON, DRUM_GAIN, BASS_ON, BASS_HOLD = 32, 33, 58, 59
NOTE_ID = slice(34, 58)
ARMS = ("intact", "no_record", "context_reset", "both")
CHOICES = (("argmax", 0), *(("sample", i) for i in (1, 2, 3, 4)))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def load_played(path, half_beats):
    """Read one complete saved case, never a whole campaign's decoded journal."""
    events = np.empty((half_beats, PORTS), dtype=np.float64)
    count = 0
    with gzip.open(path, "rt") as stream:
        for line in stream:
            require(count < half_beats, "extra event row")
            row = json.loads(line)
            require(type(row["t"]) is int and row["t"] == count, "event order")
            actual = np.asarray(row["played"], dtype=float)
            require(actual.shape == (PORTS,), "actual event shape")
            require(np.isfinite(actual).all(), "nonfinite actual event")
            events[count] = actual
            count += 1
    require(count == half_beats, "incomplete event trajectory")
    return events


def load_instrument(app):
    """Load the existing fixture arrays; check their recorded payload digests."""
    app = Path(app)
    phrase = app / "fixtures/phrase-source-v1"
    notes = app / "fixtures/bass-notes-v1"
    p, b = read(phrase / "fixture.json"), read(notes / "fixture.json")
    require(sha(phrase / "arrays.npz") == p["hashes"]["arrays.npz"], "crop hash")
    require(sha(notes / "arrays.npz") == b["arrays_sha256"], "bass hash")
    with np.load(phrase / "arrays.npz", allow_pickle=False) as z:
        crops = z["samples"].astype(np.float64)
    with np.load(notes / "arrays.npz", allow_pickle=False) as z:
        bass = [z[n["id"]].astype(np.float64) for n in b["notes"]]
    midi = np.array([n["root_midi"] for n in b["notes"]], dtype=float)
    return crops, bass, midi


def voices_for(bass, sampled_midi):
    midi = np.asarray(sampled_midi, dtype=float)
    require(midi.ndim == 1 and len(midi) == len(bass) > 0, "bass bank shape")
    require(np.isfinite(midi).all(), "nonfinite sampled pitches")
    result = []
    for note in range(NOTES):
        target = 24 + note
        index = int(np.argmin(np.abs(midi - target)))
        source = np.asarray(bass[index], dtype=np.float64)
        require(source.ndim == 1 and len(source) >= 2, "bass voice shape")
        require(np.isfinite(source).all(), "nonfinite bass voice")
        ratio = 2.0 ** ((target - midi[index]) / 12.0)
        positions = np.arange(0, len(source) - 1, ratio)
        result.append(np.interp(positions, np.arange(len(source)), source))
    return result


def stem_frames(events, instrument):
    """Yield float32 drum/bass/combined frames, retaining at most one hop."""
    events = np.asarray(events, dtype=np.float64)
    require(events.ndim == 2 and events.shape[1] == PORTS, "event shape")
    require(np.isfinite(events).all(), "nonfinite events")
    crops, bass, sampled_midi = instrument
    crops = np.asarray(crops, dtype=np.float64)
    require(crops.ndim == 3 and crops.shape[0] == CROPS, "crop bank shape")
    require(crops.shape[1] > 0 and crops.shape[2] == 2, "stereo crop shape")
    require(np.isfinite(crops).all(), "nonfinite crops")
    hop = crops.shape[1]
    voices = voices_for(bass, sampled_midi)
    notes = np.argmax(events[:, NOTE_ID], axis=1)
    enabled = events[:, BASS_ON] > 0.5
    start, length, voice = 0, 0, np.empty(0)
    for i, row in enumerate(events):
        drum = np.zeros((hop, 2), dtype=np.float64)
        if row[DRUM_ON] > 0.5:
            drum += (
                0.6
                * float(np.clip(row[DRUM_GAIN], 0.0, 1.0))
                * crops[int(np.argmax(row[:CROPS]))]
            )
        continues = (
            row[BASS_HOLD] > 0.5
            and i > 0
            and enabled[i - 1]
            and notes[i - 1] == notes[i]
        )
        onset = bool(enabled[i] and not continues)
        if onset:
            end = i + 1
            while (
                end < len(events)
                and enabled[end]
                and events[end, BASS_HOLD] > 0.5
                and notes[end] == notes[i]
            ):
                end += 1
            start, voice = i * hop, voices[notes[i]]
            length = min((end - i) * hop, len(voice))
        bass_frame = np.zeros((hop, 2), dtype=np.float64)
        offset = i * hop - start
        available = max(0, min(hop, length - offset)) if enabled[i] else 0
        if available:
            envelope = np.ones(available, dtype=np.float64)
            tail = min(220, length)
            fade_start = length - tail
            overlap = max(offset, fade_start)
            if overlap < offset + available:
                fade = np.linspace(1.0, 0.0, tail)
                envelope[overlap - offset :] = fade[
                    overlap - fade_start : offset + available - fade_start
                ]
            mono = voice[offset : offset + available] * envelope * 0.38
            bass_frame[:available] += mono[:, None]
        combined = drum + bass_frame
        require(np.max(np.abs(combined), initial=0.0) <= 1.0, "raw PCM range")
        yield {
            "drum": drum.astype(np.float32),
            "bass": bass_frame.astype(np.float32),
            "combined_without_texture": combined.astype(np.float32),
            "bass_onset": onset,
            "bass_voice_expired": bool(enabled[i] and available == 0),
        }


def summarize_events(events, instrument):
    events = np.asarray(events, dtype=np.float64)
    require(len(events) > 0 and len(events) % 8 == 0, "whole nonempty bars required")
    names = ("drum", "bass", "combined_without_texture")
    bars = []
    accum = {k: 0.0 for k in names}
    peaks = {k: 0.0 for k in names}
    sample_values = onsets = expired = bass_zero = 0
    for i, frame in enumerate(stem_frames(events, instrument)):
        sample_values += frame["drum"].size
        for name in names:
            values = frame[name].astype(np.float64)
            accum[name] += float(np.sum(values * values))
            peaks[name] = max(peaks[name], float(np.max(np.abs(values), initial=0)))
        onsets += frame["bass_onset"]
        expired += frame["bass_voice_expired"]
        bass_zero += bool(events[i, BASS_ON] > 0.5 and not np.any(frame["bass"]))
        if (i + 1) % 8 == 0:
            block = events[i - 7 : i + 1]
            effective_gain = np.where(
                block[:, DRUM_ON] > 0.5, np.clip(block[:, DRUM_GAIN], 0, 1), 0
            )
            bars.append(
                {
                    "bar": len(bars) + 1,
                    "rms": {k: (accum[k] / sample_values) ** 0.5 for k in names},
                    "peak": dict(peaks),
                    "drum_gain_mean_all_halfbeats": float(effective_gain.mean()),
                    "drum_flag_halfbeats": int(np.sum(block[:, DRUM_ON] > 0.5)),
                    "bass_flag_halfbeats": int(np.sum(block[:, BASS_ON] > 0.5)),
                    "bass_onsets": onsets,
                    "bass_flag_but_zero_pcm_halfbeats": bass_zero,
                    "bass_voice_expired_halfbeats": expired,
                }
            )
            accum, peaks = {k: 0.0 for k in names}, {k: 0.0 for k in names}
            sample_values = onsets = expired = bass_zero = 0
    groups = {}
    for name in names:
        first = float(np.mean([b["rms"][name] ** 2 for b in bars[:4]]) ** 0.5)
        last = float(np.mean([b["rms"][name] ** 2 for b in bars[-4:]]) ** 0.5)
        groups[name] = {
            "first4_rms": first,
            "last4_rms": last,
            "last_first_ratio": last / first if first > 0 else None,
            "zero_pcm_bars": sum(b["rms"][name] == 0 for b in bars),
        }
    return {"half_beats": len(events), "bars": bars, "stems": groups}


def expected_cases():
    return [
        {
            "id": f"{arm}-{mode}-{seed}",
            "arm": arm,
            "mode": mode,
            "seed": seed,
            "options": {
                "bars": 128,
                "mode": mode,
                "seed": seed,
                "energy": 1,
                "variation": 0.6 if mode == "sample" else 0,
                "riffBars": 2,
                "memory": False,
            },
        }
        for arm in ARMS
        for mode, seed in CHOICES
    ]


def campaign_binding(root):
    """Check the complete producer census and bind every input file's bytes."""
    root = Path(root).resolve()
    paths = [
        root / n
        for n in ("protocol.json", "freeze.json", "receipt.json", "progress.json")
    ]
    pins = {str(p): sha(p) for p in paths}
    protocol, freeze, receipt, progress = map(read, paths)
    require(protocol["schema"] == "amen-legacy-ablation/1", "protocol schema")
    require(receipt["schema"] == "amen-legacy-ablation-result/1", "receipt schema")
    require(protocol["cases"] == expected_cases(), "protocol case census")
    require(protocol["expected_steps"] == 20480, "protocol step census")
    require(
        sha(paths[0]) == freeze["protocol_sha256"] == receipt["protocol_sha256"],
        "protocol binding",
    )
    require(
        receipt["complete"] is True and receipt["source_unchanged"] is True,
        "incomplete producer",
    )
    require(
        receipt["training_calls"] == 0 and receipt["record_writes"] == 0,
        "fixed-model claim",
    )
    require(progress == receipt["cases"], "progress receipt mismatch")
    require(len(progress) == 20, "receipt case census")
    for expected, case in zip(expected_cases(), progress, strict=True):
        require(all(case[k] == v for k, v in expected.items()), "case identity")
        require(
            case["status"] == "complete" and case["returned_steps"] == 1024,
            "incomplete case",
        )
        require(case["fixed_before"] == case["fixed_after"], "model changed")
        require(case["work"]["steps"] == 1024, "native step census")
        path = root / "cases" / f"{case['id']}.jsonl.gz"
        require(path.stat().st_size == case["journal_bytes"], "journal bytes")
        require(sha(path) == case["journal_sha256"], "journal hash")
        pins[str(path)] = case["journal_sha256"]
    require(
        {p.name for p in (root / "cases").iterdir()}
        == {f"{c['id']}.jsonl.gz" for c in progress},
        "journal file census",
    )
    require(bool(protocol["sources"]), "empty source inventory")
    for name, value in protocol["sources"].items():
        relative = Path(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "unsafe source path",
        )
        path = root / "sources" / relative
        require(sha(path) == value, "producer source changed")
        pins[str(path)] = value
    require(
        all(sha(path) == digest for path, digest in pins.items()),
        "binding input changed",
    )
    return protocol, receipt, pins


def analyze(root, app):
    started = time.perf_counter()
    root, app = Path(root).resolve(), Path(app).resolve()
    _protocol, receipt, pins = campaign_binding(root)
    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).with_name("test_amen_legacy_audio.py").resolve(),
    ]
    source_paths += [app / "drsn_amen" / n for n in ("compose.py", "stream.py")]
    fixture_paths = [
        app / "fixtures" / bank / file
        for bank in ("phrase-source-v1", "bass-notes-v1")
        for file in ("fixture.json", "arrays.npz")
    ]
    pins.update({str(p): sha(p) for p in source_paths + fixture_paths})
    phrase = read(fixture_paths[0])
    require(
        phrase["events_per_bar"] == 8 and phrase["sample_rate"] == 22050,
        "fixture timing",
    )
    instrument = load_instrument(app)
    cases = []
    for case in receipt["cases"]:
        events = load_played(root / "cases" / f"{case['id']}.jsonl.gz", 1024)
        cases.append(
            {
                "id": case["id"],
                "arm": case["arm"],
                "mode": case["mode"],
                "seed": case["seed"],
                "actual_events_f64le_sha256": hashlib.sha256(
                    events.astype("<f8").tobytes()
                ).hexdigest(),
                **summarize_events(events, instrument),
            }
        )
    require(
        all(sha(path) == digest for path, digest in pins.items()),
        "input changed during analysis",
    )
    # One case's events and one audio hop are kept at a time. No full-track PCM is retained.
    return {
        "schema": "amen-legacy-raw-stems/1",
        "valid": True,
        "scope": "Independent saved-event audio arithmetic, not engine/model replay or musical-quality assessment. Raw Python recorded-sample drum/bass only; excludes texture, browser pad, browser tempo/key processing and normalization. Offline hold-end lookahead matches compose.render; not a streaming delivery implementation.",
        "protocol_sha256": receipt["protocol_sha256"],
        "input_sha256": pins,
        "cases_analyzed": len(cases),
        "half_beats_analyzed": sum(c["half_beats"] for c in cases),
        "native_calls": 0,
        "training_calls": 0,
        "audio_files_written": 0,
        "instrument": {
            "drum_gain": 0.6,
            "bass_gain": 0.38,
            "sample_rate": phrase["sample_rate"],
            "source_bpm": phrase["source_bpm"],
            "hop_frames": instrument[0].shape[1],
            "events_per_bar": 8,
            "key_semitones": 0,
            "end_fade_samples": 220,
        },
        "rms_definition": "sqrt(mean(stem float32 PCM squared in float64)); all samples and both stereo channels, including silence. First/last four bars use pooled RMS. Zero first RMS gives null ratio. Finite-voice expiry is distinct from the symbolic bass_on flag.",
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "seconds": time.perf_counter() - started,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), "output already exists")
    result = analyze(args.root, args.app)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "valid": result["valid"],
                "cases": result["cases_analyzed"],
                "half_beats": result["half_beats_analyzed"],
                "sha256": sha(args.out),
                "bytes": args.out.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
