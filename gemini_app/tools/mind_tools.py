"""Mind expansion tool: retrieves turns from chat memory and file contents from disk."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def expand_mind(
    working_dir: str | Path,
    history: list[dict[str, Any]],
    turn_numbers: list[int] | None = None,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Fetches up to 50 items (historical chat turns and local files/dependencies)."""
    turn_numbers = turn_numbers or []
    file_paths = file_paths or []

    total_req = len(turn_numbers) + len(file_paths)
    if total_req > 50:
        return {"error": "Maximum 50 items can be expanded at one time."}

    results: dict[str, Any] = {"turns": {}, "files": {}}

    # Read requested turns from history
    for t_num in turn_numbers:
        idx = t_num - 1
        if 0 <= idx < len(history):
            t_item = history[idx]
            results["turns"][f"T{t_num}"] = {
                "sender": t_item.get("role", "user"),
                "content": t_item.get("text", ""),
            }

    # Read requested files from disk
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
