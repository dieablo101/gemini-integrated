"""Per-Session Fleet Keyring and In-Memory Cluster Secret Management.

Holds decrypted cluster credentials, HMAC fleet keys, and node certificates
exclusively in volatile RAM for the duration of an active console session.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional

from gemini_app.config import GEMINI_HOME, VAULT_DIR
from gemini_app.vault import (
    clear_session_passkey,
    decrypt_bytes,
    encrypt_bytes,
    get_session_passkey,
    is_session_unlocked,
    set_session_passkey,
    verify_vault_passkey,
)

FLEET_VAULT_DIR: Path = VAULT_DIR / "fleet"
FLEET_KEY_ENC: Path = FLEET_VAULT_DIR / "fleet_key.enc"
CLUSTER_KEY_ENC: Path = FLEET_VAULT_DIR / "id_cluster.enc"

_KEYRING_FLEET_KEY: Optional[str] = None
_KEYRING_SSH_KEY_DATA: Optional[str] = None
_KEYRING_UNLOCKED_AT: Optional[float] = None
_KEYRING_UNLOCKING: bool = False


class FleetKeyring:
    """Singleton in-memory keyring for active session fleet operations."""

    @classmethod
    def is_unlocked(cls) -> bool:
        """Returns True if the fleet keyring is currently unlocked in volatile RAM."""
        global _KEYRING_FLEET_KEY
        return bool(_KEYRING_FLEET_KEY)

    @classmethod
    def get_fleet_key(cls) -> Optional[str]:
        """Returns active HMAC PSK fleet key from in-memory keyring."""
        global _KEYRING_FLEET_KEY, _KEYRING_UNLOCKING
        if _KEYRING_FLEET_KEY:
            return _KEYRING_FLEET_KEY
        if _KEYRING_UNLOCKING:
            return _KEYRING_FLEET_KEY
        passkey = get_session_passkey()
        if passkey and verify_vault_passkey(passkey):
            try:
                cls.unlock(passkey)
                return _KEYRING_FLEET_KEY
            except Exception:
                pass
        return None

    @classmethod
    def set_fleet_key(cls, new_key: str, passkey: Optional[str] = None) -> None:
        """Updates in-memory fleet key and re-encrypts FLEET_KEY_ENC if passkey is available."""
        global _KEYRING_FLEET_KEY
        _KEYRING_FLEET_KEY = new_key
        key = passkey or get_session_passkey()
        if key and verify_vault_passkey(key):
            try:
                FLEET_VAULT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
                enc = encrypt_bytes(new_key.encode("utf-8"), key)
                FLEET_KEY_ENC.write_bytes(enc)
                FLEET_KEY_ENC.chmod(0o600)
            except Exception:
                pass

    @classmethod
    def get_ssh_key_data(cls) -> Optional[str]:
        """Returns decrypted cluster SSH private key data from in-memory keyring."""
        global _KEYRING_SSH_KEY_DATA
        if _KEYRING_SSH_KEY_DATA:
            return _KEYRING_SSH_KEY_DATA
        passkey = get_session_passkey()
        if passkey and verify_vault_passkey(passkey):
            try:
                cls.unlock(passkey)
                return _KEYRING_SSH_KEY_DATA
            except Exception:
                pass
        return None

    @classmethod
    def unlock(cls, passkey: str) -> Dict[str, Any]:
        """Decrypts fleet secrets into volatile memory using the verified passkey."""
        global _KEYRING_FLEET_KEY, _KEYRING_SSH_KEY_DATA, _KEYRING_UNLOCKED_AT

        if not verify_vault_passkey(passkey):
            raise PermissionError("Invalid vault passkey.")

        # Ensure session passkey is cached in RAM
        set_session_passkey(passkey)
        FLEET_VAULT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        fleet_key_val: Optional[str] = None
        cluster_key_val: Optional[str] = None

        # 1. Load or migrate fleet.key
        if FLEET_KEY_ENC.exists():
            try:
                dec = decrypt_bytes(FLEET_KEY_ENC.read_bytes(), passkey)
                fleet_key_val = dec.decode("utf-8").strip()
            except Exception:
                pass

        if not fleet_key_val:
            # Check legacy ~/.gemini/fleet.key
            legacy_key_path = GEMINI_HOME / "fleet.key"
            if legacy_key_path.exists():
                try:
                    fleet_key_val = legacy_key_path.read_text(encoding="utf-8").strip()
                    enc = encrypt_bytes(fleet_key_val.encode("utf-8"), passkey)
                    FLEET_KEY_ENC.write_bytes(enc)
                    FLEET_KEY_ENC.chmod(0o600)
                    legacy_key_path.unlink(missing_ok=True)
                except Exception:
                    pass

        if not fleet_key_val:
            fleet_key_val = secrets.token_hex(32)
            try:
                enc = encrypt_bytes(fleet_key_val.encode("utf-8"), passkey)
                FLEET_KEY_ENC.write_bytes(enc)
                FLEET_KEY_ENC.chmod(0o600)
            except Exception:
                pass

        # 2. Load or migrate id_cluster SSH key
        if CLUSTER_KEY_ENC.exists():
            try:
                dec = decrypt_bytes(CLUSTER_KEY_ENC.read_bytes(), passkey)
                cluster_key_val = dec.decode("utf-8").strip()
            except Exception:
                pass

        if not cluster_key_val:
            legacy_cluster = GEMINI_HOME / "fleet" / "id_cluster"
            if legacy_cluster.exists():
                try:
                    cluster_key_val = legacy_cluster.read_text(encoding="utf-8").strip()
                    enc = encrypt_bytes(cluster_key_val.encode("utf-8"), passkey)
                    CLUSTER_KEY_ENC.write_bytes(enc)
                    CLUSTER_KEY_ENC.chmod(0o600)
                except Exception:
                    pass

        _KEYRING_FLEET_KEY = fleet_key_val
        _KEYRING_SSH_KEY_DATA = cluster_key_val
        _KEYRING_UNLOCKED_AT = time.time()

        return {
            "status": "unlocked",
            "has_fleet_key": bool(_KEYRING_FLEET_KEY),
            "has_ssh_key": bool(_KEYRING_SSH_KEY_DATA),
            "unlocked_at": _KEYRING_UNLOCKED_AT,
        }

    @classmethod
    def lock(cls) -> None:
        """Zeroes out in-memory fleet keys and locks the keyring."""
        global _KEYRING_FLEET_KEY, _KEYRING_SSH_KEY_DATA, _KEYRING_UNLOCKED_AT
        _KEYRING_FLEET_KEY = None
        _KEYRING_SSH_KEY_DATA = None
        _KEYRING_UNLOCKED_AT = None
        clear_session_passkey()

    @classmethod
    def sync_nodes(cls, passkey: Optional[str] = None) -> Dict[str, Any]:
        """Unlocks keyring if necessary and synchronizes status with all registered fleet nodes."""
        key = passkey or get_session_passkey()
        if not cls.is_unlocked():
            if not key or not verify_vault_passkey(key):
                raise PermissionError("Vault passkey required to unlock fleet node sync.")
            cls.unlock(key)

        from gemini_app.fleet.nodes import get_fleet_snapshot

        snapshot = get_fleet_snapshot()
        active: List[Dict[str, Any]] = [
            n for n in snapshot.get("nodes", []) if n.get("status") == "online"
        ]

        return {
            "status": "success",
            "keyring_unlocked": True,
            "active_nodes_count": len(active),
            "active_nodes": [n.get("node_id") for n in active],
            "total_registered": snapshot.get("total_registered", 0),
            "nodes": snapshot.get("nodes", []),
            "timestamp": time.time(),
        }
