"""Fleet and cluster SSH key management and configuration.

Manages persistent SSH key configuration stored in ~/.gemini/config.json,
auto-generates dedicated Ed25519 cluster keypairs (~/.gemini/fleet/id_cluster)
when none are configured, and eliminates hardcoded personal user/key assumptions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

from gemini_app.config import GEMINI_HOME

FLEET_DIR: Path = GEMINI_HOME / "fleet"
CONFIG_FILE: Path = GEMINI_HOME / "config.json"
DEFAULT_CLUSTER_KEY: Path = FLEET_DIR / "id_cluster"


def get_stored_cluster_key_path() -> Optional[Path]:
    """Retrieves the configured cluster SSH key path from ~/.gemini/config.json or environment."""
    # 1. Environment variable override
    env_key = os.environ.get("GEMINI_SSH_KEY", "").strip() or os.environ.get("GEMINI_FLEET_SSH_KEY", "").strip()
    if env_key:
        p = Path(os.path.expanduser(env_key)).resolve()
        if p.exists() and p.is_file():
            return p

    # 2. Check ~/.gemini/config.json
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            val = cfg.get("ssh_key_path") or cfg.get("cluster_ssh_key") or cfg.get("fleet_ssh_key")
            if val and str(val).strip():
                p = Path(os.path.expanduser(str(val).strip())).resolve()
                if p.exists() and p.is_file():
                    return p
        except Exception:
            pass

    return None


def save_cluster_key_path(key_path: Path | str) -> bool:
    """Persists the SSH key path in ~/.gemini/config.json."""
    try:
        clean_path = str(Path(os.path.expanduser(str(key_path))).resolve())
        cfg: Dict[str, Any] = {}
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}

        cfg["ssh_key_path"] = clean_path
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        CONFIG_FILE.chmod(0o600)
        return True
    except Exception:
        return False


def generate_cluster_keypair(key_path: Optional[Path] = None, comment: str = "gemini-cluster") -> Tuple[Path, Path]:
    """Generates a secure Ed25519 SSH keypair if not already present.

    Returns tuple: (private_key_path, public_key_path).
    """
    target_priv = key_path or DEFAULT_CLUSTER_KEY
    target_pub = Path(str(target_priv) + ".pub")

    target_priv.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_priv.parent.chmod(0o700)
    except Exception:
        pass

    if target_priv.exists() and target_pub.exists():
        return target_priv, target_pub

    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen:
        cmd = [
            ssh_keygen,
            "-t", "ed25519",
            "-N", "",  # Empty passphrase for cluster automation
            "-C", comment,
            "-f", str(target_priv),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                target_priv.chmod(0o600)
                target_pub.chmod(0o644)
            except Exception:
                pass
            save_cluster_key_path(target_priv)
            return target_priv, target_pub

    # Fallback: if ssh-keygen is unavailable, generate an empty template or return target
    return target_priv, target_pub


def get_cluster_ssh_key() -> Optional[Path]:
    """Finds or creates the cluster SSH private key using setup configuration."""
    return get_or_create_cluster_ssh_key()


def get_or_create_cluster_ssh_key() -> Optional[Path]:
    """Finds the configured cluster key, standard SSH keys in ~/.ssh, or auto-generates ~/.gemini/fleet/id_cluster."""
    # 1. Configured key in ~/.gemini/config.json or env
    configured = get_stored_cluster_key_path()
    if configured:
        return configured

    # 2. Check if default cluster key already exists
    if DEFAULT_CLUSTER_KEY.exists() and DEFAULT_CLUSTER_KEY.is_file():
        save_cluster_key_path(DEFAULT_CLUSTER_KEY)
        return DEFAULT_CLUSTER_KEY

    # 3. Search standard user ~/.ssh directory for existing keys
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.exists():
        # Check standard modern keys first
        for name in ["id_ed25519", "id_rsa", "id_ecdsa"]:
            candidate = ssh_dir / name
            if candidate.exists() and candidate.is_file():
                save_cluster_key_path(candidate)
                return candidate

        # Check for any existing non-.pub key file
        try:
            for f in ssh_dir.iterdir():
                if f.is_file() and not f.name.endswith(".pub") and not f.name.startswith("known_hosts") and not f.name.startswith("config"):
                    # Basic check for private key text header
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        if "PRIVATE KEY" in content:
                            save_cluster_key_path(f)
                            return f
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. Auto-generate dedicated cluster keypair in ~/.gemini/fleet/id_cluster
    priv, _ = generate_cluster_keypair()
    if priv.exists() and priv.is_file():
        return priv

    return None
