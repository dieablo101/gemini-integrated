"""Executable entry point for the modular Gemini Bilateral Terminal Console."""

from __future__ import annotations

from gemini_app.ui.app import ChatApp


def main() -> None:
    """Instantiates and executes the ChatApp Textual application."""
    app = ChatApp()
    app.run()


if __name__ == "__main__":
    main()
