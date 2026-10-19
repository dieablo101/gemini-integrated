"""Helper utilities for ray casting, syntax detection, git trees, and formatting."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.syntax import Syntax
from textual.widgets.markdown import MarkdownFence

from gemini_app.config import MAX_SNIPPET_LINES_ON_WIRE

EXTENSION_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".java": "java",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".el": "lisp",
    ".lisp": "lisp",
    ".xml": "xml",
}


def cast_ray_from_center(
    center_y: int,
    header_map: dict[int, tuple[int, str]],
) -> tuple[int, str, int]:
    """Casts a ray from vertical center_y to find the nearest turn header and offset."""
    if not header_map:
        return 0, "", 0

    sorted_headers = sorted(header_map.keys())
    lowest_header_y = sorted_headers[0]
    highest_header_y = sorted_headers[-1]

    if center_y <= lowest_header_y:
        t_idx, t_id = header_map[lowest_header_y]
        return t_idx, t_id, int(center_y - lowest_header_y)

    if center_y >= highest_header_y:
        t_idx, t_id = header_map[highest_header_y]
        return t_idx, t_id, int(center_y - highest_header_y)

    closest_line = min(
        sorted_headers,
        key=lambda y: (abs(y - center_y), 0 if y >= center_y else 1),
    )
    t_idx, t_id = header_map[closest_line]
    return t_idx, t_id, int(center_y - closest_line)


_orig_markdown_fence_render = MarkdownFence.render


def _enhanced_markdown_fence_render(self: MarkdownFence) -> RenderableType:
    renderable = _orig_markdown_fence_render(self)
    try:
        if isinstance(renderable, Syntax):
            renderable.word_wrap = True
            renderable.padding = 0
            renderable.line_numbers = True

            start_line = getattr(self, "_detected_start_line", None)
            if start_line is None:
                start_line = 1
                if self.parent:
                    siblings = list(self.parent.children)
                    if self in siblings:
                        idx = siblings.index(self)
                        for s in reversed(siblings[:idx]):
                            s_text = getattr(s, "_text", "") or ""
                            if hasattr(s, "walk_children"):
                                for child in s.walk_children():
                                    text_val = getattr(child, "text", "")
                                    if text_val:
                                        s_text += " " + str(text_val)
                            m = re.search(r"\(Lines?\s+(\d+)", s_text)
                            if m:
                                start_line = int(m.group(1))
                                break
                            if isinstance(s, MarkdownFence):
                                break
                self._detected_start_line = start_line

            renderable.start_line = start_line
    except Exception:
        pass
    return renderable


def patch_markdown_fence() -> None:
    """Enhances Textual MarkdownFence with line numbering and wrap support."""
    MarkdownFence.render = _enhanced_markdown_fence_render


# Apply patch by default on module load
patch_markdown_fence()


def detect_language(filepath: str | Path) -> str:
    """Detects syntax highlighting language string from file extension."""
    ext = Path(filepath).suffix.lower()
    return EXTENSION_LANG_MAP.get(ext, "")


def write_code_to_disk(working_dir: str | Path, filename: str, content: str) -> Path:
    """Writes code snippet content to disk safely relative to working_dir."""
    base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
    fn_path = Path(os.path.expanduser(filename.strip()))
    if fn_path.is_absolute():
        target = fn_path.resolve()
    else:
        target = (base / fn_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


COLLAPSIBLE_IGNORED_DIRS = (
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
)


def get_git_files_catalog(repo_dir: str | Path) -> dict[str, list[str]]:
    """Lists tracked and git-ignored files for the repository at repo_dir."""
    base = Path(os.path.expanduser(str(repo_dir).strip())).resolve()
    check = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0 or check.stdout.strip() != "true":
        raise ValueError(f"Directory '{base}' is not a valid Git repository.")

    res_tracked = subprocess.run(
        ["git", "-C", str(base), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [f.strip() for f in res_tracked.stdout.splitlines() if f.strip()]

    res_ignored = subprocess.run(
        ["git", "-C", str(base), "ls-files", "--others", "--ignored", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    )
    ignored_raw = [
        f.strip()
        for f in res_ignored.stdout.splitlines()
        if f.strip() and not f.strip().startswith(".git/") and not f.strip() == ".git"
    ]

    # Prune massive ignored folders to root entries so tree building doesn't blow up
    ignored: list[str] = []
    seen_pruned: set[str] = set()
    for f in ignored_raw:
        matched = False
        parts = Path(f).parts
        for i, part in enumerate(parts):
            if part in COLLAPSIBLE_IGNORED_DIRS:
                collapsed_path = "/".join(parts[: i + 1])
                if collapsed_path not in seen_pruned:
                    seen_pruned.add(collapsed_path)
                    ignored.append(collapsed_path)
                matched = True
                break
        if not matched:
            ignored.append(f)

    return {
        "tracked": sorted(tracked),
        "ignored": sorted(ignored),
    }


def build_ascii_tree(
    files: list[str],
    root_name: str = ".",
    ignored_set: set[str] | None = None,
    max_depth: int | None = None,
) -> str:
    """Renders a sorted list of relative file paths into an ASCII tree."""
    nested: dict = {}
    ignored_set = ignored_set or set()

    for path in sorted(files):
        parts = Path(path).parts
        curr = nested
        for part in parts:
            curr = curr.setdefault(part, {})

    lines: list[str] = [root_name + "/"]

    def _render(node: dict, current_acc: Path, prefix: str = "", depth: int = 1) -> None:
        items = sorted(node.keys())
        for idx, key in enumerate(items):
            child_acc = current_acc / key
            is_last = idx == len(items) - 1
            branch = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            is_dir = bool(node[key])

            rel_str = str(child_acc)
            tag = " (ignored)" if rel_str in ignored_set else ""

            if is_dir:
                display = f"{key}/"
                if max_depth is not None and depth >= max_depth and node[key]:
                    lines.append(f"{prefix}{branch}{display}{tag} ...")
                else:
                    lines.append(f"{prefix}{branch}{display}{tag}")
                    _render(node[key], child_acc, prefix + child_prefix, depth + 1)
            else:
                display = f"{key}{tag}"
                lines.append(f"{prefix}{branch}{display}")

    _render(nested, Path(), depth=1)
    return "\n".join(lines)


def truncate_wire_snippets(text: str, max_lines: int = MAX_SNIPPET_LINES_ON_WIRE) -> str:
    """Truncates large code blocks on the API wire to preserve token capacity."""
    pattern = re.compile(r"(```[a-zA-Z0-9_-]*\n)([\s\S]*?)(```)")

    def repl(m: re.Match) -> str:
        opener = m.group(1)
        code = m.group(2)
        closer = m.group(3)
        lines = code.split("\n")
        if len(lines) > max_lines:
            kept = "\n".join(lines[:max_lines])
            omitted = len(lines) - max_lines
            stub = f"\n# ... [{omitted} lines truncated from wire. Call expand_mind() to inspect full file/snippet] ...\n"
            return f"{opener}{kept}{stub}{closer}"
        return m.group(0)

    return pattern.sub(repl, text)
