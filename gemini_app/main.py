"""Executable entry point for the modular Gemini Bilateral Terminal Console."""

from __future__ import annotations

import sys

from gemini_app.config import PROJECTS_DIR
from gemini_app.onboarding import ensure_api_key_on_boot, ensure_first_time_onboarding
from gemini_app.projects import get_user_real_name, set_user_real_name
from gemini_app.storage.rollback import run_with_guardian
from gemini_app.system_deps import check_command_installed, ensure_system_dependencies
from gemini_app.ui.app import ChatApp


def start_app() -> None:
    """Instantiates and executes the ChatApp Textual application."""
    app = ChatApp()
    app.run()


def main() -> None:
    """Launches the console application protected by the autonomous crash guardian."""
    # 1. Ensure Projects directory exists in user's home directory
    try:
        PROJECTS_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    except Exception:
        pass

    # 2. Autonomous dependency check: if git is missing, install autonomously based on OS check
    if not check_command_installed("git"):
        try:
            ensure_system_dependencies(required=["git"])
        except Exception:
            pass

    # 3. First-time boot onboarding: prompts for Real Name, Git credentials & configures Git, and API key
    try:
        ensure_first_time_onboarding(interactive=sys.stdin.isatty())
    except Exception:
        try:
            ensure_api_key_on_boot(interactive=sys.stdin.isatty())
        except Exception:
            pass

    # 4. Ensure user real name for copyright is initialized in state
    try:
        set_user_real_name(get_user_real_name())
    except Exception:
        pass

    # 5. Launch console UI inside the guardian
    run_with_guardian(start_app)


if __name__ == "__main__":
    main()
