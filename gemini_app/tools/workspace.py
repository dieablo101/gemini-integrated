"""Workspace tools: directory tree inspection, file writing, patching, codebase search, and project scaffolding."""

import fnmatch
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Union

from gemini_app.helpers import build_ascii_tree, get_git_files_catalog
from gemini_app.projects import scaffold_project as _scaffold_project


def scan_workspace_tree(
    working_dir: Union[str, Path],
    include_ignored: bool = True,
    max_depth: Optional[int] = None,
) -> str:
    """Scans the working directory git tree, returning tracked and .gitignore files."""
    try:
        working_path = Path(os.path.expanduser(str(working_dir).strip())).resolve()
        cat = get_git_files_catalog(working_path)
        files = cat["tracked"] + (cat["ignored"] if include_ignored else [])
        root_lbl = working_path.name or "workspace"
        return build_ascii_tree(
            files,
            root_name=root_lbl,
            ignored_set=set(cat["ignored"]),
            max_depth=max_depth,
        )
    except Exception as e:
        return f"Error scanning tree: {e}"


def write_file(working_dir: Union[str, Path], path: str, content: str) -> Dict[str, Any]:
    """Writes or overwrites a file on disk relative to the working directory."""
    try:
        base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
        target = (base / path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def apply_patch(
    working_dir: Union[str, Path], path: str, search_block: str, replace_block: str
) -> Dict[str, Any]:
    """Applies a surgical find-and-replace patch to a file.

    The search_block must appear exactly once in the target file.
    """
    try:
        base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
        target = (base / path).resolve()
        if not target.exists():
            return {"status": "error", "message": f"File '{path}' does not exist."}

        content = target.read_text(encoding="utf-8")
        occurrences = content.count(search_block)
        if occurrences == 0:
            return {
                "status": "error",
                "message": f"search_block not found in '{path}'. Ensure surrounding context matches exactly.",
            }
        if occurrences > 1:
            return {
                "status": "error",
                "message": f"search_block matched {occurrences} times in '{path}'. Please provide a larger unique context block.",
            }

        new_content = content.replace(search_block, replace_block, 1)
        target.write_text(new_content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(target),
            "lines_delta": len(replace_block.splitlines()) - len(search_block.splitlines()),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_codebase(
    working_dir: Union[str, Path],
    query: str,
    path_pattern: str = "*",
    max_matches: int = 50,
) -> Dict[str, Any]:
    """Searches workspace files for a text pattern or regex query, returning matching lines."""
    try:
        base = Path(os.path.expanduser(str(working_dir).strip())).resolve()

        # Compile regex safely with literal escape fallback
        try:
            compiled_re = re.compile(query, re.IGNORECASE)
        except re.error:
            compiled_re = re.compile(re.escape(query), re.IGNORECASE)

        matches: List[str] = []
        ignored_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}

        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                file_path = Path(root) / f
                rel_path = file_path.relative_to(base)
                rel_str = str(rel_path)

                if path_pattern and path_pattern != "*":
                    pattern_clean = path_pattern.rstrip("/*")
                    if not (
                        fnmatch.fnmatch(rel_str, path_pattern)
                        or fnmatch.fnmatch(f, path_pattern)
                        or fnmatch.fnmatch(rel_str, f"{pattern_clean}/*")
                        or fnmatch.fnmatch(rel_str, f"*{path_pattern}*")
                    ):
                        continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                        for line_no, line in enumerate(fh, 1):
                            if compiled_re.search(line):
                                matches.append(f"{rel_str}:{line_no}: {line.rstrip()}")
                                if len(matches) >= max_matches:
                                    break
                except Exception:
                    continue
                if len(matches) >= max_matches:
                    break
            if len(matches) >= max_matches:
                break

        return {
            "status": "success",
            "total_matches": len(matches),
            "matches": matches,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def scaffold_project(
    name: str,
    description: str = "",
    realname: str = "",
    git_init: bool = True,
) -> Dict[str, Any]:
    """Scaffolds a new project under ~/Projects with Git, README.md, and MIT LICENSE (Copyright yourname unless otherwise specified)."""
    return _scaffold_project(
        name=name,
        description=description,
        realname=realname if realname else None,
        git_init=git_init,
    )
