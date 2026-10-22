"""Wingman Bilateral Interactive Applet.

Provides Gemini's web-based talk portal, visual cards, zero-trust security gate,
dropdown mode switcher (Work / Chat), remote chat stream, and WebAuthn Face ID gateway.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from gemini_app.webapplet.applets.wingman.security import WingmanSecurity, WingmanSession
from gemini_app.webapplet.applets.wingman.ui import get_wingman_html
from gemini_app.webapplet.engine import WebAppletEngine


class WingmanApplet:
    """Manages Wingman routes, live cards, zero-trust pairing, and remote chat stream."""

    def __init__(
        self,
        engine: Optional[WebAppletEngine] = None,
        host: str = "0.0.0.0",
        port: int = 8888,
        node_id: str = "local",
        require_pairing: bool = True,
    ) -> None:
        self.node_id = node_id
        self.engine = engine or WebAppletEngine(name="wingman", host=host, port=port, sse_path="/applet/wingman/events")
        self.security = WingmanSecurity(require_pairing=require_pairing)

        self._action_callbacks: List[Callable[[str, str, Dict[str, Any]], None]] = []
        self._chat_callbacks: List[Callable[[str, str, Dict[str, Any]], None]] = []
        self._pending_biometrics: Dict[str, threading.Event] = {}
        self._biometric_results: Dict[str, Dict[str, Any]] = {}
        self._recent_cards: List[Dict[str, Any]] = []
        self._chat_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        self._setup_routes()

    def _setup_routes(self) -> None:
        # Web UI root and canonical route
        self.engine.register_get("/", self._handle_index)
        self.engine.register_get("/applet/wingman", self._handle_index)
        self.engine.register_get("/applet/wingman/", self._handle_index)

        # Heartbeat ping
        self.engine.register_get("/applet/wingman/ping", self._handle_ping)

        # Zero-trust session check & passkey auth
        self.engine.register_get("/applet/wingman/session", self._handle_session_check)
        self.engine.register_get("/applet/wingman/auth_status", self._handle_auth_status)
        self.engine.register_post("/applet/wingman/auth", self._handle_passkey_auth)
        self.engine.register_post("/applet/wingman/verify_passkey", self._handle_verify_passkey)

        # Card action responses
        self.engine.register_post("/applet/wingman/action", self._handle_action)

        # Bilateral Chat Stream
        self.engine.register_post("/applet/wingman/chat", self._handle_chat)
        self.engine.register_get("/applet/wingman/chat_history", self._handle_chat_history)

        # WebAuthn response
        self.engine.register_post("/applet/wingman/webauthn_response", self._handle_biometric_response)

    def _handle_index(self, handler: Any, query: Dict[str, List[str]]) -> str:
        return get_wingman_html(port=self.engine.port, node_id=self.node_id)

    def _handle_ping(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        return {
            "status": "pong",
            "time": time.time(),
            "engine": self.engine.name,
            "node_id": self.node_id,
            "client_count": self.client_count,
        }

    def _extract_token_and_device(self, handler: Any, query: Dict[str, List[str]]) -> tuple[str, str]:
        token = ""
        device_id = ""
        # Check headers
        if hasattr(handler, "headers"):
            token = handler.headers.get("X-Wingman-Token", "")
            device_id = handler.headers.get("X-Wingman-Device", "")
            if not token:
                auth_hdr = handler.headers.get("Authorization", "")
                if auth_hdr.lower().startswith("bearer "):
                    token = auth_hdr[7:].strip()
        # Fallback to query
        if not token and "token" in query:
            token = query["token"][0]
        if not device_id and "device" in query:
            device_id = query["device"][0]
        return token, device_id

    def _handle_session_check(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        user_agent = handler.headers.get("User-Agent", "") if hasattr(handler, "headers") else ""
        token, device_id = self._extract_token_and_device(handler, query)

        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        session = self.security.create_or_resume_session(
            client_ip=client_ip,
            user_agent=user_agent,
            device_id=device_id,
            existing_token=token,
            is_loopback=is_loopback,
        )

        return {
            "session_id": session.session_id,
            "authenticated": (session.status == "authorized"),
            "status": session.status,
            "token": session.token if session.status == "authorized" else "",
            "mode": session.current_mode,
            "device_id": session.device_id,
            "node_id": self.node_id,
        }

    def _handle_passkey_auth(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        sess_id = body.get("session_id", "")
        passkey = body.get("passkey", "")
        trust_device = bool(body.get("trust_device", False))

        ok, token, msg = self.security.verify_passkey_and_authorize(
            session_id=sess_id,
            passkey=passkey,
            trust_device=trust_device,
        )
        if ok:
            # Broadcast auth approved to SSE clients
            self.engine.broadcast_event("session_authorized", {
                "session_id": sess_id,
                "token": token,
                "status": "authorized",
            })
            return {"status": "ok", "token": token, "message": msg}
        return {"status": "error", "message": msg}

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

    def _handle_chat(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        """Receives user chat message from Wingman UI and dispatches to listeners."""
        text = str(body.get("text", "")).strip()
        sender = str(body.get("sender", "operator")).strip()
        now = time.time()

        if not text:
            return {"status": "error", "message": "Empty message"}

        msg_obj = {
            "id": f"msg-{int(now * 1000)}",
            "sender": sender,
            "text": text,
            "timestamp": now,
            "is_user": True,
        }
        with self._lock:
            self._chat_history.append(msg_obj)
            if len(self._chat_history) > 100:
                self._chat_history.pop(0)

        # Notify chat callbacks (e.g. node -> mothership link)
        with self._lock:
            for cb in self._chat_callbacks:
                try:
                    cb(sender, text, body)
                except Exception:
                    pass

        return {
            "status": "ok",
            "message_id": msg_obj["id"],
            "reply": "Message received by node security stream.",
        }

    def _handle_chat_history(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        with self._lock:
            return {"status": "ok", "history": list(self._chat_history)}

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

    def on_chat_message(self, callback: Callable[[str, str, Dict[str, Any]], None]) -> None:
        """Subscribes callback to incoming chat messages from Wingman client."""
        with self._lock:
            self._chat_callbacks.append(callback)

    def on_auth_request(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribes callback to incoming zero-trust browser connection requests."""
        def _wrapper(sess: WingmanSession) -> None:
            callback({
                "auth_req_id": sess.session_id,
                "session_id": sess.session_id,
                "node_id": self.node_id,
                "client_ip": sess.client_ip,
                "user_agent": sess.user_agent,
                "device_id": sess.device_id,
                "timestamp": sess.created_at,
                "status": sess.status,
            })
        self.security.on_pending_session(_wrapper)

    def _handle_auth_status(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        req_id = query.get("req_id", [""])[0] or query.get("session_id", [""])[0]
        sess = self.security.get_session(req_id)
        if sess:
            return {
                "status": "approved" if sess.status == "authorized" else sess.status,
                "token": sess.token if sess.status == "authorized" else "",
                "auth_req_id": sess.session_id,
                "trusted": self.security.is_device_trusted(sess.device_id),
            }
        return {"status": "unknown", "error": f"Request {req_id} not found"}

    def _handle_verify_passkey(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict):
            return {"status": "error", "valid": False}
        passkey = str(body.get("passkey", "")).strip()
        sess_id = body.get("session_id") or body.get("prompt_id") or ""
        from gemini_app.vault import is_vault_configured, verify_vault_passkey
        valid = verify_vault_passkey(passkey) if is_vault_configured() else False
        if valid and sess_id:
            self.resolve_auth_request(sess_id, decision="accept")
        return {"status": "ok" if valid else "invalid", "valid": valid}

    def resolve_auth_request(self, auth_req_id: str, decision: str = "accept", trust: bool = False) -> Dict[str, Any]:
        """Resolves an incoming zero-trust session request from the operator or Mothership."""
        accepted = decision in ("accept", "trust")
        sess = self.security.authorize_session(auth_req_id, trust_device=trust) if accepted else self.security.deny_session(auth_req_id)
        if sess:
            ev_name = "auth_approved" if accepted else "auth_denied"
            self.engine.broadcast_event(ev_name, {
                "auth_req_id": auth_req_id,
                "token": sess.token if accepted else "",
                "status": "approved" if accepted else "denied",
            })
            return {
                "status": "approved" if accepted else "denied",
                "token": sess.token if accepted else "",
                "auth_req_id": auth_req_id,
            }
        return {"status": "error", "error": f"Session '{auth_req_id}' not found"}

    def prompt_passkey(self, reason: str = "Authorize Bilateral Homebase Message", prompt_id: Optional[str] = None) -> str:
        """Pushes a secure Homebase passkey authentication prompt card to Wingman."""
        p_id = prompt_id or f"pk-{secrets.token_hex(6)}"
        payload = {
            "prompt_id": p_id,
            "reason": reason,
            "timestamp": time.time(),
        }
        self.engine.broadcast_event("passkey_prompt", payload)
        return p_id

    def authorize_session(self, session_id: str, accepted: bool = True, trust_device: bool = False) -> Dict[str, Any]:
        """Approves or denies a pending session via Mothership command or operator action."""
        if accepted:
            sess = self.security.authorize_session(session_id, trust_device=trust_device)
            if sess:
                self.engine.broadcast_event("session_authorized", {
                    "session_id": session_id,
                    "token": sess.token,
                    "status": "authorized",
                })
                return {"status": "ok", "session_id": session_id, "token": sess.token}
            return {"status": "error", "error": f"Session '{session_id}' not found"}
        else:
            self.security.deny_session(session_id)
            self.engine.broadcast_event("session_denied", {
                "session_id": session_id,
                "status": "denied",
            })
            return {"status": "ok", "session_id": session_id, "action": "denied"}

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

    def push_chat_message(self, sender: str, text: str, is_user: bool = False) -> str:
        """Pushes a chat message bubble to all connected Wingman browsers in Chat mode."""
        msg_id = f"msg-{int(time.time() * 1000)}"
        msg_obj = {
            "id": msg_id,
            "sender": sender,
            "text": text,
            "timestamp": time.time(),
            "is_user": is_user,
        }
        with self._lock:
            self._chat_history.append(msg_obj)
            if len(self._chat_history) > 100:
                self._chat_history.pop(0)

        self.engine.broadcast_event("chat_message", msg_obj)
        return msg_id

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
