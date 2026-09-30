"""Amen Studio: the jungle composer's brain behind a local settle endpoint.

The browser page owns the studio: the count-in, the playing rule, the declared
per-dub variety and the instrument rendering all run in JavaScript, and the page
sends back the window of events it actually executed. This server owns the brain:
each request is one pure ``settle`` query of the trained Cadence brain over that
heard window, the clock and the wake flag. Queries admit nothing; the brain on
disk never changes. One lock serializes brain calls.

    python server.py    ->  http://localhost:8670
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import numpy as np
from aiohttp import web

import cadence
from cadence import Brain

import amen_stream as S

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("AMEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("AMEN_PORT", "8670"))
THREADS = int(os.environ.get("AMEN_THREADS", "4"))
BUDGET = int(os.environ.get("AMEN_BUDGET", "2048"))


class Model:
    def __init__(self, name, meta):
        self.name = name
        self.meta = meta
        self.lock = threading.Lock()
        path = HERE / "models" / name / "brain.json"
        self.brain = Brain.from_snapshot(path.read_text(), device=meta.get("device", "cpu"))
        info = self.brain.inspect()
        self.steps = int(meta["steps"])
        self.populations = [
            {"name": p["name"], "role": p["role"], "patches": len(p["indices"]),
             "start": p["indices"][0]}
            for p in info["populations"]
        ]
        self.patches = info["patches"]
        self.connections = info["connections"]

    def settle(self, window, t):
        inputs = S.senses([np.asarray(e, dtype=float) for e in window], int(t), self.steps)
        with self.lock:
            t0 = time.perf_counter()
            result = self.brain.settle(inputs, budget=BUDGET)
            seconds = time.perf_counter() - t0
        state = result["state"]
        errors = result["errors"]
        return {
            "qualified": result["qualified"],
            "reason": result["reason"],
            "out": S.decode(result["outputs"]["event"]).tolist(),
            "state": [round(v, 4) for v in state],
            "errors": [round(v, 4) for v in errors],
            "sweeps": result["sweeps"],
            "energy": round(result["energy"], 6),
            "stationarity": float(result["stationarity"]),
            "seconds": round(seconds, 3),
        }


def load_models():
    index = json.loads((HERE / "models" / "index.json").read_text())
    models = {}
    for entry in index["brains"]:
        models[entry["name"]] = Model(entry["name"], entry)
        print(f"loaded {entry['name']}: {models[entry['name']].patches} patches, "
              f"{models[entry['name']].connections} connections")
    return index, models


async def meta(request):
    index, models = request.app["index"], request.app["models"]
    return web.json_response({
        "cadence": cadence.__version__,
        "default": index["default"],
        "brains": [
            dict(m.meta, populations=models[m.meta["name"]].populations,
                 patches=models[m.meta["name"]].patches,
                 connections=models[m.meta["name"]].connections,
                 event_ports=S.EVENT_PORTS, clock=S.CLOCK,
                 count_in=S.COUNT_IN.tolist(), retriggers=S.RETRIGGERS.tolist(),
                 layout=dict(
                     crops=S.CROPS, notes=S.NOTES, drum_on=S.DRUM_ON, drum_gain=S.DRUM_GAIN,
                     note_start=S.NOTE_START, bass_on=S.BASS_ON, bass_hold=S.BASS_HOLD,
                     change=S.CHANGE, texture_start=S.CHANGE + 1, texture_ports=S.TEXTURE_PORTS,
                     event_ports=S.EVENT_PORTS,
                 ))
            for m in models.values()
        ],
    })


async def settle(request):
    models = request.app["models"]
    body = await request.json()
    model = models.get(body.get("brain"))
    if model is None:
        return web.json_response({"error": "unknown brain"}, status=404)
    window = body.get("window") or []
    if not window or len(window[0]) != S.EVENT_PORTS:
        return web.json_response({"error": "window must hold event rows"}, status=400)
    answer = await request.app["loop"].run_in_executor(
        None, model.settle, window, body.get("t", 0)
    )
    return web.json_response(answer)


async def index_page(request):
    return web.FileResponse(HERE / "static" / "index.html")


def main():
    try:
        import torch

        torch.set_num_threads(THREADS)
    except ImportError:
        pass
    app = web.Application()
    app["index"], app["models"] = load_models()
    app.add_routes([
        web.get("/", index_page),
        web.get("/meta", meta),
        web.post("/settle", settle),
        web.static("/", HERE / "static"),
    ])

    async def on_startup(app):
        import asyncio

        app["loop"] = asyncio.get_running_loop()

    app.on_startup.append(on_startup)
    print(f"Amen Studio on http://{HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
