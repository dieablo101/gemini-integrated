"""Textual snapshot management, SVG rendering, terminal text extraction, and indexing."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional
import xml.etree.ElementTree as ET

from gemini_app.config import SCREENSHOTS_DIR

INDEX_FILE = SCREENSHOTS_DIR / "snapshots_index.json"


def extract_text_from_svg(svg_content: str) -> str:
    """Extracts reconstructed terminal text lines from Textual SVG output."""
    try:
        root = ET.fromstring(svg_content.encode("utf-8"))
        texts: list[tuple[float, float, str]] = []
        for elem in root.iter():
            if elem.tag.endswith("text"):
                try:
                    y = float(elem.attrib.get("y", 0))
                    x = float(elem.attrib.get("x", 0))
                except (ValueError, TypeError):
                    continue
                txt = elem.text or ""
                if txt:
                    texts.append((y, x, txt))

        texts.sort(key=lambda item: (item[0], item[1]))
        lines: list[str] = []
        current_y: float | None = None
        current_line: list[tuple[float, str]] = []

        for y, x, txt in texts:
            if current_y is None or abs(y - current_y) > 6:
                if current_line:
                    lines.append("".join(t for _, t in sorted(current_line)))
                current_y = y
                current_line = [(x, txt)]
            else:
                current_line.append((x, txt))

        if current_line:
            lines.append("".join(t for _, t in sorted(current_line)))

        return "\n".join(lines).replace("\xa0", " ").strip()
    except Exception:
        # Regex failsafe fallback
        matches = re.findall(r"<text[^>]*>(.*?)</text>", svg_content, re.DOTALL)
        clean = [re.sub(r"<[^>]+>", "", m).replace("&#160;", " ").strip() for m in matches if m.strip()]
        return "\n".join(clean)


def get_snapshot_index() -> list[dict[str, Any]]:
    """Reads the snapshot index from disk."""
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_snapshot_index(entries: list[dict[str, Any]]) -> None:
    """Atomically saves the snapshot index to disk."""
    SCREENSHOTS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_file = INDEX_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    temp_file.replace(INDEX_FILE)


def cleanup_stale_ephemerals() -> int:
    """Purges previously reviewed ephemeral snapshots from disk and memory index."""
    entries = get_snapshot_index()
    if not entries:
        return 0

    surviving: list[dict[str, Any]] = []
    purged = 0

    for e in entries:
        is_persistent = e.get("persistent", False) or bool(e.get("source") == "command" and e.get("label"))
        is_held = e.get("held", True)

        if not is_persistent and not is_held:
            # Ephemeral and already reviewed: wipe from disk
            svg_p = Path(e.get("svg_path", ""))
            txt_p = Path(e.get("txt_path", ""))
            if svg_p.exists():
                try:
                    svg_p.unlink(missing_ok=True)
                except Exception:
                    pass
            if txt_p.exists():
                try:
                    txt_p.unlink(missing_ok=True)
                except Exception:
                    pass
            purged += 1
        else:
            surviving.append(e)

    if purged > 0:
        save_snapshot_index(surviving)

    return purged


def capture_ui_snapshot(
    app: Any,
    label: str = "",
    taken_by: str = "user",
    source: str = "shortcut",
    persistent: Optional[bool] = None,
) -> dict[str, Any]:
    """Captures an SVG snapshot from the live Textual application, indexes it, and holds it.

    Snapshots captured via command with a name are persistent (saved permanently without deleting).
    Snapshots captured via C-c ` (shortcut) or without a name are ephemeral (deleted from disk and mem on review).
    """
    SCREENSHOTS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = datetime.now()
    base_ts = now.strftime("%Y-%m-%d_%H-%M-%S")
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

    clean_label = label.strip() if label else ""

    # Determine persistence rule: command with name -> persistent; shortcut/unnamed -> ephemeral
    if persistent is None:
        persistent = bool(source == "command" and clean_label)

    # Incorporate name into filename stem if provided
    if clean_label:
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_label)
        filename_stem = f"snapshot_{base_ts}_{safe_name}"
    else:
        filename_stem = f"snapshot_{base_ts}"

    counter = 1
    svg_path = SCREENSHOTS_DIR / f"{filename_stem}.svg"
    txt_path = SCREENSHOTS_DIR / f"{filename_stem}.txt"
    while svg_path.exists():
        if clean_label:
            safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_label)
            filename_stem = f"snapshot_{base_ts}_{safe_name}_{counter}"
        else:
            filename_stem = f"snapshot_{base_ts}_{counter}"
        svg_path = SCREENSHOTS_DIR / f"{filename_stem}.svg"
        txt_path = SCREENSHOTS_DIR / f"{filename_stem}.txt"
        counter += 1

    svg_content = ""
    if hasattr(app, "export_screenshot"):
        try:
            svg_content = app.export_screenshot()
        except Exception:
            pass

    if not svg_content and hasattr(app, "save_screenshot"):
        try:
            app.save_screenshot(str(svg_path))
            if svg_path.exists():
                svg_content = svg_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if svg_content:
        svg_path.write_text(svg_content, encoding="utf-8")
        text_dump = extract_text_from_svg(svg_content)
        txt_path.write_text(text_dump, encoding="utf-8")
    else:
        text_dump = "[Snapshot SVG capture unavailable]"
        txt_path.write_text(text_dump, encoding="utf-8")

    screen_name = "ChatApp"
    try:
        if hasattr(app, "screen") and app.screen is not None:
            screen_name = app.screen.__class__.__name__
    except Exception:
        pass

    entries = get_snapshot_index()
    next_index = len(entries) + 1
    entry = {
        "id": filename_stem,
        "index": next_index,
        "timestamp": timestamp_str,
        "svg_path": str(svg_path),
        "txt_path": str(txt_path),
        "label": clean_label,
        "taken_by": taken_by,
        "source": source,
        "persistent": persistent,
        "held": True,
        "screen_name": screen_name,
    }

    entries.append(entry)
    save_snapshot_index(entries)
    return entry


def list_held_snapshots(only_held: bool = True) -> list[dict[str, Any]]:
    """Returns list of snapshot metadata entries, optionally filtering only held."""
    entries = get_snapshot_index()
    if only_held:
        return [e for e in entries if e.get("held", True)]
    return entries


def review_held_snapshots(
    snapshot_ids: list[str] = [],
    only_held: bool = True,
    count: int = 5,
    mark_as_reviewed: bool = True,
) -> dict[str, Any]:
    """Retrieves snapshot text contents and metadata for review by Gemini.

    Ephemeral snapshots (captured via C-c ` or without name) are deleted from disk and memory index.
    Persistent snapshots (captured via command with a name) are retained on disk with held=False.
    """
    entries = get_snapshot_index()
    if not entries:
        return {
            "status": "empty",
            "message": "No snapshots have been captured in the system yet.",
            "snapshots": [],
        }

    target_entries: list[dict[str, Any]] = []

    if snapshot_ids:
        id_set = set(snapshot_ids)
        target_entries = [e for e in entries if e.get("id") in id_set]
    elif only_held:
        target_entries = [e for e in entries if e.get("held", True)]
    else:
        target_entries = list(entries)

    if not target_entries:
        return {
            "status": "empty",
            "message": "No snapshots currently held pending review.",
            "snapshots": [],
        }

    # Order most recent first, take count, then reverse to chronological
    target_entries.sort(key=lambda x: x.get("index", 0), reverse=True)
    selected = list(reversed(target_entries[:count]))

    results = []
    reviewed_ids = set()

    for item in selected:
        txt_path = Path(item.get("txt_path", ""))
        screen_text = ""
        if txt_path.exists():
            try:
                screen_text = txt_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                screen_text = f"[Error reading text dump: {e}]"
        else:
            svg_path = Path(item.get("svg_path", ""))
            if svg_path.exists():
                try:
                    screen_text = extract_text_from_svg(svg_path.read_text(encoding="utf-8", errors="replace"))
                except Exception as e:
                    screen_text = f"[Error reading svg: {e}]"

        results.append({
            "id": item.get("id"),
            "index": item.get("index"),
            "timestamp": item.get("timestamp"),
            "label": item.get("label", ""),
            "taken_by": item.get("taken_by", "user"),
            "source": item.get("source", "shortcut"),
            "persistent": item.get("persistent", False),
            "screen_name": item.get("screen_name", "ChatApp"),
            "screen_text": screen_text,
            "svg_path": item.get("svg_path"),
        })
        reviewed_ids.add(item.get("id"))

    if mark_as_reviewed:
        surviving_entries: list[dict[str, Any]] = []
        deleted_count = 0

        for e in entries:
            eid = e.get("id")
            if eid in reviewed_ids:
                is_persistent = e.get("persistent", False) or bool(e.get("source") == "command" and e.get("label"))
                if is_persistent:
                    e["held"] = False
                    surviving_entries.append(e)
                else:
                    # Wipe ephemeral snapshot from disk
                    svg_p = Path(e.get("svg_path", ""))
                    txt_p = Path(e.get("txt_path", ""))
                    if svg_p.exists():
                        try:
                            svg_p.unlink(missing_ok=True)
                        except Exception:
                            pass
                    if txt_p.exists():
                        try:
                            txt_p.unlink(missing_ok=True)
                        except Exception:
                            pass
                    deleted_count += 1
            else:
                surviving_entries.append(e)

        save_snapshot_index(surviving_entries)

    return {
        "status": "success",
        "snapshots_reviewed": len(results),
        "snapshots": results,
    }
