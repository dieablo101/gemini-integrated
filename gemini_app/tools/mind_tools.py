"""Mind expansion and memory recall tools: retrieves turns, historical memory, and files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

from gemini_app.storage.memory_index import MemoryIndex


def expand_mind(
    working_dir: str | Path,
    history: list[dict[str, Any]],
    turn_numbers: list[int] | None = None,
    file_paths: list[str] | None = None,
    turn_ids: list[str] | None = None,
    memory_index: Optional[MemoryIndex] = None,
) -> dict[str, Any]:
    """Fetches up to 50 items (historical chat turns and local files/dependencies)."""
    turn_numbers = turn_numbers or []
    file_paths = file_paths or []
    turn_ids = turn_ids or []

    total_req = len(turn_numbers) + len(file_paths) + len(turn_ids)
    if total_req > 50:
        return {"error": "Maximum 50 items can be expanded at one time."}

    results: dict[str, Any] = {"turns": {}, "files": {}}

    # 1. Read requested turns from in-memory history
    for t_num in turn_numbers:
        idx = t_num - 1
        if 0 <= idx < len(history):
            t_item = history[idx]
            results["turns"][f"T{t_num}"] = {
                "sender": t_item.get("role", "user"),
                "content": t_item.get("text", ""),
                "turn_id": t_item.get("turn_id", ""),
            }
        elif memory_index:
            # Fallback to persistent memory index
            indexed_matches = memory_index.search(f"turn_{t_num}", limit=1)
            if indexed_matches:
                m = indexed_matches[0]
                results["turns"][f"T{t_num}"] = {
                    "sender": m.get("role", "user"),
                    "content": m.get("content", ""),
                    "turn_id": m.get("turn_id", ""),
                    "title": m.get("title", ""),
                }

    # 2. Read turns by specific turn_id
    if turn_ids and memory_index:
        for tid in turn_ids:
            turn_row = memory_index.get_turn_by_id(tid)
            if turn_row:
                results["turns"][tid] = {
                    "sender": turn_row.get("role", "user"),
                    "content": turn_row.get("content", ""),
                    "turn_number": turn_row.get("turn_number"),
                    "title": turn_row.get("title", ""),
                }

    # 3. Read requested files from disk
    base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
    for fp in file_paths:
        p = (base / fp).resolve()
        if p.exists() and p.is_file():
            try:
                results["files"][fp] = p.read_text(encoding="utf-8", errors="replace")
            except Exception as fe:
                results["files"][fp] = f"Error reading file: {fe}"
        else:
            results["files"][fp] = "File not found."

    return results


def recall_memory(
    query: str,
    max_results: int = 10,
    chat_id: Optional[str] = None,
    memory_index: Optional[MemoryIndex] = None,
) -> dict[str, Any]:
    """Fast indexed retrieval across entire conversational history and past discussions."""
    index = memory_index or MemoryIndex()
    matches = index.search(query=query, chat_id=chat_id, limit=max_results)

    clean_matches = []
    for m in matches:
        clean_matches.append({
            "turn_number": m.get("turn_number"),
            "turn_id": m.get("turn_id"),
            "role": m.get("role"),
            "title": m.get("title"),
            "chat_id": m.get("chat_id"),
            "snippet": m.get("snippet"),
            "content": m.get("content"),
            "timestamp": m.get("timestamp"),
            "project_dir": m.get("project_dir"),
        })

    return {
        "query": query,
        "matches_count": len(clean_matches),
        "matches": clean_matches,
    }
