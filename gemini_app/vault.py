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
import re
import secrets
import shutil
import time
from typing import Any

from gemini_app.config import GEMINI_HOME, STATE_FILE, VAULT_DIR

VAULT_META_FILE: Path = VAULT_DIR / ".vault_meta.json"
PBKDF2_ITERATIONS: int = 100_000

PASSWORDS_DIR: Path = VAULT_DIR / "passwords"
SECRETS_DIR: Path = VAULT_DIR / "secrets"
FILES_DIR: Path = VAULT_DIR / "files"

# Ephemeral RAM session passkey cache (never written to disk)
_SESSION_PASSKEY: str | None = None


def init_vault() -> Path:
    """Ensures ~/.gemini/vault and category subdirectories exist with strict 0700 permissions."""
    for d in (VAULT_DIR, PASSWORDS_DIR, SECRETS_DIR, FILES_DIR):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except Exception:
            pass
    return VAULT_DIR


def set_session_passkey(passkey: str) -> None:
    """Caches the verified vault passkey in RAM for the active console session."""
    global _SESSION_PASSKEY
    _SESSION_PASSKEY = passkey


def get_session_passkey() -> str | None:
    """Retrieves the active in-memory session passkey if available."""
    global _SESSION_PASSKEY
    return _SESSION_PASSKEY


def clear_session_passkey() -> None:
    """Zeroes out the in-memory session passkey (locks vault)."""
    global _SESSION_PASSKEY
    _SESSION_PASSKEY = None


def is_session_unlocked() -> bool:
    """Returns True if a valid session passkey is currently cached in RAM."""
    global _SESSION_PASSKEY
    if not _SESSION_PASSKEY:
        return False
    return verify_vault_passkey(_SESSION_PASSKEY)


def hash_passkey(passkey: str, salt: bytes | None = None) -> tuple[str, str]:
    """Generates a (salt_hex, hash_hex) pair using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key_hash = hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), key_hash.hex()


def verify_vault_passkey(passkey: str) -> bool:
    """Verifies a passkey against the stored vault hash."""
    if not passkey:
        return False

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

    set_session_passkey(clean_pass)
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


def _resolve_passkey(passkey: str | None = None) -> str:
    key = passkey or get_session_passkey()
    if not key:
        raise PermissionError("No vault passkey provided or session locked.")
    if not verify_vault_passkey(key):
        raise PermissionError("Invalid vault passkey.")
    return key


def _slugify(name: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", name).strip().lower()
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug or "untitled"


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


def retrieve_from_vault(filename: str, passkey: str | None = None) -> bytes:
    """Retrieves and decrypts a secret from ~/.gemini/vault."""
    key = _resolve_passkey(passkey)

    target = VAULT_DIR / filename
    if not target.is_file():
        target = VAULT_DIR / f"{filename}.enc"
    if not target.is_file():
        # Check subdirectories
        for sub in (PASSWORDS_DIR, SECRETS_DIR, FILES_DIR):
            cand = sub / filename
            if not cand.is_file():
                cand = sub / f"{filename}.enc"
            if not cand.is_file() and sub == FILES_DIR:
                slug = _slugify(filename)
                cand = sub / f"{slug}.file.enc"
            if cand.is_file():
                target = cand
                break

    if not target.is_file():
        raise FileNotFoundError(f"Vault secret '{filename}' not found.")

    raw = target.read_bytes()
    if target.suffix == ".enc" or raw.startswith(b"F1:") or raw.startswith(b"S1:"):
        decrypted = decrypt_bytes(raw, key)
    else:
        decrypted = raw

    try:
        dec = json.loads(decrypted.decode("utf-8"))
        if isinstance(dec, dict) and "payload_b64" in dec:
            return base64.b64decode(dec["payload_b64"])
    except Exception:
        pass
    return decrypted


def list_vault_files() -> list[str]:
    """Lists files currently stored directly in ~/.gemini/vault (excluding hidden metadata)."""
    if not VAULT_DIR.is_dir():
        return []
    return sorted(
        f.name
        for f in VAULT_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )


# ----------------------------------------------------------------------
# Categorized Storage: Passwords
# ----------------------------------------------------------------------

def store_password(
    title: str,
    password: str,
    username: str = "",
    notes: str = "",
    passkey: str | None = None,
) -> Path:
    """Encrypts and saves an account password into ~/.gemini/vault/passwords/."""
    init_vault()
    key = _resolve_passkey(passkey)
    slug = _slugify(title)
    payload = {
        "title": title.strip(),
        "username": username.strip(),
        "password": password,
        "notes": notes.strip(),
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    encrypted = encrypt_bytes(json.dumps(payload).encode("utf-8"), key)
    target = PASSWORDS_DIR / f"{slug}.pass.enc"
    target.write_bytes(encrypted)
    target.chmod(0o600)
    return target


def get_password(title: str, passkey: str | None = None) -> dict[str, Any]:
    """Retrieves and decrypts a stored password entry."""
    key = _resolve_passkey(passkey)
    slug = _slugify(title)
    target = PASSWORDS_DIR / f"{slug}.pass.enc"
    if not target.is_file():
        target = PASSWORDS_DIR / title
    if not target.is_file():
        for f in PASSWORDS_DIR.glob("*.pass.enc"):
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                if dec.get("title", "").lower() == title.lower():
                    target = f
                    break
            except Exception:
                continue

    if not target.is_file():
        raise FileNotFoundError(f"Password '{title}' not found.")

    raw = decrypt_bytes(target.read_bytes(), key)
    return json.loads(raw.decode("utf-8"))


def list_passwords(passkey: str | None = None) -> list[dict[str, Any]]:
    """Lists all stored password entries. Decrypts credentials if passkey is available."""
    init_vault()
    key = passkey or get_session_passkey()
    has_valid_key = key and verify_vault_passkey(key)

    items: list[dict[str, Any]] = []
    for f in sorted(PASSWORDS_DIR.glob("*.pass.enc")):
        if has_valid_key:
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                items.append({
                    "title": dec.get("title", f.stem.replace(".pass", "")),
                    "username": dec.get("username", ""),
                    "password": dec.get("password", ""),
                    "notes": dec.get("notes", ""),
                    "updated_at": dec.get("updated_at", f.stat().st_mtime),
                    "file_name": f.name,
                })
                continue
            except Exception:
                pass
        items.append({
            "title": f.stem.replace(".pass", "").replace("_", " ").title(),
            "username": "",
            "password": "",
            "notes": "",
            "updated_at": f.stat().st_mtime,
            "file_name": f.name,
        })
    return items


def delete_password(title: str) -> bool:
    """Deletes a password entry by title or filename."""
    slug = _slugify(title)
    target = PASSWORDS_DIR / f"{slug}.pass.enc"
    if target.is_file():
        target.unlink()
        return True
    target = PASSWORDS_DIR / title
    if target.is_file():
        target.unlink()
        return True
    return False


# ----------------------------------------------------------------------
# Categorized Storage: Secrets (Multiline Strings, API Tokens, Keys)
# ----------------------------------------------------------------------

def store_secret(
    title: str,
    secret_text: str,
    passkey: str | None = None,
) -> Path:
    """Encrypts and saves a raw secret string or multiline token."""
    init_vault()
    key = _resolve_passkey(passkey)
    slug = _slugify(title)
    payload = {
        "title": title.strip(),
        "secret": secret_text,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    encrypted = encrypt_bytes(json.dumps(payload).encode("utf-8"), key)
    target = SECRETS_DIR / f"{slug}.sec.enc"
    target.write_bytes(encrypted)
    target.chmod(0o600)
    return target


def get_secret(title: str, passkey: str | None = None) -> dict[str, Any]:
    """Retrieves and decrypts a secret entry."""
    key = _resolve_passkey(passkey)
    slug = _slugify(title)
    target = SECRETS_DIR / f"{slug}.sec.enc"
    if not target.is_file():
        target = SECRETS_DIR / title
    if not target.is_file():
        for f in SECRETS_DIR.glob("*.sec.enc"):
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                if dec.get("title", "").lower() == title.lower():
                    target = f
                    break
            except Exception:
                continue

    if not target.is_file():
        raise FileNotFoundError(f"Secret '{title}' not found.")

    raw = decrypt_bytes(target.read_bytes(), key)
    return json.loads(raw.decode("utf-8"))


def list_secrets(passkey: str | None = None) -> list[dict[str, Any]]:
    """Lists all stored secret entries."""
    init_vault()
    key = passkey or get_session_passkey()
    has_valid_key = key and verify_vault_passkey(key)

    items: list[dict[str, Any]] = []
    for f in sorted(SECRETS_DIR.glob("*.sec.enc")):
        if has_valid_key:
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                items.append({
                    "title": dec.get("title", f.stem.replace(".sec", "")),
                    "secret": dec.get("secret", ""),
                    "updated_at": dec.get("updated_at", f.stat().st_mtime),
                    "file_name": f.name,
                })
                continue
            except Exception:
                pass
        items.append({
            "title": f.stem.replace(".sec", "").replace("_", " ").title(),
            "secret": "",
            "updated_at": f.stat().st_mtime,
            "file_name": f.name,
        })
    return items


def delete_secret(title: str) -> bool:
    """Deletes a secret entry by title or filename."""
    slug = _slugify(title)
    target = SECRETS_DIR / f"{slug}.sec.enc"
    if target.is_file():
        target.unlink()
        return True
    target = SECRETS_DIR / title
    if target.is_file():
        target.unlink()
        return True
    return False


# ----------------------------------------------------------------------
# Categorized Storage: Encrypted Files & Autocomplete Imports
# ----------------------------------------------------------------------

def store_file(
    title: str,
    file_path: str | Path,
    passkey: str | None = None,
    shred_original: bool = False,
) -> Path:
    """Encrypts and stores a file payload into ~/.gemini/vault/files/."""
    init_vault()
    key = _resolve_passkey(passkey)
    src = Path(file_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source file '{file_path}' does not exist.")

    data = src.read_bytes()
    slug = _slugify(title)
    meta = {
        "title": title.strip(),
        "original_name": src.name,
        "original_size": len(data),
        "created_at": time.time(),
        "updated_at": time.time(),
        "payload_b64": base64.b64encode(data).decode("ascii"),
    }
    encrypted = encrypt_bytes(json.dumps(meta).encode("utf-8"), key)
    target = FILES_DIR / f"{slug}.file.enc"
    target.write_bytes(encrypted)
    target.chmod(0o600)

    if shred_original:
        try:
            size = src.stat().st_size
            with open(src, "wb") as f:
                f.write(secrets.token_bytes(size))
                f.flush()
                f.seek(0)
                f.write(b"\x00" * size)
                f.flush()
            src.unlink()
        except Exception:
            pass

    return target


def export_file(
    title: str,
    dest_path: str | Path,
    passkey: str | None = None,
) -> Path:
    """Decrypts a vault file and writes it to the designated destination path."""
    key = _resolve_passkey(passkey)
    slug = _slugify(title)
    target = None

    # Check FILES_DIR
    for cand in (
        FILES_DIR / f"{slug}.file.enc",
        FILES_DIR / title,
        FILES_DIR / f"{title}.file.enc",
    ):
        if cand.is_file():
            target = cand
            break

    if not target:
        for f in FILES_DIR.glob("*.file.enc"):
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                if (
                    dec.get("title", "").lower() == title.lower()
                    or dec.get("original_name", "").lower() == title.lower()
                ):
                    target = f
                    break
            except Exception:
                continue

    # Check root VAULT_DIR for legacy/direct files
    if not target:
        for cand in (
            VAULT_DIR / title,
            VAULT_DIR / f"{title}.enc",
            VAULT_DIR / f"{slug}.enc",
        ):
            if cand.is_file():
                target = cand
                break

    if not target and VAULT_DIR.is_dir():
        for f in VAULT_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                if (
                    f.name.lower() == title.lower()
                    or f.name.removesuffix(".enc").lower() == title.lower()
                    or _slugify(f.name.removesuffix(".enc")) == slug
                ):
                    target = f
                    break

    if not target or not target.is_file():
        raise FileNotFoundError(f"Vault file '{title}' not found.")

    raw = target.read_bytes()
    if target.suffix == ".enc" or raw.startswith(b"F1:") or raw.startswith(b"S1:"):
        decrypted_raw = decrypt_bytes(raw, key)
    else:
        decrypted_raw = raw

    out_name = target.name.removesuffix(".enc").removesuffix(".file")
    try:
        dec = json.loads(decrypted_raw.decode("utf-8"))
        if isinstance(dec, dict) and "payload_b64" in dec:
            payload = base64.b64decode(dec["payload_b64"])
            out_name = dec.get("original_name", out_name)
        else:
            payload = decrypted_raw
    except Exception:
        payload = decrypted_raw

    dest = Path(dest_path).expanduser().resolve()
    if dest.is_dir():
        dest = dest / out_name

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return dest


def list_categorized_files(passkey: str | None = None) -> list[dict[str, Any]]:
    """Lists all stored encrypted files across categorized files and root vault files."""
    init_vault()
    key = passkey or get_session_passkey()
    has_valid_key = bool(key and verify_vault_passkey(key))

    items: list[dict[str, Any]] = []

    # 1. Categorized files in FILES_DIR
    for f in sorted(FILES_DIR.glob("*.file.enc")):
        if has_valid_key:
            try:
                dec = json.loads(decrypt_bytes(f.read_bytes(), key).decode("utf-8"))
                items.append({
                    "title": dec.get("title", f.stem.replace(".file", "")),
                    "original_name": dec.get("original_name", "unknown"),
                    "original_size": dec.get("original_size", 0),
                    "updated_at": dec.get("updated_at", f.stat().st_mtime),
                    "file_name": f.name,
                    "is_legacy": False,
                })
                continue
            except Exception:
                pass
        items.append({
            "title": f.stem.replace(".file", "").replace("_", " ").title(),
            "original_name": "encrypted",
            "original_size": f.stat().st_size,
            "updated_at": f.stat().st_mtime,
            "file_name": f.name,
            "is_legacy": False,
        })

    # 2. Legacy / root files in ~/.gemini/vault
    if VAULT_DIR.is_dir():
        for f in sorted(VAULT_DIR.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            clean_title = f.name[:-4] if f.name.endswith(".enc") else f.name
            is_enc = f.name.endswith(".enc")

            if has_valid_key and is_enc:
                try:
                    dec_bytes = decrypt_bytes(f.read_bytes(), key)
                    try:
                        dec = json.loads(dec_bytes.decode("utf-8"))
                        if isinstance(dec, dict) and "payload_b64" in dec:
                            items.append({
                                "title": dec.get("title", clean_title),
                                "original_name": dec.get("original_name", clean_title),
                                "original_size": dec.get("original_size", len(dec_bytes)),
                                "updated_at": dec.get("updated_at", f.stat().st_mtime),
                                "file_name": f.name,
                                "is_legacy": True,
                            })
                            continue
                    except Exception:
                        pass

                    items.append({
                        "title": clean_title,
                        "original_name": clean_title,
                        "original_size": len(dec_bytes),
                        "updated_at": f.stat().st_mtime,
                        "file_name": f.name,
                        "is_legacy": True,
                    })
                    continue
                except Exception:
                    pass

            items.append({
                "title": clean_title,
                "original_name": clean_title if not is_enc else "encrypted",
                "original_size": f.stat().st_size,
                "updated_at": f.stat().st_mtime,
                "file_name": f.name,
                "is_legacy": True,
            })

    return items


def delete_vault_file(title: str) -> bool:
    """Deletes an encrypted file entry by title or filename from files/ or root vault."""
    slug = _slugify(title)
    for cand in (
        FILES_DIR / f"{slug}.file.enc",
        FILES_DIR / title,
        FILES_DIR / f"{title}.file.enc",
    ):
        if cand.is_file():
            cand.unlink()
            return True

    for cand in (
        VAULT_DIR / title,
        VAULT_DIR / f"{title}.enc",
        VAULT_DIR / f"{slug}.enc",
    ):
        if cand.is_file():
            cand.unlink()
            return True

    if VAULT_DIR.is_dir():
        for f in VAULT_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                if (
                    f.name.lower() == title.lower()
                    or f.name.removesuffix(".enc").lower() == title.lower()
                    or _slugify(f.name.removesuffix(".enc")) == slug
                ):
                    f.unlink()
                    return True

    return False


# ----------------------------------------------------------------------
# Key Rotation: Atomic Re-Encryption across All Vault Items
# ----------------------------------------------------------------------

def rotate_vault_passkey(old_passkey: str, new_passkey: str) -> dict[str, Any]:
    """Atomic key rotation: decrypts every .enc file in memory with old_passkey,

    re-encrypts with new_passkey, and updates vault metadata.
    """
    clean_old = old_passkey.strip()
    clean_new = new_passkey.strip()

    if not clean_new:
        return {"status": "error", "message": "New passkey cannot be empty."}

    if not verify_vault_passkey(clean_old):
        return {"status": "error", "message": "Current passkey is incorrect."}

    init_vault()

    # Discover all .enc files across vault root and subdirectories
    all_enc_files: list[Path] = []
    for f in VAULT_DIR.glob("*.enc"):
        if f.is_file():
            all_enc_files.append(f)
    for sub in (PASSWORDS_DIR, SECRETS_DIR, FILES_DIR):
        for f in sub.glob("*.enc"):
            if f.is_file():
                all_enc_files.append(f)

    # Phase 1: Decrypt all files into memory to guarantee integrity before modifying disk
    decrypted_map: dict[Path, bytes] = {}
    for enc_file in all_enc_files:
        try:
            raw = enc_file.read_bytes()
            plain = decrypt_bytes(raw, clean_old)
            decrypted_map[enc_file] = plain
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to decrypt '{enc_file.name}' with current passkey: {e}",
            }

    # Phase 2: Re-encrypt and overwrite every file
    for enc_file, plain_data in decrypted_map.items():
        re_encrypted = encrypt_bytes(plain_data, clean_new)
        enc_file.write_bytes(re_encrypted)
        enc_file.chmod(0o600)

    # Phase 3: Update passkey metadata and session cache
    set_vault_passkey(clean_new)
    set_session_passkey(clean_new)

    return {
        "status": "success",
        "rotated_count": len(decrypted_map),
        "message": f"Passkey successfully rotated. Re-encrypted {len(decrypted_map)} items.",
    }


# ----------------------------------------------------------------------
# Fleet Node & Credential Vault Sync
# ----------------------------------------------------------------------

def sync_fleet_vault(passkey: str | None = None, gemini_home: Path | None = None) -> dict[str, Any]:
    """Synchronizes fleet cluster keys and registered nodes into encrypted vault storage.

    Verifies passkey, backs up cluster SSH key (~/.gemini/fleet/id_cluster) and fleet HMAC PSK
    (~/.gemini/fleet.key) into categorized encrypted secrets, and takes an encrypted snapshot
    of the registered fleet nodes.
    """
    key = _resolve_passkey(passkey)
    init_vault()

    home = gemini_home or VAULT_DIR.parent
    fleet_dir = home / "fleet"
    fleet_dir.mkdir(parents=True, exist_ok=True)

    synced_items: list[str] = []

    # 1. Cluster SSH Private Key
    cluster_key_file = fleet_dir / "id_cluster"
    if cluster_key_file.is_file():
        key_content = cluster_key_file.read_text(encoding="utf-8")
        store_secret("fleet_cluster_ssh_key", key_content, passkey=key)
        synced_items.append("cluster_ssh_key")
    else:
        try:
            sec = get_secret("fleet_cluster_ssh_key", passkey=key)
            if sec.get("secret"):
                cluster_key_file.write_text(sec["secret"], encoding="utf-8")
                cluster_key_file.chmod(0o600)
                synced_items.append("cluster_ssh_key_restored")
        except Exception:
            pass

    # 2. Fleet HMAC PSK Key
    fleet_key_enc = home / "vault" / "fleet" / "fleet_key.enc"
    fleet_key_file = home / "fleet.key"
    if fleet_key_file.is_file():
        fleet_key_val = fleet_key_file.read_text(encoding="utf-8").strip()
        store_secret("fleet_hmac_psk", fleet_key_val, passkey=key)
        # Safely migrate into encrypted vault/fleet/fleet_key.enc and remove unencrypted copy
        fleet_vault_dir = home / "vault" / "fleet"
        fleet_vault_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        fleet_key_enc.write_bytes(encrypt_bytes(fleet_key_val.encode("utf-8"), key))
        fleet_key_enc.chmod(0o600)
        fleet_key_file.unlink(missing_ok=True)
        synced_items.append("fleet_hmac_psk")
    elif fleet_key_enc.is_file():
        try:
            fleet_key_val = decrypt_bytes(fleet_key_enc.read_bytes(), key).decode("utf-8").strip()
            store_secret("fleet_hmac_psk", fleet_key_val, passkey=key)
            synced_items.append("fleet_hmac_psk")
        except Exception:
            pass

    # 3. Fleet Nodes Registry Snapshot
    from gemini_app.fleet.nodes import load_nodes_registry, load_active_nodes
    registry = load_nodes_registry()
    active_nodes = load_active_nodes()

    registry_payload = json.dumps({
        "registry": registry,
        "active": active_nodes,
        "synced_at": time.time(),
    }, indent=2)
    store_secret("fleet_nodes_snapshot", registry_payload, passkey=key)
    synced_items.append("fleet_nodes_snapshot")

    return {
        "status": "success",
        "synced_at": time.time(),
        "synced_items": synced_items,
        "registered_nodes_count": len(registry),
        "active_nodes_count": len(active_nodes),
        "nodes": list(registry.keys()),
        "message": f"Synchronized {len(synced_items)} fleet secret items and {len(registry)} registered nodes.",
    }

