"""The daemon: owns the extension connection and offers a small local HTTP API (127.0.0.1 only, bearer token) to the CLI and the MCP server.

Protections: it listens on 127.0.0.1 only; every request needs the token from ~/.ytm-control/token (a web page cannot read that file);
requests that carry an Origin header (what a browser adds to cross-site requests) or a Host other than localhost are refused, which also blocks DNS rebinding."""
from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .controller import Controller
from .matching import YtmError, YtmNoMatch

API_PORTS = (47830, 47831, 47832)
ACTIONS = {
    "status": lambda c, a: c.status(),
    "play": lambda c, a: {"message": c.play(str(a.get("query", "")))},
    "play_playlist": lambda c, a: {"message": c.play_playlist(str(a.get("name", "")))},
    "search": lambda c, a: {"results": c.search(str(a.get("query", "")))},
    "click": lambda c, a: c.click(str(a.get("kind", "")), int(a.get("i", -1))),
    "state": lambda c, a: {"state": c.state()},
    "control": lambda c, a: c.control(str(a.get("what", ""))),
    "library_refresh": lambda c, a: {"message": c.library_refresh()},
    "library_find": lambda c, a: c.library_find(str(a.get("query", ""))),
    "library_playlists": lambda c, a: {"playlists": c.library_playlists()},
}


def make_handler(ctl: Controller, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            if self.headers.get("Origin") or host not in ("127.0.0.1", "localhost"):
                return self._send(403, {"ok": False, "error": "forbidden"})
            sent = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(sent.encode(), token.encode()):
                return self._send(401, {"ok": False, "error": "bad token"})
            action = self.path.rstrip("/").rsplit("/", 1)[-1]
            fn = ACTIONS.get(action)
            if fn is None:
                return self._send(404, {"ok": False, "error": f"unknown action '{action}'"})
            try:
                args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                self._send(200, {"ok": True, **fn(ctl, args)})
            except YtmNoMatch as e:
                self._send(200, {"ok": False, "no_match": True, "error": str(e), "closest": e.closest})
            except (YtmError, ValueError, TypeError) as e:
                self._send(200, {"ok": False, "error": str(e)})
            except Exception as e:  # never take the daemon down for one bad request
                self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    return Handler


def serve(ctl: Controller | None = None, ports=API_PORTS, block: bool = True):
    """Start the extension bridge and the HTTP API. Returns the HTTP server (already serving when block is False)."""
    ctl = ctl or Controller()
    if ctl.bridge.port is None and not ctl.bridge.start():
        raise SystemExit("Could not listen for the extension: ports 47821-47825 are all taken (is ytm-control already running?).")
    tok = config.token()
    for port in ports:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctl, tok))
        except OSError:
            continue
        config.write_file("api-port", str(port))
        if block:
            print(f"ytmusic-control is running (extension port {ctl.bridge.port}, API port {port}). Press Ctrl+C to stop.", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                ctl.bridge.stop()
        else:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd
    raise SystemExit("Could not open the local API port (47830-47832).")
