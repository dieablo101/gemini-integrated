"""Chat history disk persistence layer."""

import json
from pathlib import Path
import time
from uuid import uuid4

from gemini_app.config import CHATS_DIR


def get_chat_file(chat_id: str) -> Path:
    return CHATS_DIR / f"{chat_id}.json"


def get_sorted_chat_files() -> list[Path]:
    return sorted(
        CHATS_DIR.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )


def load_chat_data(chat_id: str) -> dict | None:
    path = get_chat_file(chat_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_chat(chat_id: str, title: str, messages: list[dict]) -> str:
    path = get_chat_file(chat_id)
    clean_title = title.strip()
    if not clean_title and messages:
        clean_title = messages[0]["text"][:28].replace("\n", " ")
    if not clean_title:
        clean_title = "New Chat"

    data = {
        "id": chat_id,
        "title": clean_title,
        "updated_at": time.time(),
        "messages": messages,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return clean_title


def update_chat_title(chat_id: str, new_title: str) -> bool:
    path = get_chat_file(chat_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["title"] = new_title.strip()
        data["updated_at"] = time.time()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def delete_chat(chat_id: str) -> bool:
    path = get_chat_file(chat_id)
    if path.exists():
        path.unlink()
        return True
    return False


def create_chat_session(title: str = "") -> tuple[str, str]:
    chat_id = uuid4().hex[:8]
    return chat_id, title
