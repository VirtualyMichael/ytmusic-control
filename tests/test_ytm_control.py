import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from websockets.sync.client import connect

from ytm_control import config, mcp
from ytm_control.bridge import YtmBridge, YtmPaused
from ytm_control.controller import Controller
from ytm_control.library import Library
from ytm_control.matching import YtmError, YtmNoMatch, choose, kind_of, rank, similarity, tokens
from ytm_control.server import make_handler, serve

ROOT = Path(__file__).resolve().parents[1]
EXT_ID = "abcdefghijklmnopabcdefghijklmnop"
BULLET = "•"
RESULTS = [
    {"kind": "card", "i": 0, "title": "Eternity", "sub": f"Video {BULLET} Stellardrone {BULLET} 2.1M views", "aria": ""},
    {"kind": "row", "i": 0, "title": "Eternity (Reprise)", "sub": f"Song {BULLET} Stellardrone {BULLET} 322K plays", "aria": ""},
    {"kind": "row", "i": 1, "title": "Eternity", "sub": f"Song {BULLET} Stellardrone 3.1M plays", "aria": ""},
    {"kind": "row", "i": 2, "title": "Light Years", "sub": f"Album {BULLET} Stellardrone {BULLET} 2013", "aria": ""},
    {"kind": "row", "i": 3, "title": "Stellardrone", "sub": f"Artist {BULLET} 1.2M subscribers", "aria": ""},
    {"kind": "row", "i": 4, "title": "Eternity (Orchestral)", "sub": f"Song {BULLET} Alex Warren {BULLET} 9M plays", "aria": ""},
]
SLVM = [
    {"kind": "row", "i": 0, "title": "Continuum", "sub": f"Song {BULLET} Lemaitre {BULLET} 1M plays", "aria": ""},
    {"kind": "row", "i": 1, "title": "Continuum", "sub": f"Song {BULLET} SLVMLORD {BULLET} 80K plays", "aria": ""},
]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("YTM_CONTROL_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


# ---------- matching -----------------------------------------------------------------------------
def test_matching_prefers_the_plain_song_by_the_right_artist():
    assert tokens("Maps by Maroon 5!") == ["maps", "by", "maroon", "5"]
    assert kind_of(f"Song {BULLET} Stellardrone {BULLET} 3.1M plays") == ("song", "Stellardrone")
    assert rank("Eternity Stellardrone", RESULTS)[0][1]["i"] == 1
    assert rank("Eternity by Alex Warren", RESULTS)[0][1]["title"] == "Eternity (Orchestral)"
    assert similarity("SLVM Lord", "SLVMLORD") == 1.0 and similarity("Stellardrone", "Lemaitre") < 0.5


def test_a_different_artists_song_is_never_chosen_and_the_judge_can_decide():
    with pytest.raises(YtmNoMatch) as e:
        choose("Continuum by Metallica", SLVM)
    assert any("Lemaitre" in c for c in e.value.closest)
    assert choose("Continuum by SLVM Lord", SLVM)["i"] == 1
    pick = choose("Continuum by Lemaitre", SLVM, judge=lambda q, cands: cands[0])
    assert pick["title"] == "Continuum"


# ---------- the extension side ---------------------------------------------------------------------
class FakeExtension(threading.Thread):
    def __init__(self, port, origin=f"chrome-extension://{EXT_ID}", results=RESULTS):
        super().__init__(daemon=True)
        self.port, self.origin, self.results = port, origin, results
        self.playing, self.clicked, self.title = False, [], "Eternity"

    def run(self):
        try:
            with connect(f"ws://127.0.0.1:{self.port}", additional_headers={"Origin": self.origin}) as ws:
                ws.send(json.dumps({"type": "hello", "version": "1.0.0"}))
                for raw in ws:
                    msg = json.loads(raw)
                    a = msg["action"]
                    if a == "search":
                        out = {"ok": True, "cands": self.results}
                    elif a == "click":
                        self.clicked.append((msg["kind"], msg["i"]))
                        self.playing = True
                        self.title = next(r["title"] for r in self.results if (r["kind"], r["i"]) == (msg["kind"], msg["i"]))
                        out = {"ok": True, "result": "clicked", "state": {}}
                    elif a == "control":
                        self.playing = msg["what"] == "play" or (self.playing and msg["what"] != "pause")
                        out = {"ok": True, "result": "clicked", "state": {"paused": not self.playing, "title": self.title, "by": "Stellardrone"}}
                    elif a == "state":
                        out = {"ok": True, "state": {"paused": not self.playing, "title": self.title, "by": "Stellardrone"}}
                    else:
                        out = {"ok": True}
                    ws.send(json.dumps({"id": msg["id"], **out}))
        except Exception:
            pass


def start_bridge(**kw):
    b = YtmBridge(ports=(0,), **kw)
    b.start()
    b.port = b._server.socket.getsockname()[1]
    return b


def wait(cond, seconds=3):
    end = time.time() + seconds
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


@pytest.fixture
def ctl():
    c = Controller(bridge=start_bridge(extension_id=EXT_ID), library=Library(), open_tab=lambda: None)
    yield c
    c.bridge.stop()


def test_play_through_the_extension_and_refuse_web_pages(ctl):
    for origin in ("https://evil.example", "chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba", "http://127.0.0.1:8000", ""):
        FakeExtension(ctl.bridge.port, origin=origin).start()
    time.sleep(0.4)
    assert not ctl.bridge.connected
    ext = FakeExtension(ctl.bridge.port)
    ext.start()
    assert wait(lambda: ctl.bridge.connected)
    assert ctl.play("Eternity by Stellardrone").startswith("Playing Eternity by Stellardrone (a song)") and ext.clicked == [("row", 1)]


def test_search_lists_results_best_first_and_click_plays_the_chosen_one(ctl):
    ext = FakeExtension(ctl.bridge.port)
    ext.start()
    assert wait(lambda: ctl.bridge.connected)
    found = ctl.search("Eternity by Alex Warren")
    assert found[0]["title"] == "Eternity (Orchestral)" and {"kind", "i", "description"} <= set(found[0])
    ctl.click(found[0]["kind"], found[0]["i"])
    assert ext.clicked == [("row", 4)]
    assert ctl.control("pause")["state"]["paused"] is True and ctl.control("play")["state"]["paused"] is False
    with pytest.raises(YtmError):
        ctl.control("explode")


def test_no_match_is_reported_not_replaced_by_another_song(ctl):
    FakeExtension(ctl.bridge.port, results=SLVM).start()
    assert wait(lambda: ctl.bridge.connected)
    with pytest.raises(YtmNoMatch, match="Could not find"):
        ctl.play("Continuum by Metallica")


def test_not_connected_gives_a_clear_error():
    c = Controller(bridge=YtmBridge(ports=(0,)), library=Library(), open_tab=lambda: None)
    with pytest.raises(YtmError, match="not connected"):
        c.play("anything")


def test_the_first_extension_is_remembered_on_disk_and_others_refused(home):
    trusted = []
    b = start_bridge(on_trust=trusted.append)
    try:
        FakeExtension(b.port).start()
        assert wait(lambda: b.connected) and trusted == [EXT_ID]
        FakeExtension(b.port, origin="chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba").start()
        time.sleep(0.3)
        assert b.extension_id == EXT_ID
    finally:
        b.stop()


def test_library_spelling_is_used_for_the_search(ctl, home):
    ctl.library.save({"fetchedAt": time.time() * 1000, "playlists": [{"id": "x", "title": "p", "tracks": [{"videoId": "v", "title": "Continuum", "artist": "SLVMLORD"}]}]})
    ext = FakeExtension(ctl.bridge.port, results=SLVM)
    ext.start()
    assert wait(lambda: ctl.bridge.connected)
    assert "SLVMLORD" in ctl.play("Continuum by SLVM Lord") and ext.clicked == [("row", 1)]
    assert ctl.library_find("continuum by slvm lord")["spelled_as"] == "Continuum by SLVMLORD"


# ---------- the local API ---------------------------------------------------------------------------
def api(port, path, body=None, token=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/{path}", data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_needs_the_token_and_refuses_browsers_and_rebinding(ctl):
    httpd = serve(ctl, ports=(0,), block=False)
    port = httpd.server_address[1]
    tok = config.token()
    try:
        assert api(port, "status", token=tok)[1]["ok"] is True
        assert api(port, "status", token="wrong")[0] == 401
        assert api(port, "status", token=tok, headers={"Origin": "https://evil.example"})[0] == 403  # a web page's request
        assert api(port, "status", token=tok, headers={"Host": "evil.example"})[0] == 403  # DNS rebinding
        assert api(port, "nope", token=tok)[0] == 404
        FakeExtension(ctl.bridge.port, results=SLVM).start()
        assert wait(lambda: ctl.bridge.connected)
        code, res = api(port, "play", {"query": "Continuum by SLVM Lord"}, tok)
        assert res["ok"] and "SLVMLORD" in res["message"]
        code, res = api(port, "play", {"query": "Continuum by Metallica"}, tok)
        assert res["ok"] is False and res["no_match"] and "Lemaitre" in " ".join(res["closest"])
    finally:
        httpd.shutdown()


def test_token_is_created_once_and_kept(home):
    assert config.token() == config.token() and len(config.token()) > 30


# ---------- MCP -------------------------------------------------------------------------------------
def test_mcp_lists_tools_and_reports_errors_as_tool_errors(monkeypatch):
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["serverInfo"]["name"] == "ytmusic-control" and init["result"]["protocolVersion"] == "2025-03-26"
    names = {t["name"] for t in mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    assert {"play_music", "search_music", "play_result", "music_control", "now_playing"} <= names
    monkeypatch.setattr(mcp, "call", lambda action, **kw: {"message": f"did {action} {kw}"})
    out = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "play_music", "arguments": {"query": "x"}}})
    assert out["result"]["isError"] is False and "did play" in out["result"]["content"][0]["text"]
    from ytm_control.client import DaemonError

    def boom(*a, **k):
        raise DaemonError("extension not connected")

    monkeypatch.setattr(mcp, "call", boom)
    out = mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "play_music", "arguments": {"query": "x"}}})
    assert out["result"]["isError"] is True and "not connected" in out["result"]["content"][0]["text"]
    assert mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope"}})["error"]["code"] == -32602


def test_mcp_speaks_json_lines_over_stdio():
    p = subprocess.run([sys.executable, "-m", "ytm_control", "mcp"], input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n", cwd=ROOT,
                       capture_output=True, text=True, timeout=30)
    assert json.loads(p.stdout.splitlines()[0])["result"]["tools"]


def test_cli_prints_the_extension_folder():
    p = subprocess.run([sys.executable, "-m", "ytm_control", "extension-path"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert (Path(p.stdout.strip()) / "manifest.json").exists()


# ---------- the repository's own consistency --------------------------------------------------------
def test_extension_and_server_agree_on_ports_and_the_extension_logic_passes():
    from ytm_control.bridge import PORTS

    bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    assert f"const PORTS = [{', '.join(map(str, PORTS))}]" in bg
    m = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert m["host_permissions"] == ["https://music.youtube.com/*"] and set(m["permissions"]) == {"tabs", "scripting", "alarms"}
    import shutil

    node = shutil.which("node")
    if node:
        r = subprocess.run([node, str(ROOT / "tests" / "extension_test.mjs")], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
