"""Secure local vault storage for sensitive credentials, keys, and tokens.

Provides encrypted storage under ~/.gemini/vault with PBKDF2-HMAC-SHA256
passkey authentication.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
from typing import Any

from gemini_app.config import GEMINI_HOME, STATE_FILE, VAULT_DIR

VAULT_META_FILE: Path = VAULT_DIR / ".vault_meta.json"
PBKDF2_ITERATIONS: int = 100_000


def init_vault() -> Path:
    """Ensures ~/.gemini/vault exists with strict 0700 permissions."""
    VAULT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        VAULT_DIR.chmod(0o700)
    except Exception:
        pass
    return VAULT_DIR


def hash_passkey(passkey: str, salt: bytes | None = None) -> tuple[str, str]:
    """Generates a (salt_hex, hash_hex) pair using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key_hash = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), key_hash.hex()


def verify_vault_passkey(passkey: str) -> bool:
    """Verifies a passkey against the stored vault hash."""
    salt_hex = None
    hash_hex = None

    if VAULT_META_FILE.is_file():
        try:
            meta = json.loads(VAULT_META_FILE.read_text(encoding="utf-8"))
            salt_hex = meta.get("salt")
            hash_hex = meta.get("hash")
        except Exception:
            pass

    if not (salt_hex and hash_hex) and STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            salt_hex = state.get("vault_passkey_salt")
            hash_hex = state.get("vault_passkey_hash")
        except Exception:
            pass

    if not salt_hex or not hash_hex:
        return False

    salt = bytes.fromhex(salt_hex)
    computed = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return secrets.compare_digest(computed.hex(), hash_hex)


def is_vault_configured() -> bool:
    """Returns True if a vault passkey hash is configured."""
    if VAULT_META_FILE.is_file():
        try:
            meta = json.loads(VAULT_META_FILE.read_text(encoding="utf-8"))
            if meta.get("hash"):
                return True
        except Exception:
            pass

    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if state.get("vault_passkey_hash"):
                return True
        except Exception:
            pass

    return False


def set_vault_passkey(passkey: str) -> dict[str, Any]:
    """Configures or updates the vault passkey hash and salt."""
    init_vault()
    clean_pass = passkey.strip()
    if not clean_pass:
        return {"status": "error", "message": "Passkey cannot be empty."}

    salt_hex, hash_hex = hash_passkey(clean_pass)

    meta = {
        "salt": salt_hex,
        "hash": hash_hex,
        "algorithm": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
    }
    VAULT_META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    VAULT_META_FILE.chmod(0o600)

    # Persist in state.json as well
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}

    state["vault_passkey_salt"] = salt_hex
    state["vault_passkey_hash"] = hash_hex
    STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    STATE_FILE.chmod(0o600)

    return {"status": "success", "configured": True}


def _derive_fernet_key(passkey: str, salt: bytes) -> bytes:
    derived = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(derived[:32])


def encrypt_bytes(data: bytes, passkey: str) -> bytes:
    """Encrypts byte payload using Fernet (or HMAC stream cipher fallback)."""
    salt = secrets.token_bytes(16)
    try:
        from cryptography.fernet import Fernet

        key = _derive_fernet_key(passkey, salt)
        fernet = Fernet(key)
        token = fernet.encrypt(data)
        return b"F1:" + salt.hex().encode("ascii") + b":" + token
    except ImportError:
        enc_key = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        nonce = secrets.token_bytes(16)
        stream = bytearray()
        ctr = 0
        while len(stream) < len(data):
            stream.extend(hmac.new(enc_key, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest())
            ctr += 1
        ciphertext = bytes(b ^ s for b, s in zip(data, stream[: len(data)]))
        mac = hmac.new(enc_key, nonce + ciphertext, hashlib.sha256).digest()
        return (
            b"S1:"
            + salt.hex().encode("ascii")
            + b":"
            + nonce.hex().encode("ascii")
            + b":"
            + mac.hex().encode("ascii")
            + b":"
            + base64.b64encode(ciphertext)
        )


def decrypt_bytes(payload: bytes, passkey: str) -> bytes:
    """Decrypts payload encrypted with encrypt_bytes."""
    if payload.startswith(b"F1:"):
        _, salt_hex, token = payload.split(b":", 2)
        salt = bytes.fromhex(salt_hex.decode("ascii"))
        from cryptography.fernet import Fernet

        key = _derive_fernet_key(passkey, salt)
        fernet = Fernet(key)
        return fernet.decrypt(token)
    elif payload.startswith(b"S1:"):
        _, salt_hex, nonce_hex, mac_hex, b64_cipher = payload.split(b":", 4)
        salt = bytes.fromhex(salt_hex.decode("ascii"))
        nonce = bytes.fromhex(nonce_hex.decode("ascii"))
        expected_mac = bytes.fromhex(mac_hex.decode("ascii"))
        ciphertext = base64.b64decode(b64_cipher)

        enc_key = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        computed_mac = hmac.new(enc_key, nonce + ciphertext, hashlib.sha256).digest()
        if not secrets.compare_digest(computed_mac, expected_mac):
            raise ValueError("Integrity check failed: incorrect passkey or corrupted vault data.")

        stream = bytearray()
        ctr = 0
        while len(stream) < len(ciphertext):
            stream.extend(hmac.new(enc_key, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest())
            ctr += 1
        return bytes(b ^ s for b, s in zip(ciphertext, stream[: len(ciphertext)]))
    else:
        raise ValueError("Unsupported vault encryption format.")


def store_in_vault(filename: str, content: bytes | str, passkey: str | None = None) -> Path:
    """Stores secret file in ~/.gemini/vault, encrypting if passkey provided."""
    init_vault()
    raw_bytes = content.encode("utf-8") if isinstance(content, str) else content

    if passkey:
        encrypted = encrypt_bytes(raw_bytes, passkey)
        target_name = f"{filename}.enc" if not filename.endswith(".enc") else filename
        dest = VAULT_DIR / target_name
        dest.write_bytes(encrypted)
    else:
        dest = VAULT_DIR / filename
        dest.write_bytes(raw_bytes)

    dest.chmod(0o600)
    return dest


def retrieve_from_vault(filename: str, passkey: str) -> bytes:
    """Retrieves and decrypts a secret from ~/.gemini/vault."""
    if not verify_vault_passkey(passkey):
        raise PermissionError("Invalid vault passkey.")

    target = VAULT_DIR / filename
    if not target.is_file():
        target = VAULT_DIR / f"{filename}.enc"
    if not target.is_file():
        raise FileNotFoundError(f"Vault secret '{filename}' not found.")

    raw = target.read_bytes()
    if target.suffix == ".enc" or raw.startswith(b"F1:") or raw.startswith(b"S1:"):
        return decrypt_bytes(raw, passkey)
    return raw


def list_vault_files() -> list[str]:
    """Lists files currently stored in ~/.gemini/vault (excluding hidden metadata)."""
    if not VAULT_DIR.is_dir():
        return []
    return sorted(f.name for f in VAULT_DIR.iterdir() if f.is_file() and not f.name.startswith("."))
