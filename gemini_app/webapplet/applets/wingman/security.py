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
        if not device_id:
            return False
        devices = self._load_trusted_devices()
        return device_id in devices

    def trust_device(self, device_id: str, label: str = "", client_ip: str = "") -> bool:
        """Stores device in trusted paired devices registry."""
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
        is_loopback: bool = False,
    ) -> WingmanSession:
        """Retrieves existing session by token, auto-authorizes trusted devices, or creates pending."""
        now = time.time()
        with self._lock:
            # 1. Check existing token for active authorized session
            if existing_token and existing_token in self.tokens_to_session:
                sess_id = self.tokens_to_session[existing_token]
                session = self.sessions.get(sess_id)
                if session and session.status == "authorized":
                    session.last_seen = now
                    return session

            # 2. Check if device is permanently trusted
            device_trusted = (
                (bool(device_id) and self.is_device_trusted(device_id))
                or (bool(client_ip) and self.is_device_trusted(client_ip))
            )

            # If device is already trusted or require_pairing is False
            status = "authorized" if (device_trusted or not self.require_pairing) else "pending"

            sess_id = f"sess-{secrets.token_hex(8)}"
            tok = f"wmt-{secrets.token_urlsafe(32)}"
            session = WingmanSession(
                session_id=sess_id,
                token=tok,
                client_ip=client_ip,
                user_agent=user_agent,
                device_id=device_id or f"dev-{hashlib.sha256(f'{client_ip}-{user_agent}'.encode('utf-8')).hexdigest()[:12]}",
                status=status,
                is_unlocked=False,
                created_at=now,
                last_seen=now,
            )

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
            if not session:
                return None
            session.status = "authorized"
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
    ) -> tuple[bool, Optional[str], str]:
        """Verifies passkey against Mothership/Vault salted PBKDF2 hash and unlocks session."""
        from gemini_app.vault import is_vault_configured, verify_vault_passkey

        session = self.get_session(session_id)
        if not session:
            return False, None, "Session not found or expired"

        clean_passkey = passkey.strip()
        if not clean_passkey:
            return False, None, "Passkey cannot be empty"

        # If vault is configured, verify passkey with constant-time compare
        if is_vault_configured():
            if not verify_vault_passkey(clean_passkey):
                return False, None, "Invalid Mothership passkey"
        else:
            # First-run setup: allow passkey to establish vault
            from gemini_app.vault import set_vault_passkey
            set_vault_passkey(clean_passkey)

        # Authorized!
        self.authorize_session(session_id, trust_device=trust_device)
        return True, session.token, "Authenticated successfully"
