"""A tiny MCP server over stdio (newline-delimited JSON-RPC 2.0), so any MCP-capable AI app can control YouTube Music. No MCP package needed.

The calling model is the judge: `search_music` returns what is on the page and `play_result` presses play on the one it picked, so it can reason through an
unclear request instead of trusting a single guess. `play_music` is the one-call shortcut."""
from __future__ import annotations

import json
import sys

from . import __version__
from .client import DaemonError, call

TOOLS = [
    {"name": "play_music", "description": "Search YouTube Music and play the best match, e.g. 'Maps by Maroon 5'. Never plays a different artist's song with the same title: says it could not find it instead (then use search_music and look at the results).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Song, or 'Song by Artist'"}}, "required": ["query"]}},
    {"name": "play_playlist", "description": "Play one of the user's saved YouTube Music playlists by name (needs the library; says so when no saved playlist is called that and lists the closest names).",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "search_music", "description": "List YouTube Music search results (kind, number, title, artist), best guess first, without playing. Pick one and call play_result.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "play_result", "description": "Press play on a result from the latest search_music (use its kind and number).",
     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "number": {"type": "integer"}}, "required": ["kind", "number"]}},
    {"name": "music_control", "description": "pause, play (resume), toggle, next or previous.",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["play", "pause", "toggle", "next", "previous"]}}, "required": ["action"]}},
    {"name": "now_playing", "description": "What is playing in YouTube Music right now, and whether it is paused.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "library_find", "description": "Check whether a song is in the user's saved YouTube Music playlists and how it is spelled there.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "library_refresh", "description": "Re-read all the user's playlists and songs from their signed-in YouTube Music (can take a minute).", "inputSchema": {"type": "object", "properties": {}}},
]


def run_tool(name: str, a: dict) -> str:
    if name == "play_music":
        return call("play", query=str(a["query"]))["message"]
    if name == "play_playlist":
        return call("play_playlist", name=str(a["name"]))["message"]
    if name == "search_music":
        rows = call("search", query=str(a["query"]))["results"]
        return "\n".join(f"kind={r['kind']} number={r['i']}: {r['description']}  ({r['sub']})" for r in rows) or "No results."
    if name == "play_result":
        res = call("click", kind=str(a["kind"]), i=int(a["number"]))
        s = res.get("state") or {}
        return f"{res['result']}. " + (f"{'Paused' if s.get('paused') else 'Playing'}: {s.get('title')}" if s.get("title") else "Nothing is playing.")
    if name == "music_control":
        res = call("control", what=str(a["action"]))
        s = res.get("state") or {}
        return f"{res['result']}. " + (f"{'Paused' if s.get('paused') else 'Playing'}: {s.get('title')}" if s.get("title") else "Nothing is playing.")
    if name == "now_playing":
        s = call("state")["state"]
        return f"{'Paused' if s.get('paused') else 'Playing'}: {s.get('title')}" + (f" by {s['by']}" if s.get("by") else "") if s.get("title") else "Nothing is playing."
    if name == "library_find":
        r = call("library_find", query=str(a["query"]))
        return f"In the library as: {r['spelled_as']}" if r["in_library"] else "Not in the saved library."
    if name == "library_refresh":
        return call("library_refresh", timeout=330)["message"]
    raise KeyError(name)


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, the reply out (None for notifications)."""
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2024-11-05"),
                                                       "capabilities": {"tools": {}}, "serverInfo": {"name": "ytmusic-control", "version": __version__}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = msg.get("params") or {}
        try:
            text, err = run_tool(p.get("name", ""), p.get("arguments") or {}), False
        except KeyError:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool {p.get('name')}"}}
        except (DaemonError, ValueError, TypeError) as e:
            text, err = f"{e}", True
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0
