#!/usr/bin/env python3
"""Run the companion and its simulator on your PC, no board needed.

    python3 tools/run_pc.py          then open http://localhost:7000
    python3 tools/run_pc.py --lan    also reachable from your phone on the same Wi-Fi

Serves the same assets/ folder as the board. The board's libs/arduino.js
(socket.io) is swapped for tools/pc_webui.js, which has the same API over plain
HTTP, so the simulator code is identical in both places. Standard library only.
"""

import argparse
import json
import queue
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from companion.core import Companion  # noqa: E402  (needs the path above)
from companion.llm import LlmClient  # noqa: E402

ASSETS = ROOT / "assets"
SHIM = ROOT / "tools" / "pc_webui.js"
CHANNEL = "msg"   # same single channel as python/main.py
KEEPALIVE_S = 15  # comment line sent to idle event streams


class Clients:
    """One outgoing queue per open browser tab."""

    def __init__(self):
        self._lock = threading.Lock()
        self._queues = {}  # client id -> queue of JSON strings

    def add(self, cid):
        q = queue.Queue(maxsize=1000)
        with self._lock:
            self._queues[cid] = q
        return q

    def remove(self, cid, q):
        with self._lock:
            if self._queues.get(cid) is q:
                del self._queues[cid]

    def send(self, msg, to=None):
        """The Companion's send callback: one client, or all when to is None."""
        data = json.dumps(msg, separators=(",", ":"))
        with self._lock:
            if to is None:
                targets = list(self._queues.values())
            else:
                targets = [self._queues[to]] if to in self._queues else []
        for q in targets:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass  # that tab stopped reading; drop rather than block the companion


def make_handler(clients, brain):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ASSETS), **kwargs)

        def log_message(self, format, *args):
            pass  # keep the console for the companion's own log

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")  # always serve the latest files
            super().end_headers()

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/libs/arduino.js":
                self._send_body(SHIM.read_bytes(), "text/javascript")
            elif url.path == "/libs/socket.io.min.js":
                self._send_body(b"// not needed on the PC, see tools/pc_webui.js\n", "text/javascript")
            elif url.path == "/events":
                self._stream_events(_client_id(url))
            else:
                super().do_GET()

        def do_POST(self):
            url = urlparse(self.path)
            if url.path != "/send":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self.send_error(400, "invalid JSON")
                return
            if isinstance(body, dict) and body.get("name") == CHANNEL:
                brain.receive(body.get("data"), _client_id(url))
            self.send_response(204)
            self.end_headers()

        def _send_body(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self, cid):
            if not cid:
                self.send_error(400, "missing id")
                return
            q = clients.add(cid)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=KEEPALIVE_S)
                        self.wfile.write(f"event: {CHANNEL}\ndata: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except OSError:
                pass  # the tab was closed
            finally:
                clients.remove(cid, q)

    return Handler


def _client_id(url):
    return parse_qs(url.query).get("id", [""])[0]


def main():
    parser = argparse.ArgumentParser(description="Run the companion simulator on this PC.")
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument("--lan", action="store_true",
                        help="listen on all network interfaces, e.g. to open it on your phone")
    parser.add_argument("--llm", metavar="URL",
                        help="an OpenAI-compatible AI model server for questions the data cannot answer, "
                             "e.g. llama.cpp's llama-server: http://localhost:8080/v1")
    args = parser.parse_args()

    clients = Clients()
    brain = Companion(ROOT / "config", clients.send, echo=lambda line: print(line, flush=True),
                      llm=LlmClient(args.llm) if args.llm else None, warm_up=bool(args.llm))
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    try:
        server = ThreadingHTTPServer((host, args.port), make_handler(clients, brain))
    except OSError as e:
        sys.exit(f"Cannot use port {args.port}: {e.strerror}. Is the simulator already running? "
                 f"Stop it with Ctrl+C, or start this one with --port {args.port + 1}.")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Simulator running: http://localhost:{args.port}  (Ctrl+C stops it)", flush=True)
    try:
        while True:  # the same loop python/main.py runs on the board
            brain.tick()
            time.sleep(1 / brain.fps)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
