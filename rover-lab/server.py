"""Local rover dashboard. Run: python3 server.py, then http://localhost:8670."""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from rover import Life, PROTOCOL

HERE = Path(__file__).resolve().parent
MAX_STEPS = 3600
MAX_BODY = 16 * 1024 * 1024


class Runtime:
    def __init__(self, seed, weak_gain):
        self.seed, self.weak_gain = seed, weak_gain
        self.commands = queue.Queue(maxsize=32)
        self.lock = threading.Lock()
        self.cached = {"ready": False, "running": False, "error": None,
                       "status": "Preparing measured motor experience", "models": []}
        self.life, self.running = None, False
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.work, daemon=True)
        self.thread.start()

    def publish(self, status=None, error=None):
        with self.lock:
            self.cached = self.life.state() if self.life else {"ready": False, "models": []}
            self.cached.update(running=self.running, status=status, error=error)

    def state(self):
        with self.lock:
            return self.cached

    def request(self, operation, payload=None):
        done, result = threading.Event(), {}
        try:
            self.commands.put_nowait((operation, payload, done, result))
        except queue.Full:
            raise ValueError("The control queue is full; try again") from None
        if not done.wait(30):
            raise ValueError("Controller is busy; try again after preparation finishes")
        if "error" in result:
            raise ValueError(result["error"])
        return result["value"]

    def control(self, data):
        action = data.get("action")
        if action == "reset":
            seed = data.get("seed", self.seed)
            gain = data.get("weak_gain", self.weak_gain)
            if type(seed) is not int or not 0 <= seed <= 2**31-1:
                raise ValueError("Seed must be an integer between 0 and 2147483647")
            if type(gain) not in (int, float) or not .25 <= gain <= .5:
                raise ValueError("Wheel strength must be between 0.25 and 0.50")
            self.running = False
            candidate = Life(seed, gain, progress=lambda msg: self.publish(status=msg))
            self.life, self.seed, self.weak_gain = candidate, seed, gain
        elif action == "start":
            if self.life.step >= MAX_STEPS:
                raise ValueError("This life reached the 3,600-step limit; save it and restart")
            if self.life.auto and self.life.step >= sum(n for _, n in PROTOCOL["phases"]):
                raise ValueError("Automatic run complete; choose Run automatic demo to start a fresh life")
            self.running = True
        elif action == "pause":
            self.running = False
        elif action in {"weaken", "restore"}:
            if action == "weaken":
                gain = data.get("weak_gain", self.life.weak_gain)
                if type(gain) not in (int, float) or not .25 <= gain <= .5:
                    raise ValueError("Wheel strength must be between 0.25 and 0.50")
                self.life.weak_gain = float(gain)
            self.life.auto = False
            self.life.change_phase("weakened" if action == "weaken" else "restored_probe")
        elif action == "auto":
            # Automatic sequence starts a fresh comparable life.
            gain = data.get("weak_gain", self.weak_gain)
            if type(gain) not in (int, float) or not .25 <= gain <= .5:
                raise ValueError("Wheel strength must be between 0.25 and 0.50")
            self.running = False
            self.life = Life(self.seed, gain, progress=lambda msg: self.publish(status=msg))
            self.weak_gain = float(gain)
            self.running = True
        elif action == "relearn":
            self.life.auto = False
            self.life.change_phase("restored_learning")
        else:
            raise ValueError("Unknown control action")
        self.publish()
        return {"ok": True}

    def work(self):
        try:
            self.life = Life(self.seed, self.weak_gain, progress=lambda msg: self.publish(status=msg))
            self.publish()
        except Exception as exc:
            self.publish(error=str(exc))
            return
        deadline = time.monotonic()
        while not self.closed.is_set():
            try:
                operation, data, done, result = self.commands.get(timeout=0.005)
            except queue.Empty:
                operation = None
            if operation:
                try:
                    if operation == "control":
                        value = self.control(data)
                    elif operation == "checkpoint":
                        value = self.life.snapshot()
                    elif operation == "receipt":
                        value = self.life.receipt()
                    elif operation == "restore":
                        candidate = Life.from_snapshot(data)
                        if not 0 <= candidate.step <= MAX_STEPS:
                            raise ValueError("Checkpoint exceeds the life step limit")
                        self.life, self.running = candidate, False
                        self.seed, self.weak_gain = candidate.seed, candidate.weak_gain
                        self.publish()
                        value = {"ok": True}
                    else:
                        raise ValueError("Unknown request")
                    result["value"] = value
                except Exception as exc:
                    result["error"] = str(exc)
                finally:
                    done.set()
                    deadline = time.monotonic()
            if not self.running:
                deadline = time.monotonic()
                continue
            if time.monotonic() < deadline:
                continue
            queue_delay = max(0., (time.monotonic() - deadline)*1000)
            try:
                self.life.tick(queue_delay_ms=queue_delay)
                if self.life.step >= MAX_STEPS or (self.life.auto and self.life.step >= sum(n for _, n in PROTOCOL["phases"])):
                    self.running = False
                self.publish()
            except Exception as exc:
                self.running = False
                self.publish(error=f"Simulation stopped: {exc}")
            # No catch-up burst: a slow command is measured and simulation slows.
            deadline = max(deadline + PROTOCOL["dt"], time.monotonic())


class Handler(BaseHTTPRequestHandler):
    runtime: Runtime

    def log_message(self, *args):
        pass

    def send(self, value, status=200, filename=None):
        data = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/state":
                self.send(self.runtime.state())
            elif path in {"/api/checkpoint", "/api/receipt"}:
                op = path.rsplit("/", 1)[-1]
                self.send(self.runtime.request(op), filename=f"rover-{op}.json")
            elif path in {"/", "/index.html", "/app.js", "/style.css"}:
                file = HERE / "static" / ("index.html" if path == "/" else path[1:])
                data = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}[file.suffix])
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send({"error": "Not found"}, 404)
        except (ValueError, KeyError, TypeError) as exc:
            self.send({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        # Local application: reject cross-origin writes and arbitrary file paths.
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self.send({"error": "Cross-origin writes are disabled"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("Expected a JSON body smaller than 16 MB")
            data = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urlsplit(self.path).path
            if path not in {"/api/control", "/api/checkpoint"}:
                self.send({"error": "Not found"}, 404)
                return
            self.send(self.runtime.request("control" if path == "/api/control" else "restore", data))
        except (ValueError, KeyError, TypeError) as exc:
            self.send({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8670)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--weak-gain", type=float, default=.35)
    args = parser.parse_args()
    Handler.runtime = Runtime(args.seed, args.weak_gain)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Rover Lab: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.runtime.closed.set()
        server.server_close()


if __name__ == "__main__":
    main()
