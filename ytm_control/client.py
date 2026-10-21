"""Talk to the running daemon (starting it in the background when it is not running yet)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import config
from .server import API_PORTS


class DaemonError(RuntimeError):
    pass


def _call(port: int, action: str, args: dict, token: str, timeout: float) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/{action}", data=json.dumps(args).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def start_daemon() -> None:
    """Run `python -m ytm_control serve` detached, so it keeps running after this command ends."""
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "ytm_control", "serve"], **kw)


def call(action: str, timeout: float = 120.0, autostart: bool = True, **args) -> dict:
    """Run an action on the daemon and return its answer. Raises DaemonError when the daemon cannot be reached or says the action failed."""
    tok = config.token()
    ports = [int(p) for p in [config.read_file("api-port")] if p.isdigit()] + [p for p in API_PORTS]
    for attempt in range(2):
        for port in dict.fromkeys(ports):
            try:
                res = _call(port, action, args, tok, timeout)
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                continue
            if not res.get("ok"):
                raise DaemonError(res.get("error") or "The action failed.")
            return res
        if attempt == 0 and autostart:
            start_daemon()
            end = time.time() + 8
            while time.time() < end:
                time.sleep(0.4)
                if any(_try_status(p, tok) for p in dict.fromkeys(ports)):
                    break
        else:
            break
    raise DaemonError("Could not reach the ytmusic-control daemon. Start it with: python -m ytm_control serve")


def _try_status(port: int, tok: str) -> bool:
    try:
        return bool(_call(port, "status", {}, tok, 2).get("ok"))
    except Exception:
        return False
