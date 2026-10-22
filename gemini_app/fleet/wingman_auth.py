"""Wingman Bilateral Authentication & Pairing Security.

Manages zero-trust pairing, trusted device registry, ephemeral session tokens,
session authorization gates, and PBKDF2 homebase passkey verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from gemini_app.config import GEMINI_HOME, VAULT_DIR


TRUSTED_WINGMAN_FILE: Path = VAULT_DIR / "trusted_wingman_devices.json"


def _ensure_vault_dir() -> Path:
    try:
        VAULT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    except Exception:
        pass
    return VAULT_DIR


def load_trusted_devices() -> Dict[str, Dict[str, Any]]:
    """Loads dictionary of trusted/paired devices and tokens."""
    _ensure_vault_dir()
    if not TRUSTED_WINGMAN_FILE.is_file():
        return {}
    try:
        data = json.loads(TRUSTED_WINGMAN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_trusted_devices(devices: Dict[str, Dict[str, Any]]) -> bool:
    """Persists trusted devices registry with strict permissions."""
    _ensure_vault_dir()
    try:
        tmp = TRUSTED_WINGMAN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(devices, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(TRUSTED_WINGMAN_FILE)
        return True
    except Exception:
        try:
            TRUSTED_WINGMAN_FILE.write_text(json.dumps(devices, indent=2), encoding="utf-8")
            TRUSTED_WINGMAN_FILE.chmod(0o600)
            return True
        except Exception:
            return False


def is_device_trusted(identifier: str) -> bool:
    """Checks if a device identifier (IP, node_id, or token) is trusted."""
    if not identifier:
        return False
    # Always allow local loopback
    if identifier in ("127.0.0.1", "::1", "localhost", "local"):
        return True
    devices = load_trusted_devices()
    return identifier in devices


def trust_device(
    identifier: str,
    node_id: str = "",
    client_ip: str = "",
    label: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Adds a device or IP to the trusted paired registry."""
    devices = load_trusted_devices()
    entry = {
        "identifier": identifier,
        "node_id": node_id,
        "client_ip": client_ip,
        "label": label or f"Paired Node {node_id or identifier}",
        "trusted_at": time.time(),
        "trusted_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "meta": meta or {},
    }
    devices[identifier] = entry
    if client_ip and client_ip not in devices:
        devices[client_ip] = entry
    save_trusted_devices(devices)
    return entry


def revoke_trusted_device(identifier: str) -> bool:
    """Removes a device or IP from the trusted registry."""
    devices = load_trusted_devices()
    removed = False
    if identifier in devices:
        del devices[identifier]
        removed = True
    # Also clean matching client_ip or node_id
    to_delete = [
        k for k, v in devices.items()
        if v.get("node_id") == identifier or v.get("client_ip") == identifier
    ]
    for k in to_delete:
        del devices[k]
        removed = True
    if removed:
        save_trusted_devices(devices)
    return removed


def list_trusted_devices() -> List[Dict[str, Any]]:
    """Returns unique list of trusted device entries."""
    devices = load_trusted_devices()
    seen = set()
    result = []
    for k, v in devices.items():
        ident = v.get("identifier", k)
        if ident not in seen:
            seen.add(ident)
            result.append(v)
    return result


def verify_system_password(password: str) -> bool:
    """Verifies password against the host Linux system account."""
    if not password:
        return False
    import getpass
    import subprocess
    user = getpass.getuser()

    # 1. PAM check if pamela or pam is available
    for mod in ("pamela", "pam"):
        try:
            m = __import__(mod)
            if hasattr(m, "authenticate"):
                if m.authenticate(user, password):
                    return True
            elif hasattr(m, "pam"):
                if m.pam().authenticate(user, password):
                    return True
        except Exception:
            pass

    # 2. Subprocess sudo verification fallback
    try:
        proc = subprocess.run(
            ["sudo", "-k", "-S", "true"],
            input=password.encode("utf-8") + b"\n",
            capture_output=True,
            timeout=5.0,
        )
        if proc.returncode == 0:
            return True
    except Exception:
        pass

    return False


def verify_homebase_passkey(passkey: str) -> bool:
    """Verifies a passkey against Homebase's encrypted vault PBKDF2 hash

    or host Linux system credentials. This serves as the cryptographic baseline
    for sensitive operations originating from Wingman satellites.
    """
    if not passkey:
        return False
    clean = passkey.strip()
    if not clean:
        return False

    # 1. Vault passkey check
    try:
        from gemini_app.vault import is_vault_configured, verify_vault_passkey, get_session_passkey, set_session_passkey
        if is_vault_configured() and verify_vault_passkey(clean):
            set_session_passkey(clean)
            return True
        cached = get_session_passkey()
        if cached and clean == cached:
            return True
    except Exception:
        pass

    # 2. Host Linux system password check (PAM / sudo)
    if verify_system_password(clean):
        try:
            from gemini_app.vault import set_session_passkey
            set_session_passkey(clean)
        except Exception:
            pass
        return True

    return False


def generate_session_token(node_id: str, client_ip: str) -> str:
    """Generates an ephemeral cryptographic session token for Wingman."""
    raw = f"{node_id}:{client_ip}:{time.time()}:{secrets.token_hex(16)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class WingmanSession:
    """Tracks state and authorization status for an active Wingman browser session."""

    def __init__(
        self,
        session_id: str,
        client_ip: str = "127.0.0.1",
        node_id: str = "local",
        user_agent: str = "",
        is_approved: bool = False,
    ) -> None:
        self.session_id = session_id
        self.client_ip = client_ip
        self.node_id = node_id
        self.user_agent = user_agent
        self.is_approved = is_approved
        self.is_unlocked = False  # Requires passkey unlock on first sensitive action
        self.created_at = time.time()
        self.last_active = time.time()
        self.token = generate_session_token(node_id, client_ip)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "client_ip": self.client_ip,
            "node_id": self.node_id,
            "is_approved": self.is_approved,
            "is_unlocked": self.is_unlocked,
            "is_trusted": is_device_trusted(self.client_ip) or is_device_trusted(self.node_id),
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class WingmanSessionManager:
    """Thread-safe manager for Wingman sessions, pending access requests, and passkey unlocking."""

    def __init__(self) -> None:
        self.sessions: Dict[str, WingmanSession] = {}
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._approval_listeners: List[Callable[[str, bool], None]] = []

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        client_ip: str = "127.0.0.1",
        node_id: str = "local",
        user_agent: str = "",
    ) -> WingmanSession:
        """Retrieves an existing session or initializes a new one."""
        with self._lock:
            sid = session_id or f"sess-{secrets.token_hex(12)}"
            if sid in self.sessions:
                sess = self.sessions[sid]
                sess.last_active = time.time()
                if client_ip:
                    sess.client_ip = client_ip
                return sess

            # Auto-approve if client IP or node_id is already trusted / loopback
            auto_approved = is_device_trusted(client_ip) or is_device_trusted(node_id)
            sess = WingmanSession(
                session_id=sid,
                client_ip=client_ip,
                node_id=node_id,
                user_agent=user_agent,
                is_approved=auto_approved,
            )
            self.sessions[sid] = sess

            if not auto_approved:
                req_id = f"req-{secrets.token_hex(8)}"
                self.pending_requests[sid] = {
                    "request_id": req_id,
                    "session_id": sid,
                    "node_id": node_id,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "requested_at": time.time(),
                }
            return sess

    def get_session(self, session_id: str) -> Optional[WingmanSession]:
        with self._lock:
            return self.sessions.get(session_id)

    def request_access(
        self,
        session_id: str,
        client_ip: str = "127.0.0.1",
        node_id: str = "local",
        user_agent: str = "",
    ) -> Tuple[bool, str]:
        """Registers a pending connection request for Homebase confirmation."""
        sess = self.get_or_create_session(session_id, client_ip, node_id, user_agent)
        if sess.is_approved:
            return True, ""

        with self._lock:
            req = self.pending_requests.get(session_id)
            if not req:
                req_id = f"req-{secrets.token_hex(8)}"
                req = {
                    "request_id": req_id,
                    "session_id": session_id,
                    "node_id": node_id,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "requested_at": time.time(),
                }
                self.pending_requests[session_id] = req
            return False, req["request_id"]

    def approve_session(self, identifier: str, trust_permanently: bool = False) -> bool:
        """Approves a pending session request (by session_id or request_id)."""
        target_session: Optional[WingmanSession] = None
        with self._lock:
            # Check by session_id
            if identifier in self.sessions:
                target_session = self.sessions[identifier]
            else:
                # Check by request_id
                for sid, req in list(self.pending_requests.items()):
                    if req.get("request_id") == identifier and sid in self.sessions:
                        target_session = self.sessions[sid]
                        break

            if not target_session:
                return False

            target_session.is_approved = True
            self.pending_requests.pop(target_session.session_id, None)

            if trust_permanently:
                trust_device(
                    identifier=target_session.client_ip,
                    node_id=target_session.node_id,
                    client_ip=target_session.client_ip,
                    label=f"Wingman Node {target_session.node_id}",
                )

        # Notify any approval listeners outside lock
        for cb in self._approval_listeners:
            try:
                cb(target_session.session_id, True)
            except Exception:
                pass
        return True

    def deny_session(self, identifier: str) -> bool:
        """Denies a pending session request and invalidates it."""
        with self._lock:
            target_sid = None
            if identifier in self.sessions:
                target_sid = identifier
            else:
                for sid, req in list(self.pending_requests.items()):
                    if req.get("request_id") == identifier:
                        target_sid = sid
                        break

            if not target_sid:
                return False

            sess = self.sessions.get(target_sid)
            if sess:
                sess.is_approved = False
                sess.is_unlocked = False
            self.pending_requests.pop(target_sid, None)

        for cb in self._approval_listeners:
            try:
                cb(target_sid, False)
            except Exception:
                pass
        return True

    def unlock_session(
        self,
        session_id: str,
        passkey: str,
        verifier: Optional[Callable[[str], bool]] = None,
    ) -> bool:
        """Verifies the Homebase passkey and unlocks the session for interactive use."""
        verify_fn = verifier or verify_homebase_passkey
        if not verify_fn(passkey):
            return False

        with self._lock:
            sess = self.sessions.get(session_id)
            if sess:
                sess.is_unlocked = True
                sess.last_active = time.time()
                return True
            # If session didn't exist yet, create it unlocked
            sess = WingmanSession(session_id=session_id, is_approved=True)
            sess.is_unlocked = True
            self.sessions[session_id] = sess
            return True

    def is_session_unlocked(self, session_id: str) -> bool:
        with self._lock:
            sess = self.sessions.get(session_id)
            return bool(sess and sess.is_unlocked)

    def is_session_approved(self, session_id: str) -> bool:
        with self._lock:
            sess = self.sessions.get(session_id)
            return bool(sess and sess.is_approved)

    def list_pending(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.pending_requests.values())

    def on_approval(self, callback: Callable[[str, bool], None]) -> None:
        self._approval_listeners.append(callback)


_GLOBAL_SESSION_MANAGER: Optional[WingmanSessionManager] = None


def get_session_manager() -> WingmanSessionManager:
    """Returns the process-wide WingmanSessionManager singleton."""
    global _GLOBAL_SESSION_MANAGER
    if _GLOBAL_SESSION_MANAGER is None:
        _GLOBAL_SESSION_MANAGER = WingmanSessionManager()
    return _GLOBAL_SESSION_MANAGER
