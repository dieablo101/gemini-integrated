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
        self._recent_cards: List[Dict[str, Any]] = [
            {
                "id": "screen-capture-card",
                "title": "🖥️ iPad Screen & Camera Capture",
                "content": "On iPadOS, Apple requires selecting 'Photo Library' to pick a screenshot. Alternatively, take an iPad screenshot (Top Button + Volume Up) and tap 'Sync Latest Screenshot'.",
                "actions": [
                    {"label": "🖼️ Pick Screenshot (Photos)", "action": "screen_capture", "style": "primary"},
                    {"label": "⚡ Sync Latest Saved Screenshot", "action": "sync_latest_screenshot", "style": "secondary"},
                    {"label": "📸 Snap Front Camera", "action": "camera_webrtc", "style": "secondary"},
                ],
                "accent": True,
                "timestamp": time.time(),
            },
            {
                "id": "camera-shutter",
                "title": "📸 Screen-Side Camera Capture",
                "content": "Capture a live photo from the iPad TrueDepth front camera.",
                "actions": [
                    {"label": "📸 Snap Front Camera", "action": "camera_webrtc", "style": "primary"},
                    {"label": "📷 iOS Viewfinder Shutter", "action": "camera_native", "style": "secondary"},
                ],
                "accent": False,
                "timestamp": time.time(),
            },
        ]
        self._chat_history: List[Dict[str, Any]] = []
        self._local_vitals: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._passkey_verifier: Optional[Callable[[str], bool]] = None
        self._chat_history_fetcher: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self.boot_id = secrets.token_hex(8)
        self.mothership_boot_id: Optional[str] = None
        self.maintenance_mode: bool = False

        self._setup_routes()

    def set_maintenance_mode(self, active: bool, reason: str = "") -> None:
        """Enables or releases targeted Wingman maintenance lockout during code updates or reboots."""
        self.maintenance_mode = active
        msg = reason or (
            "Wingman maintenance in progress — Mothership updates underway. Reconnection paused until release."
            if active else ""
        )
        self.engine.broadcast_event("wingman_maintenance", {
            "active": active,
            "message": msg,
            "timestamp": time.time(),
        })

    def on_mothership_reboot(self, new_boot_id: str) -> None:
        """Handles Mothership restart by invalidating all one-time (unpaired) sessions and resetting epoch."""
        self.mothership_boot_id = new_boot_id
        # Invalidate unpaired sessions while keeping active gate connections in pending state
        self.security.prune_stale_sessions(max_pending_age=45.0, invalidate_unpaired=True)
        # Immediately re-notify any active pending sessions so Mothership receives prompt without user reload
        now = time.time()
        with self.security._lock:
            for s in list(self.security.sessions.values()):
                if s.status == "pending":
                    s._last_notified = now
                    for cb in list(self.security._on_pending_session_callbacks):
                        try:
                            cb(s)
                        except Exception:
                            pass
        self.engine.broadcast_event("mothership_rebooted", {
            "mothership_boot_id": new_boot_id,
            "timestamp": time.time(),
        })

    def set_passkey_verifier(self, verifier: Callable[[str], bool]) -> None:
        """Sets external passkey verification function (e.g. delegated Mothership check for satellites)."""
        self._passkey_verifier = verifier

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
        self.engine.register_get("/applet/wingman/cards", self._handle_cards_history)

        # Telemetry & HUD Stream
        self.engine.register_get("/applet/wingman/telemetry", self._handle_telemetry)

        # Camera photo capture backhaul
        self.engine.register_post("/applet/wingman/photo", self._handle_photo)

        # Screenshots discovery & direct sync
        self.engine.register_get("/applet/wingman/latest_screenshot", self._handle_latest_screenshot)
        self.engine.register_post("/applet/wingman/latest_screenshot", self._handle_latest_screenshot)

        # Bilateral Chat Stream
        self.engine.register_post("/applet/wingman/chat", self._handle_chat)
        self.engine.register_get("/applet/wingman/chat_history", self._handle_chat_history)

        # WebAuthn response
        self.engine.register_post("/applet/wingman/webauthn_response", self._handle_biometric_response)

        # Satellite Setup Portal & APK Downloads
        self.engine.register_get("/setup", self._handle_portal)
        self.engine.register_get("/portal", self._handle_portal)
        self.engine.register_get("/cmd", self._handle_portal_cmd)
        self.engine.register_get("/download/termux", self._handle_download_termux)
        self.engine.register_get("/download/termux-api", self._handle_download_termux_api)
        self.engine.register_get("/download/termux-boot", self._handle_download_termux_boot)

    def _handle_portal(self, handler: Any, query: Dict[str, List[str]]) -> tuple[int, str, str]:
        from gemini_app.fleet.portal import HTML_PAGE
        return (200, HTML_PAGE, "text/html; charset=utf-8")

    def _handle_portal_cmd(self, handler: Any, query: Dict[str, List[str]]) -> tuple[int, str, str]:
        from gemini_app.fleet.portal import BOOTSTRAP_CMD
        return (200, BOOTSTRAP_CMD, "text/plain; charset=utf-8")

    def _serve_apk(self, handler: Any, apk_path: str, filename: str) -> None:
        import os
        if not os.path.exists(apk_path):
            handler.send_response(404)
            handler.send_header("Content-Type", "text/plain")
            handler.end_headers()
            handler.wfile.write(b"APK not found")
            return
        size = os.path.getsize(apk_path)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/vnd.android.package-archive")
        handler.send_header("Content-Length", str(size))
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        handler.end_headers()
        with open(apk_path, "rb") as f:
            while chunk := f.read(65536):
                handler.wfile.write(chunk)

    def _handle_download_termux(self, handler: Any, query: Dict[str, List[str]]) -> None:
        from gemini_app.fleet.portal import TERMUX_APK
        self._serve_apk(handler, TERMUX_APK, "Termux_v0.118.3_arm64.apk")

    def _handle_download_termux_api(self, handler: Any, query: Dict[str, List[str]]) -> None:
        from gemini_app.fleet.portal import API_APK
        self._serve_apk(handler, API_APK, "Termux_API_v0.53.0.apk")

    def _handle_download_termux_boot(self, handler: Any, query: Dict[str, List[str]]) -> None:
        from gemini_app.fleet.portal import BOOT_APK
        self._serve_apk(handler, BOOT_APK, "Termux_Boot_v0.8.1.apk")

    def _handle_index(self, handler: Any, query: Dict[str, List[str]]) -> str:
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        try:
            from gemini_app.fleet.telemetry import get_local_lan_ip
            device_ip = client_ip if client_ip not in ("127.0.0.1", "::1", "localhost") else (get_local_lan_ip() or "127.0.0.1")
            import importlib
            from gemini_app.webapplet.applets.wingman import ui as wingman_ui
            importlib.reload(wingman_ui)
            return wingman_ui.get_wingman_html(
                port=self.engine.port,
                node_id=self.node_id,
                client_ip=device_ip,
                device_ip=device_ip,
            )
        except Exception:
            from gemini_app.fleet.telemetry import get_local_lan_ip
            device_ip = client_ip if client_ip not in ("127.0.0.1", "::1", "localhost") else (get_local_lan_ip() or "127.0.0.1")
            return get_wingman_html(
                port=self.engine.port,
                node_id=self.node_id,
                client_ip=device_ip,
                device_ip=device_ip,
            )

    def _handle_ping(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        uptime_sec = 0.0
        try:
            from gemini_app.fleet.telemetry import get_system_uptime
            uptime_sec = round(get_system_uptime(), 1)
        except Exception:
            pass
        return {
            "status": "pong",
            "time": time.time(),
            "engine": self.engine.name,
            "node_id": self.node_id,
            "boot_id": self.boot_id,
            "mothership_boot_id": self.mothership_boot_id,
            "maintenance": self.maintenance_mode,
            "client_count": self.client_count,
            "uptime_seconds": uptime_sec,
        }

    def _extract_token_and_device(self, handler: Any, query: Dict[str, List[str]]) -> tuple[str, str, str]:
        token = ""
        device_id = ""
        session_id = ""
        # Check headers
        if hasattr(handler, "headers"):
            token = handler.headers.get("X-Wingman-Token", "")
            device_id = handler.headers.get("X-Wingman-Device", "")
            session_id = handler.headers.get("X-Wingman-Session", "")
            if not token:
                auth_hdr = handler.headers.get("Authorization", "")
                if auth_hdr.lower().startswith("bearer "):
                    token = auth_hdr[7:].strip()
        # Fallback to query
        if not token and "token" in query:
            token = query["token"][0]
        if not device_id and "device" in query:
            device_id = query["device"][0]
        if not session_id and "session_id" in query:
            session_id = query["session_id"][0]
        elif not session_id and "session" in query:
            session_id = query["session"][0]
        return token, device_id, session_id

    def _handle_session_check(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        user_agent = handler.headers.get("User-Agent", "") if hasattr(handler, "headers") else ""
        token, device_id, session_id = self._extract_token_and_device(handler, query)

        if self.maintenance_mode:
            return {
                "session_id": session_id or "maint",
                "authenticated": False,
                "status": "maintenance",
                "maintenance": True,
                "message": "Wingman maintenance in progress — Mothership updates underway. Reconnection paused until release.",
                "boot_id": self.boot_id,
                "mothership_boot_id": self.mothership_boot_id,
                "node_id": self.node_id,
            }

        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        session = self.security.create_or_resume_session(
            client_ip=client_ip,
            user_agent=user_agent,
            device_id=device_id,
            existing_token=token,
            existing_session_id=session_id,
            is_loopback=is_loopback,
        )

        from gemini_app.fleet.telemetry import get_local_lan_ip
        device_ip = client_ip if not is_loopback else (get_local_lan_ip() or "127.0.0.1")

        is_trusted = bool(session.device_id) and self.security.is_device_trusted(session.device_id)
        is_paired = is_trusted or getattr(session, "is_paired", False)
        return {
            "session_id": session.session_id,
            "authenticated": (session.status == "authorized"),
            "status": session.status,
            "is_unlocked": session.is_unlocked,
            "is_paired": is_paired,
            "token": session.token if session.status == "authorized" else "",
            "mode": session.current_mode,
            "device_id": session.device_id,
            "client_ip": client_ip,
            "device_ip": device_ip,
            "node_id": self.node_id,
            "trusted": is_trusted,
            "boot_id": self.boot_id,
            "mothership_boot_id": self.mothership_boot_id,
            "maintenance": False,
        }

    def _handle_passkey_auth(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        sess_id = body.get("session_id", "")
        token, dev_id, _ = self._extract_token_and_device(handler, query)
        if not sess_id and token:
            s = self.security.get_session_by_token(token)
            if s:
                sess_id = s.session_id
        if not sess_id:
            client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
            s = self.security.create_or_resume_session(client_ip=client_ip, device_id=dev_id)
            sess_id = s.session_id

        passkey = body.get("passkey", "")
        trust_device = bool(body.get("trust_device", False))

        ok, token_out, msg = self.security.verify_passkey_and_authorize(
            session_id=sess_id,
            passkey=passkey,
            trust_device=trust_device,
            verifier=self._passkey_verifier,
        )
        if ok:
            sess = self.security.get_session(sess_id)
            if sess:
                sess.is_unlocked = True
            # Broadcast auth approved to SSE clients
            self.engine.broadcast_event("session_authorized", {
                "session_id": sess_id,
                "token": token_out,
                "status": "authorized",
            })
            return {"status": "ok", "token": token_out, "message": msg}
        return {"status": "error", "message": msg}

    def _handle_action(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        card_id = body.get("card_id", "")
        action = body.get("action", "")
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        token, _, _ = self._extract_token_and_device(handler, query)
        sess = self.security.get_session_by_token(token) if token else None

        if self.security.require_pairing:
            if token and not sess:
                return {"status": "error", "session_locked": True, "reauth_required": True, "message": "Session expired or Mothership rebooted. Re-authorization required."}
            if not sess or sess.status != "authorized":
                return {"status": "error", "session_locked": True, "reauth_required": True, "message": "Session is awaiting Mothership console authorization."}
            if not sess.is_unlocked:
                return {"status": "error", "session_locked": True, "message": "Session is locked. Passkey unlock required."}

        with self._lock:
            for cb in self._action_callbacks:
                try:
                    cb(card_id, action, body)
                except Exception:
                    pass
        return {"status": "ok", "card_id": card_id, "action": action}

    def _handle_cards_history(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        """Returns recent cards for initial UI hydration."""
        with self._lock:
            return {"status": "ok", "cards": list(self._recent_cards)}

    def update_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Updates internal telemetry cache from satellite/mothership stream."""
        with self._lock:
            if not hasattr(self, "_telemetry"):
                self._telemetry = {}
            if isinstance(telemetry, dict):
                self._telemetry.update(telemetry)

    def update_local_vitals(self, vitals: Dict[str, Any]) -> None:
        """Updates local hardware vitals directly from satellite node telemetry."""
        with self._lock:
            if not hasattr(self, "_local_vitals"):
                self._local_vitals = {}
            if isinstance(vitals, dict):
                self._local_vitals.update(vitals)

    def _handle_telemetry(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        """Returns live cognitive telemetry and vitals for Wingman HUD view."""
        with self._lock:
            telem = dict(getattr(self, "_telemetry", {}))
            local_v = dict(getattr(self, "_local_vitals", {}))

        if not local_v:
            try:
                from gemini_app.fleet.satellite import collect_telemetry as sat_collect
                local_v = sat_collect()
            except Exception:
                pass

        if not telem:
            try:
                from gemini_app.fleet.telemetry import collect_mothership_telemetry
                telem = collect_mothership_telemetry()
            except Exception:
                telem = {}

        # Merge local vitals so that HUD cards always have access to node vitals
        if local_v:
            telem["local_vitals"] = local_v
            # If root vitals are missing, populate from local vitals
            if "mem_total_mb" not in telem and "mem_total_mb" in local_v:
                telem["mem_total_mb"] = local_v.get("mem_total_mb")
                telem["mem_avail_mb"] = local_v.get("mem_avail_mb")
            if "disk_free_gb" not in telem and "disk_free_gb" in local_v:
                telem["disk_free_gb"] = local_v.get("disk_free_gb")
                telem["disk_total_gb"] = local_v.get("disk_total_gb")
            if "git_commit" not in telem and "git_commit" in local_v:
                telem["git_commit"] = local_v.get("git_commit")
                telem["git_branch"] = local_v.get("git_branch")
            if "battery" not in telem and "battery" in local_v:
                telem["battery"] = local_v.get("battery")
            if "is_ish" in local_v:
                telem["is_ish"] = local_v["is_ish"]
            if "is_termux" in local_v:
                telem["is_termux"] = local_v["is_termux"]

        # Ensure root vitals/git fallback from mothership vitals/git if present
        mv = telem.get("vitals")
        if isinstance(mv, dict):
            if "mem_total_mb" not in telem and "mem_total_mb" in mv:
                telem["mem_total_mb"] = mv["mem_total_mb"]
                telem["mem_avail_mb"] = max(0, mv["mem_total_mb"] - mv.get("mem_used_mb", 0))
            if "disk_free_gb" not in telem and "disk_free_gb" in mv:
                telem["disk_free_gb"] = mv["disk_free_gb"]
                telem["disk_total_gb"] = mv.get("disk_total_gb", 1)
        mg = telem.get("git")
        if isinstance(mg, dict):
            if "git_commit" not in telem and "commit" in mg:
                telem["git_commit"] = mg["commit"]
            if "git_branch" not in telem and "branch" in mg:
                telem["git_branch"] = mg["branch"]

        if "nodes" not in telem and "satellites" in telem:
            telem["nodes"] = telem["satellites"]

        # Ensure uptime_seconds is present
        if "uptime_seconds" not in telem:
            if "uptime_seconds" in local_v:
                telem["uptime_seconds"] = local_v["uptime_seconds"]
            else:
                try:
                    from gemini_app.fleet.telemetry import get_system_uptime
                    telem["uptime_seconds"] = round(get_system_uptime(), 1)
                except Exception:
                    telem["uptime_seconds"] = 0.0

        if "ping_ms" not in telem:
            if self.node_id == "mothership":
                telem["ping_ms"] = 0.0
            elif "ping_ms" in local_v:
                telem["ping_ms"] = local_v.get("ping_ms")

        return {"status": "ok", "telemetry": telem, "timestamp": time.time()}

    def _handle_photo(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        """Receives camera photo payload from connected Wingman browser."""
        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        data_b64 = body.get("data_b64") or body.get("image_b64") or ""
        if data_b64.startswith("data:image"):
            data_b64 = data_b64.split(",", 1)[-1]

        if not data_b64:
            return {"status": "error", "message": "No image data received"}

        import base64
        from pathlib import Path
        from gemini_app.config import GEMINI_HOME
        try:
            raw_bytes = base64.b64decode(data_b64)
        except Exception as exc:
            return {"status": "error", "message": f"Base64 decode failed: {exc}"}

        method = body.get("method", "camera")
        is_screen = ("screenshot" in method or method == "get_display_media")
        prefix = "wingman_screenshot" if is_screen else "wingman_camera"
        fname = f"{prefix}_{self.node_id}_{int(time.time())}.jpg"
        dest_dir = GEMINI_HOME / "screenshots"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / fname
        dest_file.write_bytes(raw_bytes)

        ocr_text = ""
        try:
            from gemini_app.fleet.media_ocr import extract_screen_text
            ocr_text = extract_screen_text(dest_file)
        except Exception:
            pass

        card_id = body.get("card_id", "camera-shutter")
        with self._lock:
            for cb in self._action_callbacks:
                try:
                    cb(card_id, "photo_captured", {
                        "filename": fname,
                        "data_b64": data_b64,
                        "size_bytes": len(raw_bytes),
                        "local_path": str(dest_file),
                        "node_id": self.node_id,
                        "facing": body.get("facing", "screen" if is_screen else "user"),
                        "method": method,
                        "ocr_text": ocr_text,
                    })
                except Exception:
                    pass

        return {
            "status": "ok",
            "filename": fname,
            "size_bytes": len(raw_bytes),
            "local_path": str(dest_file),
            "message": "Photo synchronized with node filesystem",
        }

    def _handle_latest_screenshot(self, handler: Any, query: Dict[str, List[str]], body: Any = None) -> Dict[str, Any]:
        """Discovers and returns the latest screenshot from local node storage (/mnt/ipad, ~/.gemini/screenshots)."""
        import base64
        from pathlib import Path
        from gemini_app.fleet.satellite import find_node_screenshots

        screenshots = find_node_screenshots(limit=5)
        if not screenshots:
            return {
                "status": "not_found",
                "message": "No screenshots found on iPad storage yet. Take an iPad screenshot (Top Button + Volume Up) first!",
            }

        top = screenshots[0]
        p = Path(top["path"])
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"Screenshot file missing: {top.get('filename')}"}

        try:
            raw_bytes = p.read_bytes()
        except Exception as exc:
            return {"status": "error", "message": f"Failed to read screenshot: {exc}"}

        ocr_text = ""
        try:
            from gemini_app.fleet.media_ocr import extract_screen_text
            ocr_res = extract_screen_text(p)
            ocr_text = ocr_res.get("raw_text", "") if isinstance(ocr_res, dict) else str(ocr_res)
        except Exception:
            pass

        data_b64 = base64.b64encode(raw_bytes).decode("ascii")
        ext = p.suffix.lower().lstrip(".") or "jpg"
        mime = f"image/{ext}" if ext in ("png", "jpeg", "webp") else "image/jpeg"
        data_uri = f"data:{mime};base64,{data_b64}"

        card_id = "screen-capture-card"
        with self._lock:
            for cb in self._action_callbacks:
                try:
                    cb(card_id, "photo_captured", {
                        "filename": p.name,
                        "data_b64": data_b64,
                        "size_bytes": len(raw_bytes),
                        "local_path": str(p),
                        "node_id": self.node_id,
                        "facing": "screen",
                        "method": "node_filesystem_sync",
                        "ocr_text": ocr_text,
                    })
                except Exception:
                    pass

        return {
            "status": "ok",
            "filename": p.name,
            "path": str(p),
            "size_bytes": len(raw_bytes),
            "mtime": top.get("mtime", 0.0),
            "ocr_text": ocr_text,
            "data_b64": data_uri,
        }

    def _handle_chat(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        """Receives user chat message from Wingman UI and dispatches to listeners."""
        text = str(body.get("text", "")).strip()
        sender = str(body.get("sender", "operator")).strip()
        attachment = body.get("attachment")
        now = time.time()

        if not text and not attachment:
            return {"status": "error", "message": "Empty message"}

        if not text and attachment:
            kind_label = "Screenshot" if (isinstance(attachment, dict) and "screen" in str(attachment.get("kind", ""))) else "Photo"
            text = f"📷 [{kind_label}]"

        client_ip = handler.client_address[0] if hasattr(handler, "client_address") else "127.0.0.1"
        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        token, _, _ = self._extract_token_and_device(handler, query)
        sess = self.security.get_session_by_token(token) if token else None

        if self.security.require_pairing:
            if token and not sess:
                return {"status": "error", "session_locked": True, "reauth_required": True, "message": "Session expired or Mothership rebooted. Re-authorization required."}
            if not sess or sess.status != "authorized":
                return {"status": "error", "session_locked": True, "reauth_required": True, "message": "Session is awaiting Mothership console authorization."}
            if not sess.is_unlocked:
                return {"status": "error", "session_locked": True, "message": "Session is locked. Passkey unlock required."}

        saved_attachment = None
        if isinstance(attachment, dict) and attachment.get("data_b64"):
            try:
                import base64
                from pathlib import Path
                from gemini_app.config import GEMINI_HOME
                raw_b64 = str(attachment["data_b64"])
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                raw_bytes = base64.b64decode(raw_b64)
                kind = str(attachment.get("kind", "screenshot"))
                prefix = "wingman_screenshot" if "screen" in kind else "wingman_photo"
                dest_dir = GEMINI_HOME / "screenshots"
                dest_dir.mkdir(parents=True, exist_ok=True)
                fname = f"{prefix}_{self.node_id}_{int(now)}.jpg"
                dest_file = dest_dir / fname
                dest_file.write_bytes(raw_bytes)

                ocr_text = ""
                try:
                    from gemini_app.fleet.media_ocr import extract_screen_text
                    ocr_res = extract_screen_text(dest_file)
                    ocr_text = ocr_res.get("raw_text", "") if isinstance(ocr_res, dict) else str(ocr_res)
                except Exception:
                    pass

                saved_attachment = {
                    "filename": fname,
                    "original_name": attachment.get("filename", fname),
                    "size_bytes": len(raw_bytes),
                    "local_path": str(dest_file),
                    "ocr_text": ocr_text,
                    "data_b64": attachment.get("data_b64", ""),
                    "kind": kind,
                }
            except Exception as exc:
                logger.warning(f"Failed to process chat attachment: {exc}")

        msg_id_val = str(body.get("id") or body.get("msg_id") or f"msg-{secrets.token_hex(4)}-{int(now * 1000)}").strip()
        dev_id = str(body.get("device_id") or handler.headers.get("X-Wingman-Device", "")).strip()
        dev_label = str(body.get("device_label") or body.get("device_name") or "").strip()
        msg_obj = {
            "id": msg_id_val,
            "sender": sender,
            "text": text,
            "timestamp": now,
            "is_user": True,
            "origin_device": dev_id,
            "origin_label": dev_label,
            "attachment": saved_attachment or attachment,
        }
        if text.lower() == "/clear":
            self.clear_chat()
        else:
            with self._lock:
                if not any(m.get("id") == msg_id_val for m in self._chat_history):
                    self._chat_history.append(msg_obj)
                    self._chat_history.sort(key=lambda x: x.get("timestamp", 0.0))
                    if len(self._chat_history) > 50:
                        self._chat_history.pop(0)

        # Broadcast chat message to other connected Wingman clients via SSE
        if text.lower() != "/clear":
            self.engine.broadcast_event("chat_message", msg_obj)

        # Notify chat callbacks (e.g. node -> mothership link)
        with self._lock:
            for cb in self._chat_callbacks:
                try:
                    cb(sender, text, {**body, "attachment": saved_attachment or attachment})
                except Exception:
                    pass

        return {
            "status": "ok",
            "message_id": msg_obj["id"],
            "timestamp": msg_obj["timestamp"],
            "reply": "Bilateral chat cleared across fleet." if text.lower() == "/clear" else "Transmitted to Mothership — awaiting Gemini reply...",
        }

    def _handle_chat_history(self, handler: Any, query: Dict[str, List[str]]) -> Dict[str, Any]:
        with self._lock:
            if getattr(self, "_chat_history_fetcher", None):
                try:
                    fetched = self._chat_history_fetcher()
                    if isinstance(fetched, list):
                        fetched_ids = {m.get("id") for m in fetched if m.get("id")}
                        now = time.time()
                        merged = list(fetched)
                        for m in self._chat_history:
                            m_id = m.get("id")
                            m_ts = m.get("timestamp", 0.0)
                            if m_id and m_id not in fetched_ids and (now - m_ts < 20.0 or m_ts > now):
                                merged.append(m)
                        merged.sort(key=lambda x: x.get("timestamp", 0.0))
                        self._chat_history = merged[-50:]
                except Exception:
                    pass
            self._chat_history.sort(key=lambda x: x.get("timestamp", 0.0))
            return {"status": "ok", "history": list(self._chat_history[-50:])}

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
        dev_id = query.get("device_id", [""])[0] or (handler.headers.get("X-Wingman-Device", "") if hasattr(handler, "headers") else "")
        sess = self.security.get_session(req_id)
        if not sess and dev_id:
            for s in list(self.security.sessions.values()):
                if s.device_id == dev_id and s.status in ("authorized", "pending"):
                    sess = s
                    break
        if not sess and req_id:
            for s in list(self.security.sessions.values()):
                if s.session_id.startswith(req_id) or req_id.startswith(s.session_id):
                    sess = s
                    break
        if sess:
            now = time.time()
            sess.last_seen = now
            if sess.status == "pending":
                should_notify = (now - getattr(sess, "_last_notified", 0.0)) > 4.0
                if should_notify:
                    sess._last_notified = now
                    for cb in list(self.security._on_pending_session_callbacks):
                        try:
                            cb(sess)
                        except Exception:
                            pass
            is_trusted = bool(sess.device_id) and self.security.is_device_trusted(sess.device_id)
            is_paired = is_trusted or getattr(sess, "is_paired", False)
            return {
                "status": "approved" if sess.status == "authorized" else sess.status,
                "token": sess.token if sess.status == "authorized" else "",
                "auth_req_id": sess.session_id,
                "trusted": is_trusted,
                "is_paired": is_paired,
            }
        return {"status": "unknown", "needs_reauth": True, "error": f"Request {req_id} not found"}

    def _handle_verify_passkey(self, handler: Any, query: Dict[str, List[str]], body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict):
            return {"status": "error", "valid": False}
        passkey = str(body.get("passkey", "")).strip()
        sess_id = body.get("session_id") or body.get("prompt_id") or ""
        token = body.get("session_token", "")

        if self._passkey_verifier:
            try:
                valid = bool(self._passkey_verifier(passkey))
            except Exception:
                valid = False
        else:
            from gemini_app.fleet.wingman_auth import verify_homebase_passkey
            valid = verify_homebase_passkey(passkey)

        if valid:
            sess = None
            if sess_id:
                sess = self.security.get_session(sess_id)
            if not sess and token:
                sess = self.security.get_session_by_token(token)
            if sess:
                sess.is_unlocked = True
        return {
            "status": "ok" if valid else "invalid",
            "valid": valid,
            "token": sess.token if (valid and sess) else token,
            "message": "Authenticated successfully" if valid else "Invalid Homebase vault passkey.",
        }

    def resolve_auth_request(self, auth_req_id: str, decision: str = "accept", trust: bool = False) -> Dict[str, Any]:
        """Resolves an incoming zero-trust session request from the operator or Mothership."""
        accepted = decision in ("accept", "trust", "pair")
        trust_device = trust or (decision in ("trust", "pair"))
        sess = self.security.authorize_session(auth_req_id, trust_device=trust_device) if accepted else self.security.deny_session(auth_req_id)
        if sess:
            is_trusted = bool(sess.device_id) and (trust_device or self.security.is_device_trusted(sess.device_id))
            ev_name = "auth_approved" if accepted else "auth_denied"
            self.engine.broadcast_event(ev_name, {
                "auth_req_id": auth_req_id,
                "session_id": auth_req_id,
                "token": sess.token if accepted else "",
                "status": "approved" if accepted else "denied",
                "is_paired": is_trusted if accepted else False,
            })
            return {
                "status": "approved" if accepted else "denied",
                "token": sess.token if accepted else "",
                "auth_req_id": auth_req_id,
                "is_paired": is_trusted if accepted else False,
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
                is_trusted = bool(sess.device_id) and (trust_device or self.security.is_device_trusted(sess.device_id))
                auth_payload = {
                    "session_id": session_id,
                    "auth_req_id": session_id,
                    "token": sess.token,
                    "status": "authorized",
                    "is_paired": is_trusted,
                }
                self.engine.broadcast_event("session_authorized", auth_payload)
                self.engine.broadcast_event("auth_approved", auth_payload)
                return {"status": "ok", "session_id": session_id, "token": sess.token, "is_paired": is_trusted}
            return {"status": "error", "error": f"Session '{session_id}' not found"}
        else:
            self.security.deny_session(session_id)
            self.engine.broadcast_event("session_denied", {
                "session_id": session_id,
                "status": "denied",
            })
            self.engine.broadcast_event("auth_denied", {
                "auth_req_id": session_id,
                "session_id": session_id,
                "status": "denied",
            })
            return {"status": "ok", "session_id": session_id, "action": "denied"}

    def is_browser_open(self) -> bool:
        """Returns True if a browser tab is currently open and connected to Wingman."""
        if self.engine.is_client_active(window_seconds=25.0):
            return True
        now = time.time()
        if hasattr(self, "security"):
            with self.security._lock:
                for s in self.security.sessions.values():
                    if (now - getattr(s, "last_seen", 0.0)) < 30.0:
                        return True
        return False

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

    def clear_chat(self) -> None:
        """Clears local chat history and notifies connected browsers to clear chat feed."""
        with self._lock:
            self._chat_history.clear()
        self.engine.broadcast_event("clear_chat", {"timestamp": time.time()})
        self.engine.broadcast_event("chat_clear", {"timestamp": time.time()})

    def push_chat_message(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        msg_id: str = "",
        timestamp: Optional[float] = None,
        origin_device: str = "",
        origin_label: str = "",
        attachment: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Pushes a chat message bubble to all connected Wingman browsers in Chat mode."""
        msg_id_val = msg_id or f"msg-{secrets.token_hex(4)}-{int(time.time() * 1000)}"
        ts = timestamp if (isinstance(timestamp, (int, float)) and timestamp > 0) else time.time()
        msg_obj = {
            "id": msg_id_val,
            "sender": sender,
            "text": text,
            "timestamp": ts,
            "is_user": is_user,
            "origin_device": origin_device,
            "origin_label": origin_label,
            "attachment": attachment,
        }
        with self._lock:
            if not any(m.get("id") == msg_id_val for m in self._chat_history):
                self._chat_history.append(msg_obj)
                self._chat_history.sort(key=lambda x: x.get("timestamp", 0.0))
                if len(self._chat_history) > 50:
                    self._chat_history.pop(0)

        self.engine.broadcast_event("chat_message", msg_obj)
        return msg_id_val

    def request_biometric(
        self,
        reason: str = "Authorize Operation",
        method: str = "facescan",
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Dispatches a WebAuthn or optical Face ID scan challenge to the open Wingman browser."""
        chal_id = f"chal-{secrets.token_hex(8)}"
        nonce = secrets.token_hex(16)
        ev = threading.Event()

        with self._lock:
            self._pending_biometrics[chal_id] = ev

        chal_payload = {
            "challenge_id": chal_id,
            "nonce": nonce,
            "reason": reason,
            "method": method,
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
