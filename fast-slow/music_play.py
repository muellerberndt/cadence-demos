"""Free music continuations with actual executed history and native instruments."""

import argparse
import json
from pathlib import Path
import sys
import time
import wave

import numpy as np
from cadence import Brain

from actor import FastSlowActor
from data import load, sha
from train import write


def wav(path, audio, rate=22050):
    if not np.isfinite(audio).all() or np.max(np.abs(audio)) > 1:
        raise ValueError("invalid PCM; no normalization fallback")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1 if audio.ndim == 1 else audio.shape[1])
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((audio * 32767).astype("<i2").tobytes())


def amen_context(workspace, metadata):
    sys.path.insert(0, str(workspace / "cadence-amen"))
    from drsn_amen import stream as s
    from drsn_amen import compose as c

    if sha(s.__file__) != metadata["source_sha256"]["stream.py"]:
        raise ValueError("Amen source changed")
    history = [s.COUNT_IN.copy()]

    def features(tick):
        return np.r_[
            history[-1],
            np.eye(8)[tick % 8],
            float(tick == 0),
            np.mean(history[-8:], axis=0),
            np.mean(history[-32:], axis=0),
        ]

    def execute(output):
        event = s.executed(s.decode(output))
        history.append(event)
        return event

    def render(events):
        events = np.asarray(events)
        return c.render(events, c.load_instrument()), {
            "drum_density": float(events[:, s.DRUM_ON].mean()),
            "bass_density": float(events[:, s.BASS_ON].mean()),
            "distinct_drum_crops": len(
                set(
                    np.argmax(
                        events[events[:, s.DRUM_ON] > 0.5, s.DRUM_ID], axis=1
                    ).tolist()
                )
            ),
            "distinct_bass_notes": len(
                set(
                    np.argmax(
                        events[events[:, s.BASS_ON] > 0.5, s.NOTE_ID], axis=1
                    ).tolist()
                )
            ),
        }

    return (
        features,
        execute,
        render,
        {"start": "count-in only", "decoder": "fixed argmax; no procedural variety"},
    )


def c64_context(workspace, metadata, frames):
    sys.path.insert(0, str(workspace / "cadence-c64-maestro"))
    from population_composer import features as f, model
    from experience_v1.codec import GestureCodec
    from experience_v1.instrument import ChipConfig, OfflineInstrument

    if sha(f.__file__) != metadata["feature_sha256"]:
        raise ValueError("C64 feature source changed")
    selected = next(s for s in metadata["sequences"] if s["split"])
    path = (
        workspace / "cadence-c64-maestro/data/performances" / f"{selected['name']}.npz"
    )
    if sha(path) != metadata["source_sha256"][path.name]:
        raise ValueError("C64 source performance changed")
    with np.load(path, allow_pickle=False) as z:
        goals = z["goals"].copy()
        history = [g.copy() for g in z["gestures"][: selected["start"]]]
    prefix = len(history)
    if prefix + frames > len(goals):
        raise ValueError("continuation exceeds declared clock")
    warmup = history[-f.PHRASE :]

    def features(tick):
        inputs = f.build_inputs(
            f.voice_tracks(np.stack(history)), goals, prefix + tick, len(goals)
        )
        return np.concatenate([inputs[k] for k in f.INPUT_SHAPES])

    def execute(output):
        event = model.decode_event(output)
        history.append(event)
        return event

    def render(events):
        instrument = OfflineInstrument(ChipConfig(frames_per_second=f.FPS))
        try:
            for event in warmup:
                instrument.step(GestureCodec.registers(event))
            audio = np.concatenate(
                [instrument.step(GestureCodec.registers(event)) for event in events]
            )
        finally:
            instrument.close()
        events = np.asarray(events)
        pitches = events[:, list(f.VOICE_NOTE)]
        sounding = (pitches > 0) & (events[:, list(f.VOICE_GATE)] > 0)
        return audio, {
            "sounding_density": float(sounding.mean()),
            "distinct_pitches_per_voice": [
                len(set(pitches[sounding[:, i], i].tolist())) for i in range(3)
            ],
        }

    return (
        features,
        execute,
        render,
        {
            "performance": path.name,
            "prefix_frames": prefix,
            "clock": "source metronome only",
            "decoder": "fixed rounded pitch/gate; no jitter",
        },
    )


def run(args):
    _, metadata, mean, scale = load(args.data)
    report = json.loads((args.run / "report.json").read_text())
    protocol = json.loads((args.run / "protocol.json").read_text())
    if report["status"] != "complete" or sha(args.data) != protocol["data_sha256"]:
        raise ValueError("complete, source-bound run required")
    for name, digest in report["artifacts"].items():
        if sha(args.run / name) != digest:
            raise ValueError(f"modified artifact {name}")
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema": "cadence.fast-slow-music/1",
        "domain": metadata["domain"],
        "training_report_sha256": sha(args.run / "report.json"),
        "data_sha256": sha(args.data),
        "sources": {p.name: sha(p) for p in Path(__file__).parent.glob("*.py")},
        "frames": args.frames,
        "status": "running",
        "arms": [],
        "nonclaims": [
            "These are development continuations, not unseen-track tests",
            "Instrument rendering and diversity do not establish musical quality",
            "No listening assessment recorded",
        ],
    }
    write(args.out / "report.json", receipt)
    for arm in ("fast_only", "conditioned", "conditioned_disabled"):
        features, execute, render, start = (
            amen_context(args.workspace, metadata)
            if metadata["domain"] == "amen"
            else c64_context(args.workspace, metadata, args.frames)
        )
        checkpoint = "conditioned" if arm.startswith("conditioned") else arm
        actor = FastSlowActor(
            Brain.from_snapshot(
                (args.run / f"{checkpoint}.json").read_text(), device="python"
            ),
            Brain.from_snapshot((args.run / "slow.json").read_text(), device="python"),
            71 if metadata["domain"] == "amen" else 6,
            period=protocol["period"],
            max_age=4.0,
            enabled=arm == "conditioned",
        )
        events, times = [], []
        try:
            for tick in range(args.frames):
                started = time.monotonic()
                x = np.clip((features(tick) - mean) / scale, -3, 3) * 0.2
                row = actor.step(x)
                if not row["qualified"]:
                    break
                events.append(execute(row["output"]))
                times.append(time.monotonic() - started)
                time.sleep(max(0, 0.125 - times[-1]))
        finally:
            trace = actor.close()
        audio, metrics = render(events) if events else (np.zeros(1), {})
        wav(args.out / f"{arm}.wav", audio)
        write(
            args.out / f"{arm}.json",
            {"events": np.asarray(events).tolist(), "settlements": trace},
        )
        result = {
            "arm": arm,
            "start": start,
            "generated": len(events),
            "qualified": sum(r["qualified"] for r in actor.rows),
            "feedback_events": sum(r["feedback_source_tick"] >= 0 for r in actor.rows),
            "event_median_ms": float(np.median(times)) * 1000,
            "event_p95_ms": float(np.quantile(times, 0.95)) * 1000,
            "runtime": trace["runtime"],
            "metrics": metrics,
            "wav_sha256": sha(args.out / f"{arm}.wav"),
            "trace_sha256": sha(args.out / f"{arm}.json"),
            "audio_seconds": len(audio) / 22050,
        }
        receipt["arms"].append(result)
        write(args.out / "report.json", receipt)
        print(json.dumps(result), flush=True)
    receipt["status"] = (
        "complete"
        if all(a["generated"] == args.frames for a in receipt["arms"])
        else "refused"
    )
    receipt["sources_unchanged"] = all(
        sha(Path(__file__).parent / k) == v for k, v in receipt["sources"].items()
    )
    write(args.out / "report.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=128)
    run(parser.parse_args())
