"""First-time boot onboarding: Real Name, Git credentials, and Gemini API Key configuration.

Prompts user on initial launch for:
1. Real Name (for project licensing, README attribution, and git commits)
2. Git credentials (global user.name and user.email)
3. Google Gemini API Key

Persists configurations across git config, ~/.gemini/.env, state.json,
and user shell startup files.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from gemini_app.config import GEMINI_HOME, STATE_FILE
from gemini_app.fleet.keys import (
    generate_cluster_keypair,
    get_or_create_cluster_ssh_key,
    get_stored_cluster_key_path,
    save_cluster_key_path,
)
from gemini_app.projects import get_user_real_name, set_user_real_name
from gemini_app.vault import is_vault_configured, set_vault_passkey, verify_vault_passkey

DOTENV_FILE: Path = GEMINI_HOME / ".env"
SHELL_CONFIG_FILES: list[Path] = [
    Path.home() / ".bashrc",
    Path.home() / ".zshrc",
    Path.home() / ".profile",
    Path.home() / ".bash_profile",
]


def get_git_config(key: str) -> str | None:
    """Reads a git configuration setting via `git config --get <key>`."""
    git_bin = shutil.which("git")
    if not git_bin:
        return None
    try:
        proc = subprocess.run(
            [git_bin, "config", "--get", key],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            val = proc.stdout.strip()
            if val:
                return val
    except Exception:
        pass
    return None


def set_git_config(key: str, value: str, scope: str = "--global") -> bool:
    """Sets a git configuration setting via `git config <scope> <key> <value>`."""
    git_bin = shutil.which("git")
    if not git_bin or not value:
        return False
    try:
        proc = subprocess.run(
            [git_bin, "config", scope, key, value],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def get_stored_user_real_name() -> str | None:
    """Returns stored user real name from state.json or git config."""
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            val = state.get("user_realname") or state.get("user_real_name") or state.get("copyright_name")
            if val and str(val).strip():
                return str(val).strip()
        except Exception:
            pass
    return get_git_config("user.name")


def get_stored_git_email() -> str | None:
    """Returns stored git email from state.json or git config."""
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            val = state.get("git_email") or state.get("user_email")
            if val and str(val).strip():
                return str(val).strip()
        except Exception:
            pass
    return get_git_config("user.email")


def setup_git_credentials(real_name: str = "", email: str = "") -> dict[str, Any]:
    """Configures global git credentials and updates user state.

    Sets git user.name and user.email globally, configures defaultBranch to main
    if unset, and saves the author credentials to state.json.
    """
    clean_name = real_name.strip()
    clean_email = email.strip()
    results: dict[str, Any] = {
        "status": "success",
        "name_configured": False,
        "email_configured": False,
        "default_branch_configured": False,
        "real_name": clean_name,
        "git_email": clean_email,
    }

    if clean_name:
        results["name_configured"] = set_git_config("user.name", clean_name)
        set_user_real_name(clean_name)

    if clean_email:
        results["email_configured"] = set_git_config("user.email", clean_email)

    # Set defaultBranch = main if not already defined
    if not get_git_config("init.defaultBranch"):
        results["default_branch_configured"] = set_git_config("init.defaultBranch", "main")

    # Persist git credentials into state.json
    try:
        state: dict[str, Any] = {}
        if STATE_FILE.is_file():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        if clean_name:
            state["user_realname"] = clean_name
            state["user_real_name"] = clean_name
            state["copyright_name"] = clean_name
            state["git_name"] = clean_name
        if clean_email:
            state["git_email"] = clean_email
        STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass

    return results


def is_first_boot_pending() -> bool:
    """Returns True if the user has not completed first-time boot onboarding."""
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if state.get("onboarding_completed", False):
                return False
        except Exception:
            pass
    return True


def mark_onboarding_completed() -> None:
    """Flags first-time onboarding as completed in state.json."""
    try:
        state: dict[str, Any] = {}
        if STATE_FILE.is_file():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        state["onboarding_completed"] = True
        STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass


def get_stored_api_key() -> str | None:
    """Returns the Gemini API key from environment, ~/.gemini/.env, or state.json."""
    # 1. Direct environment variables
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    # 2. Check ~/.gemini/.env
    if DOTENV_FILE.is_file():
        try:
            for line in DOTENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                        cleaned = v.strip().strip('"').strip("'")
                        if cleaned:
                            os.environ["GEMINI_API_KEY"] = cleaned
                            return cleaned
        except Exception:
            pass

    # 3. Check ~/.gemini/state.json
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            key = state.get("gemini_api_key", "").strip()
            if key:
                os.environ["GEMINI_API_KEY"] = key
                return key
        except Exception:
            pass

    return None


def persist_api_key_to_shell(api_key: str) -> list[str]:
    """Appends export GEMINI_API_KEY to user shell profile files if not already present."""
    clean_key = api_key.strip()
    export_line = f'export GEMINI_API_KEY="{clean_key}"\n'
    updated_files: list[str] = []

    # Ensure .bashrc exists at minimum
    bashrc = Path.home() / ".bashrc"
    if not bashrc.exists():
        try:
            bashrc.touch(mode=0o644)
        except Exception:
            pass

    for shell_file in SHELL_CONFIG_FILES:
        if shell_file.is_file():
            try:
                content = shell_file.read_text(encoding="utf-8")
                if "GEMINI_API_KEY=" in content:
                    # Update existing line if present
                    lines = content.splitlines()
                    new_lines = []
                    replaced = False
                    for line in lines:
                        if line.strip().startswith("export GEMINI_API_KEY=") or line.strip().startswith("GEMINI_API_KEY="):
                            new_lines.append(f'export GEMINI_API_KEY="{clean_key}"')
                            replaced = True
                        else:
                            new_lines.append(line)
                    if replaced:
                        shell_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                        updated_files.append(str(shell_file))
                else:
                    # Append new export block
                    with open(shell_file, "a", encoding="utf-8") as f:
                        f.write(f"\n# Google Gemini API Key configured by Gemini Integrated\n{export_line}")
                    updated_files.append(str(shell_file))
            except Exception:
                continue

    return updated_files


def save_gemini_api_key(api_key: str) -> dict[str, Any]:
    """Saves API key to current environment, .env file, state.json, and shell configs."""
    clean_key = api_key.strip()
    if not clean_key:
        return {"status": "error", "message": "API key cannot be empty."}

    # 1. Set in active process environment
    os.environ["GEMINI_API_KEY"] = clean_key

    # 2. Save to ~/.gemini/.env
    try:
        DOTENV_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        DOTENV_FILE.write_text(f'GEMINI_API_KEY="{clean_key}"\n', encoding="utf-8")
        DOTENV_FILE.chmod(0o600)
    except Exception:
        pass

    # 3. Save to ~/.gemini/state.json
    try:
        state: dict[str, Any] = {}
        if STATE_FILE.is_file():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        state["gemini_api_key"] = clean_key
        STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass

    # 4. Save to shell configs
    updated_shells = persist_api_key_to_shell(clean_key)

    return {
        "status": "success",
        "saved_to_env": True,
        "saved_to_dotenv": str(DOTENV_FILE),
        "updated_shells": updated_shells,
    }


def ensure_first_time_onboarding(interactive: bool = True) -> dict[str, Any]:
    """Orchestrates first-time boot onboarding: Real Name, Git credentials setup, and API key.

    Prompts user on initial launch for:
    1. Real Name (used for Copyright holder in MIT license and Git user.name)
    2. Git Credentials (email and global Git setup)
    3. Google Gemini API Key

    Persists configuration across git config, ~/.gemini/.env, ~/.gemini/state.json,
    and user shell startup files.
    """
    results: dict[str, Any] = {
        "status": "completed",
        "first_boot": False,
        "real_name": None,
        "git_email": None,
        "api_key_configured": False,
    }

    if not is_first_boot_pending():
        # Already onboarded, ensure API key is present in environment
        key = get_stored_api_key()
        results["api_key_configured"] = bool(key)
        results["real_name"] = get_stored_user_real_name()
        results["git_email"] = get_stored_git_email()
        return results

    results["first_boot"] = True

    if not interactive or not sys.stdin.isatty():
        # Non-interactive / headless fallback
        cand_name = get_stored_user_real_name() or get_git_config("user.name")
        cand_email = get_stored_git_email() or get_git_config("user.email")
        if cand_name or cand_email:
            setup_git_credentials(cand_name or "", cand_email or "")
        key = get_stored_api_key()
        results["real_name"] = cand_name
        results["git_email"] = cand_email
        results["api_key_configured"] = bool(key)
        # Ensure cluster key exists
        cluster_k = get_or_create_cluster_ssh_key()
        if cluster_k:
            results["ssh_key_path"] = str(cluster_k)
        mark_onboarding_completed()
        return results

    # Interactive first boot onboarding
    print()
    print("\033[1;36m╭─────────────────────────────────────────────────────────────────╮\033[0m")
    print("\033[1;36m│             GEMINI INTEGRATED — FIRST TIME ONBOARDING           │\033[0m")
    print("\033[1;36m╰─────────────────────────────────────────────────────────────────╯\033[0m")
    print("\033[1mWelcome! Let's get your development environment configured.\033[0m\n")

    # 1. Real Name
    default_name = get_stored_user_real_name() or get_git_config("user.name") or ""
    prompt_name = f"Enter your Real Name (for project Copyright & Git) [{default_name}]: " if default_name else "Enter your Real Name (for project Copyright & Git): "
    try:
        name_val = input(prompt_name).strip()
        real_name = name_val if name_val else default_name
    except (KeyboardInterrupt, EOFError):
        print("\nSetup skipped.")
        return {"status": "aborted"}

    # 2. Git Credentials & Email
    default_email = get_stored_git_email() or get_git_config("user.email") or ""
    prompt_email = f"Enter your Git Email (for commits & git config) [{default_email}]: " if default_email else "Enter your Git Email (for commits & git config): "
    try:
        email_val = input(prompt_email).strip()
        git_email = email_val if email_val else default_email
    except (KeyboardInterrupt, EOFError):
        print("\nSetup skipped.")
        return {"status": "aborted"}

    if real_name or git_email:
        setup_git_credentials(real_name=real_name, email=git_email)
        print(f"\033[1;32m✓ Git credentials configured globally (name: '{real_name}', email: '{git_email}')\033[0m")
        results["real_name"] = real_name
        results["git_email"] = git_email

    # 3. Google Gemini API Key
    existing_key = get_stored_api_key()
    if not existing_key:
        print("\nA Google Gemini API key is required for AI inference.")
        print("You can obtain a free key at: \033[4;34mhttps://aistudio.google.com/app/apikey\033[0m\n")
        try:
            entered_key = getpass.getpass("Enter your Google Gemini API Key: ").strip()
        except Exception:
            try:
                entered_key = input("Enter your Google Gemini API Key: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nSetup aborted.")
                return {"status": "aborted"}

        if entered_key:
            save_gemini_api_key(entered_key)
            print("\033[1;32m✓ Saved GEMINI_API_KEY to environment & ~/.bashrc\033[0m")
            results["api_key_configured"] = True
    else:
        print("\033[1;32m✓ Google Gemini API Key verified.\033[0m")
        results["api_key_configured"] = True

    # 4. Vault Passkey (protects sensitive tokens & recovery keys in ~/.gemini/vault)
    if not is_vault_configured():
        print("\nA Vault Passkey protects sensitive tokens and recovery files in ~/.gemini/vault.")
        while True:
            try:
                vault_pass = getpass.getpass("Enter Vault Passkey (or press Enter to skip): ").strip()
                if not vault_pass:
                    results["vault_configured"] = False
                    break
                confirm_pass = getpass.getpass("Confirm Vault Passkey: ").strip()
                if vault_pass == confirm_pass:
                    set_vault_passkey(vault_pass)
                    print("\033[1;32m✓ Vault configured with salted PBKDF2-HMAC-SHA256 passkey.\033[0m")
                    results["vault_configured"] = True
                    break
                else:
                    print("\033[1;31mPasskeys do not match. Please try again (or press Enter to skip).\033[0m")
            except (KeyboardInterrupt, EOFError):
                results["vault_configured"] = False
                break
    else:
        results["vault_configured"] = True

    # 5. Fleet / Cluster SSH Key Setup
    existing_ssh = get_stored_cluster_key_path()
    if not existing_ssh:
        print("\nGemini Fleet allows distributed satellite nodes (iPad, Android, remote servers) with SSH rescue.")
        default_cluster_key = GEMINI_HOME / "fleet" / "id_cluster"
        prompt_ssh = f"Enter path to your SSH private key for node rescue [press Enter to auto-generate {default_cluster_key.name}]: "
        try:
            ssh_input = input(prompt_ssh).strip()
            if ssh_input:
                expanded = Path(os.path.expanduser(ssh_input)).resolve()
                if expanded.is_file():
                    save_cluster_key_path(expanded)
                    print(f"\033[1;32m✓ Configured cluster SSH key: {expanded}\033[0m")
                    results["ssh_key_path"] = str(expanded)
                else:
                    print(f"\033[1;33mSpecified path '{ssh_input}' not found. Generating default cluster keypair...\033[0m")
                    priv, _ = generate_cluster_keypair()
                    save_cluster_key_path(priv)
                    print(f"\033[1;32m✓ Generated cluster Ed25519 keypair: {priv}\033[0m")
                    results["ssh_key_path"] = str(priv)
            else:
                priv, _ = generate_cluster_keypair()
                save_cluster_key_path(priv)
                print(f"\033[1;32m✓ Auto-generated cluster Ed25519 keypair: {priv}\033[0m")
                results["ssh_key_path"] = str(priv)
        except (KeyboardInterrupt, EOFError):
            priv, _ = generate_cluster_keypair()
            save_cluster_key_path(priv)
            results["ssh_key_path"] = str(priv)
    else:
        results["ssh_key_path"] = str(existing_ssh)

    mark_onboarding_completed()
    print("\n\033[1;32m✓ First-time setup complete! Launching Gemini Integrated...\033[0m\n")
    return results


def ensure_api_key_on_boot(interactive: bool = True) -> str | None:
    """Checks for GEMINI_API_KEY and prompts user on first boot if missing (backwards-compatible)."""
    existing_key = get_stored_api_key()
    if existing_key:
        return existing_key

    if not interactive or not sys.stdin.isatty():
        return None

    res = ensure_first_time_onboarding(interactive=True)
    return get_stored_api_key()
