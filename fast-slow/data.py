"""Small chronological, source-bound windows from the actual demo corpora."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, sequences, metadata):
    """Normalize from training rows only; preserve sequence boundaries and order."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    train = np.concatenate([s["x"] for s in sequences if s["split"] == 0])
    mean, scale = train.mean(0), np.maximum(train.std(0), 0.05)
    arrays = {"mean": mean, "scale": scale}
    manifest = []
    for i, sequence in enumerate(sequences):
        x, y = np.asarray(sequence["x"]), np.asarray(sequence["y"])
        if len(x) != len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Invalid sequence")
        arrays[f"x{i}"] = np.clip((x - mean) / scale, -3, 3) * 0.2
        arrays[f"y{i}"] = y
        manifest.append({k: v for k, v in sequence.items() if k not in {"x", "y"}})
    metadata = {
        **metadata,
        "sequences": manifest,
        "normalization": "train-only mean/std floor .05; clip +/-3 then multiply .2",
    }
    arrays["meta"] = np.array(json.dumps(metadata, sort_keys=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        np.savez_compressed(handle, **arrays)
    return {
        "path": str(path),
        "sha256": sha(path),
        "bytes": path.stat().st_size,
        "meta": metadata,
    }


def load(path):
    with np.load(path, allow_pickle=False) as z:
        metadata = json.loads(str(z["meta"]))
        sequences = [
            {**m, "x": z[f"x{i}"].copy(), "y": z[f"y{i}"].copy()}
            for i, m in enumerate(metadata["sequences"])
        ]
        return sequences, metadata, z["mean"].copy(), z["scale"].copy()


def amen(workspace, out, *, seed=101, frames=128, train_sequences=24):
    workspace = Path(workspace)
    sys.path.insert(0, str(workspace / "cadence-amen"))
    from drsn_amen import stream as s

    fixture, regions, _ = s.load_fixture()
    rng = np.random.default_rng(seed)
    training = [r for r in sorted(regions) if r not in s.HELD_OUT]
    selected = list(rng.permutation(training)[:train_sequences]) + list(s.HELD_OUT)
    sequences = []
    for index, name in enumerate(selected):
        events = regions[name]
        heard = s.heard_sequence(events)
        start = int(rng.integers(32, max(33, len(events) - frames)))
        if name not in s.HELD_OUT and index % 2 == 0:
            start = 0  # Include waking from the declared count-in during training.
        stop = min(start + frames, len(events))
        rows = []
        for t in range(start, stop):
            clock = np.eye(8)[t % 8]
            rows.append(
                np.r_[
                    heard[t],
                    clock,
                    float(t == 0),
                    heard[max(0, t - 7) : t + 1].mean(0),
                    heard[max(0, t - 31) : t + 1].mean(0),
                ]
            )
        sequences.append(
            dict(
                name=str(name),
                split=int(name in s.HELD_OUT),
                start=start,
                x=np.asarray(rows),
                y=s.encode(events[start:stop]),
            )
        )
    return save(
        out,
        sequences,
        {
            "domain": "amen",
            "seed": seed,
            "fixture": fixture["receipt_sha256"],
            "source_sha256": {"stream.py": sha(s.__file__)},
            "features": "previous executed event, 8-phase clock, wake, trailing 8/32 heard-event means; no future input",
            "target": "71 encoded next-event ports; original soft transcription",
            "reserved_test": "none newly claimed; eight existing held-out tracks are development here",
        },
    )


def c64(
    workspace, out, *, seed=101, frames=128, train_sequences=24, validation_sequences=8
):
    workspace = Path(workspace)
    sys.path.insert(0, str(workspace / "cadence-c64-maestro"))
    from population_composer import features as f

    rng = np.random.default_rng(seed)
    paths = sorted((workspace / "cadence-c64-maestro/data/performances").glob("*.npz"))
    sequences, families, sources = [], set(), {}
    counts = {"train": 0, "validation": 0}
    limits = {"train": train_sequences, "validation": validation_sequences}
    for index in rng.permutation(len(paths)):
        path = paths[index]
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["meta"]))
            split, family = meta["split"], meta["family"]
            if (
                split not in limits
                or counts[split] >= limits[split]
                or family in families
            ):
                continue
            gestures, goals = z["gestures"], z["goals"]
            if len(gestures) < frames + f.PHRASE:
                continue
            tracks = f.voice_tracks(gestures)
            start = int(rng.integers(f.PHRASE, len(gestures) - frames + 1))
            x, y = [], []
            for t in range(start, start + frames):
                inputs = f.build_inputs(tracks, goals, t, len(gestures))
                x.append(np.concatenate([inputs[k] for k in f.INPUT_SHAPES]))
                y.append(f.interleave(tracks["pitch"][t], tracks["flags"][t]))
            sequences.append(
                dict(
                    name=path.stem,
                    family=family,
                    split=int(split == "validation"),
                    start=start,
                    x=np.asarray(x),
                    y=np.asarray(y),
                )
            )
            sources[path.name] = sha(path)
            counts[split] += 1
            families.add(family)
        if counts == limits:
            break
    if counts != limits:
        raise ValueError(f"Insufficient independent performances: {counts}")
    return save(
        out,
        sequences,
        {
            "domain": "c64",
            "seed": seed,
            "source_sha256": sources,
            "feature_sha256": sha(f.__file__),
            "features": list(f.INPUT_SHAPES),
            "target": "next frame: carried pitch and sounding flag for each of 3 SID voices",
            "reserved_test": "original test families unopened",
        },
    )


def atari_features(rgb, previous, action, actions):
    """Declared area-pooled 21x20 pixels, frame difference and executed action."""
    grey = (np.asarray(rgb, dtype=float) @ [0.299, 0.587, 0.114]) / 255.0
    pooled = grey.reshape(21, 10, 20, 8).mean(axis=(1, 3)).reshape(-1)
    difference = np.zeros_like(pooled) if previous is None else pooled - previous
    return np.r_[pooled, difference, np.eye(actions)[action]], pooled


def teacher(game, ram, meanings, tick):
    if game == "Freeway":
        return meanings.index("UP")
    if game == "SpaceInvaders":
        return meanings.index("RIGHTFIRE" if int(ram[28]) < 75 else "LEFTFIRE")
    raise ValueError(game)


def atari(
    out, *, game="SpaceInvaders", frames=256, train_sequences=8, validation_sequences=4
):
    import ale_py
    import gymnasium as gym

    gym.register_envs(ale_py)
    env = gym.make(
        f"ALE/{game}-v5",
        frameskip=4,
        repeat_action_probability=0.0,
        full_action_space=False,
    )
    meanings = env.unwrapped.get_action_meanings()
    sequences = []
    try:
        for index in range(train_sequences + validation_sequences):
            seed = 310100 + index if index < train_sequences else 410100 + index
            obs, _ = env.reset(seed=seed)
            previous, action, x, y, score = None, 0, [], [], 0.0
            # Seeded NOOP starts diversify teacher trajectories without changing labels.
            for _ in range(1 + seed % 29):
                obs, _, terminated, truncated, _ = env.step(0)
                if terminated or truncated:
                    raise RuntimeError("Episode ended during declared start")
            for tick in range(frames):
                features, previous = atari_features(
                    obs, previous, action, len(meanings)
                )
                action = teacher(game, env.unwrapped.ale.getRAM(), meanings, tick)
                x.append(features)
                y.append(np.where(np.arange(len(meanings)) == action, 0.6, -0.6))
                obs, reward, terminated, truncated, _ = env.step(action)
                score += float(reward)
                if terminated or truncated:
                    break
            sequences.append(
                dict(
                    name=f"{game}-{seed}",
                    seed=seed,
                    split=int(index >= train_sequences),
                    teacher_return=score,
                    censored=not (terminated or truncated),
                    start=0,
                    x=np.asarray(x),
                    y=np.asarray(y),
                )
            )
    finally:
        env.close()
    return save(
        out,
        sequences,
        {
            "domain": "atari",
            "game": game,
            "meanings": meanings,
            "ale_version": ale_py.__version__,
            "gym_version": gym.__version__,
            "features": "21x20 area-pooled current pixels, previous-frame difference, last executed action; no RAM",
            "teacher": "existing Arcade Freeway/SpaceInvaders RAM teacher; labels only",
            "reserved_play_seeds": [510102, 510107],
        },
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("domain", choices=("amen", "c64", "atari"))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--game", default="SpaceInvaders")
    args = parser.parse_args()
    result = (
        atari(args.out, game=args.game)
        if args.domain == "atari"
        else globals()[args.domain](args.workspace, args.out)
    )
    print(json.dumps({k: v for k, v in result.items() if k != "meta"}, indent=2))
