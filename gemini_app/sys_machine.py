"""System-level infrastructure management: ~/.sys directory and SSH Machine.

Manages the system-level ~/.sys folder for host-specific tools and scripts,
installs bulletproof POSIX ssh-agent deduplication and key loading (~/.sys/ssh_machine.sh),
and hooks into shell startup configurations (~/.bashrc, ~/.zshrc, ~/.profile).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from gemini_app.config import GEMINI_HOME
from gemini_app.fleet.keys import (
    DEFAULT_CLUSTER_KEY,
    get_or_create_cluster_ssh_key,
    get_stored_cluster_key_path,
)

SYS_DIR: Path = Path.home() / ".sys"
SSH_MACHINE_PATH: Path = SYS_DIR / "ssh_machine.sh"

SHELL_PROFILES: List[Path] = [
    Path.home() / ".bashrc",
    Path.home() / ".zshrc",
    Path.home() / ".profile",
    Path.home() / ".bash_profile",
]

SHELL_HOOK_SNIPPET: str = """
# SSH Machine: Bulletproof agent deduplication & key management (Gemini Integrated)
if [ -f "$HOME/.sys/ssh_machine.sh" ]; then
    . "$HOME/.sys/ssh_machine.sh"
fi
"""

SSH_MACHINE_TEMPLATE: str = """#!/bin/sh
# ==============================================================================
# SSH Machine — Bulletproof Agent Deduplication & Key Loader
# Managed by Gemini Integrated Console
# ==============================================================================

# 1. Resolve Target SSH Key
# Hierarchy: $GEMINI_SSH_KEY env -> ~/.gemini/config.json -> fallback key
TARGET_KEY=""

if [ -n "$GEMINI_SSH_KEY" ] && [ -f "$GEMINI_SSH_KEY" ]; then
    TARGET_KEY="$GEMINI_SSH_KEY"
elif [ -f "$HOME/.gemini/config.json" ]; then
    TARGET_KEY=$(sed -n 's/^[[:space:]]*"ssh_key_path"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' "$HOME/.gemini/config.json" 2>/dev/null)
fi

# Fallback to configured target key if config extraction didn't resolve an existing file
if [ -z "$TARGET_KEY" ] || [ ! -f "$TARGET_KEY" ]; then
    TARGET_KEY="__TARGET_KEY_PLACEHOLDER__"
fi

# Fallback search if still unresolved
if [ ! -f "$TARGET_KEY" ]; then
    for candidate in "$HOME/.gemini/fleet/id_cluster" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
        if [ -f "$candidate" ]; then
            TARGET_KEY="$candidate"
            break
        fi
    done
fi

# 2. Agent Deduplication & Health Check
# Agent is healthy if SSH_AUTH_SOCK is set, is a socket, and ssh-add -l returns 0 or 1 (not 2 = unreachable)
agent_healthy() {
    if [ -n "$SSH_AUTH_SOCK" ] && [ -S "$SSH_AUTH_SOCK" ]; then
        ssh-add -l > /dev/null 2>&1
        status=$?
        [ "$status" -ne 2 ] && return 0
    fi
    return 1
}

if ! agent_healthy; then
    eval "$(ssh-agent -s)" > /dev/null 2>&1
fi

# 3. Key Ring Verification & Load
if [ -f "$TARGET_KEY" ]; then
    TARGET_FP=$(ssh-keygen -lf "$TARGET_KEY" 2>/dev/null | awk '{print $2}')
    KEY_NAME=$(basename "$TARGET_KEY")

    KEY_LOADED=0
    if [ -n "$TARGET_FP" ] && ssh-add -l 2>/dev/null | grep -q -F "$TARGET_FP"; then
        KEY_LOADED=1
    elif ssh-add -l 2>/dev/null | grep -q "$KEY_NAME"; then
        KEY_LOADED=1
    fi

    if [ "$KEY_LOADED" -eq 0 ]; then
        ssh-add "$TARGET_KEY" > /dev/null 2>&1
    fi
fi
"""


def ensure_sys_directory() -> Path:
    """Ensures ~/.sys directory exists for machine-specific scripts and tools."""
    SYS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        SYS_DIR.chmod(0o755)
    except Exception:
        pass
    return SYS_DIR


def get_public_key(priv_key_path: Path | str) -> Optional[str]:
    """Retrieves or derives the OpenSSH public key for a given private key."""
    p = Path(os.path.expanduser(str(priv_key_path))).resolve()
    if not p.is_file():
        return None

    # 1. Check for standard .pub companion file
    pub_file = Path(str(p) + ".pub")
    if pub_file.is_file():
        try:
            content = pub_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    # 2. Derive on the fly via ssh-keygen -y -f
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen:
        try:
            res = subprocess.run(
                [ssh_keygen, "-y", "-f", str(p)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                derived = res.stdout.strip()
                # Optionally cache it back as .pub
                try:
                    pub_file.write_text(derived + "\n", encoding="utf-8")
                    pub_file.chmod(0o644)
                except Exception:
                    pass
                return derived
        except Exception:
            pass

    return None


def build_ssh_machine_script(target_key: Path | str | None = None) -> str:
    """Builds the bulletproof POSIX shell script content for ~/.sys/ssh_machine.sh."""
    resolved_str = ""
    if target_key:
        resolved_str = str(Path(os.path.expanduser(str(target_key))).resolve())

    return SSH_MACHINE_TEMPLATE.replace("__TARGET_KEY_PLACEHOLDER__", resolved_str)


def install_ssh_machine(target_key: Path | str | None = None) -> Path:
    """Installs or updates ~/.sys/ssh_machine.sh with bulletproof deduplication and key loading."""
    ensure_sys_directory()

    # Determine default target key if none provided
    resolved_key = target_key or get_stored_cluster_key_path() or get_or_create_cluster_ssh_key()
    script_content = build_ssh_machine_script(resolved_key)

    SSH_MACHINE_PATH.write_text(script_content, encoding="utf-8")
    try:
        SSH_MACHINE_PATH.chmod(0o755)
    except Exception:
        pass

    return SSH_MACHINE_PATH


def hook_ssh_machine_to_shells() -> List[str]:
    """Ensures ~/.sys/ssh_machine.sh is sourced in user shell profile files.

    Scans ~/.bashrc, ~/.zshrc, ~/.profile, and ~/.bash_profile without creating duplicates.
    Returns list of modified file paths.
    """
    updated: List[str] = []

    # Ensure at least ~/.profile exists if neither .bashrc nor .profile exist
    primary_bashrc = Path.home() / ".bashrc"
    primary_profile = Path.home() / ".profile"
    if not primary_bashrc.exists() and not primary_profile.exists():
        try:
            primary_profile.touch(mode=0o644)
        except Exception:
            pass

    for shell_file in SHELL_PROFILES:
        if shell_file.is_file():
            try:
                content = shell_file.read_text(encoding="utf-8", errors="ignore")
                # Check if ssh_machine.sh is already invoked
                if "ssh_machine.sh" in content:
                    continue

                with open(shell_file, "a", encoding="utf-8") as f:
                    f.write(SHELL_HOOK_SNIPPET)
                updated.append(str(shell_file))
            except Exception:
                continue

    return updated


def sync_system_ssh_machine(target_key: Path | str | None = None) -> Dict[str, Any]:
    """Orchestrates complete machine-level setup: ~/.sys folder, ssh_machine.sh, and shell hooks.

    Returns summary dictionary with paths and public key information.
    """
    ensure_sys_directory()

    # Determine key
    chosen_key = target_key or get_stored_cluster_key_path() or get_or_create_cluster_ssh_key()
    script_path = install_ssh_machine(chosen_key)
    hooked_shells = hook_ssh_machine_to_shells()

    pub_key = None
    if chosen_key:
        pub_key = get_public_key(chosen_key)

    return {
        "sys_dir": str(SYS_DIR),
        "ssh_machine_script": str(script_path),
        "target_key": str(chosen_key) if chosen_key else None,
        "public_key": pub_key,
        "hooked_shells": hooked_shells,
    }
