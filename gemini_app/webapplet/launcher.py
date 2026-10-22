"""Browser launcher and endpoint utilities for WebApplets."""

from __future__ import annotations

import socket
import urllib.request
import webbrowser
from typing import Optional


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a local TCP port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_browser(url: str, new_window: bool = True) -> bool:
    """Opens browser pointing to the WebApplet URL on desktop environments."""
    try:
        if new_window:
            return webbrowser.open_new(url)
        return webbrowser.open(url)
    except Exception:
        return False


def probe_webapplet(url: str, timeout: float = 1.5) -> bool:
    """Checks if a WebApplet endpoint is responding."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Gemini-WebApplet-Probe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204, 404)
    except Exception:
        return False
