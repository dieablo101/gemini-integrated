"""Multimodal Sketch-to-Code Ingestion and Scaffolding Pipeline.

Provides autonomous bridging from iPad sketches (iSH iOS document mount, Procreate,
Apple Notes, or local drawing exports) to production Textual TUI widgets or HTML prototypes.
"""

from __future__ import annotations

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from gemini_app.config import GEMINI_HOME

SKETCHES_DIR: Path = GEMINI_HOME / "sketches"
SKETCHES_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

SUPPORTED_SKETCH_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".bmp",
}

# Standard mount paths for iPad / iOS files app
IPAD_MOUNT_CANDIDATES: list[Path] = [
    Path("/mnt/ipad/sketches"),
    Path("/mnt/ipad"),
    Path("/mnt/ios"),
    Path.home() / "sketches",
    SKETCHES_DIR,
]


def get_sketch_directories() -> list[Path]:
    """Returns valid existing sketch search directories."""
    dirs: list[Path] = []
    for p in IPAD_MOUNT_CANDIDATES:
        try:
            if p.is_dir():
                dirs.append(p)
        except Exception:
            pass
    if SKETCHES_DIR not in dirs:
        dirs.append(SKETCHES_DIR)
    return dirs


def list_sketches(search_dirs: Optional[list[str | Path]] = None) -> list[dict[str, Any]]:
    """Lists available sketches across iPad mount and local sketch stores.

    Returns:
        List of dicts with sketch filename, full path, size, format, mtime, and source origin.
    """
    target_dirs = [Path(d) for d in search_dirs] if search_dirs else get_sketch_directories()
    results: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for d in target_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_file():
                        ext = Path(entry.name).suffix.lower()
                        if ext in SUPPORTED_SKETCH_EXTENSIONS:
                            abs_path = str(Path(entry.path).resolve())
                            if abs_path in seen_paths:
                                continue
                            seen_paths.add(abs_path)
                            st = entry.stat()
                            source = "ipad_mount" if "/mnt/ipad" in abs_path or "/mnt/ios" in abs_path else "local"
                            results.append({
                                "name": entry.name,
                                "path": abs_path,
                                "size_bytes": st.st_size,
                                "format": ext.lstrip("."),
                                "mtime": st.st_mtime,
                                "mtime_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "source": source,
                            })
        except Exception:
            continue

    results.sort(key=lambda s: s["mtime"], reverse=True)
    return results


def ingest_sketch(
    path_or_name: str,
    copy_to_vault: bool = True,
) -> dict[str, Any]:
    """Reads a sketch image, packages its metadata and base64 payload for vision ingestion.

    Args:
        path_or_name: Filename in sketch directories or absolute path to the sketch file.
        copy_to_vault: If True, copies the sketch into ~/.gemini/sketches/ for indexing.

    Returns:
        Dictionary containing sketch metadata, image dimensions/format, and base64 representation.
    """
    candidate = Path(path_or_name)
    resolved_path: Optional[Path] = None

    if candidate.is_file():
        resolved_path = candidate.resolve()
    else:
        # Search sketch directories
        for d in get_sketch_directories():
            target = d / path_or_name
            if target.is_file():
                resolved_path = target.resolve()
                break

    if not resolved_path or not resolved_path.exists():
        return {
            "status": "error",
            "message": f"Sketch '{path_or_name}' not found across sketch directories: {[str(d) for d in get_sketch_directories()]}",
        }

    ext = resolved_path.suffix.lower()
    if ext not in SUPPORTED_SKETCH_EXTENSIONS:
        return {
            "status": "error",
            "message": f"Unsupported sketch extension '{ext}'. Supported: {sorted(list(SUPPORTED_SKETCH_EXTENSIONS))}",
        }

    # Optionally archive into local ~/.gemini/sketches
    if copy_to_vault and resolved_path.parent != SKETCHES_DIR:
        dest = SKETCHES_DIR / resolved_path.name
        try:
            shutil.copy2(resolved_path, dest)
            resolved_path = dest
        except Exception:
            pass

    try:
        raw_bytes = resolved_path.read_bytes()
        b64_data = base64.b64encode(raw_bytes).decode("ascii")
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

        return {
            "status": "success",
            "name": resolved_path.name,
            "path": str(resolved_path),
            "size_bytes": len(raw_bytes),
            "mime_type": mime_type,
            "format": ext.lstrip("."),
            "base64_payload": b64_data,
            "is_svg": ext == ".svg",
            "svg_content": raw_bytes.decode("utf-8", errors="replace") if ext == ".svg" else None,
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed reading sketch '{resolved_path}': {e}"}


def generate_scaffold_prompt(
    sketch_info: dict[str, Any],
    target_framework: str = "textual",
) -> str:
    """Constructs the high-fidelity prompt template guiding the model to generate layout code."""
    fw = target_framework.lower().strip()
    name = sketch_info.get("name", "sketch")
    fmt = sketch_info.get("format", "image")

    if fw == "textual":
        return f"""Analyze the provided UI sketch ({name}, format: {fmt}) and scaffold a production Textual widget layout.

### Architectural Rules for Textual Scaffolding:
1. Identify container divisions: Vertical and Horizontal flex splits matching visual wireframe regions.
2. Map UI primitives:
   - Header / Title -> Label(..., id="...") or header widget
   - Navigation / Tabs -> Horizontal bar of Button or OptionList
   - Main content / Feed -> VerticalScroll or DataTable
   - Inputs / Forms -> Input, TextArea, Checkbox, RadioSet
   - Action buttons -> Button(..., variant="primary"|"default"|"error")
3. Layout styling: Define scoped CSS rules with clean spacing, margin, padding, borders, and dark-theme accents.
4. Implement reactive callbacks: Wire `@on(Button.Pressed)` or `@on(Input.Submitted)` stubs.
5. Provide complete, runnable code within a clean ```python codeblock.
"""
    else:
        return f"""Analyze the provided UI sketch ({name}, format: {fmt}) and scaffold clean HTML5 + CSS3 flexbox/grid prototype.

### Rules for HTML Prototype:
1. Semantic markup (<header>, <nav>, <main>, <aside>, <section>, <footer>).
2. Modern responsive Flexbox / CSS Grid styling matching the sketch wireframe.
3. Clean modern typography, accessible contrast, and dark mode palette.
4. Provide complete, self-contained HTML in a ```html codeblock.
"""


def scaffold_sketch_to_code(
    sketch_path_or_name: str,
    target_framework: str = "textual",
    output_path: str = "",
) -> dict[str, Any]:
    """Ingests a sketch and returns the complete scaffolding specification ready for execution.

    Args:
        sketch_path_or_name: Path or filename of the sketch.
        target_framework: Target framework ('textual' or 'html').
        output_path: Optional destination path to write scaffolded code.

    Returns:
        Dictionary containing ingested sketch metadata, scaffold prompt, and staging location.
    """
    ingested = ingest_sketch(sketch_path_or_name)
    if ingested.get("status") != "success":
        return ingested

    prompt = generate_scaffold_prompt(ingested, target_framework=target_framework)
    dest_path = output_path or ""
    if not dest_path:
        base_name = Path(ingested["name"]).stem
        ext = ".py" if target_framework.lower() == "textual" else ".html"
        dest_path = str(Path.cwd() / f"scaffold_{base_name}{ext}")

    return {
        "status": "success",
        "action": "sketch_to_code_ready",
        "sketch_name": ingested["name"],
        "sketch_path": ingested["path"],
        "format": ingested["format"],
        "size_bytes": ingested["size_bytes"],
        "target_framework": target_framework,
        "recommended_output": dest_path,
        "scaffold_prompt": prompt,
        "has_base64_payload": bool(ingested.get("base64_payload")),
    }


def sync_ipad_sketches(target_dir: Optional[str] = None) -> dict[str, Any]:
    """Scans iPad mount (/mnt/ipad) and synchronizes all new sketches into ~/.gemini/sketches/.

    Returns:
        Summary of scanned, synced, and existing sketches.
    """
    dest = Path(target_dir) if target_dir else SKETCHES_DIR
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)

    ipad_mount = Path("/mnt/ipad")
    if not ipad_mount.exists() or not ipad_mount.is_dir():
        # Fallback check for /mnt/ios
        if Path("/mnt/ios").is_dir():
            ipad_mount = Path("/mnt/ios")
        else:
            return {
                "status": "warning",
                "message": "iPad document mount (/mnt/ipad or /mnt/ios) is not currently mounted.",
                "local_sketches": list_sketches(search_dirs=[dest]),
            }

    synced_files: list[str] = []
    skipped_count = 0

    for root, _, files in os.walk(ipad_mount):
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_SKETCH_EXTENSIONS:
                src_path = Path(root) / f
                dst_path = dest / f
                try:
                    if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
                        shutil.copy2(src_path, dst_path)
                        synced_files.append(f)
                    else:
                        skipped_count += 1
                except Exception:
                    continue

    return {
        "status": "success",
        "synced_count": len(synced_files),
        "synced_sketches": synced_files,
        "skipped_up_to_date": skipped_count,
        "destination": str(dest),
    }
