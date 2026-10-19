"""First-time boot onboarding and Gemini API Key configuration.

Prompts user on initial launch for GEMINI_API_KEY and persists it across
environment variables (~/.bashrc, ~/.zshrc, ~/.profile), ~/.gemini/.env,
and state.json.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any

from gemini_app.config import GEMINI_HOME, STATE_FILE

DOTENV_FILE: Path = GEMINI_HOME / ".env"
SHELL_CONFIG_FILES: list[Path] = [
    Path.home() / ".bashrc",
    Path.home() / ".zshrc",
    Path.home() / ".profile",
    Path.home() / ".bash_profile",
]


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


def ensure_api_key_on_boot(interactive: bool = True) -> str | None:
    """Checks for GEMINI_API_KEY and prompts user on first boot if missing."""
    existing_key = get_stored_api_key()
    if existing_key:
        return existing_key

    if not interactive or not sys.stdin.isatty():
        return None

    # First boot interactive terminal prompt
    print()
    print("\033[1;36m╭─────────────────────────────────────────────────────────────────╮\033[0m")
    print("\033[1;36m│             GEMINI INTEGRATED — FIRST TIME ONBOARDING           │\033[0m")
    print("\033[1;36m╰─────────────────────────────────────────────────────────────────╯\033[0m")
    print("\033[1mWelcome! Gemini Integrated requires a Google Gemini API key.\033[0m")
    print("If you do not have one yet, you can create one at:")
    print("\033[4;34mhttps://aistudio.google.com/app/apikey\033[0m")
    print()

    try:
        entered_key = getpass.getpass("Enter your Google Gemini API Key: ").strip()
    except Exception:
        try:
            entered_key = input("Enter your Google Gemini API Key: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            return None

    if entered_key:
        save_gemini_api_key(entered_key)
        print(f"\033[1;32m✓ Saved GEMINI_API_KEY to environment variables & ~/.bashrc\033[0m\n")
        return entered_key

    return None
