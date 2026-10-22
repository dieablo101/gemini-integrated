"""Wingman Bilateral Interactive Applet.

Provides Gemini's web-based talk portal, visual cards, confirmation dialogs,
and WebAuthn Face ID gateway.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from gemini_app.webapplet.applets.wingman.ui import get_wingman_html
from gemini_app.webapplet.engine import WebAppletEngine


class WingmanApplet:
    """Manages Wingman routes, live cards, and biometric challenges."""

    def __init__(self, engine: Optional[WebAppletEngine] = None, port: int = 8888) -> None:
        self.engine = engine or WebAppletEngine(name="wingman", host="127.0.0.1", port=port, sse_path="/applet/wingman/events")
        self._action_callbacks: List[Callable[[str, str, Dict[str, Any]], None]] = []
        self._pending_biometrics: Dict[str, threading.Event] = {}
        self._biometric_results: Dict[str, Dict[str, Any]] = {}
        self._recent_cards: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        self._setup_routes()

    def _setup_routes(self) -> None:
        # Web UI root and canonical route
        self.engine.register_get("/", self._handle_index)
        self.engine.register_get("/applet/wingman", self._handle_index)
        self.engine.register_get("/applet/wingman/", self._handle_index)

        # Heartbeat ping
        self.engine.register_get("/applet/wingman/ping", self._handle_ping)

        # Card action responses
        self.engine.register_post("/applet/wingman/action", self._handle_action)

        # WebAuthn response
        self.engine.register_post("/applet/wingman/webauthn_response", self._handle_biometric_response)

    def _handle_index(self, handler: Any, query: Dict[str, List[str]]) -> str:
        return get_wingman_html(port=self.engine.port)

    def _handle_ping(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        return {"status": "pong", "time": time.time(), "engine": self.engine.name}

    def _handle_action(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        card_id = body.get("card_id", "")
        action = body.get("action", "")
        with self._lock:
            for cb in self._action_callbacks:
                try:
                    cb(card_id, action, body)
                except Exception:
                    pass
        return {"status": "ok", "card_id": card_id, "action": action}

    def _handle_biometric_response(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        chal_id = body.get("challenge_id", "")
        res = body.get("result", {})
        with self._lock:
            if chal_id in self._pending_biometrics:
                self._biometric_results[chal_id] = res
                self._pending_biometrics[chal_id].set()
        return {"status": "ok"}

    def on_action(self, callback: Callable[[str, str, Dict[str, Any]], None]) -> None:
        """Subscribes callback to user button clicks on cards."""
        with self._lock:
            self._action_callbacks.append(callback)

    def is_browser_open(self) -> bool:
        """Returns True if a browser tab is currently open and connected to Wingman."""
        return self.engine.is_client_active(window_seconds=15.0)

    @property
    def client_count(self) -> int:
        return self.engine.get_active_client_count()

    def push_card(
        self,
        title: str,
        content: str,
        actions: Optional[List[Dict[str, str]]] = None,
        accent: bool = True,
        card_id: Optional[str] = None,
    ) -> str:
        """Pushes an interactive visual card to the connected browser(s)."""
        c_id = card_id or f"card-{int(time.time() * 1000)}"
        card_obj = {
            "id": c_id,
            "title": title,
            "content": content,
            "actions": actions or [],
            "accent": accent,
            "timestamp": time.time(),
        }
        with self._lock:
            self._recent_cards.append(card_obj)
            if len(self._recent_cards) > 50:
                self._recent_cards.pop(0)

        self.engine.broadcast_event("card", card_obj)
        return c_id

    def request_biometric(self, reason: str = "Authorize Operation", timeout: float = 30.0) -> Dict[str, Any]:
        """Dispatches a WebAuthn biometric challenge to the open Wingman browser."""
        chal_id = f"chal-{secrets.token_hex(8)}"
        nonce = secrets.token_hex(16)
        ev = threading.Event()

        with self._lock:
            self._pending_biometrics[chal_id] = ev

        chal_payload = {
            "challenge_id": chal_id,
            "nonce": nonce,
            "reason": reason,
            "timestamp": time.time(),
        }

        self.engine.broadcast_event("biometric_challenge", chal_payload)

        # Wait for user Face ID / Touch ID scan
        completed = ev.wait(timeout=timeout)

        with self._lock:
            self._pending_biometrics.pop(chal_id, None)
            result = self._biometric_results.pop(chal_id, None)

        if not completed or not result:
            return {"status": "timeout", "error": f"Biometric authorization timed out after {timeout}s"}

        return result

    def start(self) -> bool:
        return self.engine.start()

    def stop(self) -> None:
        self.engine.stop()
