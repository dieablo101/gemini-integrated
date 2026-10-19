"""Executable entry point for the modular Gemini Bilateral Terminal Console."""

from __future__ import annotations

from gemini_app.storage.rollback import run_with_guardian
from gemini_app.ui.app import ChatApp


def start_app() -> None:
    """Instantiates and executes the ChatApp Textual application."""
    app = ChatApp()
    app.run()


def main() -> None:
    """Launches the console application protected by the autonomous crash guardian."""
    run_with_guardian(start_app)


if __name__ == "__main__":
    main()
