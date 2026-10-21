"""Where ytmusic-control keeps its small files: the library, the trusted extension id and the local API token. Override with YTM_CONTROL_HOME."""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def home() -> Path:
    p = Path(os.environ.get("YTM_CONTROL_HOME") or Path.home() / ".ytm-control")
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_file(name: str) -> str:
    try:
        return (home() / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_file(name: str, text: str) -> None:
    (home() / name).write_text(text, encoding="utf-8")


def token() -> str:
    """The secret the local API requires. Created once; only programs that can read your user folder know it."""
    t = read_file("token")
    if not t:
        t = secrets.token_urlsafe(32)
        write_file("token", t)
        try:
            os.chmod(home() / "token", 0o600)
        except OSError:
            pass
    return t
