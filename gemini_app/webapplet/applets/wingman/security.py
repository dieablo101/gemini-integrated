"""Wingman Bilateral Zero-Trust Security & Session Gateway.

Provides pairing modals, challenge-response tokens, device fingerprinting,
trusted device persistence, and salted PBKDF2 passkey verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from gemini_app.config import VAULT_DIR


def get_trusted_devices_file() -> Path:
    """Returns path to ~/.gemini/vault/trusted_wingman_devices.json."""
    return VAULT_DIR / "trusted_wingman_devices.json"


@dataclass
class WingmanSession:
    """Represents an active or pending Wingman browser session."""

    session_id: str
    token: str
    client_ip: str
    user_agent: str = ""
    device_id: str = ""
    status: str = "pending"  # "pending", "authorized", "denied"
    is_unlocked: bool = False  # Action-gated session passkey status
    is_paired: bool = False  # Permanent device pairing status
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    current_mode: str = "work"  # "work" or "chat"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "token": self.token if self.status == "authorized" else "",
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "device_id": self.device_id,
            "status": self.status,
            "is_unlocked": self.is_unlocked,
            "is_paired": self.is_paired,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "current_mode": self.current_mode,
        }


class WingmanSecurity:
    """Manages zero-trust authorization, pairing modals, and PBKDF2 passkey gate."""

    def __init__(self, devices_file: Optional[Path] = None, require_pairing: bool = True) -> None:
        self.devices_file = devices_file or get_trusted_devices_file()
        self.require_pairing = require_pairing
        self.sessions: Dict[str, WingmanSession] = {}
        self.tokens_to_session: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._on_pending_session_callbacks: List[Callable[[WingmanSession], None]] = []
        self._load_trusted_devices()

    def _load_trusted_devices(self) -> Dict[str, Dict[str, Any]]:
        if not self.devices_file.is_file():
            return {}
        try:
            return json.loads(self.devices_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_trusted_devices(self, devices: Dict[str, Dict[str, Any]]) -> bool:
        try:
            self.devices_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.devices_file.write_text(json.dumps(devices, indent=2), encoding="utf-8")
            self.devices_file.chmod(0o600)
            return True
        except Exception:
            return False

    def is_device_trusted(self, device_id: str) -> bool:
        """Returns True if device ID / fingerprint has been permanently paired."""
        if not device_id or device_id in ("127.0.0.1", "::1", "localhost", "local"):
            return False
        devices = self._load_trusted_devices()
        return device_id in devices

    def trust_device(self, device_id: str, label: str = "", client_ip: str = "") -> bool:
        """Stores device in trusted paired devices registry."""
        if not device_id and not client_ip:
            return False
        if device_id in ("127.0.0.1", "::1", "localhost", "local"):
            device_id = ""
        if client_ip in ("127.0.0.1", "::1", "localhost", "local"):
            client_ip = ""
        if not device_id and not client_ip:
            return False
        with self._lock:
            devices = self._load_trusted_devices()
            entry = {
                "device_id": device_id or f"ip-{client_ip}",
                "label": label or f"Paired Satellite ({client_ip or device_id})",
                "client_ip": client_ip,
                "paired_at": time.time(),
                "last_used": time.time(),
            }
            if device_id:
                devices[device_id] = entry
            if client_ip:
                devices[client_ip] = entry
            return self._save_trusted_devices(devices)

    def revoke_device(self, device_id: str) -> bool:
        """Revokes a trusted device pairing."""
        with self._lock:
            devices = self._load_trusted_devices()
            if device_id in devices:
                del devices[device_id]
                self._save_trusted_devices(devices)
                # Sever any active sessions for this device
                for s in self.sessions.values():
                    if s.device_id == device_id:
                        s.status = "denied"
                return True
            return False

    def list_trusted_devices(self) -> List[Dict[str, Any]]:
        """Returns list of all trusted and paired devices."""
        devices = self._load_trusted_devices()
        return list(devices.values())

    def on_pending_session(self, callback: Callable[[WingmanSession], None]) -> None:
        """Registers callback fired when a new unauthenticated browser requests access."""
        self._on_pending_session_callbacks.append(callback)

    def create_or_resume_session(
        self,
        client_ip: str,
        user_agent: str = "",
        device_id: str = "",
        existing_token: str = "",
        existing_session_id: str = "",
        is_loopback: bool = False,
    ) -> WingmanSession:
        """Retrieves existing session by token, auto-authorizes trusted devices, or creates pending."""
        now = time.time()
        effective_device_id = device_id or f"dev-{hashlib.sha256(f'{client_ip}-{user_agent}'.encode('utf-8')).hexdigest()[:12]}"

        with self._lock:
            # 1. Check existing token for active authorized session
            if existing_token and existing_token in self.tokens_to_session:
                sess_id = self.tokens_to_session[existing_token]
                session = self.sessions.get(sess_id)
                if session and session.status == "authorized":
                    session.last_seen = now
                    return session

            device_trusted = bool(effective_device_id) and self.is_device_trusted(effective_device_id)

            # 2. Check if existing_session_id is already in sessions
            if existing_session_id and existing_session_id in self.sessions:
                cand = self.sessions[existing_session_id]
                match_dev = bool(effective_device_id and cand.device_id == effective_device_id)
                if match_dev or is_loopback:
                    cand.last_seen = now
                    if cand.status == "authorized":
                        return cand
                    elif cand.status == "denied":
                        return cand
                    elif cand.status == "pending":
                        if user_agent:
                            cand.user_agent = user_agent
                        should_notify = (now - getattr(cand, "_last_notified", 0.0)) > 3.0
                        if should_notify:
                            cand._last_notified = now
                            for cb in list(self._on_pending_session_callbacks):
                                try:
                                    cb(cand)
                                except Exception:
                                    pass
                        return cand

            # 3. If device is permanently trusted or require_pairing is False
            status = "authorized" if (device_trusted or not self.require_pairing) else "pending"

            # 4. If there is already an existing pending session for this device, reuse it!
            if status == "pending":
                matched_existing = None
                for cand in self.sessions.values():
                    if cand.status == "pending":
                        match_dev = bool(effective_device_id and cand.device_id == effective_device_id)
                        if match_dev:
                            matched_existing = cand
                            break

                if matched_existing:
                    matched_existing.last_seen = now
                    if user_agent:
                        matched_existing.user_agent = user_agent
                    should_notify = (now - getattr(matched_existing, "_last_notified", 0.0)) > 3.0
                    if should_notify:
                        matched_existing._last_notified = now
                    if should_notify:
                        for cb in list(self._on_pending_session_callbacks):
                            try:
                                cb(matched_existing)
                            except Exception:
                                pass
                    return matched_existing

            sess_id = existing_session_id or f"sess-{secrets.token_hex(8)}"
            tok = f"wmt-{secrets.token_urlsafe(32)}"
            session = WingmanSession(
                session_id=sess_id,
                token=tok,
                client_ip=client_ip,
                user_agent=user_agent,
                device_id=effective_device_id,
                status=status,
                is_unlocked=False,
                is_paired=device_trusted,
                created_at=now,
                last_seen=now,
            )
            session._last_notified = now

            self.sessions[sess_id] = session
            if status == "authorized":
                self.tokens_to_session[tok] = sess_id

        if status == "pending":
            for cb in list(self._on_pending_session_callbacks):
                try:
                    cb(session)
                except Exception:
                    pass

        return session

    def get_session(self, session_id: str) -> Optional[WingmanSession]:
        with self._lock:
            return self.sessions.get(session_id)

    def get_session_by_token(self, token: str) -> Optional[WingmanSession]:
        if not token:
            return None
        with self._lock:
            sess_id = self.tokens_to_session.get(token)
            if sess_id:
                s = self.sessions.get(sess_id)
                if s and s.status == "authorized":
                    s.last_seen = time.time()
                    return s
            return None

    def authorize_session(
        self,
        session_id: str,
        trust_device: bool = False,
        device_label: str = "",
    ) -> Optional[WingmanSession]:
        """Operator explicitly authorizes a pending session."""
        with self._lock:
            session = self.sessions.get(session_id)
            if not session and session_id:
                for cand in self.sessions.values():
                    if cand.session_id == session_id or cand.session_id.startswith(session_id):
                        session = cand
                        break
            if not session:
                pending_sessions = [s for s in self.sessions.values() if s.status == "pending"]
                if len(pending_sessions) == 1:
                    session = pending_sessions[0]
            if not session:
                return None
            session.status = "authorized"
            session.is_paired = trust_device
            session.last_seen = time.time()
            self.tokens_to_session[session.token] = session.session_id

        if trust_device and session.device_id:
            self.trust_device(session.device_id, label=device_label or f"Browser on {session.client_ip}", client_ip=session.client_ip)

        return session

    def deny_session(self, session_id: str) -> Optional[WingmanSession]:
        """Operator explicitly denies or revokes a session."""
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return None
            session.status = "denied"
            self.tokens_to_session.pop(session.token, None)
            return session

    def verify_passkey_and_authorize(
        self,
        session_id: str,
        passkey: str,
        trust_device: bool = False,
        verifier: Optional[Callable[[str], bool]] = None,
    ) -> tuple[bool, Optional[str], str]:
        """Verifies passkey strictly against Mothership/Vault salted PBKDF2 hash or custom verifier."""
        session = self.get_session(session_id)
        if not session:
            return False, None, "Session not found or expired"

        clean_passkey = passkey.strip()
        if not clean_passkey:
            return False, None, "Passkey cannot be empty"

        valid = False
        if verifier:
            try:
                valid = bool(verifier(clean_passkey))
            except Exception:
                valid = False
        else:
            from gemini_app.fleet.wingman_auth import verify_homebase_passkey
            valid = verify_homebase_passkey(clean_passkey)

        if not valid:
            return False, None, "Invalid Homebase vault passkey"

        # Authorized!
        self.authorize_session(session_id, trust_device=trust_device)
        session.is_unlocked = True
        return True, session.token, "Authenticated successfully"

    def prune_stale_sessions(
        self,
        max_pending_age: float = 45.0,
        max_inactive_age: float = 86400.0,
        invalidate_unpaired: bool = False,
    ) -> int:
        """Prunes orphaned pending sessions, expired unpaired sessions, and ancient inactive sessions."""
        now = time.time()
        pruned_count = 0
        with self._lock:
            to_remove = []
            for sid, sess in self.sessions.items():
                is_trusted = bool(sess.device_id) and self.is_device_trusted(sess.device_id)
                is_paired = is_trusted or getattr(sess, "is_paired", False)

                # Pending sessions where browser stopped polling or hasn't checked in
                if sess.status == "pending":
                    age = now - getattr(sess, "last_seen", sess.created_at)
                    if age > max_pending_age:
                        to_remove.append(sid)
                elif sess.status in ("denied", "expired"):
                    if (now - getattr(sess, "last_seen", sess.created_at)) > 60.0:
                        to_remove.append(sid)
                elif not is_paired:
                    # Unpaired accepted sessions: expire if browser closed or inactive > 180s
                    age = now - getattr(sess, "last_seen", sess.created_at)
                    if invalidate_unpaired:
                        # If browser is still actively connected (polling within 45s),
                        # downgrade to pending rather than destroying the session
                        if age < 45.0:
                            sess.status = "pending"
                            if sess.token:
                                self.tokens_to_session.pop(sess.token, None)
                                sess.token = ""
                            sess.is_unlocked = False
                            sess._last_notified = 0.0
                        else:
                            to_remove.append(sid)
                    elif age > 180.0:
                        to_remove.append(sid)
                else:
                    # Permanently paired sessions: persist up to max_inactive_age (e.g. 24h)
                    if (now - getattr(sess, "last_seen", sess.created_at)) > max_inactive_age:
                        to_remove.append(sid)

            for sid in to_remove:
                s = self.sessions.pop(sid, None)
                if s and s.token:
                    self.tokens_to_session.pop(s.token, None)
                pruned_count += 1

        return pruned_count

