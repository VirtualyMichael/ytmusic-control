"""What the daemon can do, in one place: the extension bridge plus the saved library, behind a handful of actions that the HTTP API, the CLI and the MCP server all share."""
from __future__ import annotations

import webbrowser

from . import config
from .bridge import YtmBridge, YtmPaused
from .library import Library
from .matching import YtmError, YtmNoMatch, describe, rank

MUSIC_URL = "https://music.youtube.com"
CONTROLS = ("play", "pause", "toggle", "next", "previous")


def open_music_tab() -> None:
    webbrowser.open(MUSIC_URL)


class Controller:
    def __init__(self, bridge: YtmBridge | None = None, library: Library | None = None, open_tab=open_music_tab):
        self.bridge = bridge or YtmBridge(extension_id=config.read_file("extension-id"), on_trust=lambda i: config.write_file("extension-id", i))
        self.library = library or Library()
        self.open_tab = open_tab

    def status(self) -> dict:
        return {"extension_connected": self.bridge.connected, "extension_version": self.bridge.version, "port": self.bridge.port, "library": self.library.summary()}

    def play(self, query: str) -> str:
        """Search, pick the best match and play it. Says plainly when nothing matches (it never plays a different artist's song)."""
        if not self.bridge.connected and self.bridge.extension_id:
            self.bridge.wait_connected()
        if not self.bridge.connected:
            raise YtmError("The browser extension is not connected. Install it from the extension folder and keep the browser open (see the README).")
        try:
            return self.bridge.play(query, open_tab=self.open_tab, library=self.library)
        except YtmPaused as e:
            return str(e)

    def search(self, query: str) -> list[dict]:
        """The visible results for a search, best guess first, each with the `kind` and `i` that `click` needs. An agent can read these and choose for itself."""
        self.bridge.ensure_tab(self.open_tab)
        cands = self.bridge.request("search", timeout=30, query=query).get("cands", [])
        best = {(c["kind"], c["i"]): n for n, (_, c) in enumerate(rank(query, cands))}
        out = [{"kind": c["kind"], "i": c["i"], "title": c["title"], "sub": c.get("sub", ""), "description": describe(c)} for c in cands]
        return sorted(out, key=lambda c: best.get((c["kind"], c["i"]), 999))

    def click(self, kind: str, i: int) -> dict:
        res = self.bridge.request("click", kind=kind, i=int(i))
        return {"result": res.get("result"), "state": res.get("state", {})}

    def state(self) -> dict:
        return self.bridge.request("state").get("state", {})

    def control(self, what: str) -> dict:
        if what not in CONTROLS:
            raise YtmError(f"Unknown control '{what}'. Use one of: {', '.join(CONTROLS)}.")
        res = self.bridge.request("control", what=what)
        return {"result": res.get("result"), "state": res.get("state", {})}

    def library_refresh(self) -> str:
        return self.library.refresh(self.bridge)

    def library_find(self, query: str) -> dict:
        spelled = self.library.resolve(query)
        return {"in_library": spelled is not None, "spelled_as": spelled, "library": self.library.summary()}

    def library_playlists(self) -> list[str]:
        return self.library.playlist_titles()
