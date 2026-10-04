#!/opt/gemini/.venv/bin/python3
"""Application entrypoint."""

from gemini_app.app import ChatApp

def main() -> None:
    app = ChatApp()
    app.run()

if __name__ == "__main__":
    main()
