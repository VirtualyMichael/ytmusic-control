"""Command line: `ytm-control play "Continuum by SLVMLORD"`, `ytm-control next`, `ytm-control search "..."`, and so on. Output is plain text (or JSON with --json)."""
from __future__ import annotations

import argparse
import json
import sys

from .bridge import extension_folder
from .client import DaemonError, call


def _state_line(state: dict) -> str:
    if not state or not state.get("title"):
        return "Nothing is playing."
    return f"{'Paused' if state.get('paused') else 'Playing'}: {state['title']}" + (f" by {state['by']}" if state.get("by") else "")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ytm-control", description="Control the YouTube Music you are signed in to, through the ytmusic-control browser extension.")
    p.add_argument("--json", action="store_true", help="print the raw JSON answer")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the daemon in the foreground (the other commands start it for you when needed)")
    sub.add_parser("status", help="is the extension connected, and what is in the saved library")
    sub.add_parser("extension-path", help="print the folder to load as an unpacked extension")
    s = sub.add_parser("play", help="search and play the best match, e.g. 'Maps by Maroon 5'")
    s.add_argument("query", nargs="+")
    s = sub.add_parser("playlist", help="play one of your saved playlists by name, e.g. 'early morning'")
    s.add_argument("name", nargs="+")
    s = sub.add_parser("search", help="list the search results (with the numbers `click` needs) instead of playing")
    s.add_argument("query", nargs="+")
    s = sub.add_parser("click", help="press play on one search result: ytm-control click song 2")
    s.add_argument("kind")
    s.add_argument("i", type=int)
    for name in ("pause", "resume", "next", "previous", "toggle"):
        sub.add_parser(name, help=f"{name} the music")
    sub.add_parser("now", help="what is playing")
    lib = sub.add_parser("library", help="your saved playlists and songs")
    ls = lib.add_subparsers(dest="lib", required=True)
    ls.add_parser("refresh", help="read all your playlists and songs from your signed-in YouTube Music and save them")
    ls.add_parser("playlists", help="list the saved playlist names")
    f = ls.add_parser("find", help="is this song in your library, and how is it spelled there")
    f.add_argument("query", nargs="+")
    sub.add_parser("mcp", help="run as an MCP server over stdio, for AI apps that speak MCP")
    return p


def run(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd == "serve":
        from .server import serve

        serve()
        return 0
    if a.cmd == "extension-path":
        print(extension_folder())
        return 0
    if a.cmd == "mcp":
        from .mcp import main

        return main()
    try:
        if a.cmd == "status":
            res = call("status", autostart=True)
            text = f"extension: {'connected' if res['extension_connected'] else 'NOT connected (load it in your browser, see the README)'}\nlibrary: {res['library']}"
        elif a.cmd == "play":
            res = call("play", query=" ".join(a.query))
            text = res["message"]
        elif a.cmd == "playlist":
            res = call("play_playlist", name=" ".join(a.name))
            text = res["message"]
        elif a.cmd == "search":
            res = call("search", query=" ".join(a.query))
            text = "\n".join(f"{n}. [{r['kind']} {r['i']}] {r['description']}  ({r['sub']})" for n, r in enumerate(res["results"], 1)) or "No results."
        elif a.cmd == "click":
            res = call("click", kind=a.kind, i=a.i)
            text = f"{res['result']}. {_state_line(res['state'])}"
        elif a.cmd in ("pause", "resume", "next", "previous", "toggle"):
            res = call("control", what="play" if a.cmd == "resume" else a.cmd)
            text = f"{res['result']}. {_state_line(res['state'])}"
        elif a.cmd == "now":
            res = call("state")
            text = _state_line(res["state"])
        else:  # library
            if a.lib == "refresh":
                res = call("library_refresh", timeout=330)
                text = res["message"]
            elif a.lib == "playlists":
                res = call("library_playlists")
                text = "\n".join(res["playlists"]) or "No library saved yet. Run: ytm-control library refresh"
            else:
                res = call("library_find", query=" ".join(a.query))
                text = f"In your library as: {res['spelled_as']}" if res["in_library"] else "Not found in your saved library."
    except DaemonError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2) if a.json else text)
    return 0


def main() -> None:
    raise SystemExit(run())
