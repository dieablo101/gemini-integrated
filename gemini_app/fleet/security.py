"""Cryptographic Fleet Authentication and Node Verification.

Provides zero-dependency mutual authentication and HMAC-SHA256 challenge-response
verification across Mothership and Satellite nodes, ensuring open-source clusters
cannot be spoofed, hijacked, or poisoned by unauthorized nodes or external motherships.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from gemini_app.config import GEMINI_HOME

FLEET_KEY_FILE = GEMINI_HOME / "fleet.key"
MAX_TIMESTAMP_DRIFT = 60.0  # Seconds allowed for clock skew between nodes


def get_or_create_fleet_key(key_path: Optional[Path] = None) -> str:
    """Retrieves the cluster PSK fleet key, or generates a secure 256-bit key if absent."""
    # 1. Environment variable override
    env_key = os.environ.get("GEMINI_FLEET_KEY", "").strip()
    if env_key:
        return env_key

    target_file = key_path or FLEET_KEY_FILE
    try:
        target_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except Exception:
        pass

    if target_file.exists():
        try:
            key_data = target_file.read_text(encoding="utf-8").strip()
            if key_data:
                return key_data
        except Exception:
            pass

    # Generate new cryptographically secure 256-bit hex token
    new_key = secrets.token_hex(32)
    try:
        target_file.write_text(new_key, encoding="utf-8")
        target_file.chmod(0o600)
    except Exception:
        pass
    return new_key


def save_fleet_key(key: str, key_path: Optional[Path] = None) -> bool:
    """Saves the cluster fleet key to disk with strict permissions."""
    if not key or not isinstance(key, str):
        return False
    target_file = key_path or FLEET_KEY_FILE
    try:
        target_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_file.write_text(key.strip(), encoding="utf-8")
        target_file.chmod(0o600)
        return True
    except Exception:
        return False


def get_existing_fleet_key(key_path: Optional[Path] = None) -> Optional[str]:
    """Reads existing cluster key without automatically generating a new one."""
    env_key = os.environ.get("GEMINI_FLEET_KEY", "").strip()
    if env_key:
        return env_key
    target_file = key_path or FLEET_KEY_FILE
    if target_file.exists():
        try:
            k = target_file.read_text(encoding="utf-8").strip()
            if k:
                return k
        except Exception:
            pass
    return None


def generate_challenge() -> Tuple[str, float]:
    """Generates a random 32-byte nonce and timestamp for challenge-response auth."""
    nonce = secrets.token_hex(16)
    timestamp = time.time()
    return nonce, timestamp


def compute_auth_signature(key: str, node_id: str, nonce: str, timestamp: float) -> str:
    """Computes an HMAC-SHA256 signature for node challenge response."""
    msg = f"{node_id}:{nonce}:{int(timestamp)}".encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_auth_signature(
    key: str,
    node_id: str,
    nonce: str,
    timestamp: float,
    signature: str,
    max_drift: float = MAX_TIMESTAMP_DRIFT,
) -> bool:
    """Verifies that the HMAC-SHA256 challenge response matches and is within timestamp drift."""
    if not key or not signature:
        return False
    # Prevent replay attacks with stale timestamps
    now = time.time()
    if abs(now - timestamp) > max_drift:
        return False

    expected_sig = compute_auth_signature(key, node_id, nonce, timestamp)
    return hmac.compare_digest(expected_sig, signature)


def compute_command_signature(key: str, action: str, node_id: str, timestamp: float) -> str:
    """Computes an HMAC-SHA256 signature for remote dispatch commands."""
    msg = f"cmd:{action}:{node_id}:{int(timestamp)}".encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_command_signature(
    key: str,
    action: str,
    node_id: str,
    timestamp: float,
    signature: str,
    max_drift: float = MAX_TIMESTAMP_DRIFT,
) -> bool:
    """Verifies that an incoming remote command originated from a verified Mothership."""
    if not key or not signature:
        return False
    now = time.time()
    if abs(now - timestamp) > max_drift:
        return False
    expected_sig = compute_command_signature(key, action, node_id, timestamp)
    return hmac.compare_digest(expected_sig, signature)
