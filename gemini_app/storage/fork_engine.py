"""Fork engine managing lineage, turn branching, and ancestral note resolution."""

from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

from gemini_app.config import FORK_HEADER_TEXT
from gemini_app.storage.chat_store import ChatStore


class ForkEngine:
    """Handles branching conversations into isolated sub-chats with traceable lineage."""

    def __init__(self, chat_store: ChatStore) -> None:
        self.store = chat_store

    def create_fork(
        self,
        parent_id: str,
        parent_history: list[dict[str, Any]],
        selected_indices: list[int],
        fork_title: str = "",
        working_dir: str | None = None,
        notes: str = "",
    ) -> tuple[str, list[dict[str, Any]]]:
        """Creates and saves a branched child chat containing only the selected turns."""
        fork_id = uuid4().hex[:8]
        selected_indices = sorted(set(selected_indices))

        forked_turns: list[dict[str, Any]] = []
        for idx in selected_indices:
            if 0 <= idx < len(parent_history):
                turn_copy = copy.deepcopy(parent_history[idx])
                turn_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
                forked_turns.append(turn_copy)

        # Ensure fork banner is present on the first turn if not already
        if forked_turns:
            first_text = forked_turns[0].get("text", "")
            if FORK_HEADER_TEXT not in first_text:
                forked_turns[0]["text"] = f"{FORK_HEADER_TEXT}\n\n{first_text}"

        title = fork_title.strip() if fork_title else f"Fork of {parent_id}"

        self.store.save_chat(
            chat_id=fork_id,
            title=title,
            history=forked_turns,
            notes=notes,
            working_dir=working_dir,
            parent_id=parent_id,
            last_turn_index=max(0, len(forked_turns) - 1),
            center_marker=forked_turns[-1].get("turn_id", "") if forked_turns else "",
            is_legacy=False,
        )

        return fork_id, forked_turns

    def get_parent_lineage(self, parent_id: str | None) -> list[dict[str, Any]]:
        """Traverses ancestral chat hierarchy to gather lineage titles, IDs, and notes."""
        lineage: list[dict[str, Any]] = []
        curr_id = parent_id
        visited: set[str] = set()

        while curr_id and curr_id not in visited:
            visited.add(curr_id)
            parent_chat = self.store.load_chat(curr_id)
            if not parent_chat or not parent_chat.get("title"):
                break

            lineage.append({
                "id": curr_id,
                "title": parent_chat.get("title", f"Parent ({curr_id})"),
                "notes": parent_chat.get("notes", ""),
                "working_dir": parent_chat.get("working_dir"),
            })
            curr_id = parent_chat.get("parent_id")

        return lineage
