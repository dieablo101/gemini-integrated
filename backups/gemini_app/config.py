"""Configuration constants and path definitions."""

from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
CHATS_DIR = Path("chats")
CHATS_DIR.mkdir(exist_ok=True)
SOCKET_PATH = Path("/tmp/gemini_textual.sock")

# Model Configuration
DEFAULT_MODEL = "gemini-3.8-flash"
