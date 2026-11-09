"""Watch a Cadence brain play Castlevania on your own cartridge dump.

    python -m simon.rom ~/roms          # once: copy your Castlevania (U) PRG1 dump in
    python server.py                    # open http://localhost:8846/

The server runs the console and the brain in one thread at the game's speed (or faster) and
the page polls ``/api/state`` for the newest frame and the brain's last decision.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import threading
import time
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from simon.console import Console
from simon.player import BRAIN, Player, load_brain, populations

HERE = Path(__file__).resolve().parent


def png(frame: np.ndarray) -> bytes:
    """A minimal RGB PNG encoder (no imaging dependency)."""
    h, w, _ = frame.shape
    raw = b"".join(b"\x00" + frame[r].astype(np.uint8).tobytes() for r in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))


class Game(threading.Thread):
    """The console and the player; ``speed`` is a multiple of the NES's 60 frames a second
    (0 = as fast as the brain answers)."""

    def __init__(self, brain_path: Path, backend: str) -> None:
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.console = Console()
        self.player = Player(load_brain(brain_path, backend), populations(brain_path))
        self.brain_file = brain_path.name
        self.speed, self.paused, self.idle = 1.0, False, 0
        self.restart_requested = True
        self.frame, self.snap, self.stats = None, {}, {}
        self.version = 0

    def restart(self, idle: int) -> None:
        with self.lock:
            self.idle, self.restart_requested = int(idle), True

    def _new_game(self) -> None:
        with self.lock:  # take the request: a restart posted from here on starts another game
            idle, self.restart_requested = self.idle, False
        frame, ram = self.console.power_on(idle)
        self.player.new_game()
        r = self.console.readings()
        self.stats = {"idle": idle, "furthest_stage": r["stage"], "lives_lost": 0, "lives": r["lives"],
                      "started": time.time(), "over": False}
        with self.lock:
            self.frame = frame
        self.ram = ram

    def run_loop(self) -> None:
        while True:
            if self.restart_requested:
                self._new_game()
            if self.paused or self.stats.get("over"):
                time.sleep(0.05)
                continue
            frame = self.frame
            action = self.player.decide(frame, self.ram)
            snap = self.player.snapshot()
            t0 = time.perf_counter()
            done = False
            for k, (frame, done) in enumerate(self.console.frames(action)):
                with self.lock:
                    self.frame = frame
                    self.version += 1
                if self.speed > 0:
                    wait = (k + 1) / (60.0 * self.speed) - (time.perf_counter() - t0)
                    if wait > 0:
                        time.sleep(wait)
                if self.restart_requested:
                    break
            self.ram = self.console.ram()
            r = self.console.readings()
            if r["lives"] < self.stats["lives"]:
                self.stats["lives_lost"] += 1
            self.stats["lives"] = r["lives"]
            if r["stage"] != 20 and r["stage"] > self.stats["furthest_stage"]:
                self.stats["furthest_stage"] = r["stage"]
            if done or r["lives"] == 0:
                self.stats["over"] = True
            with self.lock:
                self.snap = snap

    def run(self) -> None:
        self.run_loop()

    def state(self) -> dict:
        with self.lock:
            frame, snap, run = self.frame, dict(self.snap), dict(self.stats)
        # the page shows the core's own 240 x 224 picture (the eye reads it edge-padded by 8)
        shown = frame[8:232, 8:248] if frame is not None else None
        return {"frame": base64.b64encode(png(shown)).decode() if shown is not None else None,
                "brain": snap, "run": run, "speed": self.speed, "paused": self.paused,
                "brain_file": self.brain_file}


def handler_for(game: Game, meta: dict):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HERE / "web"), **kwargs)

        def log_message(self, *args):  # quiet
            pass

        def _json(self, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                return self._json(game.state())
            if self.path.startswith("/api/meta"):
                return self._json(meta)
            return super().do_GET()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/restart":
                game.restart(int(body.get("idle", 0)))
            elif self.path == "/api/pause":
                game.paused = bool(body.get("paused", not game.paused))
            elif self.path == "/api/speed":
                game.speed = float(body.get("speed", 1.0))
            return self._json({"ok": True})

    return Handler


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8846)
    p.add_argument("--brain", type=Path, default=BRAIN)
    p.add_argument("--backend", default="cpu", help="cpu, or a device backend cadence-net offers")
    a = p.parse_args()
    game = Game(a.brain, a.backend)
    receipt = HERE / "evidence" / "receipt.json"
    meta = {"brain": a.brain.name, "describe": game.player.brain.describe().get("layout", {}),
            "receipt": json.loads(receipt.read_text()) if receipt.exists() else None}
    meta["describe"].pop("populations", None)
    game.start()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler_for(game, meta))
    print(f"open http://localhost:{a.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
