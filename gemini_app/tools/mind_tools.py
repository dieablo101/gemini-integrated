"""Mind expansion and memory recall tools: retrieves turns, historical memory, and files."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, List, Optional

from gemini_app.storage.memory_index import MemoryIndex


def format_file_slice(content: str, start: int, end: int, rel_path: str = "") -> str:
    """Formats a specific line range slice with line numbers."""
    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return f"# [{rel_path} - empty file]"
    start_idx = max(1, start)
    end_idx = min(total, max(start_idx, end))
    if start_idx > total:
        return f"# Error: Requested start line {start_idx} exceeds total lines ({total}) in {rel_path}."

    header = f"# [{rel_path} - lines {start_idx} to {end_idx} of {total}]"
    out = [header]
    width = len(str(end_idx))
    for i in range(start_idx, end_idx + 1):
        line_str = lines[i - 1]
        out.append(f"{i:{width}d} | {line_str}")
    return "\n".join(out)


def format_file_outline(content: str, rel_path: str = "") -> str:
    """Extracts class and def declarations with line numbers for rapid structural scanning."""
    lines = content.splitlines()
    total = len(lines)
    header = f"# [Outline of {rel_path} - {total} lines]"
    out = [header]
    found = 0
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if (
            stripped.startswith("def ")
            or stripped.startswith("async def ")
            or stripped.startswith("class ")
        ):
            indent_len = len(line) - len(line.lstrip())
            indent = " " * indent_len
            out.append(f"Line {idx:4d}: {indent}{stripped}")
            found += 1
    if found == 0:
        out.append("  (No class or function definitions detected)")
    return "\n".join(out)


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

    # 3. Read requested files from disk (supports whole file, line range slice 'path:10-50', and outline 'path:outline')
    base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
    for fp in file_paths:
        p = (base / fp).resolve()
        if p.exists() and p.is_file():
            try:
                results["files"][fp] = p.read_text(encoding="utf-8", errors="replace")
            except Exception as fe:
                results["files"][fp] = f"Error reading file: {fe}"
            continue

        target_str = fp
        spec = ""
        if "#" in fp:
            target_str, spec = fp.split("#", 1)
        elif ":" in fp:
            target_str, spec = fp.rsplit(":", 1)

        spec = spec.strip().lower()
        p_spec = (base / target_str).resolve()
        if p_spec.exists() and p_spec.is_file():
            try:
                raw_text = p_spec.read_text(encoding="utf-8", errors="replace")
                if spec in ("outline", "symbols"):
                    results["files"][fp] = format_file_outline(raw_text, target_str)
                elif spec:
                    m_range = re.match(r"^(\d+)\s*(?:-|to|\.\.)\s*(\d+)$", spec)
                    m_plus = re.match(r"^(\d+)\s*\+\s*(\d+)$", spec)
                    m_single = re.match(r"^(\d+)$", spec)
                    if m_range:
                        s, e = int(m_range.group(1)), int(m_range.group(2))
                        results["files"][fp] = format_file_slice(raw_text, s, e, target_str)
                    elif m_plus:
                        s = int(m_plus.group(1))
                        count = int(m_plus.group(2))
                        results["files"][fp] = format_file_slice(raw_text, s, s + count - 1, target_str)
                    elif m_single:
                        s = int(m_single.group(1))
                        results["files"][fp] = format_file_slice(raw_text, s, s + 30, target_str)
                    else:
                        results["files"][fp] = raw_text
                else:
                    results["files"][fp] = raw_text
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
    cortex_brain: Optional[Any] = None,
) -> dict[str, Any]:
    """Fast indexed retrieval across entire conversational history and past discussions.
    Supports dual FTS5 lexical recall + associative hypergraph cortex recall."""
    if cortex_brain is not None:
        rec = cortex_brain.recall(query=query, max_results=max_results, chat_id=chat_id)
        return {
            "query": query,
            "matches_count": rec.get("matches_count", 0),
            "matches": rec.get("matches", []),
            "graph_associations": rec.get("graph_associations", []),
            "relational_shards": rec.get("relational_shards", []),
            "latency_ms": rec.get("latency_ms", 0.0),
        }

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
