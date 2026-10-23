"""Persistence manager for sharded chats, legacy JSON files, notes, and session state."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
from typing import Any
from uuid import uuid4

from gemini_app.config import (
    ARCHIVE_DIR,
    CHATS_DIR,
    STATE_FILE,
    TURNS_PER_SEGMENT,
)


class ChatStore:
    """Manages chat persistence, sharding, and session state on disk."""

    def __init__(
        self,
        chats_dir: Path | str = CHATS_DIR,
        archive_dir: Path | str = ARCHIVE_DIR,
        state_file: Path | str = STATE_FILE,
    ) -> None:
        self.chats_dir = Path(chats_dir)
        self.archive_dir = Path(archive_dir)
        self.state_file = Path(state_file)
        self.chats_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.archive_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def get_chat_dir(self, chat_id: str) -> Path:
        return self.chats_dir / chat_id

    def get_legacy_chat_file(self, chat_id: str) -> Path:
        return self.chats_dir / f"{chat_id}.json"

    def list_chats(self) -> list[dict[str, Any]]:
        """Scans chats directory returning metadata for all legacy and sharded chats."""
        entries: list[dict[str, Any]] = []

        if not self.chats_dir.exists():
            return entries

        for item in self.chats_dir.iterdir():
            if item.name.startswith("."):
                continue

            # Modern Sharded Chat Directory
            if item.is_dir():
                meta_file = item / "meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        entries.append({
                            "id": meta.get("id", item.name),
                            "title": meta.get("title") or "Untitled Chat",
                            "updated_at": meta.get("updated_at", item.stat().st_mtime),
                            "working_dir": meta.get("working_dir"),
                            "parent_id": meta.get("parent_id"),
                            "notes": meta.get("notes", ""),
                            "is_legacy": False,
                            "turns_count": meta.get("storage", {}).get("total_turns", 0),
                        })
                    except Exception:
                        pass
                continue

            # Legacy Single JSON File
            if item.is_file() and item.suffix == ".json":
                try:
                    data = json.loads(item.read_text(encoding="utf-8"))
                    entries.append({
                        "id": data.get("id", item.stem),
                        "title": data.get("title") or "Untitled Chat",
                        "updated_at": data.get("updated_at", item.stat().st_mtime),
                        "working_dir": data.get("working_dir"),
                        "parent_id": data.get("parent_id"),
                        "notes": data.get("notes", ""),
                        "is_legacy": True,
                        "turns_count": len(data.get("messages", [])),
                    })
                except Exception:
                    pass

        entries.sort(key=lambda x: x["updated_at"], reverse=True)
        return entries

    def load_chat(self, chat_id: str) -> dict[str, Any]:
        """Loads a chat by ID, seamlessly handling legacy JSON or sharded directory."""
        legacy_file = self.get_legacy_chat_file(chat_id)
        chat_dir = self.get_chat_dir(chat_id)

        if legacy_file.exists():
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            raw_messages = data.get("messages", [])
            history = []
            for m in raw_messages:
                m_copy = dict(m)
                if "turn_id" not in m_copy or not m_copy["turn_id"]:
                    m_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
                history.append(m_copy)

            notes_raw = data.get("notes", "")
            if isinstance(notes_raw, dict):
                notes_bundle = {
                    "gemini_notes": notes_raw.get("gemini_notes", ""),
                    "global_notes": notes_raw.get("global_notes", ""),
                    "relational_notes": notes_raw.get("relational_notes", {}),
                }
                notes_text = notes_raw.get("gemini_notes", "") or notes_raw.get("global_notes", "")
            else:
                notes_text = str(notes_raw or "")
                notes_bundle = {
                    "gemini_notes": notes_text,
                    "global_notes": "",
                    "relational_notes": {},
                }

            return {
                "id": chat_id,
                "is_legacy": True,
                "title": data.get("title", ""),
                "working_dir": data.get("working_dir"),
                "parent_id": data.get("parent_id"),
                "notes": notes_text,
                "notes_bundle": notes_bundle,
                "last_turn_index": data.get("last_turn_index"),
                "center_marker": data.get("center_marker", ""),
                "history": history,
                "mind_map": {
                    "gemini_state": "Unified Console: Autonomous Relational Mind & Archival Engine",
                    "user_state": "Continuing unified session.",
                    "tree_state": ["T1", "F:gemini_app/"],
                    "tree_content": "└── Unified Stream [Active]",
                },
            }

        if chat_dir.is_dir() and (chat_dir / "meta.json").exists():
            meta_path = chat_dir / "meta.json"
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            viewport = meta_data.get("viewport", {})

            history = []
            segment_files = sorted(
                chat_dir.glob("segment_*.json"),
                key=lambda f: int(f.stem.split("_")[1]) if "_" in f.stem else 0,
            )
            for sf in segment_files:
                try:
                    seg_turns = json.loads(sf.read_text(encoding="utf-8"))
                    for m in seg_turns:
                        m_copy = dict(m)
                        if "turn_id" not in m_copy or not m_copy["turn_id"]:
                            m_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
                        history.append(m_copy)
                except Exception:
                    pass

            notes_raw = meta_data.get("notes", "")
            if isinstance(notes_raw, dict):
                notes_bundle = {
                    "gemini_notes": notes_raw.get("gemini_notes", ""),
                    "global_notes": notes_raw.get("global_notes", ""),
                    "relational_notes": notes_raw.get("relational_notes", {}),
                }
                notes_text = notes_raw.get("gemini_notes", "") or notes_raw.get("global_notes", "")
            else:
                notes_text = str(notes_raw or "")
                notes_bundle = {
                    "gemini_notes": notes_text,
                    "global_notes": "",
                    "relational_notes": {},
                }

            stored_mind = meta_data.get("mind_map", {})
            gem_state = stored_mind.get("gemini_state")
            if not gem_state or gem_state == "Legacy active session.":
                gem_state = "Unified Console: Autonomous Relational Mind & Archival Engine"
            usr_state = stored_mind.get("user_state") or "Continuing unified session."
            tree_content = stored_mind.get("tree_content") or "└── Unified Stream [Active]"
            tree_state = stored_mind.get("tree_state", ["T1", "F:gemini_app/"])

            return {
                "id": chat_id,
                "is_legacy": False,
                "title": meta_data.get("title", ""),
                "working_dir": meta_data.get("working_dir"),
                "parent_id": meta_data.get("parent_id"),
                "notes": notes_text,
                "notes_bundle": notes_bundle,
                "last_turn_index": viewport.get("last_turn_index"),
                "center_marker": viewport.get("center_marker", ""),
                "history": history,
                "mind_map": {
                    "gemini_state": gem_state,
                    "user_state": usr_state,
                    "tree_state": tree_state,
                    "tree_content": tree_content,
                },
            }

        # Return empty record if chat does not exist
        return {
            "id": chat_id,
            "is_legacy": False,
            "title": "",
            "working_dir": None,
            "parent_id": None,
            "notes": "",
            "last_turn_index": 0,
            "center_marker": "",
            "history": [],
            "mind_map": {
                "gemini_state": "",
                "user_state": "",
                "tree_state": [],
                "tree_content": "",
            },
        }

    def save_chat(
        self,
        chat_id: str,
        title: str,
        history: list[dict[str, Any]],
        notes: str | dict[str, Any] = "",
        working_dir: str | None = None,
        parent_id: str | None = None,
        last_turn_index: int = 0,
        center_marker: str = "",
        mind_map: dict[str, Any] | None = None,
        is_legacy: bool = False,
    ) -> None:
        """Saves chat data into sharded directory or legacy JSON file with inline cryptographic redaction."""
        if not chat_id:
            return

        mind_map = mind_map or {}
        passkey = None
        try:
            from gemini_app.vault import get_session_passkey
            passkey = get_session_passkey()
        except Exception:
            pass

        from gemini_app.security.redaction import redact_secrets_in_text

        sanitized_history = []
        for m in history:
            m_copy = dict(m)
            if "turn_id" not in m_copy or not m_copy["turn_id"]:
                m_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
            if "text" in m_copy and isinstance(m_copy["text"], str):
                redacted_text, _ = redact_secrets_in_text(m_copy["text"], passkey=passkey)
                m_copy["text"] = redacted_text
            sanitized_history.append(m_copy)

        if is_legacy:
            path = self.get_legacy_chat_file(chat_id)
            existing_data = {}
            if path.exists():
                try:
                    existing_data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing_data = {}

            data = {
                **existing_data,
                "id": chat_id,
                "title": title,
                "parent_id": parent_id,
                "updated_at": time.time(),
                "working_dir": working_dir,
                "last_turn_index": last_turn_index,
                "center_marker": center_marker,
                "notes": notes,
                "messages": sanitized_history,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            chat_dir = self.get_chat_dir(chat_id)
            chat_dir.mkdir(parents=True, exist_ok=True)

            total_turns = len(sanitized_history)
            seg_count = max(1, (total_turns + TURNS_PER_SEGMENT - 1) // TURNS_PER_SEGMENT) if total_turns > 0 else 1
            active_seg = max(0, seg_count - 1)

            meta_data = {
                "id": chat_id,
                "title": title,
                "parent_id": parent_id,
                "updated_at": time.time(),
                "working_dir": working_dir,
                "notes": notes,
                "viewport": {
                    "last_turn_index": last_turn_index,
                    "center_marker": center_marker,
                },
                "storage": {
                    "total_turns": total_turns,
                    "segment_count": seg_count,
                    "active_segment": active_seg,
                    "max_segment_size": TURNS_PER_SEGMENT,
                },
                "mind_map": {
                    "gemini_state": mind_map.get("gemini_state", ""),
                    "user_state": mind_map.get("user_state", ""),
                    "tree_state": mind_map.get("tree_state", []),
                    "tree_content": mind_map.get("tree_content", ""),
                },
            }
            (chat_dir / "meta.json").write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

            # Write segment files
            for s_idx in range(seg_count):
                start = s_idx * TURNS_PER_SEGMENT
                end = start + TURNS_PER_SEGMENT
                seg_slice = sanitized_history[start:end]
                seg_file = chat_dir / f"segment_{s_idx}.json"
                seg_file.write_text(json.dumps(seg_slice, indent=2), encoding="utf-8")

        self.save_state_key("active_chat", chat_id)

    def flush_chat_notes(self, chat_id: str, notes_text: str | dict[str, Any]) -> None:
        """Flushes chat notes directly to disk without rewriting entire message history."""
        if not chat_id:
            return

        legacy_path = self.get_legacy_chat_file(chat_id)
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
                data["notes"] = notes_text
                legacy_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return
            except Exception:
                pass

        chat_dir = self.get_chat_dir(chat_id)
        meta_file = chat_dir / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["notes"] = notes_text
                meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            except Exception:
                pass

    def delete_chat(self, chat_id: str) -> None:
        """Deletes a chat directory or legacy JSON file."""
        legacy_file = self.get_legacy_chat_file(chat_id)
        if legacy_file.exists():
            legacy_file.unlink()

        chat_dir = self.get_chat_dir(chat_id)
        if chat_dir.is_dir():
            for child in chat_dir.iterdir():
                child.unlink()
            chat_dir.rmdir()

    def archive_chat(self, chat_id: str) -> bool:
        """Moves a chat directory or legacy JSON file into the .archive folder."""
        legacy_file = self.get_legacy_chat_file(chat_id)
        if legacy_file.exists():
            shutil.move(str(legacy_file), str(self.archive_dir / legacy_file.name))
            return True

        chat_dir = self.get_chat_dir(chat_id)
        if chat_dir.is_dir():
            dest = self.archive_dir / chat_dir.name
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.move(str(chat_dir), str(dest))
            return True

        return False

    def load_state(self) -> dict[str, Any]:
        """Loads persistent console state from state.json."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_state_key(self, key: str, value: Any) -> None:
        """Atomically saves a key-value pair to state.json."""
        state = self.load_state()
        state[key] = value
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
