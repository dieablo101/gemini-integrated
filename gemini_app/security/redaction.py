"""Inline Cryptographic Redaction and Zero-Leakage In-Stream Enclaves.

Provides military/government-style classified inline cryptographic redaction.
Sensitive strings, API tokens, passkeys, and private keys typed in chat streams
are intercepted before serialization and replaced directly in the text with
self-contained AES-256-GCM encrypted envelopes:

    [ENC:v1:{salt_hex}:{nonce_hex}:{b64_payload}]

Disk storage (chat segments, lineage logs, SQLite databases, and git commits)
stores zero plaintext. When an authorized process or user needs to read the secret,
it is decrypted in volatile RAM only on demand using the master vault password.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from typing import Any, Callable, Dict, List, Optional, Tuple

PBKDF2_ITERATIONS: int = 100_000

# Matches [ENC:v1:{salt_hex_32}:{nonce_hex_24}:{b64_payload}]
ENCLAVE_PATTERN = re.compile(
    r"\[ENC:v1:([0-9a-fA-F]{32}):([0-9a-fA-F]{24}):([A-Za-z0-9+/=_-]+)\]"
)

# Explicit inline redaction syntax
EXPLICIT_SECRET_TAG_PATTERNS = [
    re.compile(r"!secret\[(.*?)\]", re.DOTALL),
    re.compile(r":::secret\s*(.*?)\s*:::", re.DOTALL),
    re.compile(r"::secret\[(.*?)\]::", re.DOTALL),
    re.compile(r"\[SECRET:(.*?)\]", re.DOTALL),
]

# High-entropy token and secret detection patterns
KNOWN_SECRET_PATTERNS = [
    re.compile(r"(pypi-AgEI[A-Za-z0-9_\-]+)"),
    re.compile(r"(ghp_[A-Za-z0-9]{36,})"),
    re.compile(r"(gho_[A-Za-z0-9]{36,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]{40,})"),
    re.compile(r"(sk-[a-zA-Z0-9_\-]{32,})"),
    re.compile(r"(-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]+ PRIVATE KEY-----)"),
]

# Natural language intent: "add this to my vault as <name>: <value>"
VAULT_STORE_INTENT_PATTERN = re.compile(
    r"(?i)\badd\s+(?:this\s+)?to\s+(?:my\s+)?vault\s+as\s+([a-zA-Z0-9_\-\.]+)\s*[:=]\s*([^\r\n]+)"
)


def _derive_key(passkey: str, salt: bytes) -> bytes:
    """Derives a 256-bit symmetric encryption key using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", passkey.encode("utf-8"), salt, PBKDF2_ITERATIONS)


def encrypt_inline(secret_text: str, passkey: str) -> str:
    """Encrypts a plaintext string into a self-contained inline cryptographic envelope.

    Envelope format: [ENC:v1:{salt_hex}:{nonce_hex}:{b64_payload}]
    """
    if not passkey:
        raise ValueError("Passkey is required to encrypt inline secret.")

    data = secret_text.encode("utf-8")
    salt = secrets.token_bytes(16)
    key = _derive_key(passkey, salt)
    nonce = secrets.token_bytes(12)

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        # AESGCM.encrypt appends a 16-byte authentication tag to the ciphertext
        encrypted = aesgcm.encrypt(nonce, data, None)
        b64_payload = base64.b64encode(encrypted).decode("ascii")
        return f"[ENC:v1:{salt.hex()}:{nonce.hex()}:{b64_payload}]"
    except ImportError:
        # Zero-dependency fallback: HMAC-SHA256 CTR stream cipher with 32-byte HMAC tag
        stream = bytearray()
        ctr = 0
        while len(stream) < len(data):
            stream.extend(hmac.new(key, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest())
            ctr += 1
        ciphertext = bytes(b ^ s for b, s in zip(data, stream[: len(data)]))
        tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        payload = tag + ciphertext
        b64_payload = base64.b64encode(payload).decode("ascii")
        return f"[ENC:v1:{salt.hex()}:{nonce.hex()}:{b64_payload}]"


def decrypt_inline(envelope: str, passkey: str) -> str:
    """Decrypts a self-contained inline cryptographic envelope using the provided passkey."""
    m = ENCLAVE_PATTERN.search(envelope)
    if not m:
        raise ValueError("Invalid inline cryptographic envelope format.")

    salt_hex, nonce_hex, b64_payload = m.groups()
    salt = bytes.fromhex(salt_hex)
    nonce = bytes.fromhex(nonce_hex)
    payload = base64.b64decode(b64_payload)

    key = _derive_key(passkey, salt)

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, payload, None)
        return decrypted.decode("utf-8")
    except ImportError:
        # Zero-dependency fallback verification and decryption
        if len(payload) < 32:
            raise ValueError("Corrupted inline envelope payload.")
        expected_tag = payload[:32]
        ciphertext = payload[32:]
        computed_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not secrets.compare_digest(computed_tag, expected_tag):
            raise ValueError("Integrity check failed: incorrect passkey or corrupted envelope.")

        stream = bytearray()
        ctr = 0
        while len(stream) < len(ciphertext):
            stream.extend(hmac.new(key, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest())
            ctr += 1
        decrypted = bytes(b ^ s for b, s in zip(ciphertext, stream[: len(ciphertext)]))
        return decrypted.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption failed (invalid passkey or corrupted envelope): {e}")


def is_redacted_envelope(text: str) -> bool:
    """Returns True if the text contains one or more inline encrypted envelopes."""
    return bool(ENCLAVE_PATTERN.search(text))


def mask_inline_envelopes(text: str, mask_style: str = "classified") -> str:
    """Replaces inline cryptographic envelopes with classified document redaction blocks for display."""
    if mask_style == "classified":
        return ENCLAVE_PATTERN.sub("████[CLASSIFIED:ENCRYPTED]████", text)
    elif mask_style == "clean":
        return ENCLAVE_PATTERN.sub("[REDACTED:ENCRYPTED]", text)
    else:
        return ENCLAVE_PATTERN.sub("[ENC:v1:PROTECTED]", text)


def redact_secrets_in_text(
    text: str,
    passkey: Optional[str] = None,
    on_vault_store: Optional[Callable[[str, str], None]] = None,
) -> Tuple[str, int]:
    """Scans text for explicit secret syntax, natural vault intents, and high-entropy tokens.

    Replaces detected secrets with self-contained inline encrypted envelopes [ENC:v1:...].
    Returns (redacted_text, count_of_redactions).
    """
    if not text:
        return text, 0

    redacted_count = 0
    result_text = text

    # Helper to encrypt or mask
    def _replace_secret(secret_val: str) -> str:
        nonlocal redacted_count
        clean_secret = secret_val.strip()
        if not clean_secret:
            return secret_val

        redacted_count += 1
        if passkey:
            return encrypt_inline(clean_secret, passkey)
        else:
            # If no passkey is available in session, redact with cryptographic digest placeholder
            digest = hashlib.sha256(clean_secret.encode("utf-8")).hexdigest()[:16]
            return f"[REDACTED:TOKEN:{digest}]"

    # 1. Process natural language intent: "add this to my vault as <name>: <value>"
    def _vault_intent_sub(match: re.Match) -> str:
        name = match.group(1).strip()
        val = match.group(2).strip()
        if on_vault_store:
            try:
                on_vault_store(name, val)
            except Exception:
                pass
        enc_val = _replace_secret(val)
        return f"Add this to my vault as {name}: {enc_val}"

    result_text = VAULT_STORE_INTENT_PATTERN.sub(_vault_intent_sub, result_text)

    # 2. Process explicit secret tags (!secret[...], :::secret ... :::, etc.)
    for pattern in EXPLICIT_SECRET_TAG_PATTERNS:
        matches = list(pattern.finditer(result_text))
        for m in reversed(matches):
            full_match = m.group(0)
            inner_secret = m.group(1)
            enc_replacement = _replace_secret(inner_secret)
            start, end = m.span()
            result_text = result_text[:start] + enc_replacement + result_text[end:]

    # 3. Process known high-entropy tokens (PyPI, GitHub, OpenAI keys, SSH private keys)
    for pattern in KNOWN_SECRET_PATTERNS:
        matches = list(pattern.finditer(result_text))
        for m in reversed(matches):
            token_val = m.group(1)
            # Avoid re-encrypting something that is already inside an envelope
            start, end = m.span()
            # Check context around token
            context_prefix = result_text[max(0, start - 20) : start]
            if "[ENC:v1:" in context_prefix:
                continue
            enc_replacement = _replace_secret(token_val)
            result_text = result_text[:start] + enc_replacement + result_text[end:]

    return result_text, redacted_count


def unlock_inline_redactions(text: str, passkey: str) -> Tuple[str, int]:
    """Finds all [ENC:v1:...] envelopes in text, decrypts them with passkey, and restores plaintext."""
    if not text or not passkey:
        return text, 0

    unlocked_count = 0

    def _decrypt_sub(match: re.Match) -> str:
        nonlocal unlocked_count
        envelope = match.group(0)
        try:
            plain = decrypt_inline(envelope, passkey)
            unlocked_count += 1
            return plain
        except Exception:
            return envelope  # Keep encrypted if passkey is wrong or corrupted

    unlocked_text = ENCLAVE_PATTERN.sub(_decrypt_sub, text)
    return unlocked_text, unlocked_count
