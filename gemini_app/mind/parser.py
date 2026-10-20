"""Cognitive mind map parser and prompt construction."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


def build_system_instruction(
    working_dir: str | Path,
    total_turns: int,
    gemini_state: str = "",
    user_state: str = "",
    tree_state: list[str] | None = None,
    tree_content: str = "",
) -> str:
    """Builds the comprehensive system instruction containing persistent anchors and expansion specs."""
    tree_state_str = ", ".join(str(x) for x in tree_state) if tree_state else "None"
    working_dir_str = str(working_dir)

    return (
        f"You are Gemini running inside a bilateral terminal console.\n"
        f"Working directory: {working_dir_str}\n"
        f"Total conversation turns on record: {total_turns}\n\n"
        f"### CURRENT COGNITIVE MIND MAP (PERSISTENT ANCHORS)\n"
        f"• GEMINI MIND STATE: {gemini_state or 'None'}\n"
        f"• USER MIND STATE: {user_state or 'None'}\n"
        f"• TREE ANCHOR STATE: [{tree_state_str}]\n\n"
        f"### VISUAL RELATION TREE:\n"
        f"```text\n{tree_content or '└── *[Session Start]*'}\n```\n\n"
        f"### EXPANSION CAPABILITIES\n"
        f"You have tools available to inspect the environment, write files, and execute commands:\n"
        f"1. `scan_workspace_tree(include_ignored=True, max_depth=None)`: Survey directory structure and dependencies.\n"
        f"2. `expand_mind(turn_numbers=[...], file_paths=[...], turn_ids=[...])`: Pull up to 50 items (turns or files/slices/outlines) into thought memory.\n"
        f"3. `write_file(path='...', content='...')`: Write or overwrite a file directly on disk.\n"
        f"4. `execute_shell(command='...', timeout_seconds=60)`: Run shell commands (e.g. tests, linters, python scripts).\n\n"
        f"### REQUIRED METADATA FOOTER\n"
        f"At the very end of your response, always output this exact JSON block fenced in json:mind_map\n"
        f"{{\n"
        f'  "gemini_state": "<Summary of technical direction and active sub-tasks>",\n'
        f'  "user_state": "<Summary of inferred user intent and immediate constraints>",\n'
        f'  "tree_state": ["T...", "F:..."],\n'
        f'  "tree_content": "<ASCII tree showing where current conversation and files connect>"\n'
        f"}}\n"
        f"```"
    )


def extract_mind_map(
    raw_reply: str,
    default_gemini_state: str = "",
    default_user_state: str = "",
    default_tree_content: str = "",
    default_tree_state: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Extracts json:mind_map footer from model output, returning clean reply and metadata."""
    default_tree_state = default_tree_state or []

    gemini_state = default_gemini_state
    user_state = default_user_state
    tree_content = default_tree_content
    tree_state = list(default_tree_state)

    tag_open = chr(96) * 3 + "json:mind_map"
    tag_close = chr(96) * 3
    pattern = re.compile(
        re.escape(tag_open) + r"\s*\n(.*?)\n" + re.escape(tag_close),
        re.DOTALL,
    )
    match = pattern.search(raw_reply)

    clean_reply = raw_reply
    if match:
        json_str = match.group(1).strip()
        clean_reply = pattern.sub("", raw_reply).rstrip()
        try:
            meta_dict = json.loads(json_str)
            gemini_state = meta_dict.get("gemini_state", gemini_state)
            user_state = meta_dict.get("user_state", user_state)
            tree_content = meta_dict.get("tree_content", tree_content)
            tree_state = meta_dict.get("tree_state", tree_state)
        except Exception:
            pass

    return clean_reply, {
        "gemini_state": gemini_state,
        "user_state": user_state,
        "tree_content": tree_content,
        "tree_state": tree_state,
    }
