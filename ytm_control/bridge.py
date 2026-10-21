"""The local end of the browser extension: a WebSocket server on 127.0.0.1 that the extension in your normal browser connects to.

The browser itself reports who is connecting (a web page shows up as its own https origin and is refused; an extension shows up as chrome-extension://<id>).
The first extension that connects is remembered and the only one accepted from then on. The server can then ask it to search, click play, read the player
state and read your library, all in your own signed-in YouTube Music tab or app window."""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

from .matching import YtmError, YtmNoMatch, choose, kind_of, no_match_message, search_queries, started

PORTS = (47821, 47822, 47823, 47824, 47825)


class YtmPaused(YtmError):
    """The song was loaded in the user's tab but the browser did not let it start by itself: not a failure to fall back from."""


def extension_folder() -> Path:
    """The extension's files: in the repository next to this package, or inside an installed copy."""
    for candidate in (Path(__file__).resolve().parents[1] / "extension", Path(__file__).resolve().parent / "extension"):
        if (candidate / "manifest.json").exists():
            return candidate
    return Path(__file__).resolve().parents[1] / "extension"


class YtmBridge:
    def __init__(self, ports=PORTS, extension_id: str = "", serve=None, on_trust=None):
        """extension_id: the extension remembered from an earlier run (empty the first time); on_trust(id) is called when a new one is remembered."""
        self.ports, self.extension_id, self.on_trust = ports, extension_id, on_trust
        self._serve = serve
        self.port: int | None = None
        self.version = ""
        self._server = None
        self._ws = None
        self._lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}

    # ---- server -----------------------------------------------------------------------
    def start(self) -> bool:
        if self._serve is None:
            from websockets.sync.server import serve

            self._serve = serve
        for port in self.ports:
            try:
                self._server = self._serve(self._handler, "127.0.0.1", port, max_size=64 * 1024 * 1024)  # a whole library is a big message
            except OSError:
                continue
            self.port = port
            threading.Thread(target=self._server.serve_forever, daemon=True).start()
            return True
        return False

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _handler(self, ws) -> None:
        origin = ""
        try:
            origin = ws.request.headers.get("Origin", "")
        except Exception:
            pass
        prefix = "chrome-extension://"
        if not origin.startswith(prefix) or (self.extension_id and origin != prefix + self.extension_id):  # a web page, or another extension than the remembered one
            ws.close(1008, "origin not allowed")
            return
        if not self.extension_id:  # first connection ever: remember this extension, refuse any other from now on
            self.extension_id = origin[len(prefix):]
            if self.on_trust:
                self.on_trust(self.extension_id)
        with self._lock:
            self._ws = ws
        try:
            for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if msg.get("type") == "hello":
                    self.version = str(msg.get("version", ""))
                elif msg.get("type") == "ping":
                    ws.send(json.dumps({"type": "pong"}))
                elif "id" in msg:
                    q = self._pending.get(msg["id"])
                    if q is not None:
                        q.put(msg)
        finally:
            with self._lock:
                if self._ws is ws:
                    self._ws = None

    # ---- requests -----------------------------------------------------------------------
    def request(self, action: str, timeout: float = 25.0, **payload) -> dict:
        ws = self._ws
        if ws is None:
            raise YtmError("The browser extension is not connected.")
        mid = uuid.uuid4().hex
        q: queue.Queue = queue.Queue()
        self._pending[mid] = q
        try:
            ws.send(json.dumps({"id": mid, "action": action, **payload}))
            try:
                msg = q.get(timeout=timeout)
            except queue.Empty:
                raise YtmError(f"The browser extension did not answer '{action}' in time.")
        finally:
            self._pending.pop(mid, None)
        if not msg.get("ok"):
            raise YtmError(msg.get("error") or "The extension reported an error.")
        return msg

    # ---- playing ------------------------------------------------------------------------
    def ensure_tab(self, open_tab, sleep=time.sleep, clock=time.time, timeout: float = 25.0) -> None:
        """Make sure the user's browser has a YouTube Music tab or app window; if not, open their YouTube Music (signed in) and wait for it."""
        try:
            self.request("ping", timeout=8)
            return
        except YtmError as e:
            if "No YouTube Music tab" not in str(e) or open_tab is None:
                raise
        open_tab()
        end = clock() + timeout
        while clock() < end:
            sleep(1.0)
            try:
                self.request("ping", timeout=8)
                sleep(1.5)  # let the page finish loading its search box
                return
            except YtmError:
                continue
        raise YtmError("I opened YouTube Music in your browser, but its page never became ready.")

    def wait_connected(self, seconds: float = 8.0, sleep=time.sleep, clock=time.time) -> bool:
        """The extension reconnects by itself within about half a minute of the app starting; wait briefly for it when it is known to be installed."""
        end = clock() + seconds
        while not self.connected and clock() < end:
            sleep(0.4)
        return self.connected

    def play(self, query: str, sleep=time.sleep, clock=time.time, open_tab=None, judge=None, library=None) -> str:
        """Search in the user's own YouTube Music tab, click play on the best match, confirm."""
        self.ensure_tab(open_tab, sleep, clock)
        best, closest = None, []
        spelled = (library.resolve(query) if library else None) or query  # the saved library's own spelling of the song, when it is one of yours
        for q in search_queries(spelled):
            cands = self.request("search", timeout=30, query=q).get("cands", [])
            try:
                best = choose(spelled, cands, judge)
                break
            except YtmNoMatch as e:
                closest += e.closest
        if best is None:
            raise YtmNoMatch(no_match_message(query, closest), closest)
        state: dict = {}
        for attempt in (1, 2):
            res = self.request("click", kind=best["kind"], i=best["i"])
            if res.get("result") != "clicked":
                raise YtmError("The play button of the best match could not be found on the page.")
            end = clock() + 9
            while clock() < end:
                sleep(0.7)
                state = self.request("state").get("state", {})
                done = started(best, state)
                if done:
                    return done
        if state.get("paused") and state.get("title") and set(state["title"].lower().split()) & set(best["title"].lower().split()):
            raise YtmPaused(f"Opened {state['title']} in your YouTube Music, but the browser did not let it start by itself; press play there.")
        raise YtmError(f"I clicked play on '{best['title']}', but the page did not start playing that song (it shows '{state.get('title') or 'nothing'}').")
