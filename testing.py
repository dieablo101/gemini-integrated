#!/opt/gemini/.venv/bin/python3

import asyncio
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from uuid import uuid4

import pyperclip
from google import genai
from rich.console import RenderableType
from rich.syntax import Syntax
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    Markdown,
    OptionList,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
    Tree,
)
from textual.widgets.markdown import MarkdownFence
from textual.widgets.option_list import Option
from textual.widgets.text_area import Selection
from textual.widgets.tree import TreeNode

try:
    from markdown_it import MarkdownIt
    _MD_PARSER = MarkdownIt()
except Exception:
    _MD_PARSER = None

# User-specific directory and socket paths
GEMINI_HOME = Path.home() / ".gemini"
GEMINI_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)

CHATS_DIR = GEMINI_HOME / "chats"
CHATS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

SCREENSHOTS_DIR = GEMINI_HOME / "screenshots"
SCREENSHOTS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

STATE_FILE = GEMINI_HOME / "state.json"
SOCKET_PATH = GEMINI_HOME / "gemini_textual.sock"

FORK_HEADER_TEXT = "## This chat is a fork of another / previous chat"

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ---------------------------------------------------------------------------
# Global Engine Toggles & Runway Constants
# ---------------------------------------------------------------------------
CENTER_SCREEN_MODE: bool = True

RUNWAY_ABOVE_BUDGET: int = 4
RUNWAY_BELOW_BUDGET: int = 5
DEFAULT_WINDOW_CAPACITY: int = 10
DEFAULT_MODEL: str = "gemini-3.8-flash"

# Keys selectively gated and consumed at the App Root during lockout
GATED_NAV_KEYS = {
    "home",
    "end",
    "pageup",
    "pagedown",
    "up",
    "down",
    "shift+up",
    "shift+down",
    "ctrl+j",
    "ctrl+k",
    "alt+n",
    "meta+n",
    "alt+p",
    "meta+p",
}

# ---------------------------------------------------------------------------
# Pure 1D Outward Raycast Math Function (Independent of Textual)
# ---------------------------------------------------------------------------

def cast_ray_from_center(
    center_y: int,
    header_map: dict[int, tuple[int, str]],
    win_start: int,
    win_end: int,
    total_messages: int,
    max_radius: int = 150,
) -> tuple[int, str, int]:
    """Casts two 1D rays outward from the screen center line along the Y axis.

    Steps line-by-line (0, 1, -1, 2, -2, ...) until striking a card header.
    Boundary aware: If ray escapes mounted memory, identifies adjacent unmounted turn.
    Returns: (turn_index, turn_id, signed_delta_offset)
    """
    if not header_map:
        return 0, "", 0

    sorted_headers = sorted(header_map.keys())
    lowest_header_y = sorted_headers[0]
    highest_header_y = sorted_headers[-1]

    # Ceiling Boundary Detection: Screen center is above all mounted cards
    if center_y < lowest_header_y:
        if win_start > 0:
            target_idx = win_start - 1
            return target_idx, f"turn_{target_idx}", int(center_y - lowest_header_y)
        t_idx, t_id = header_map[lowest_header_y]
        return t_idx, t_id, int(center_y - lowest_header_y)

    # Floor Boundary Detection: Screen center is below all mounted headers
    if center_y > (highest_header_y + 40):
        if win_end < total_messages:
            target_idx = win_end
            return target_idx, f"turn_{target_idx}", int(center_y - highest_header_y)
        t_idx, t_id = header_map[highest_header_y]
        return t_idx, t_id, int(center_y - highest_header_y)

    # Outward Line-by-Line Stepping
    for radius in range(max_radius + 1):
        # Downward ray (+radius)
        down_line = center_y + radius
        if down_line in header_map:
            t_idx, t_id = header_map[down_line]
            delta = center_y - down_line
            return t_idx, t_id, delta

        # Upward ray (-radius)
        if radius > 0:
            up_line = center_y - radius
            if up_line in header_map:
                t_idx, t_id = header_map[up_line]
                delta = center_y - up_line
                return t_idx, t_id, delta

    closest_line = min(header_map.keys(), key=lambda y: abs(y - center_y))
    t_idx, t_id = header_map[closest_line]
    return t_idx, t_id, int(center_y - closest_line)

# ---------------------------------------------------------------------------
# Reusable Core File & Git Services
# ---------------------------------------------------------------------------

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
}

def detect_language(filepath: str | Path) -> str:
    ext = Path(filepath).suffix.lower()
    return EXTENSION_LANG_MAP.get(ext, "")

def write_code_to_disk(working_dir: str | Path, filename: str, content: str) -> Path:
    base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
    target = (base / filename.strip()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target

def get_git_files_catalog(repo_dir: str | Path) -> dict[str, list[str]]:
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
    ignored = [
        f.strip()
        for f in res_ignored.stdout.splitlines()
        if f.strip() and not f.strip().startswith(".git/") and not f.strip() == ".git"
    ]

    return {
        "tracked": sorted(tracked),
        "ignored": sorted(ignored),
    }

def build_ascii_tree(files: list[str], root_name: str = ".", ignored_set: set[str] | None = None) -> str:
    nested: dict = {}
    ignored_set = ignored_set or set()

    for path in sorted(files):
        parts = Path(path).parts
        curr = nested
        for part in parts:
            curr = curr.setdefault(part, {})

    lines: list[str] = [root_name + "/"]

    def _render(node: dict, current_acc: Path, prefix: str = "") -> None:
        items = sorted(node.keys())
        for idx, key in enumerate(items):
            child_acc = current_acc / key
            is_last = idx == len(items) - 1
            branch = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            is_dir = bool(node[key])

            if is_dir:
                display = f"{key}/"
            else:
                rel_str = str(child_acc)
                tag = " (ignored)" if rel_str in ignored_set else ""
                display = f"{key}{tag}"

            lines.append(f"{prefix}{branch}{display}")
            if is_dir:
                _render(node[key], child_acc, prefix + child_prefix)

    _render(nested, Path())
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Dynamic MarkdownFence Hook
# ---------------------------------------------------------------------------
_orig_markdown_fence_render = MarkdownFence.render

def _enhanced_markdown_fence_render(self: MarkdownFence) -> RenderableType:
    renderable = _orig_markdown_fence_render(self)
    try:
        if isinstance(renderable, Syntax):
            renderable.word_wrap = True
            renderable.padding = 0
            renderable.line_numbers = True

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

            renderable.start_line = start_line
    except Exception:
        pass
    return renderable

MarkdownFence.render = _enhanced_markdown_fence_render

# ---------------------------------------------------------------------------
# Event & Message System
# ---------------------------------------------------------------------------

class RemoteInsert(Message):
    def __init__(
        self,
        text: str,
        lang: str = "",
        file: str = "",
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        super().__init__()
        self.text = text
        self.lang = lang
        self.file = file
        self.start_line = start_line
        self.end_line = end_line

class RequestPhaseUpdate(Message):
    def __init__(self, phase: str) -> None:
        super().__init__()
        self.phase = phase

class RequestFinished(Message):
    def __init__(self, full_text: str, elapsed: float, words: int) -> None:
        super().__init__()
        self.full_text = full_text
        self.elapsed = elapsed
        self.words = words

class RequestFailed(Message):
    def __init__(self, error_message: str) -> None:
        super().__init__()
        self.error_message = error_message

class AppLockEngaged(Message):
    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason

class AppLockReleased(Message):
    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason

# ---------------------------------------------------------------------------
# Expandable App-Wide Root Lock Controller
# ---------------------------------------------------------------------------

class AppLockController:
    """Outermost Air-Traffic-Controller for application-wide locks."""
    def __init__(self, app: App) -> None:
        self.app = app
        self._active_reasons: set[str] = set()

    @property
    def is_locked(self) -> bool:
        return len(self._active_reasons) > 0

    def has_reason(self, reason: str) -> bool:
        return reason in self._active_reasons

    def acquire(self, reason: str) -> None:
        was_locked = self.is_locked
        self._active_reasons.add(reason)
        if not was_locked:
            self.app.post_message(AppLockEngaged(reason))

    def release(self, reason: str) -> None:
        if reason in self._active_reasons:
            self._active_reasons.remove(reason)
            if not self.is_locked:
                self.app.post_message(AppLockReleased(reason))

# ---------------------------------------------------------------------------
# Modals & Dialog Widgets
# ---------------------------------------------------------------------------

class DirectoryPathInput(Input):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_tab_time: float = 0.0

    def _on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()

            now = time.monotonic()
            if now - self._last_tab_time < 0.35:
                self._last_tab_time = 0.0
                self.screen.focus_next()
                return
            else:
                self._last_tab_time = now
                self._autocomplete_directory()
                return

        super()._on_key(event)

    def _autocomplete_directory(self) -> None:
        raw = self.value.strip()
        expanded = os.path.expanduser(raw) if raw else os.getcwd()

        parent_raw = os.path.dirname(raw)
        if raw.endswith(os.sep) or (os.path.isdir(expanded) and not raw.endswith(os.sep)):
            if os.path.isdir(expanded):
                search_dir = expanded
                prefix = ""
                parent_raw = raw.rstrip(os.sep)
            else:
                search_dir = os.path.dirname(expanded) or "."
                prefix = ""
        else:
            search_dir = os.path.dirname(expanded) or "."
            prefix = os.path.basename(expanded)

        try:
            entries: list[str] = []
            for d in os.listdir(search_dir):
                if d in (".", ".."):
                    continue
                if not prefix.startswith(".") and d.startswith("."):
                    continue
                full_path = os.path.join(search_dir, d)
                if os.path.isdir(full_path):
                    entries.append(d)
        except Exception:
            return

        matches = [d for d in entries if d.startswith(prefix)]
        if not matches:
            if prefix.startswith("."):
                try:
                    matches = [
                        d for d in os.listdir(search_dir)
                        if d.startswith(prefix) and os.path.isdir(os.path.join(search_dir, d))
                    ]
                except Exception:
                    pass
            if not matches:
                return

        common = os.path.commonprefix(matches)
        target = matches[0] if len(matches) == 1 else common
        if not target:
            return

        if parent_raw:
            completed = os.path.join(parent_raw, target)
        else:
            completed = target

        if len(matches) == 1:
            completed += os.sep

        if raw.startswith("~") and not completed.startswith("~"):
            home = os.path.expanduser("~")
            if completed.startswith(home):
                completed = "~" + completed[len(home):]

        self.value = completed
        self.cursor_position = len(self.value)

class FilePathInput(Input):
    def __init__(self, base_dir_getter=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_tab_time: float = 0.0
        self.base_dir_getter = base_dir_getter

    def _on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()

            now = time.monotonic()
            if now - self._last_tab_time < 0.35:
                self._last_tab_time = 0.0
                self.screen.focus_next()
                return
            else:
                self._last_tab_time = now
                self._autocomplete_path()
                return

        super()._on_key(event)

    def _autocomplete_path(self) -> None:
        raw = self.value.strip()

        base_dir = os.getcwd()
        if self.base_dir_getter:
            try:
                b = self.base_dir_getter()
                if b:
                    base_dir = os.path.expanduser(b.strip())
            except Exception:
                pass

        if raw.startswith("~") or os.path.isabs(raw):
            expanded = os.path.expanduser(raw)
        else:
            expanded = os.path.join(base_dir, raw) if raw else base_dir

        parent_raw = os.path.dirname(raw)
        if raw.endswith(os.sep) or (os.path.isdir(expanded) and not raw.endswith(os.sep)):
            if os.path.isdir(expanded):
                search_dir = expanded
                prefix = ""
                parent_raw = raw.rstrip(os.sep)
            else:
                search_dir = os.path.dirname(expanded) or base_dir
                prefix = ""
        else:
            search_dir = os.path.dirname(expanded) or base_dir
            prefix = os.path.basename(expanded)

        try:
            entries: list[tuple[str, bool]] = []
            for entry in os.listdir(search_dir):
                if entry in (".", ".."):
                    continue
                if not prefix.startswith(".") and entry.startswith("."):
                    continue
                full_path = os.path.join(search_dir, entry)
                is_dir = os.path.isdir(full_path)
                entries.append((entry, is_dir))
        except Exception:
            return

        matches = [e for e in entries if e[0].startswith(prefix)]
        if not matches:
            return

        if len(matches) == 1:
            name, is_dir = matches[0]
            suffix = os.sep if is_dir else ""
            if parent_raw:
                completed = os.path.join(parent_raw, name) + suffix
            else:
                completed = name + suffix
        else:
            names = [e[0] for e in matches]
            common = os.path.commonprefix(names)
            if not common:
                return
            suffix = ""
            for n, is_d in matches:
                if n == common and is_d:
                    suffix = os.sep
                    break
            if parent_raw:
                completed = os.path.join(parent_raw, common) + suffix
            else:
                completed = common + suffix

        self.value = completed
        self.cursor_position = len(self.value)

class ConfirmModal(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #confirm_dialog {
        padding: 1 2;
        width: 52;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #confirm_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        text-align: center;
        width: 100%;
        color: #ffffff;
    }
    #confirm_buttons {
        width: 100%;
        align-horizontal: center;
    }
    #confirm_buttons Button {
        margin: 0 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #confirm_buttons Button:hover {
        background: #141414;
        color: red;
    }
    #confirm_buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    def __init__(self, message: str = "File already exists. Overwrite?") -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_dialog"):
            yield Label(self.message)
            with Horizontal(id="confirm_buttons"):
                yield Button("No", id="no_btn")
                yield Button("Yes", id="yes_btn")

    def on_mount(self) -> None:
        self.query_one("#no_btn", Button).focus()

    @on(Button.Pressed, "#yes_btn")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no_btn")
    def action_cancel(self) -> None:
        self.dismiss(False)

class ForkModal(ModalScreen[str | None]):
    DEFAULT_CSS = """
    ForkModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #fork_dialog {
        padding: 1 2;
        width: 66;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #fork_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
    }
    #fork_prefix_hint {
        color: red;
        margin-bottom: 1;
    }
    #fork_title_input {
        margin-bottom: 1;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #fork_buttons {
        width: 100%;
        align-horizontal: right;
    }
    #fork_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #fork_buttons Button:hover {
        background: #141414;
        color: red;
    }
    #fork_buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, default_title: str = "") -> None:
        super().__init__()
        clean_default = default_title
        if clean_default.startswith("Fork: "):
            clean_default = clean_default[6:]
        self.default_title = clean_default

    def compose(self) -> ComposeResult:
        with Vertical(id="fork_dialog"):
            yield Label("Name forked chat:")
            yield Label("Prefix 'Fork: ' will be permanently attached to the title.", id="fork_prefix_hint")
            yield Input(
                value=self.default_title,
                placeholder="Enter topic/name...",
                id="fork_title_input",
            )
            with Horizontal(id="fork_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Fork It", id="fork_btn")

    def on_mount(self) -> None:
        self.query_one("#fork_title_input", Input).focus()

    @on(Input.Submitted, "#fork_title_input")
    def on_submit(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#fork_btn")
    def on_fork_pressed(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _confirm(self) -> None:
        raw = self.query_one("#fork_title_input", Input).value.strip()
        if not raw:
            raw = self.default_title or "Untitled"
        if not raw.startswith("Fork: "):
            final_title = f"Fork: {raw}"
        else:
            final_title = raw
        self.dismiss(final_title)

class TurnCard(Vertical):
    can_focus = False

    def __init__(self, index: int, sender: str, text: str, turn_id: str, is_selected: bool = False, **kwargs) -> None:
        instance_id = f"card_{uuid4().hex[:12]}"
        super().__init__(classes="turn_card", id=instance_id, **kwargs)
        self.turn_index = index
        self.turn_id = turn_id
        self.sender = sender
        self.text_content = text
        self.is_selected = is_selected
        self.data = {"turn_index": index, "turn_id": turn_id}

        self.snippets: list[str] = []
        if _MD_PARSER:
            try:
                tokens = _MD_PARSER.parse(text)
                self.snippets = [t.content for t in tokens if t.type == "fence"]
            except Exception:
                pass
        if not self.snippets:
            self.snippets = [m.group(1) for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL)]

    def compose(self) -> ComposeResult:
        with Horizontal(classes="turn_header"):
            yield Label(self._get_box_label(), classes="turn_box_label")
        yield Markdown(f"{self.text_content}\n\n---", classes="turn_body")

    def _get_box_label(self) -> str:
        feed = None
        if self.is_mounted and hasattr(self.app, "query_one"):
            try:
                feed = self.app.query_one("#feed", FeedArea)
            except Exception:
                pass

        fork_active = feed.fork_ui_active if feed else False
        is_current = (feed.active_turn_index == self.turn_index) if feed else False

        if fork_active:
            if self.is_selected:
                box = "[❌]"
            elif is_current:
                box = "[⚠️]"
            else:
                box = "[ ]"
            return f"{box}  {self.sender}  (#{self.turn_index + 1})"
        else:
            return f"      {self.sender}  (#{self.turn_index + 1})"

    def update_display(self) -> None:
        try:
            lbl = self.query_one(".turn_box_label", Label)
            lbl.update(self._get_box_label())
        except Exception:
            pass

    def update_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self.update_display()

    def toggle(self) -> None:
        feed = self.app.query_one("#feed", FeedArea)
        new_val = not self.is_selected
        if new_val:
            feed._fork_selected_indices.add(self.turn_index)
        else:
            feed._fork_selected_indices.discard(self.turn_index)
        self.update_selected(new_val)
        self.refresh()

    @on(events.Click)
    def on_card_click(self, event: events.Click) -> None:
        feed = self.app.query_one("#feed", FeedArea)
        if feed.is_locked():
            event.stop()
            return
        if feed.fork_ui_active:
            curr = event.widget
            while curr and curr is not self:
                if "turn_header" in curr.classes or "turn_box_label" in curr.classes:
                    event.stop()
                    feed.highlight_card(self.turn_index, scroll=False)
                    self.toggle()
                    return
                curr = curr.parent

class WriteSnippetModal(ModalScreen[dict | None]):
    DEFAULT_CSS = """
    WriteSnippetModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #save_dialog {
        padding: 1 2;
        width: 72;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #save_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
        color: #ffffff;
    }
    #save_dialog Input {
        margin-bottom: 1;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #dialog_buttons {
        width: 100%;
        align-horizontal: right;
        margin-top: 1;
    }
    #dialog_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #dialog_buttons Button:hover {
        background: #141414;
        color: red;
    }
    #dialog_buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, snippet_content: str, initial_dir: str) -> None:
        super().__init__()
        self.snippet_content = snippet_content
        self.initial_dir = initial_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="save_dialog"):
            yield Label("Working Directory (Tab: auto-complete, 2x Tab: navigate):")
            yield DirectoryPathInput(value=self.initial_dir, id="dir_input")
            yield Label("Filename to write:")
            yield Input(placeholder="e.g. main.py, server.go, script.sh", id="filename_input")
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Write to Disk", id="confirm_btn")

    def on_mount(self) -> None:
        self.query_one("#filename_input", Input).focus()

    @on(Input.Submitted, "#dir_input")
    def on_dir_submitted(self) -> None:
        self.query_one("#filename_input", Input).focus()

    @on(Input.Submitted, "#filename_input")
    def on_filename_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        working_dir = self.query_one("#dir_input", DirectoryPathInput).value.strip()
        filename = self.query_one("#filename_input", Input).value.strip()

        if not filename:
            self.notify("Filename cannot be blank.", severity="error")
            self.query_one("#filename_input", Input).focus()
            return

        if not working_dir:
            working_dir = os.getcwd()

        self.dismiss({
            "working_dir": working_dir,
            "filename": filename,
            "content": self.snippet_content,
        })

class InsertFileModal(ModalScreen[dict | None]):
    DEFAULT_CSS = """
    InsertFileModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #insert_file_dialog {
        padding: 1 2;
        width: 76;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #insert_file_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
        color: #ffffff;
    }
    #insert_file_dialog Input {
        margin-bottom: 1;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #dialog_buttons {
        width: 100%;
        align-horizontal: right;
        margin-top: 1;
    }
    #dialog_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #dialog_buttons Button:hover {
        background: #141414;
        color: red;
    }
    #dialog_buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str) -> None:
        super().__init__()
        self.initial_dir = initial_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="insert_file_dialog"):
            yield Label("Working Directory (Tab: auto-complete, 2x Tab: navigate):")
            yield DirectoryPathInput(value=self.initial_dir, id="dir_input")
            yield Label("File Path (Tab: auto-complete, 2x Tab: navigate):")
            yield FilePathInput(
                placeholder="e.g. src/main.py, config.json, README.md",
                id="file_input",
                base_dir_getter=self._get_working_dir,
            )
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Insert File", id="confirm_btn")

    def _get_working_dir(self) -> str:
        try:
            dir_val = self.query_one("#dir_input", DirectoryPathInput).value.strip()
            if dir_val:
                return os.path.expanduser(dir_val)
        except Exception:
            pass
        return os.getcwd()

    def on_mount(self) -> None:
        self.query_one("#file_input", FilePathInput).focus()

    @on(Input.Submitted, "#dir_input")
    def on_dir_submitted(self) -> None:
        self.query_one("#file_input", FilePathInput).focus()

    @on(Input.Submitted, "#file_input")
    def on_file_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        working_dir = self.query_one("#dir_input", DirectoryPathInput).value.strip()
        file_path_raw = self.query_one("#file_input", FilePathInput).value.strip()

        if not file_path_raw:
            self.notify("File path cannot be blank.", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        if not working_dir:
            working_dir = os.getcwd()

        base = Path(os.path.expanduser(working_dir)).resolve()
        raw_path = Path(os.path.expanduser(file_path_raw))
        if raw_path.is_absolute():
            resolved_file = raw_path.resolve()
        else:
            resolved_file = (base / raw_path).resolve()

        if not resolved_file.exists():
            self.notify(f"File not found: {resolved_file}", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        if not resolved_file.is_file():
            self.notify(f"Target is a directory: {resolved_file}", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        self.dismiss({
            "working_dir": working_dir,
            "file_path": str(resolved_file),
            "rel_path": file_path_raw,
        })

class GitTreeModal(ModalScreen[dict | None]):
    DEFAULT_CSS = """
    GitTreeModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #git_dialog {
        padding: 1 2;
        width: 110;
        height: 92vh;
        max-height: 95vh;
        border: thick red;
        background: #000000;
    }
    #git_repo_row {
        height: auto;
        margin-bottom: 1;
    }
    #git_repo_row DirectoryPathInput {
        width: 1fr;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #git_repo_row Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #git_repo_row Button:hover {
        background: #141414;
        color: red;
    }
    #git_repo_row Button:focus {
        border: double red;
    }
    #dual_tree_row {
        height: 1fr;
        min-height: 10;
        margin-bottom: 1;
    }
    .tree_pane {
        width: 1fr;
        height: 1fr;
    }
    #pane_tracked {
        margin-right: 1;
    }
    .tree_pane Label {
        text-style: bold;
        height: auto;
        margin-bottom: 0;
        color: #ffffff;
    }
    .tree_pane Tree {
        border: solid red;
        height: 1fr;
        min-height: 5;
        background: #000000;
        color: #ffffff;
    }
    #tree_ignored {
        border: solid #555555;
    }
    #tree_options_row {
        height: auto;
        margin-bottom: 0;
        align-vertical: middle;
    }
    #tree_options_row RadioSet {
        layout: horizontal;
        height: auto;
        background: transparent;
        border: none;
    }
    #tree_options_row RadioButton {
        margin-right: 2;
        color: #ffffff;
    }
    #status_label {
        height: auto;
        color: red;
        margin-top: 1;
        margin-bottom: 1;
    }
    #git_buttons {
        height: auto;
        width: 100%;
        align-horizontal: right;
    }
    #git_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #git_buttons Button:hover {
        background: #141414;
        color: red;
    }
    #git_buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str) -> None:
        super().__init__()
        self.repo_dir = initial_dir
        self.tracked_files: list[str] = []
        self.ignored_files: list[str] = []
        self.selected_files: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="git_dialog"):
            yield Label("Git Repository Path (Tab: auto-complete, 2x Tab: navigate):")
            with Horizontal(id="git_repo_row"):
                yield DirectoryPathInput(value=self.repo_dir, id="git_dir_input")
                yield Button("Scan Tree", id="scan_btn")

            with Horizontal(id="dual_tree_row"):
                with Vertical(classes="tree_pane", id="pane_tracked"):
                    yield Label("Tracked Files:", id="lbl_tracked")
                    yield Tree("Tracked Files", id="tree_tracked")
                with Vertical(classes="tree_pane", id="pane_ignored"):
                    yield Label(".gitignore Ignored Files:", id="lbl_ignored")
                    yield Tree("Ignored Files", id="tree_ignored")

            yield Label("Tree Structure in Prompt:")
            with Horizontal(id="tree_options_row"):
                with RadioSet(id="tree_mode_radios"):
                    yield RadioButton("Full Tree", value=True, id="radio_full")
                    yield RadioButton("Selected Files Only", id="radio_selected")
                    yield RadioButton("None", id="radio_none")

            yield Label("0 files selected. [Space]/Click to toggle file/folder, [a] all in tree", id="status_label")

            with Horizontal(id="git_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Insert Selected & Tree", id="insert_btn")

    def on_mount(self) -> None:
        self.query_one("#tree_tracked", Tree).show_root = False
        self.query_one("#tree_ignored", Tree).show_root = False
        self._scan_and_populate()
        self.query_one("#tree_tracked").focus()

    def _scan_and_populate(self) -> None:
        raw_dir = self.query_one("#git_dir_input", DirectoryPathInput).value.strip()
        expanded = os.path.expanduser(raw_dir) if raw_dir else os.getcwd()
        self.repo_dir = expanded

        if hasattr(self.app, "set_working_dir"):
            self.app.set_working_dir(self.repo_dir)

        tree_tracked = self.query_one("#tree_tracked", Tree)
        tree_ignored = self.query_one("#tree_ignored", Tree)
        tree_tracked.clear()
        tree_ignored.clear()
        self.selected_files.clear()

        try:
            catalog = get_git_files_catalog(self.repo_dir)
            self.tracked_files = catalog["tracked"]
            self.ignored_files = catalog["ignored"]
        except Exception as e:
            self.notify(f"Git Scan Error: {e}", severity="error")
            self.tracked_files = []
            self.ignored_files = []
            self._update_status()
            return

        def populate_tree(tree_widget: Tree, file_list: list[str]) -> None:
            nodes: dict[str, TreeNode] = {"": tree_widget.root}
            for file_path in file_list:
                parts = Path(file_path).parts
                current_path = ""
                for i, part in enumerate(parts):
                    parent_path = current_path
                    current_path = str(Path(current_path) / part) if current_path else part
                    is_file = i == len(parts) - 1

                    if current_path not in nodes:
                        parent_node = nodes[parent_path]
                        if is_file:
                            label = f"[ ] {part}"
                            node = parent_node.add_leaf(label, data={"path": file_path, "name": part, "is_file": True})
                        else:
                            node = parent_node.add(f"[ ] 📁 {part}", data={"path": current_path, "name": part, "is_file": False})
                            node.expand()
                        nodes[current_path] = node
            tree_widget.root.expand()

        populate_tree(tree_tracked, self.tracked_files)
        populate_tree(tree_ignored, self.ignored_files)

        self.query_one("#lbl_tracked", Label).update(f"Tracked Files ({len(self.tracked_files)}):")
        self.query_one("#lbl_ignored", Label).update(f".gitignore Ignored Files ({len(self.ignored_files)}):")
        self._update_status()

    def _get_tree_of_node(self, node: TreeNode) -> Tree | None:
        curr = node
        while curr.parent:
            curr = curr.parent
        for t in (self.query_one("#tree_tracked", Tree), self.query_one("#tree_ignored", Tree)):
            if t.root is curr:
                return t
        return None

    def _refresh_tree_labels(self, root_node: TreeNode) -> tuple[int, int]:
        data = root_node.data or {}
        if data.get("is_file"):
            is_sel = data["path"] in self.selected_files
            part = data.get("name", Path(data["path"]).name)
            box = "✓" if is_sel else " "
            root_node.set_label(f"[{box}] {part}")
            return (1 if is_sel else 0, 1)

        sel_total = 0
        file_total = 0
        for child in root_node.children:
            s, f = self._refresh_tree_labels(child)
            sel_total += s
            file_total += f

        if root_node.parent is not None:
            part = data.get("name", "")
            if file_total > 0 and sel_total == file_total:
                root_node.set_label(f"[✓] 📁 {part}")
            elif sel_total > 0:
                root_node.set_label(f"[-] 📁 {part}")
            else:
                root_node.set_label(f"[ ] 📁 {part}")

        return (sel_total, file_total)

    def _update_status(self) -> None:
        total = len(self.tracked_files) + len(self.ignored_files)
        count = len(self.selected_files)
        lbl = self.query_one("#status_label", Label)
        lbl.update(f"{count} file(s) selected out of {total}. [Space]/Click to toggle file/folder, [a] all in tree")

    def _toggle_node(self, node: TreeNode) -> None:
        data = node.data or {}

        if data.get("is_file"):
            file_path = data["path"]
            if file_path in self.selected_files:
                self.selected_files.remove(file_path)
            else:
                self.selected_files.add(file_path)
        else:
            descendant_files: list[str] = []

            def collect_files(n: TreeNode) -> None:
                if n.data and n.data.get("is_file"):
                    descendant_files.append(n.data["path"])
                for c in n.children:
                    collect_files(c)

            collect_files(node)
            if not descendant_files:
                return

            all_selected = all(p in self.selected_files for p in descendant_files)
            for p in descendant_files:
                if all_selected:
                    self.selected_files.discard(p)
                else:
                    self.selected_files.add(p)

        tree = self._get_tree_of_node(node)
        if tree:
            self._refresh_tree_labels(tree.root)
        self._update_status()

    def _toggle_all_in_tree(self, tree_widget: Tree) -> None:
        contained_files: list[str] = []

        def walk(n: TreeNode):
            if n.data and n.data.get("is_file"):
                contained_files.append(n.data["path"])
            for c in n.children:
                walk(c)

        walk(tree_widget.root)
        if not contained_files:
            return

        all_selected = all(p in self.selected_files for p in contained_files)
        for file_path in contained_files:
            if all_selected:
                self.selected_files.discard(file_path)
            else:
                self.selected_files.add(file_path)

        self._refresh_tree_labels(tree_widget.root)
        self._update_status()

    @on(Tree.NodeSelected)
    def on_tree_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        self._toggle_node(event.node)

    @on(Tree.NodeCollapsed)
    def on_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        event.prevent_default()
        event.stop()
        event.node.expand()

    @on(Button.Pressed, "#scan_btn")
    def on_scan_pressed(self) -> None:
        self._scan_and_populate()

    @on(Input.Submitted, "#git_dir_input")
    def on_dir_submitted(self) -> None:
        self._scan_and_populate()

    @on(Button.Pressed, "#insert_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Tree):
            if event.key == "space":
                event.prevent_default()
                event.stop()
                if focused.cursor_node:
                    self._toggle_node(focused.cursor_node)
                return
            elif event.key == "a":
                event.prevent_default()
                event.stop()
                self._toggle_all_in_tree(focused)
                return

        super()._on_key(event)

    def _submit(self) -> None:
        radios = self.query_one("#tree_mode_radios", RadioSet)

        tree_mode = "full"
        if radios.pressed_button:
            if radios.pressed_button.id == "radio_selected":
                tree_mode = "selected"
            elif radios.pressed_button.id == "radio_none":
                tree_mode = "none"

        self.dismiss({
            "repo_dir": self.repo_dir,
            "selected_files": sorted(list(self.selected_files)),
            "tracked_files": self.tracked_files,
            "ignored_files": self.ignored_files,
            "tree_mode": tree_mode,
        })

class TitlePromptModal(ModalScreen[str | None]):
    DEFAULT_CSS = """
    TitlePromptModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
    }
    #dialog Input {
        margin-bottom: 1;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #dialog-buttons {
        width: 100%;
        align-horizontal: right;
    }
    #dialog-buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #dialog-buttons Button:hover {
        background: #141414;
        color: red;
    }
    #dialog-buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, prompt: str = "Enter chat topic / title:", default_title: str = "") -> None:
        super().__init__()
        self.prompt_text = prompt
        self.default_title = default_title

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.prompt_text)
            yield Input(
                placeholder="Leave blank for auto-generated title...",
                value=self.default_title,
                id="title_input",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Confirm", id="confirm_btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted, "#title_input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        val = self.query_one(Input).value.strip()
        self.dismiss(val)

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

class FrameSelectModal(ModalScreen[dict | None]):
    DEFAULT_CSS = """
    FrameSelectModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #frame_dialog {
        padding: 1 2;
        width: 70;
        height: auto;
        border: thick red;
        background: #000000;
    }
    #frame_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
    }
    #frame_options {
        height: auto;
        max-height: 14;
        margin-bottom: 1;
        border: solid red;
        background: #000000;
        color: #ffffff;
    }
    #dialog-buttons {
        width: 100%;
        align-horizontal: right;
    }
    #dialog-buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    #dialog-buttons Button:hover {
        background: #141414;
        color: red;
    }
    #dialog-buttons Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, frame_data: list[dict], default_file: str = "") -> None:
        super().__init__()
        self.frame_data = frame_data
        self.default_file = default_file
        self.flat_targets: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="frame_dialog"):
            yield Label("Multiple Emacs frames detected.\nSelect destination window:")
            yield OptionList(id="frame_options")
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        opt_list = self.query_one("#frame_options", OptionList)
        self.flat_targets = []
        default_index = 0

        for f in self.frame_data:
            frame_num = f.get("frame_num", 1)
            windows = f.get("windows", [])
            summary_files = ", ".join(w["file_name"] for w in windows)

            if len(windows) > 1:
                header_text = f"Frame {frame_num} (windows: {summary_files})"
                opt_list.add_option(Option(prompt=f"▼ {header_text}", disabled=True))

                for w in windows:
                    self.flat_targets.append(w)
                    idx = len(self.flat_targets) - 1
                    opt_list.add_option(
                        Option(prompt=f"   └─ {w['file_name']}  ({w['buf_name']})", id=str(idx))
                    )
                    if self.default_file and w["file_name"] == self.default_file:
                        default_index = idx
            elif len(windows) == 1:
                w = windows[0]
                self.flat_targets.append(w)
                idx = len(self.flat_targets) - 1
                opt_list.add_option(
                    Option(prompt=f"Frame {frame_num}: {w['file_name']}  ({w['buf_name']})", id=str(idx))
                )
                if self.default_file and w["file_name"] == self.default_file:
                    default_index = idx

        if self.flat_targets:
            opt_list.highlighted = default_index
        opt_list.focus()

    @on(OptionList.OptionSelected, "#frame_options")
    def on_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option_id is not None:
            idx = int(event.option_id)
            self.dismiss(self.flat_targets[idx])

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

class EmacsBaseTextArea(TextArea):
    def on_mount(self) -> None:
        self.soft_wrap = True
        self._mark_point: tuple[int, int] | None = None

    def _sync_selection(self) -> None:
        if self._mark_point is not None:
            self.selection = Selection(self._mark_point, self.cursor_location)

    def _clear_mark(self) -> None:
        self._mark_point = None
        self.move_cursor(self.cursor_location, select=False)

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        if event.key in ("ctrl+space", "ctrl+at", "ctrl+tilde") or (
            event.character and ord(event.character) == 0
        ):
            event.prevent_default(); event.stop()
            self._mark_point = self.cursor_location
            self.selection = Selection(self._mark_point, self._mark_point)
            self.app.notify("Mark set", timeout=1.5)
            return

        is_selecting = self._mark_point is not None

        if event.key in ("ctrl+f", "right"):
            event.prevent_default(); event.stop()
            self.action_cursor_right(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+b", "left"):
            event.prevent_default(); event.stop()
            self.action_cursor_left(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+n", "down"):
            event.prevent_default(); event.stop()
            self.action_cursor_down(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+p", "up"):
            event.prevent_default(); event.stop()
            self.action_cursor_up(select=is_selecting)
            self._sync_selection()
            return
        elif event.key == "ctrl+a":
            event.prevent_default(); event.stop()
            self.action_cursor_line_start(select=is_selecting)
            self._sync_selection()
            return
        elif event.key == "ctrl+e":
            event.prevent_default(); event.stop()
            self.action_cursor_line_end(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("alt+f", "meta+f"):
            event.prevent_default(); event.stop()
            self.action_cursor_word_right(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("alt+b", "meta+b"):
            event.prevent_default(); event.stop()
            self.action_cursor_word_left(select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+home", "alt+<", "meta+<", "alt+comma"):
            event.prevent_default(); event.stop()
            self.move_cursor((0, 0), select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+end", "alt+>", "meta+>", "alt+period"):
            event.prevent_default(); event.stop()
            self.move_cursor(self.document.end, select=is_selecting)
            self._sync_selection()
            return
        elif event.key in ("ctrl+v", "pagedown"):
            event.prevent_default(); event.stop()
            self.action_cursor_page_down()
            self._sync_selection()
            return
        elif event.key in ("alt+v", "meta+v", "pageup"):
            event.prevent_default(); event.stop()
            self.action_cursor_page_up()
            self._sync_selection()
            return
        elif event.key == "ctrl+d":
            event.prevent_default(); event.stop()
            self.action_delete_right()
            self._clear_mark()
            return
        elif event.key == "ctrl+k":
            event.prevent_default(); event.stop()
            self._kill_line_forward()
            self._clear_mark()
            return
        elif event.key == "ctrl+u":
            event.prevent_default(); event.stop()
            self._kill_line_backward()
            self._clear_mark()
            return
        elif event.key in ("alt+d", "meta+d"):
            event.prevent_default(); event.stop()
            self._kill_word_forward()
            self._clear_mark()
            return
        elif event.key in ("ctrl+w", "alt+backspace", "meta+backspace"):
            event.prevent_default(); event.stop()
            if self.selected_text:
                self.app.copy_to_clipboard(self.selected_text)
                self.delete(self.selection.start, self.selection.end)
                self._clear_mark()
            else:
                self._kill_word_backward()
            return
        elif event.key == "ctrl+y":
            event.prevent_default(); event.stop()
            try:
                paste_text = pyperclip.paste()
                if paste_text:
                    if self.selected_text:
                        self.delete(self.selection.start, self.selection.end)
                    self.insert(paste_text)
                    self._clear_mark()
            except Exception:
                pass
            return
        elif event.key in ("alt+w", "meta+w"):
            event.prevent_default(); event.stop()
            if self.selected_text:
                self.app.copy_to_clipboard(self.selected_text)
                self.notify("Copied region", timeout=1.5)
            return
        elif event.key in ("ctrl+slash", "ctrl+underscore"):
            event.prevent_default(); event.stop()
            self.undo()
            self._clear_mark()
            return

        if event.is_printable or event.key in ("backspace", "delete"):
            self._mark_point = None

        super()._on_key(event)

    def _kill_line_forward(self) -> None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if col < len(line):
            killed = line[col:]
            self.delete((row, col), (row, len(line)))
        else:
            if row < self.document.line_count - 1:
                killed = "\n"
                self.delete((row, col), (row + 1, 0))
            else:
                return
        self.app.copy_to_clipboard(killed)

    def _kill_line_backward(self) -> None:
        row, col = self.cursor_location
        if col > 0:
            line = self.document.get_line(row)
            killed = line[:col]
            self.delete((row, 0), (row, col))
            self.app.copy_to_clipboard(killed)

    def _kill_word_forward(self) -> None:
        start = self.cursor_location
        self.action_cursor_word_right(select=False)
        end = self.cursor_location
        if start != end:
            killed = self.get_text_range(start, end)
            self.delete(start, end)
            self.app.copy_to_clipboard(killed)

    def _kill_word_backward(self) -> None:
        start = self.cursor_location
        self.action_cursor_word_left(select=False)
        end = self.cursor_location
        if start != end:
            killed = self.get_text_range(end, start)
            self.delete(end, start)
            self.app.copy_to_clipboard(killed)

class SnippetPreview(EmacsBaseTextArea):
    can_focus = False

    def __init__(self, **kwargs) -> None:
        kwargs["show_line_numbers"] = True
        super().__init__(**kwargs)
        self.active_tag: str = ""

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = True

    def show_snippet(
        self,
        tag: str,
        num: int | str,
        code: str,
        lang: str = "text",
        file: str = "",
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        self.active_tag = tag
        self.show_line_numbers = True
        self.line_number_start = start_line if (start_line and start_line > 0) else 1

        lang_label = lang if lang else "text"
        file_label = f" {file}" if file else ""
        line_label = ""
        if start_line is not None and end_line is not None:
            line_label = f":{start_line}" if start_line == end_line else f":{start_line}-{end_line}"

        self.border_title = f" Edit Snippet {num}{file_label}{line_label} ({lang_label}) "
        self.load_text(code)
        try:
            self.language = lang if lang else None
        except Exception:
            self.language = None

        lines = self.document.line_count if self.document else 1
        target_height = min(max(lines + 2, 4), 10)
        if self.styles.height != target_height:
            self.styles.height = target_height
        self.styles.display = "block"
        self.scroll_home(animate=False)
        self.refresh()

    def hide_preview(self) -> None:
        self.text = ""
        self.active_tag = ""
        self.styles.display = "none"

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self.active_tag:
            input_box = self.app.query_one("#input", ExpandingInput)
            if self.active_tag in input_box._snippets:
                input_box._snippets[self.active_tag]["code"] = self.text.rstrip("\n")

        lines = self.document.line_count if self.document else 1
        target_height = min(max(lines + 2, 4), 10)
        if self.styles.height != target_height:
            self.styles.height = target_height

class ExpandingInput(EmacsBaseTextArea):
    can_focus = True

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = False
        self._snippets: dict[str, dict] = {}
        self._snippet_counter: int = 1
        self._last_nav_time: float = 0.0
        self._nav_cooldown: float = 0.022
        self.call_after_refresh(self._update_layout)

    def register_and_insert_snippet(
        self,
        code: str,
        lang: str = "",
        file: str = "",
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[str, int]:
        current_num = self._snippet_counter
        tag = f"{{&snippet{current_num}}}"
        clean_code = code.rstrip("\n")

        self._snippets[tag] = {
            "code": clean_code,
            "lang": (lang or "").strip(),
            "number": str(current_num),
            "file": (file or "").strip(),
            "start_line": start_line,
            "end_line": end_line,
        }
        self._snippet_counter += 1

        self.insert(f" {tag} ")
        self._clear_mark()

        row, col = self.cursor_location
        if col > 0:
            self.move_cursor((row, col - 1), select=False)

        self.call_after_refresh(self._update_layout)
        self.call_after_refresh(self._sync_snippet_preview)
        return tag, current_num

    def reset_snippets(self) -> None:
        self._snippets.clear()
        self._snippet_counter = 1

    def _get_snippet_at_cursor(self) -> tuple[str, dict] | None:
        try:
            row, col = self.cursor_location
            line = self.document.get_line(row)
        except Exception:
            return None

        for match in re.finditer(r"\{&snippet\d+\}", line):
            if match.start() <= col <= match.end():
                tag = match.group(0)
                if tag in self._snippets:
                    return tag, self._snippets[tag]
        return None

    def _sync_snippet_preview(self) -> None:
        try:
            preview_box = self.app.query_one("#snippet_preview", SnippetPreview)
        except Exception:
            return

        if preview_box.has_focus:
            return

        found = self._get_snippet_at_cursor()
        if found:
            tag, data = found
            if preview_box.active_tag != tag or preview_box.styles.display == "none":
                preview_box.show_snippet(
                    tag=tag,
                    num=data.get("number", ""),
                    code=data.get("code", ""),
                    lang=data.get("lang", ""),
                    file=data.get("file", ""),
                    start_line=data.get("start_line"),
                    end_line=data.get("end_line"),
                )
        else:
            if preview_box.styles.display != "none":
                preview_box.hide_preview()

    @on(TextArea.SelectionChanged)
    def _on_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        self._sync_snippet_preview()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.call_after_refresh(self._update_layout)
        self._sync_snippet_preview()

    def _on_key(self, event: events.Key) -> None:
        feed = self.app.query_one("#feed", FeedArea)
        is_nav = getattr(self.app, "feed_nav_mode", False)

        if is_nav:
            if event.key == "ctrl+q":
                event.prevent_default(); event.stop()
                self.app.action_quit()
                return

            if event.key in ("escape", "ctrl+o"):
                event.prevent_default(); event.stop()
                self.app.action_toggle_feed_nav()
                return

            if self.app.intercept_c_c_key(event):
                return

            # Frame-Rate Input Governor for rapid arrow repeats
            now = time.monotonic()
            if event.key in ("down", "up", "shift+up", "shift+down"):
                if now - self._last_nav_time < self._nav_cooldown:
                    event.prevent_default(); event.stop()
                    return
                self._last_nav_time = now

            if event.key in ("period", "full_stop", "."):
                event.prevent_default(); event.stop()
                feed.toggle_fork_ui()
                self.app.update_feed_nav_banner()
                return

            elif event.key == "space":
                event.prevent_default(); event.stop()
                feed.toggle_current_card_selection()
                return

            elif event.key == "a":
                event.prevent_default(); event.stop()
                feed.toggle_all_fork_checkboxes()
                return

            elif event.key in ("enter", "return"):
                event.prevent_default(); event.stop()
                self.app.action_fork_chat()
                return

            # Viewport Height Paging (Shift + Arrows) -> Triggers 1D Raycast & Runway Sync
            elif event.key in ("shift+up", "shift+down"):
                event.prevent_default(); event.stop()
                direction = -1 if event.key == "shift+up" else 1
                feed.viewport_page_navigate(direction)
                return

            # Fine-line Arrow Navigation (pure Up/Down) -> Triggers 1D Raycast & Runway Sync
            elif event.key == "down":
                event.prevent_default(); event.stop()
                feed.arrow_navigate(1)
                return
            elif event.key == "up":
                event.prevent_default(); event.stop()
                feed.arrow_navigate(-1)
                return

            # Discrete Card Stepping -> Docks to Row 0 Top
            elif event.key in ("pagedown", "ctrl+j"):
                event.prevent_default(); event.stop()
                feed.step_card(1)
                return
            elif event.key in ("pageup", "ctrl+k"):
                event.prevent_default(); event.stop()
                feed.step_card(-1)
                return

            # Strict Localized Card-by-Card Snippet Traversal (Protected by Runway Sync)
            elif event.key in ("alt+n", "meta+n"):
                event.prevent_default(); event.stop()
                feed.navigate_snippet(1)
                return
            elif event.key in ("alt+p", "meta+p"):
                event.prevent_default(); event.stop()
                feed.navigate_snippet(-1)
                return

            # Home / End -> Docks header flush to Row 0
            elif event.key == "home":
                event.prevent_default(); event.stop()
                feed.jump_to_home()
                return
            elif event.key == "end":
                event.prevent_default(); event.stop()
                feed.jump_to_end()
                return

            event.prevent_default(); event.stop()
            return

        if self.app.intercept_c_c_key(event):
            return

        if event.key == "ctrl+o":
            event.prevent_default(); event.stop()
            self.app.action_toggle_feed_nav()
            return

        if event.key in ("shift+enter", "shift+return", "ctrl+j", "alt+enter", "meta+enter"):
            event.prevent_default(); event.stop()
            self.action_newline()
            return
        elif event.key == "enter":
            event.prevent_default(); event.stop()
            self.action_submit()
            return

        if event.key in ("ctrl+g", "escape"):
            event.prevent_default(); event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            return

        super()._on_key(event)

    def _update_layout(self) -> None:
        lines = 1
        if hasattr(self, "wrapped_document") and self.wrapped_document:
            lines = self.wrapped_document.height
        elif hasattr(self, "document") and self.document:
            lines = self.document.line_count

        target_height = min(max(lines, 1), 6) + 2
        if self.styles.height != target_height:
            self.styles.height = target_height

        self.scroll_cursor_visible()

    def action_newline(self) -> None:
        self.insert("\n")
        self.scroll_cursor_visible()

    def action_submit(self) -> None:
        raw_text = self.text.strip()
        if not raw_text:
            return

        def replacer(match):
            token = match.group(0).replace(" ", "")
            if token in self._snippets:
                item = self._snippets[token]
                lang = item["lang"]
                num = item["number"]
                code = item["code"]
                file = item.get("file", "")
                start_l = item.get("start_line")
                end_l = item.get("end_line")

                file_part = ""
                if file:
                    line_part = ""
                    if start_l is not None and end_l is not None:
                        if start_l == end_l:
                            line_part = f" (Line {start_l})"
                        else:
                            line_part = f" (Lines {start_l}-{end_l})"
                    file_part = f" - `{file}`{line_part}"

                lang_part = f" - `{lang}`" if lang else ""
                title = f"#### (Snippet {num}){file_part}{lang_part}"
                ticks = chr(96) * 3
                return f"\n\n{title}\n{ticks}{lang}\n{code}\n{ticks}\n\n"
            return match.group(0)

        resolved_text = re.sub(r"\{\s*&snippet\d+\s*\}", replacer, raw_text)
        resolved_text = re.sub(r"\n{3,}", "\n\n", resolved_text).strip()

        self.post_message(self.Submitted(resolved_text))
        self.clear()
        self.reset_snippets()
        self._clear_mark()
        self.call_after_refresh(self._update_layout)

        self.app.query_one("#snippet_preview", SnippetPreview).hide_preview()

# ---------------------------------------------------------------------------
# Feed View & Target Snapping Engine
# ---------------------------------------------------------------------------

class FeedArea(VerticalScroll):
    can_focus = False
    auto_scroll = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.active_turn_index: int = 0
        self.active_snippet_turn: int = -1
        self.active_snippet_fence: int = -1

        self.fork_ui_active: bool = False
        self._fork_selected_indices: set[int] = set()

        self._all_messages: list[dict] = []
        self._win_start: int = 0
        self._win_end: int = 0

        # In-Memory 1D Header Map: {Header Line Y: (Turn Index, Turn ID)}
        self._header_map: dict[int, tuple[int, str]] = {}

    def compose(self) -> ComposeResult:
        yield Vertical(id="turns_container")

    def get_tier_config(self) -> tuple[int, int]:
        return (DEFAULT_WINDOW_CAPACITY, 1)

    def is_locked(self) -> bool:
        """Queries the root AppLockController directly."""
        return self.app.lock.is_locked

    def scroll_to_widget(self, widget: Widget, *args, **kwargs) -> None:
        """Suppresses Textual's automatic child-focus/layout snapping."""
        pass

    def clear(self) -> None:
        self.fork_ui_active = False
        self.remove_class("fork-ui-active")
        self._fork_selected_indices.clear()
        self.active_snippet_turn = -1
        self.active_snippet_fence = -1
        self._header_map.clear()
        if hasattr(self.app, "hide_status"):
            self.app.hide_status()

        self.set_messages([])

    def _sync_header_map(self) -> None:
        """Reads card header row positions after layout pass; spatial map is cached in-memory."""
        self._header_map.clear()
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and getattr(child, "virtual_region", None):
                self._header_map[int(child.virtual_region.y)] = (child.turn_index, child.turn_id)

    def _get_card_header_y(self, turn_idx: int) -> int | None:
        """Looks up the absolute canvas line of a card header directly from our in-memory 1D map."""
        for y, (idx, _) in self._header_map.items():
            if idx == turn_idx:
                return y
        return None

    def _execute_1d_raycast(self, current_y: int | None = None) -> None:
        """Executes the pure in-memory 1D outward raycast strictly on continuous movement.
        Enforces lockout de-activation and sameness checks to eliminate race conditions.
        """
        if self.is_locked() or not self._header_map or not self._all_messages:
            return

        y = int(self.scroll_y) if current_y is None else int(current_y)
        view_h = self.container_size.height or 24
        prev_target = self.active_turn_index
        total = len(self._all_messages)

        if CENTER_SCREEN_MODE:
            center_y = y + (view_h // 2)
            t_idx, t_id, delta = cast_ray_from_center(
                center_y, self._header_map, self._win_start, self._win_end, total
            )

            current_active_id = getattr(self.app, "current_chat_center_marker", "").split(":")[0]
            if t_id != current_active_id:
                self.active_turn_index = t_idx
                if hasattr(self.app, "current_chat_last_index"):
                    self.app.current_chat_last_index = t_idx
                    sign = f"+{delta}" if delta > 0 else str(delta)
                    self.app.current_chat_center_marker = f"{t_id}:{sign}" if delta != 0 else t_id
            else:
                self.active_turn_index = t_idx
        else:
            for line_y in sorted(self._header_map.keys()):
                if line_y >= y:
                    t_idx, t_id = self._header_map[line_y]
                    current_active_id = getattr(self.app, "current_chat_center_marker", "")
                    if t_id != current_active_id:
                        self.active_turn_index = t_idx
                        if hasattr(self.app, "current_chat_last_index"):
                            self.app.current_chat_last_index = t_idx
                            self.app.current_chat_center_marker = t_id
                    break

        if self.active_turn_index != prev_target and not self.is_locked():
            self.highlight_card(self.active_turn_index, scroll=False)
            self.request_runway_sync(self.active_turn_index, prev_idx=prev_target, discrete_dock=False)

    # --- Pre-Flight Checks & Synchronous Gate Initiation ---

    def will_require_load(self, target_idx: int) -> bool:
        """Functional pre-flight check: determines if target card is outside currently mounted boundary."""
        cards_above = min(target_idx, RUNWAY_ABOVE_BUDGET)
        cards_below = min(len(self._all_messages) - 1 - target_idx, RUNWAY_BELOW_BUDGET)
        rem = DEFAULT_WINDOW_CAPACITY - (1 + cards_above + cards_below)
        if target_idx - cards_above == 0:
            cards_below = min(len(self._all_messages) - 1 - target_idx, cards_below + rem)
        elif target_idx + cards_below == len(self._all_messages) - 1:
            cards_above = min(target_idx, cards_above + rem)

        ideal_start = max(0, target_idx - cards_above)
        ideal_end = min(len(self._all_messages), target_idx + cards_below + 1)
        return not (self._win_start == ideal_start and self._win_end == ideal_end)

    def request_runway_sync(
        self,
        target_idx: int,
        prev_idx: int | None = None,
        discrete_dock: bool = False,
        target_fence_idx: int | None = None,
    ) -> None:
        """Synchronously locks the entire application before dispatching the background worker."""
        if self.will_require_load(target_idx):
            self.app.lock.acquire("dom_load")
            self.app.show_loader_banner()

        self._sync_runway_to_target(
            target_idx,
            prev_idx=prev_idx,
            discrete_dock=discrete_dock,
            target_fence_idx=target_fence_idx,
        )

    # --- Unified 1-in / 1-out Conveyor Belt (Atomic Single-Tick Zero-Shift) ---

    @work(exclusive=True)
    async def _sync_runway_to_target(
        self,
        target_idx: int,
        prev_idx: int | None = None,
        discrete_dock: bool = False,
        target_fence_idx: int | None = None,
    ) -> None:
        """Slides the window around target_idx under the outermost app root lock."""
        try:
            total = len(self._all_messages)
            if total <= DEFAULT_WINDOW_CAPACITY:
                if discrete_dock:
                    target_card = self._get_target_widget(target_idx)
                    if target_card:
                        self._scroll_to_turn_widget(target_card, center=False)
                elif target_fence_idx is not None:
                    self._apply_fence_highlight(target_idx, target_fence_idx)
                return

            cards_above = min(target_idx, RUNWAY_ABOVE_BUDGET)
            cards_below = min(total - 1 - target_idx, RUNWAY_BELOW_BUDGET)
            rem = DEFAULT_WINDOW_CAPACITY - (1 + cards_above + cards_below)
            if target_idx - cards_above == 0:
                cards_below = min(total - 1 - target_idx, cards_below + rem)
            elif target_idx + cards_below == total - 1:
                cards_above = min(target_idx, cards_above + rem)

            ideal_start = max(0, target_idx - cards_above)
            ideal_end = min(total, target_idx + cards_below + 1)

            container = self.query_one("#turns_container", Vertical)
            mounted_cards = [c for c in container.children if isinstance(c, TurnCard)]
            mounted_indices = {c.turn_index for c in mounted_cards}
            desired_indices = set(range(ideal_start, ideal_end))

            if mounted_indices == desired_indices:
                self._win_start = ideal_start
                self._win_end = ideal_end
                if discrete_dock:
                    target_card = self._get_target_widget(target_idx)
                    if target_card:
                        self._scroll_to_turn_widget(target_card, center=False)
                elif target_fence_idx is not None:
                    self._apply_fence_highlight(target_idx, target_fence_idx)
                return

            # Capture Visual Anchor prior to mutation:
            # We preserve the exact signed distance from the raycast target header to screen center
            anchor_card = self._get_target_widget(self.active_turn_index)
            signed_delta = 0
            if anchor_card and anchor_card.virtual_region:
                view_h = self.container_size.height or 24
                center_y = int(self.scroll_y) + (view_h // 2)
                signed_delta = center_y - int(anchor_card.virtual_region.y)

            # 1. Prune out-of-boundary cards
            cards_to_remove = [c for c in mounted_cards if c.turn_index not in desired_indices]
            for c in cards_to_remove:
                await c.remove()

            # 2. Mount missing cards below (in order)
            for idx in range(ideal_start, ideal_end):
                if idx not in mounted_indices and (not mounted_cards or idx > mounted_cards[-1].turn_index):
                    new_card = self._create_turn_widget(idx)
                    if new_card:
                        await container.mount(new_card)

            # 3. Mount missing cards above (prepending)
            for idx in range(ideal_start, ideal_end):
                if idx not in mounted_indices and (mounted_cards and idx < mounted_cards[0].turn_index):
                    new_card = self._create_turn_widget(idx)
                    if new_card:
                        first_child = container.children[0] if container.children else None
                        if first_child:
                            await container.mount(new_card, before=first_child)
                        else:
                            await container.mount(new_card)

            self._win_start = ideal_start
            self._win_end = ideal_end

            # Synchronous Single-Tick Layout Realignment
            settle_event = asyncio.Event()

            def _on_runway_settle() -> None:
                try:
                    self._sync_header_map()
                    view_h = self.container_size.height or 24

                    if discrete_dock:
                        target_card = self._get_target_widget(target_idx)
                        if target_card:
                            self.highlight_card(target_idx, scroll=False)
                            self._scroll_to_turn_widget(target_card, center=False)
                    else:
                        # Re-anchor screen position using captured signed delta (Zero Visual Shift)
                        ref_card = self._get_target_widget(self.active_turn_index)
                        if ref_card and getattr(ref_card, "virtual_region", None):
                            new_header_y = int(ref_card.virtual_region.y)
                            new_center_y = new_header_y + signed_delta
                            target_scroll_y = max(0, new_center_y - (view_h // 2))
                            max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - view_h))
                            self.scroll_y = min(max_scroll, target_scroll_y)

                    if target_fence_idx is not None:
                        self._apply_fence_highlight(target_idx, target_fence_idx)
                finally:
                    settle_event.set()

            self.call_after_refresh(_on_runway_settle)
            try:
                await asyncio.wait_for(settle_event.wait(), timeout=0.6)
            except asyncio.TimeoutError:
                self._sync_header_map()

        finally:
            self.app.hide_loader_banner()
            def _complete_unlock() -> None:
                self.app.lock.release("dom_load")
            self.call_after_refresh(_complete_unlock)

    def _apply_fence_highlight(self, turn_idx: int, fence_idx: int) -> None:
        """Docks chosen snippet directly to Screen Row 2 using settled widget relative offsets."""
        target_card = self._get_target_widget(turn_idx)
        if not target_card:
            return

        self.highlight_card(turn_idx, scroll=False)
        fences = list(target_card.query(MarkdownFence))
        if 0 <= fence_idx < len(fences):
            for f in self._get_fences():
                f.remove_class("active-snippet")
            chosen = fences[fence_idx]
            chosen.add_class("active-snippet")

            card_header_y = self._get_card_header_y(turn_idx)
            if card_header_y is not None:
                card_region_y = int(target_card.virtual_region.y)
                chosen_region_y = int(chosen.virtual_region.y)
                relative_offset = max(0, chosen_region_y - card_region_y)
                target_scroll_y = max(0, (card_header_y + relative_offset) - 2)
                max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))
                self.scroll_y = min(max_scroll, target_scroll_y)
            chosen.refresh()

    def _create_turn_widget(self, idx: int) -> TurnCard | None:
        if not (0 <= idx < len(self._all_messages)):
            return None

        turn = self._all_messages[idx]
        turn_id = turn.get("turn_id")
        if not turn_id:
            turn_id = f"turn_{uuid4().hex[:8]}"
            turn["turn_id"] = turn_id

        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_index == idx:
                return None

        sender = "You" if turn["role"] == "user" else "Gemini"
        is_sel = idx in self._fork_selected_indices

        card = TurnCard(
            index=idx,
            sender=sender,
            text=turn["text"],
            turn_id=turn_id,
            is_selected=is_sel,
        )

        if idx == self.active_turn_index:
            card.add_class("card-active")

        return card

    def set_messages(self, messages: list[dict], initial_target_marker: str | int | None = None) -> None:
        self.fork_ui_active = False
        self.remove_class("fork-ui-active")
        self._fork_selected_indices.clear()
        self.active_snippet_turn = -1
        self.active_snippet_fence = -1
        if hasattr(self.app, "hide_status"):
            self.app.hide_status()

        self._run_target_mutation("reset_chat", new_messages=messages, target_marker=initial_target_marker)

    def _get_target_widget(self, idx: int) -> TurnCard | None:
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_index == idx:
                return child
        return None

    def _get_target_widget_by_id(self, turn_id: str) -> TurnCard | None:
        if not turn_id:
            return None
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_id == turn_id:
                return child
        return None

    def _scroll_to_turn_widget(
        self,
        target_w: TurnCard,
        center: bool = False,
        line_offset: int | None = None,
    ) -> None:
        """Positions target widget in viewport using pure 1D coordinate assignment."""
        view_h = self.container_size.height
        header_y = int(target_w.virtual_region.y)
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - view_h))

        if not center:
            self.scroll_y = max(0, min(max_scroll, header_y))
            return

        offset = line_offset if line_offset is not None else 0
        target_y = (header_y + offset) - (view_h // 2)
        self.scroll_y = max(0, min(max_scroll, target_y))

    # --- Mouse Scroll Wheel Handlers (Strictly Gated by Lock) ---

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self.is_locked():
            event.stop()
            return
        self.scroll_down(animate=False)
        self._execute_1d_raycast()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self.is_locked():
            event.stop()
            return
        self.scroll_up(animate=False)
        self._execute_1d_raycast()

    # --- Target Mutation Initializer & Full Resets ---

    @work(exclusive=True)
    async def _run_target_mutation(
        self,
        action: str,
        new_messages: list[dict] | None = None,
        target_index: int | None = None,
        target_marker: str | int | None = None,
    ) -> None:
        self.app.lock.acquire("dom_load")
        container = self.query_one("#turns_container", Vertical)
        capacity, _ = self.get_tier_config()

        try:
            if action == "reset_chat":
                self._all_messages = list(new_messages or [])
                total = len(self._all_messages)

                await container.remove_children()

                if total == 0:
                    self._win_start = 0
                    self._win_end = 0
                    self.active_turn_index = 0
                    self._header_map.clear()
                    self.scroll_y = 0
                    return

                if target_marker == "end":
                    self._win_start = max(0, total - capacity)
                    self._win_end = total
                    widgets_to_mount = [
                        w for idx in range(self._win_start, self._win_end)
                        if (w := self._create_turn_widget(idx)) is not None
                    ]
                    if widgets_to_mount:
                        await container.mount_all(widgets_to_mount)

                    settle_event = asyncio.Event()

                    def _on_end_reset_settle() -> None:
                        try:
                            self._sync_header_map()
                            self.active_turn_index = total - 1
                            self.highlight_card(total - 1, scroll=False)
                            target_w = self._get_target_widget(total - 1)
                            if target_w:
                                self._scroll_to_turn_widget(target_w, center=False)
                            else:
                                self.scroll_end(animate=False)
                        finally:
                            settle_event.set()

                    self.call_after_refresh(_on_end_reset_settle)
                    try:
                        await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                    except asyncio.TimeoutError:
                        pass
                    return

                req_idx = 0
                line_offset: int | None = None

                if target_marker is not None:
                    marker_str = str(target_marker).strip()
                    if ":" in marker_str:
                        tid, offset_str = marker_str.split(":", 1)
                        if CENTER_SCREEN_MODE:
                            try:
                                parsed = int(offset_str)
                                line_offset = parsed if parsed != 0 else None
                            except Exception:
                                line_offset = None
                        else:
                            line_offset = None
                    else:
                        tid = marker_str

                    matched_idx = next((i for i, m in enumerate(self._all_messages) if m.get("turn_id") == tid), None)
                    if matched_idx is not None:
                        req_idx = matched_idx
                    else:
                        try:
                            req_idx = max(0, min(total - 1, int(target_marker)))
                        except Exception:
                            req_idx = max(0, total - 1)
                elif target_index is not None and 0 <= target_index < total:
                    req_idx = target_index
                else:
                    req_idx = max(0, total - 1)

                cards_above = min(req_idx, RUNWAY_ABOVE_BUDGET)
                cards_below = min(total - 1 - req_idx, RUNWAY_BELOW_BUDGET)
                rem = capacity - (1 + cards_above + cards_below)
                if req_idx - cards_above == 0:
                    cards_below = min(total - 1 - req_idx, cards_below + rem)
                elif req_idx + cards_below == total - 1:
                    cards_above = min(req_idx, cards_above + rem)

                self._win_start = max(0, req_idx - cards_above)
                self._win_end = min(total, req_idx + cards_below + 1)

                widgets_to_mount = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if widgets_to_mount:
                    await container.mount_all(widgets_to_mount)

                settle_event = asyncio.Event()

                def _on_initial_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.active_turn_index = req_idx
                        target_w = self._get_target_widget(req_idx)
                        if target_w:
                            should_center = CENTER_SCREEN_MODE and (line_offset is not None)
                            self._scroll_to_turn_widget(
                                target_w,
                                center=should_center,
                                line_offset=line_offset,
                            )
                        else:
                            self.scroll_end(animate=False)
                        self.highlight_card(req_idx, scroll=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_initial_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

            elif action == "jump_home":
                total = len(self._all_messages)
                if total == 0:
                    self.scroll_home(animate=False)
                    return

                self.app.show_loader_banner()
                self._win_start = 0
                self._win_end = min(capacity, total)

                await container.remove_children()
                home_widgets = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if home_widgets:
                    await container.mount_all(home_widgets)

                self.active_turn_index = 0
                settle_event = asyncio.Event()

                def _on_home_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.scroll_y = 0
                        self.highlight_card(0, scroll=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_home_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

            elif action == "jump_end":
                total = len(self._all_messages)
                if total == 0:
                    self.scroll_end(animate=False)
                    return

                self.app.show_loader_banner()
                self._win_start = max(0, total - capacity)
                self._win_end = total

                await container.remove_children()
                end_widgets = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if end_widgets:
                    await container.mount_all(end_widgets)

                self.active_turn_index = total - 1
                settle_event = asyncio.Event()

                def _on_end_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.highlight_card(self.active_turn_index, scroll=False)
                        target_w = self._get_target_widget(self.active_turn_index)
                        if target_w:
                            self._scroll_to_turn_widget(target_w, center=False)
                        else:
                            self.scroll_end(animate=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_end_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

        finally:
            self.app.hide_loader_banner()
            def _settle_release():
                self.app.lock.release("dom_load")
            self.call_after_refresh(_settle_release)

    # --- Unified Navigation: Card Stepping (Discrete) vs Viewport/Arrows (Continuous) ---

    def step_card(self, delta: int) -> None:
        """Discrete card stepping: explicit intent, docks header flush to Row 0 Top."""
        total = len(self._all_messages)
        if not total or self.is_locked():
            return

        target_idx = max(0, min(total - 1, self.active_turn_index + delta))
        if target_idx == self.active_turn_index:
            return

        prev_idx = self.active_turn_index
        self.active_turn_index = target_idx
        if hasattr(self.app, "current_chat_last_index"):
            self.app.current_chat_last_index = target_idx
            self.app.current_chat_center_marker = self._all_messages[target_idx].get("turn_id", "")

        existing_card = self._get_target_widget(target_idx)
        if isinstance(existing_card, TurnCard) and not self.will_require_load(target_idx):
            self.highlight_card(target_idx, scroll=False)
            self._scroll_to_turn_widget(existing_card, center=False)
        else:
            self.request_runway_sync(target_idx, prev_idx=prev_idx, discrete_dock=True)

    def viewport_page_navigate(self, direction: int) -> None:
        """Continuous viewport stepping: Raycast fires to detect nearest card."""
        if self.is_locked():
            return

        page_step = max(self.container_size.height - 3, 5)
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))

        if direction < 0:
            target_y = max(0, self.scroll_y - page_step)
            self.scroll_to(y=target_y, animate=False)
        else:
            target_y = min(max_scroll, self.scroll_y + page_step)
            self.scroll_to(y=target_y, animate=False)

        self._execute_1d_raycast(target_y)

    def arrow_navigate(self, direction: int) -> None:
        """Continuous fine-line arrow navigation: Raycast fires to detect nearest card."""
        if self.is_locked():
            return

        line_step = 2
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))

        if direction < 0:
            target_y = max(0, self.scroll_y - line_step)
            self.scroll_y = target_y
            self._execute_1d_raycast(target_y)
        else:
            target_y = min(max_scroll, self.scroll_y + line_step)
            self.scroll_y = target_y
            self._execute_1d_raycast(target_y)

    def jump_to_home(self) -> None:
        if self.is_locked():
            return
        self.highlight_card(0, scroll=False)
        self._run_target_mutation("jump_home")

    def jump_to_end(self) -> None:
        if self.is_locked():
            return
        last_idx = max(0, len(self._all_messages) - 1)
        self.highlight_card(last_idx, scroll=False)
        self._run_target_mutation("jump_end")

    async def append_message(self, sender: str, text: str, jump_to_start: bool = False) -> None:
        new_idx = len(self._all_messages)
        turn_data = {
            "turn_id": f"turn_{uuid4().hex[:8]}",
            "role": "user" if sender == "You" else "model",
            "text": text,
        }
        self._all_messages.append(turn_data)

        container = self.query_one("#turns_container", Vertical)
        capacity, _ = self.get_tier_config()

        if self._win_end == new_idx:
            new_widget = self._create_turn_widget(new_idx)
            if new_widget is not None:
                await container.mount(new_widget)
                self._win_end += 1

                while (self._win_end - self._win_start) > capacity and len(container.children) > 0:
                    top_child = container.children[0]
                    await top_child.remove()
                    self._win_start += 1

                self.active_turn_index = new_idx

                def _on_append_settle() -> None:
                    self._sync_header_map()
                    if jump_to_start:
                        self._scroll_to_turn_widget(new_widget, center=False)
                    else:
                        self.scroll_end(animate=False)

                self.call_after_refresh(_on_append_settle)
        else:
            self.jump_to_end()

    # --- Strict Localized Card-by-Card Snippet Traversal ---

    def _get_fences(self) -> list[MarkdownFence]:
        return list(self.query(MarkdownFence))

    def _extract_code_from_fence(self, fence: MarkdownFence) -> str:
        if hasattr(fence, "text") and fence.text:
            return fence.text
        if hasattr(fence, "code") and fence.code:
            return fence.code
        if hasattr(fence, "renderable") and isinstance(fence.renderable, Syntax):
            return fence.renderable.code
        for child in fence.walk_children():
            if hasattr(child, "renderable") and isinstance(child.renderable, Syntax):
                return child.renderable.code
        return str(getattr(fence, "renderable", ""))

    def _count_snippets_in_text(self, text: str) -> int:
        if _MD_PARSER:
            try:
                tokens = _MD_PARSER.parse(text)
                count = sum(1 for t in tokens if t.type == "fence")
                if count > 0:
                    return count
            except Exception:
                pass
        return len(re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL))

    def navigate_snippet(self, delta: int) -> None:
        """Card-by-card localized snippet traversal held down strictly by root locking."""
        if self.is_locked():
            return

        total = len(self._all_messages)
        if not total:
            return

        curr_t = self.active_snippet_turn
        curr_f = self.active_snippet_fence

        if curr_t < 0 or curr_t >= total:
            curr_t = self.active_turn_index
            curr_f = -1

        curr_card = self._get_target_widget(curr_t)
        curr_count = len(curr_card.snippets) if curr_card else self._count_snippets_in_text(self._all_messages[curr_t]["text"])

        # 1. Forward (Alt+n)
        if delta > 0:
            if curr_f + 1 < curr_count:
                self.select_response_snippet(curr_t, curr_f + 1)
                return

            next_t = curr_t + 1
            while next_t < total:
                snip_count = self._count_snippets_in_text(self._all_messages[next_t]["text"])
                if snip_count > 0:
                    self.select_response_snippet(next_t, 0)
                    return
                next_t += 1

            self.app.notify("Already at last snippet", timeout=1.5)
            return

        # 2. Backward (Alt+p)
        else:
            if curr_f > 0:
                self.select_response_snippet(curr_t, curr_f - 1)
                return

            prev_t = curr_t - 1
            while prev_t >= 0:
                snip_count = self._count_snippets_in_text(self._all_messages[prev_t]["text"])
                if snip_count > 0:
                    self.select_response_snippet(prev_t, snip_count - 1)
                    return
                prev_t -= 1

            self.app.notify("Already at first snippet", timeout=1.5)
            return

    def select_response_snippet(self, turn_idx: int, fence_idx: int) -> None:
        """Docks locally if mounted; enters lock cycle if conveyor sliding is required."""
        prev_turn = self.active_turn_index
        self.active_snippet_turn = turn_idx
        self.active_snippet_fence = fence_idx
        self.active_turn_index = turn_idx

        turn_w = self._get_target_widget(turn_idx)
        if isinstance(turn_w, TurnCard) and not self.will_require_load(turn_idx):
            self._apply_fence_highlight(turn_idx, fence_idx)
            return

        self.request_runway_sync(
            turn_idx,
            prev_idx=prev_turn,
            discrete_dock=False,
            target_fence_idx=fence_idx,
        )

    def select_snippet_by_widget(self, target_fence: MarkdownFence) -> None:
        fences = self._get_fences()
        if target_fence not in fences:
            return

        parent_turn = target_fence
        while parent_turn and not isinstance(parent_turn, TurnCard):
            parent_turn = parent_turn.parent

        if isinstance(parent_turn, TurnCard):
            turn_fences = list(parent_turn.query(MarkdownFence))
            self.active_snippet_turn = parent_turn.turn_index
            self.active_snippet_fence = turn_fences.index(target_fence) if target_fence in turn_fences else -1
            self.highlight_card(parent_turn.turn_index, scroll=False)

        for f in fences:
            if f is target_fence:
                f.add_class("active-snippet")
                f.refresh()
            else:
                f.remove_class("active-snippet")
                f.refresh()

    def get_active_snippet(self) -> str | None:
        target_card = self._get_target_widget(self.active_snippet_turn)
        if target_card and 0 <= self.active_snippet_fence < len(target_card.snippets):
            return target_card.snippets[self.active_snippet_fence]

        for f in self._get_fences():
            if "active-snippet" in f.classes:
                return self._extract_code_from_fence(f)
        return None

    # --- Unified Navigation & Zero-Cost Fork Selection ---

    def toggle_fork_ui(self) -> None:
        self.fork_ui_active = not self.fork_ui_active
        if self.fork_ui_active:
            self.add_class("fork-ui-active")
        else:
            self.remove_class("fork-ui-active")
        self._refresh_all_fork_card_checkboxes()

    def highlight_card(self, turn_idx: int, scroll: bool = True) -> None:
        prev_idx = self.active_turn_index
        self.active_turn_index = turn_idx
        container = self.query_one("#turns_container", Vertical)

        for card in container.query(TurnCard):
            if card.turn_index == turn_idx:
                card.add_class("card-active")
                card.update_display()
                if scroll:
                    self._scroll_to_turn_widget(card, center=False)
            else:
                card.remove_class("card-active")
                if card.turn_index == prev_idx:
                    card.update_display()

    def toggle_current_card_selection(self) -> None:
        target_card = self._get_target_widget(self.active_turn_index)
        if isinstance(target_card, TurnCard):
            target_card.toggle()

    def toggle_all_fork_checkboxes(self) -> None:
        total = len(self._all_messages)
        if not total:
            return

        all_selected = (len(self._fork_selected_indices) == total)
        if all_selected:
            self._fork_selected_indices.clear()
        else:
            self._fork_selected_indices = set(range(total))

        self._refresh_all_fork_card_checkboxes()
        state_msg = "Selected all turns" if not all_selected else "Deselected all turns"
        self.app.notify(state_msg, timeout=2.0)

    def _refresh_all_fork_card_checkboxes(self) -> None:
        container = self.query_one("#turns_container", Vertical)
        for card in container.query(TurnCard):
            card.update_selected(card.turn_index in self._fork_selected_indices)

    def get_selected_fork_indices(self) -> list[int]:
        return sorted(list(self._fork_selected_indices))

    @on(events.Click)
    def _on_feed_click(self, event: events.Click) -> None:
        if self.is_locked() or self.fork_ui_active:
            return

        curr = event.widget
        while curr and curr is not self:
            if isinstance(curr, MarkdownFence):
                self.select_snippet_by_widget(curr)
                event.stop()
                return
            curr = curr.parent

class HistoryList(OptionList):
    async def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        if event.key in ("escape", "ctrl+g", "q"):
            event.prevent_default(); event.stop()
            self.app.action_toggle_history()
        elif event.key in ("delete", "backspace", "d", "x"):
            event.prevent_default(); event.stop()
            await self.app.delete_highlighted_chat()
        elif event.key in ("r",):
            event.prevent_default(); event.stop()
            self.app.rename_highlighted_chat()
        elif event.key in ("k", "ctrl+p", "up"):
            event.prevent_default(); event.stop()
            self.action_cursor_up()
        elif event.key in ("j", "ctrl+n", "down"):
            event.prevent_default(); event.stop()
            self.action_cursor_down()
        else:
            super()._on_key(event)

# ---------------------------------------------------------------------------
# Main Chat Application
# ---------------------------------------------------------------------------

class ChatApp(App):
    ENABLE_COMMAND_PALETTE = False
    COMMAND_PALETTE_BINDING = None
    COMMANDS = set()

    def action_command_palette(self) -> None:
        pass

    CSS = """
    Screen {
        layout: vertical;
        layers: base toasts overlay;
        background: #000000;
    }
    ToastRack {
        dock: top;
        align: right top;
        layer: toasts;
        background: transparent;
    }
    Toast {
        background: #141414;
        color: #ffffff;
        border: solid red;
    }
    #feed_loader_banner {
        layer: toasts;
        dock: top;
        width: 100%;
        height: 1;
        background: #141414;
        color: red;
        border-bottom: solid red;
        content-align: center middle;
        text-style: bold;
        display: none;
    }
    #main_container {
        height: 1fr;
        width: 100%;
        layout: vertical;
        background: #000000;
    }
    #feed {
        height: 1fr;
        border: solid red;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-gutter: stable;
        scrollbar-color: red #000000;
        padding: 0 2 0 1;
        width: 100%;
        max-width: 100%;
        background: #000000;
    }
    #feed #turns_container {
        width: 100%;
        max-width: 100%;
        height: auto;
        background: #000000;
    }
    .turn_card {
        width: 100%;
        max-width: 100%;
        height: auto;
        margin-bottom: 1;
        padding: 0;
        background: #000000;
        border: none;
    }
    .turn_card .turn_header {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: #141414;
    }
    .turn_card.card-active .turn_header {
        background: #2a0808;
    }
    .turn_box_label {
        width: 100%;
        text-style: bold;
        color: #ffffff;
    }
    .turn_card.card-active .turn_box_label {
        color: red;
    }
    .turn_card .turn_body {
        width: 100%;
        max-width: 100%;
        height: auto;
        background: #000000;
        color: #ffffff;
    }
    MarkdownHorizontalRule {
        border-bottom: solid red;
        color: red;
        margin: 1 0;
    }
    #feed_status {
        width: 100%;
        height: auto;
        min-height: 1;
        padding: 0 1;
        color: red;
        text-style: bold;
        background: #141414;
        border-top: solid red;
        display: none;
    }
    #feed_nav_banner {
        width: 100%;
        height: 1;
        background: #b91c1c;
        color: #ffffff;
        text-style: bold;
        content-align: center middle;
        display: none;
    }
    #feed MarkdownBlock,
    #feed MarkdownParagraph,
    #feed MarkdownTable {
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
        color: #ffffff;
    }
    #feed MarkdownFence {
        width: 100%;
        max-width: 100%;
        height: auto;
        overflow-x: hidden;
        margin: 1 0;
        border: solid transparent;
        background: #0a0a0a;
    }
    #feed MarkdownFence.active-snippet {
        border: solid red !important;
        background: #141414 !important;
    }
    #feed MarkdownFence > * {
        width: 100%;
        max-width: 100%;
    }
    #history {
        height: 1fr;
        border: solid red;
        background: #000000;
        color: #ffffff;
        display: none;
    }
    #snippet_preview {
        width: 100%;
        max-height: 10;
        border: round red;
        background: #000000;
        color: #ffffff;
        display: none;
        margin-bottom: 0;
        scrollbar-color: red #000000;
    }
    #input {
        border: solid red;
        background: #000000;
        color: #ffffff;
        scrollbar-color: red #000000;
        scrollbar-gutter: stable;
    }
    #input:focus {
        border: solid red;
        background: #000000;
    }
    TextArea > .text-area--cursor-line {
        background: #141414;
    }
    ScrollBar {
        background: #000000;
        color: red;
    }
    ScrollBar.-vertical {
        width: 1;
    }
    ScrollBar:hover {
        background: #141414;
        color: #ff4d4d;
    }
    ScrollBarCorner {
        background: #000000;
    }
    Button {
        background: #000000;
        color: #ffffff;
        border: solid red;
    }
    Button:hover {
        background: #141414;
        color: red;
    }
    Button:focus {
        border: double red;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "c_c_prefix_stub", "C-c [e,w,y,t,b,n,r,f,g,.,`]", show=True),
        Binding("ctrl+o", "toggle_feed_nav", "C-o (Feed Nav)", show=True),
        Binding("ctrl+full_stop", "fork_chat", "C-. (Fork)", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client()
        self.lock = AppLockController(self)

        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.current_chat_parent_id: str | None = None
        self.current_chat_working_dir: str | None = None
        self.current_chat_last_index: int = 0
        self.current_chat_center_marker: str = ""
        self.history: list[dict] = []
        self._server: asyncio.AbstractServer | None = None

        self.feed_nav_mode: bool = False
        self._prefix_c_c: bool = False
        self._c_c_timer: Timer | None = None

        self._request_phase: str = "idle"
        self._request_start_time: float = 0.0
        self._spinner_idx: int = 0
        self._status_timer: Timer | None = None
        self._banner_shown_time: float = 0.0

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None
        self._prefix_c_c = True
        self._c_c_timer = self.set_timer(3.5, self._expire_c_c_prefix)
        self.notify("C-c- (e:emacs, w:copy, y:yank, t:rename, b:hist, n:new, r:save, f:file, g:git, .:fork, `:svg)", timeout=3.5)

    def _expire_c_c_prefix(self) -> None:
        self._prefix_c_c = False
        self._c_c_timer = None

    def intercept_c_c_key(self, event: events.Key) -> bool:
        if event.key == "ctrl+c":
            event.prevent_default()
            event.stop()
            self.set_c_c_prefix()
            return True

        if self._prefix_c_c:
            event.prevent_default()
            event.stop()
            self.handle_c_c_prefix(event)
            return True

        return False

    def handle_c_c_prefix(self, event: events.Key) -> bool:
        if not self._prefix_c_c:
            return False

        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None

        self._prefix_c_c = False

        key = event.key.lower()
        char = (event.character or "").lower()

        if key in ("ctrl+g", "escape"):
            self.notify("Quit", timeout=1.0)
            return True

        if key in ("ctrl+e", "e") or char == "e":
            self.action_send_to_emacs()
            return True
        elif key in ("ctrl+w", "w") or char == "w":
            self.action_copy_active_snippet()
            return True
        elif key in ("ctrl+y", "y") or char == "y":
            self.action_yank_to_input()
            return True
        elif key in ("ctrl+t", "t") or char == "t":
            self.action_rename_chat()
            return True
        elif key in ("ctrl+n", "n") or char == "n":
            self.action_new_chat()
            return True
        elif key in ("ctrl+b", "b") or char == "b":
            self.action_toggle_history()
            return True
        elif key in ("ctrl+r", "r") or char == "r":
            self.action_save_snippet_to_disk()
            return True
        elif key in ("ctrl+f", "f") or char == "f":
            self.action_insert_file_from_disk()
            return True
        elif key in ("g", "ctrl+backslash", "backslash") or char == "g":
            self.action_open_git_tree()
            return True
        elif key in ("period", "full_stop", ".", "ctrl+period", "ctrl+full_stop") or char == ".":
            self.action_fork_chat()
            return True
        elif key in ("grave", "backtick", "`") or char == "`":
            self.action_take_svg_screenshot()
            return True

        self.notify(f"C-c {key} is undefined", timeout=2.0)
        return False

    def action_c_c_prefix_stub(self) -> None:
        self.set_c_c_prefix()

    def action_take_svg_screenshot(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_file = SCREENSHOTS_DIR / f"screenshot_{timestamp}.svg"
        try:
            self.save_screenshot(str(target_file))
            self.notify(f"Screenshot saved: {target_file.name}", timeout=3.5)
        except Exception as e:
            self.notify(f"Screenshot error: {e}", severity="error")

    def update_feed_nav_banner(self) -> None:
        banner = self.query_one("#feed_nav_banner", Static)
        feed = self.query_one("#feed", FeedArea)
        if not self.feed_nav_mode:
            banner.styles.display = "none"
            return

        if feed.fork_ui_active:
            banner.update("[NAV / FORK] Space: Toggle [❌] | a: All | Enter: Fork | .: Hide Checks | Esc: Exit")
        else:
            banner.update("[NAV ACTIVE] PgUp/PgDn: Cards | M-n/M-p: Snippets | Space/.: Fork | Esc: Exit")
        banner.styles.display = "block"

    def action_toggle_feed_nav(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        if self.feed_nav_mode:
            if feed.fork_ui_active:
                feed.toggle_fork_ui()
            self.feed_nav_mode = False
            self.update_feed_nav_banner()
            self.notify("Exited feed navigation")
        else:
            self.feed_nav_mode = True
            self.update_feed_nav_banner()
            self.notify("Feed navigation active")

        self.query_one("#input", ExpandingInput).focus()

    # --- Outermost App-Level Root Lock Interceptor ---

    def on_key(self, event: events.Key) -> None:
        key_name = event.key.lower()

        # Intercept and strictly swallow gated keys during active lockout
        if self.lock.is_locked:
            if key_name in GATED_NAV_KEYS:
                event.prevent_default()
                event.stop()
                return

        if self.intercept_c_c_key(event):
            return

        if event.key in ("ctrl+full_stop", "ctrl+period", "ctrl+."):
            event.prevent_default(); event.stop()
            self.action_fork_chat()
            return

    def compose(self) -> ComposeResult:
        yield Static("▲ Loading messages...", id="feed_loader_banner")
        with Vertical(id="main_container"):
            yield FeedArea(id="feed")
            yield HistoryList(id="history")
            yield Label("", id="feed_status")
            yield Static("", id="feed_nav_banner")
            yield SnippetPreview(id="snippet_preview")
            yield ExpandingInput(id="input")
        yield Footer()

    async def on_mount(self) -> None:
        await self.start_socket_server()
        self.call_after_refresh(self._initial_startup_load)

    async def _initial_startup_load(self) -> None:
        last_active_id = self._read_active_chat_from_state()
        if last_active_id and self._get_chat_file(last_active_id).exists():
            await self.load_chat(last_active_id)
        else:
            files = self._get_sorted_files()
            if files:
                first_id = files[0].stem
                await self.load_chat(first_id)
            else:
                self._start_new_chat(title="")

        self.query_one("#input").focus()

    def show_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            banner.update("▲ Loading messages...")
            banner.styles.display = "block"
            self._banner_shown_time = time.monotonic()
        except Exception:
            pass

    def hide_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            elapsed = time.monotonic() - self._banner_shown_time
            if elapsed < 0.4:
                self.set_timer(0.4 - elapsed, lambda: setattr(banner.styles, "display", "none"))
            else:
                banner.styles.display = "none"
        except Exception:
            pass

    def set_status_text(self, text: str) -> None:
        status_lbl = self.query_one("#feed_status", Label)
        status_lbl.update(text)
        if status_lbl.styles.display == "none":
            status_lbl.styles.display = "block"

    def hide_status(self) -> None:
        try:
            status_lbl = self.query_one("#feed_status", Label)
            status_lbl.update("")
            status_lbl.styles.display = "none"
        except Exception:
            pass

    def _start_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
        self._request_start_time = time.monotonic()
        self._spinner_idx = 0
        self._status_timer = self.set_interval(0.1, self._tick_status)

    def _stop_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None
        self._request_phase = "idle"

    def _tick_status(self) -> None:
        if self._request_phase == "idle":
            return

        elapsed = time.monotonic() - self._request_start_time
        frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
        self._spinner_idx += 1

        if self._request_phase == "connecting":
            status_text = f"{frame} Connecting / Sending request... ({elapsed:.1f}s)"
        elif self._request_phase == "waiting":
            status_text = f"{frame} Waiting on Gemini response... ({elapsed:.1f}s)"
        else:
            status_text = f"{frame} Working... ({elapsed:.1f}s)"

        self.set_status_text(status_text)

    @on(RequestPhaseUpdate)
    def on_request_phase_update(self, event: RequestPhaseUpdate) -> None:
        self._request_phase = event.phase

    @on(RequestFinished)
    async def on_request_finished(self, event: RequestFinished) -> None:
        self._stop_status_ticker()

        feed = self.query_one("#feed", FeedArea)
        jump_top = not self.feed_nav_mode
        await feed.append_message("Gemini", event.full_text, jump_to_start=jump_top)

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        self.history.append({"turn_id": new_turn_id, "role": "model", "text": event.full_text})
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id
        self.save_current_chat()

        self.set_status_text(f"✓ Response complete ({event.words} words in {event.elapsed:.1f}s)")
        self.set_timer(1.0, self.hide_status)

        self.query_one("#input", ExpandingInput).focus()

    @on(RequestFailed)
    def on_request_failed(self, event: RequestFailed) -> None:
        self._stop_status_ticker()
        self.set_status_text(f"✗ Error: {event.error_message}")
        self.notify(f"API Error: {event.error_message}", severity="error")
        self.set_timer(5.0, self.hide_status)
        self.query_one("#input", ExpandingInput).focus()

    def _read_active_chat_from_state(self) -> str | None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                return data.get("active_chat")
            except Exception:
                pass
        return None

    def _save_active_chat_to_state(self, chat_id: str) -> None:
        try:
            state: dict = {}
            if STATE_FILE.exists():
                try:
                    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
            state["active_chat"] = chat_id
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            STATE_FILE.chmod(0o600)
        except Exception:
            pass

    def get_effective_working_dir(self) -> str:
        if self.current_chat_working_dir:
            return self.current_chat_working_dir
        return os.getcwd()

    def set_working_dir(self, directory: str) -> None:
        expanded = os.path.expanduser(directory.strip())
        self.current_chat_working_dir = expanded
        self.save_current_chat()

    async def start_socket_server(self) -> None:
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_socket_client,
                path=str(SOCKET_PATH),
            )
            SOCKET_PATH.chmod(0o600)
        except Exception as e:
            self.notify(f"Socket server error: {e}", severity="error")

    async def _handle_socket_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        data = await reader.read()
        if data:
            try:
                payload = json.loads(data.decode("utf-8"))
                if payload.get("action") == "insert":
                    self.post_message(RemoteInsert(
                        text=payload.get("text", ""),
                        lang=payload.get("lang", ""),
                        file=payload.get("file", ""),
                        start_line=payload.get("start_line"),
                        end_line=payload.get("end_line"),
                    ))
            except Exception:
                pass
        writer.close()
        await writer.wait_closed()

    @on(RemoteInsert)
    def on_remote_insert(self, event: RemoteInsert) -> None:
        input_widget = self.query_one("#input", ExpandingInput)
        preview_widget = self.query_one("#snippet_preview", SnippetPreview)

        input_widget.focus()
        tag, num = input_widget.register_and_insert_snippet(
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        preview_widget.show_snippet(
            tag=tag,
            num=num,
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        loc = f" ({event.file}:{event.start_line}-{event.end_line})" if event.file else ""
        self.notify(f"Inserted {tag}{loc} at cursor")

    def action_quit(self) -> None:
        if self.current_chat_id:
            self.save_current_chat()
        self.exit()

    def on_unmount(self) -> None:
        self._stop_status_ticker()
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None

        if self.current_chat_id:
            self.save_current_chat()

        if self._server:
            self._server.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink(missing_ok=True)

    def _get_chat_file(self, chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    def _get_sorted_files(self) -> list[Path]:
        return sorted(
            CHATS_DIR.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

    def refresh_history_list(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        history_widget.clear_options()

        files = self._get_sorted_files()
        chats_by_id: dict[str, dict] = {}
        for f in files:
            try:
                data = json.loads(f.read_text())
                cid = data.get("id", f.stem)
                chats_by_id[cid] = data
            except Exception:
                continue

        for cid, data in chats_by_id.items():
            parent_id = data.get("parent_id")
            if parent_id and parent_id not in chats_by_id:
                data["parent_id"] = None
                target_file = self._get_chat_file(cid)
                if target_file.exists():
                    target_file.write_text(json.dumps(data, indent=2))

        children_map: dict[str, list[dict]] = {}
        roots: list[dict] = []
        for cid, data in chats_by_id.items():
            parent_id = data.get("parent_id")
            if parent_id and parent_id in chats_by_id and parent_id != cid:
                children_map.setdefault(parent_id, []).append(data)
            else:
                roots.append(data)

        roots.sort(key=lambda d: d.get("updated_at", 0), reverse=True)
        for pid in children_map:
            children_map[pid].sort(key=lambda d: d.get("updated_at", 0), reverse=False)

        def add_chat_node(chat_data: dict, depth: int, index_label: str) -> None:
            cid = chat_data["id"]
            title = chat_data.get("title", cid)
            active = " (Active)" if cid == self.current_chat_id else ""
            if depth == 0:
                prompt = f"{index_label}. {title}{active}"
            else:
                indent = "   " * depth + "└─ "
                prompt = f"{indent}{title}{active}"
            history_widget.add_option(Option(prompt=prompt, id=cid))

            for child in children_map.get(cid, []):
                add_chat_node(child, depth + 1, "")

        root_counter = 1
        for root in roots:
            add_chat_node(root, depth=0, index_label=str(root_counter))
            root_counter += 1

    async def load_chat(self, chat_id: str) -> None:
        self._stop_status_ticker()
        self.hide_status()

        if self.current_chat_id and self.current_chat_id != chat_id:
            self.save_current_chat()

        self.current_chat_id = chat_id
        self._save_active_chat_to_state(chat_id)

        path = self._get_chat_file(chat_id)
        saved_marker: str = ""
        saved_turn_idx: int | None = None
        if path.exists():
            data = json.loads(path.read_text())
            raw_messages = data.get("messages", [])
            self.history = []
            for m in raw_messages:
                m_copy = dict(m)
                if "turn_id" not in m_copy or not m_copy["turn_id"]:
                    m_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
                self.history.append(m_copy)

            self.current_chat_title = data.get("title", "")
            self.current_chat_working_dir = data.get("working_dir")
            self.current_chat_parent_id = data.get("parent_id")
            saved_marker = data.get("center_marker", "")
            saved_turn_idx = data.get("last_turn_index")

            if saved_marker:
                self.current_chat_center_marker = saved_marker
            elif saved_turn_idx is not None and self.history:
                self.current_chat_last_index = max(0, min(len(self.history) - 1, saved_turn_idx))
                self.current_chat_center_marker = self.history[self.current_chat_last_index].get("turn_id", "")
            else:
                self.current_chat_last_index = max(0, len(self.history) - 1)
                self.current_chat_center_marker = self.history[-1].get("turn_id", "") if self.history else ""
        else:
            self.history = []
            self.current_chat_title = ""
            self.current_chat_working_dir = None
            self.current_chat_parent_id = None
            self.current_chat_last_index = 0
            self.current_chat_center_marker = ""

        feed = self.query_one("#feed", FeedArea)
        if feed.styles.display == "none":
            feed.styles.display = "block"

        marker_target = self.current_chat_center_marker or self.current_chat_last_index
        feed.set_messages(self.history, initial_target_marker=marker_target)

        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()

    def save_current_chat(self) -> None:
        if not self.current_chat_id:
            return

        path = self._get_chat_file(self.current_chat_id)

        title = self.current_chat_title.strip()
        if not title and self.history:
            title = self.history[0]["text"][:28].replace("\n", " ")
        if not title:
            title = "New Chat"

        self.current_chat_title = title

        for m in self.history:
            if "turn_id" not in m or not m["turn_id"]:
                m["turn_id"] = f"turn_{uuid4().hex[:8]}"

        final_marker = self.current_chat_center_marker
        if final_marker.endswith(":+0") or final_marker.endswith(":-0") or final_marker.endswith(":0"):
            final_marker = final_marker.split(":")[0]
        elif not CENTER_SCREEN_MODE and ":" in final_marker:
            final_marker = final_marker.split(":")[0]

        data = {
            "id": self.current_chat_id,
            "title": self.current_chat_title,
            "parent_id": self.current_chat_parent_id,
            "updated_at": time.time(),
            "working_dir": self.current_chat_working_dir,
            "last_turn_index": self.current_chat_last_index,
            "center_marker": final_marker,
            "messages": self.history,
        }
        path.write_text(json.dumps(data, indent=2))
        self._save_active_chat_to_state(self.current_chat_id)

    async def delete_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)

        target_file = self._get_chat_file(target_id)
        if target_file.exists():
            target_file.unlink()

        for f in self._get_sorted_files():
            try:
                data = json.loads(f.read_text())
                if data.get("parent_id") == target_id:
                    data["parent_id"] = None
                    f.write_text(json.dumps(data, indent=2))
            except Exception:
                pass

        files = self._get_sorted_files()
        if self.current_chat_id == target_id:
            if files:
                await self.load_chat(files[0].stem)
            else:
                self._start_new_chat(title="")
                return

        current_idx = history_widget.highlighted
        self.refresh_history_list()
        if history_widget.option_count > 0:
            history_widget.highlighted = min(
                current_idx, history_widget.option_count - 1
            )

    def rename_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)
        target_file = self._get_chat_file(target_id)
        if not target_file.exists():
            return

        data = json.loads(target_file.read_text())
        current_title = data.get("title", "")

        def on_rename(new_title: str | None) -> None:
            if new_title is not None and new_title.strip():
                data["title"] = new_title.strip()
                data["updated_at"] = time.time()
                target_file.write_text(json.dumps(data, indent=2))
                if target_id == self.current_chat_id:
                    self.current_chat_title = new_title.strip()
                self.refresh_history_list()
                self.notify("Chat renamed.")

        self.push_screen(
            TitlePromptModal(prompt="Edit chat title:", default_title=current_title),
            callback=on_rename,
        )

    # --- Actions & Snippet Controls ---

    def action_rename_chat(self) -> None:
        def on_renamed(new_title: str | None) -> None:
            if new_title is not None and new_title.strip():
                self.current_chat_title = new_title.strip()
                self.save_current_chat()
                self.notify(f"Renamed chat to: {self.current_chat_title}")

        self.push_screen(
            TitlePromptModal(
                prompt="Edit chat title:",
                default_title=self.current_chat_title,
            ),
            callback=on_renamed,
        )

    def action_fork_chat(self) -> None:
        feed = self.query_one("#feed", FeedArea)

        if not feed.fork_ui_active:
            self.feed_nav_mode = True
            feed.toggle_fork_ui()
            self.update_feed_nav_banner()
            self.notify("Fork selection active: Space toggles, Enter forks, '.' hides checkboxes.", timeout=3.5)
            return

        selected_indices = feed.get_selected_fork_indices()
        if not selected_indices:
            self.notify("Please select at least one response to fork.", severity="warning")
            return

        def on_fork_named(fork_title: str | None) -> None:
            if not fork_title:
                self.notify("Fork cancelled.")
                feed.toggle_fork_ui()
                self.update_feed_nav_banner()
                return
            self._execute_chat_fork(selected_indices, fork_title)

        self.push_screen(
            ForkModal(default_title=self.current_chat_title),
            callback=on_fork_named,
        )

    def _execute_chat_fork(self, selected_indices: list[int], fork_title: str) -> None:
        feed = self.query_one("#feed", FeedArea)
        feed.toggle_fork_ui()
        self.feed_nav_mode = False
        self.update_feed_nav_banner()

        selected_turns = [copy.deepcopy(self.history[i]) for i in selected_indices]
        if not selected_turns:
            return

        if selected_turns[0]["role"] == "user":
            text = selected_turns[0]["text"]
            while text.startswith(FORK_HEADER_TEXT):
                text = text[len(FORK_HEADER_TEXT):].lstrip("\n")
            selected_turns[0]["text"] = f"{FORK_HEADER_TEXT}\n\n{text}"
        else:
            selected_turns.insert(0, {
                "turn_id": f"turn_{uuid4().hex[:8]}",
                "role": "user",
                "text": FORK_HEADER_TEXT
            })

        for turn in selected_turns:
            turn["turn_id"] = f"turn_{uuid4().hex[:8]}"

        self.save_current_chat()

        parent_chat_id = self.current_chat_id
        parent_working_dir = self.current_chat_working_dir
        new_chat_id = uuid4().hex[:8]

        self.current_chat_id = new_chat_id
        self.current_chat_title = fork_title
        self.current_chat_parent_id = parent_chat_id
        self.current_chat_working_dir = parent_working_dir
        self.current_chat_last_index = 0
        self.current_chat_center_marker = selected_turns[0].get("turn_id", "")
        self.history = selected_turns

        self.save_current_chat()
        self._render_forked_chat(selected_turns)

    def _render_forked_chat(self, turns: list[dict]) -> None:
        feed = self.query_one("#feed", FeedArea)
        first_marker = turns[0].get("turn_id", 0) if turns else 0
        feed.set_messages(turns, initial_target_marker=first_marker)
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()
        self.refresh_history_list()
        self.notify(f"Fork created: '{self.current_chat_title}' (Awaiting response)", timeout=4.0)

    def action_toggle_history(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        history_widget = self.query_one("#history", HistoryList)
        input_widget = self.query_one("#input", ExpandingInput)

        if history_widget.styles.display == "none":
            if self.current_chat_id and feed._all_messages and feed.styles.display != "none":
                self.save_current_chat()

            self.refresh_history_list()
            self.hide_status()
            feed.styles.display = "none"
            history_widget.styles.display = "block"
            history_widget.focus()
        else:
            history_widget.styles.display = "none"
            feed.styles.display = "block"
            feed.refresh(layout=True)

            marker = self.current_chat_center_marker
            target_w = None
            line_offset = None

            if marker == "end":
                feed.call_after_refresh(lambda: feed.scroll_end(animate=False))
            else:
                if ":" in marker:
                    tid, offset_str = marker.split(":", 1)
                    if CENTER_SCREEN_MODE:
                        try:
                            parsed_offset = int(offset_str)
                            line_offset = parsed_offset if parsed_offset != 0 else None
                        except Exception:
                            line_offset = None
                    else:
                        line_offset = None
                    target_w = feed._get_target_widget_by_id(tid)
                elif marker:
                    target_w = feed._get_target_widget_by_id(marker)

                if not target_w:
                    target_w = feed._get_target_widget(self.current_chat_last_index)

                if target_w:
                    feed.call_after_refresh(
                        lambda: feed._scroll_to_turn_widget(
                            target_w,
                            center=CENTER_SCREEN_MODE and (line_offset is not None),
                            line_offset=line_offset,
                        )
                    )
            input_widget.focus()

    def action_new_chat(self) -> None:
        def on_title_chosen(chosen_title: str | None) -> None:
            if chosen_title is None:
                return
            self._start_new_chat(title=chosen_title)

        self.push_screen(
            TitlePromptModal(prompt="Enter topic for new chat:"),
            callback=on_title_chosen,
        )

    def _start_new_chat(self, title: str) -> None:
        self._stop_status_ticker()
        self.hide_status()

        if self.current_chat_id:
            self.save_current_chat()

        self.query_one("#history").styles.display = "none"
        self.query_one("#feed").styles.display = "block"

        self.current_chat_id = uuid4().hex[:8]
        self.current_chat_title = title
        self.current_chat_parent_id = None
        self.current_chat_working_dir = None
        self.current_chat_last_index = 0
        self.current_chat_center_marker = ""
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()
        self._save_active_chat_to_state(self.current_chat_id)

    def action_save_snippet_to_disk(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        content = feed.get_active_snippet()

        if not content:
            self.notify("No snippet selected to write.", severity="warning")
            return

        initial_dir = self.get_effective_working_dir()

        def on_save_modal_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            filename = result["filename"]
            code = result["content"]

            base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
            target = (base / filename.strip()).resolve()

            def do_write() -> None:
                try:
                    written_path = write_code_to_disk(working_dir, filename, code)
                    self.set_working_dir(working_dir)
                    self.notify(f"Saved: {written_path}", timeout=3.5)
                except Exception as e:
                    self.notify(f"Failed to write file: {e}", severity="error")

            if target.exists():
                def on_overwrite_confirmed(confirmed: bool | None) -> None:
                    if confirmed:
                        do_write()
                    else:
                        self.notify("Save cancelled.", timeout=2.0)

                self.push_screen(
                    ConfirmModal(message=f"'{target.name}' already exists.\nOverwrite?"),
                    callback=on_overwrite_confirmed,
                )
            else:
                do_write()

        self.push_screen(
            WriteSnippetModal(
                snippet_content=content,
                initial_dir=initial_dir,
            ),
            callback=on_save_modal_result,
        )

    def action_insert_file_from_disk(self) -> None:
        initial_dir = self.get_effective_working_dir()

        def on_file_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            file_path_str = result["file_path"]
            rel_path = result["rel_path"]

            self.set_working_dir(working_dir)

            target_file = Path(file_path_str)
            try:
                code_content = target_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                self.notify(f"Failed to read file: {e}", severity="error")
                return

            lines = code_content.count("\n") + 1
            lang = detect_language(target_file)

            display_path = rel_path
            try:
                base = Path(os.path.expanduser(working_dir)).resolve()
                display_path = str(target_file.relative_to(base))
            except Exception:
                pass

            input_widget = self.query_one("#input", ExpandingInput)
            preview_widget = self.query_one("#snippet_preview", SnippetPreview)

            input_widget.focus()
            tag, num = input_widget.register_and_insert_snippet(
                code=code_content,
                lang=lang,
                file=display_path,
                start_line=1,
                end_line=lines,
            )

            preview_widget.show_snippet(
                tag=tag,
                num=num,
                code=code_content,
                lang=lang,
                file=display_path,
                start_line=1,
                end_line=lines,
            )

            self.notify(f"Inserted {tag} ({display_path})")

        self.push_screen(
            InsertFileModal(initial_dir=initial_dir),
            callback=on_file_result,
        )

    def action_open_git_tree(self) -> None:
        initial_dir = self.get_effective_working_dir()

        def on_git_tree_result(result: dict | None) -> None:
            if not result:
                return

            repo_dir = result["repo_dir"]
            selected_files: list[str] = result["selected_files"]
            tracked_files: list[str] = result["tracked_files"]
            ignored_files: list[str] = result["ignored_files"]
            tree_mode: str = result["tree_mode"]

            self.set_working_dir(repo_dir)

            input_widget = self.query_one("#input", ExpandingInput)
            preview_widget = self.query_one("#snippet_preview", SnippetPreview)

            sections: list[str] = []
            root_label = Path(repo_dir).name or repo_dir
            ignored_set = set(ignored_files)

            if tree_mode == "full":
                all_files = tracked_files + [f for f in selected_files if f in ignored_set]
                if all_files:
                    ascii_tree = build_ascii_tree(all_files, root_name=root_label, ignored_set=ignored_set)
                    sections.append(f"Repository Tree (`{root_label}`):\n```text\n{ascii_tree}\n```")
            elif tree_mode == "selected" and selected_files:
                ascii_tree = build_ascii_tree(selected_files, root_name=root_label, ignored_set=ignored_set)
                sections.append(f"Selected Files Tree (`{root_label}`):\n```text\n{ascii_tree}\n```")

            last_tag = ""
            last_num = 1
            last_code = ""
            last_lang = ""
            last_file = ""

            for rel_path in selected_files:
                abs_path = Path(repo_dir) / rel_path
                try:
                    code_content = abs_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    code_content = f"// Error reading file: {e}"

                lang = detect_language(rel_path)
                lines = code_content.count("\n") + 1

                tag, num = input_widget.register_and_insert_snippet(
                    code=code_content,
                    lang=lang,
                    file=rel_path,
                    start_line=1,
                    end_line=lines,
                )
                last_tag = tag
                last_num = num
                last_code = code_content
                last_lang = lang
                last_file = rel_path

            if sections:
                current_text = input_widget.text
                input_widget.text = "\n\n".join(sections) + ("\n\n" + current_text if current_text else "")

            if last_tag:
                preview_widget.show_snippet(
                    tag=last_tag,
                    num=last_num,
                    code=last_code,
                    lang=last_lang,
                    file=last_file,
                    start_line=1,
                    end_line=last_code.count("\n") + 1,
                )

            input_widget.focus()
            self.notify(f"Inserted tree & {len(selected_files)} file(s).")

        self.push_screen(
            GitTreeModal(initial_dir=initial_dir),
            callback=on_git_tree_result,
        )

    def _get_emacs_frames(self) -> list[dict]:
        try:
            res = subprocess.run(
                ["emacsclient", "--eval", "(gemini-list-open-frames)"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                raw_json = res.stdout.strip()
                parsed = json.loads(raw_json)
                while isinstance(parsed, str):
                    parsed = json.loads(parsed)
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        return []

    def _send_to_emacs_buffer(self, code_text: str, target_buf: str | None = None) -> bool:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as tmp:
                tmp.write(code_text)
                tmp.flush()
                temp_path = tmp.name

            escaped_tmp = json.dumps(temp_path)
            if target_buf:
                escaped_buf = json.dumps(target_buf)
                elisp = f'(gemini-insert-file-into-window {escaped_buf} {escaped_tmp})'
            else:
                elisp = f'(with-current-buffer (window-buffer (selected-window)) (insert-file-contents {escaped_tmp}))'

            res = subprocess.run(
                ["emacsclient", "--eval", elisp],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def action_send_to_emacs(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        text_to_send = feed.get_active_snippet()
        if not text_to_send:
            self.notify("No snippet to send to Emacs.", severity="warning")
            return

        frames = self._get_emacs_frames()
        if len(frames) <= 1:
            success = self._send_to_emacs_buffer(text_to_send)
            if success:
                self.notify("Snippet sent to Emacs client")
            else:
                self.notify("Failed to connect to Emacs server", severity="error")
            return

        def on_window_chosen(chosen: dict | None) -> None:
            if chosen:
                buf = chosen.get("buf_name")
                success = self._send_to_emacs_buffer(text_to_send, target_buf=buf)
                if success:
                    self.notify(f"Snippet sent to Emacs client ({chosen.get('file_name')})")
                else:
                    self.notify("Failed to send to Emacs window", severity="error")

        self.push_screen(FrameSelectModal(frames), callback=on_window_chosen)

    def action_copy_active_snippet(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        text_to_send = feed.get_active_snippet()
        if not text_to_send:
            self.notify("No snippet selected to copy.", severity="warning")
            return

        self.copy_to_clipboard(text_to_send)
        self.notify("Copied to system clipboard")

    def action_yank_to_input(self) -> None:
        try:
            paste_text = pyperclip.paste()
            if not paste_text:
                self.notify("Clipboard is empty.", severity="warning")
                return

            input_widget = self.query_one("#input", ExpandingInput)
            input_widget.focus()
            if input_widget.selected_text:
                input_widget.delete(input_widget.selection.start, input_widget.selection.end)
            input_widget.insert(paste_text)
            input_widget._clear_mark()
            self.notify("Pasted clipboard to prompt input")
        except Exception as e:
            self.notify(f"Clipboard paste error: {e}", severity="error")

    @on(OptionList.OptionSelected, "#history")
    async def on_history_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            chat_id = str(event.option_id)
            self.query_one("#history").styles.display = "none"
            self.query_one("#feed").styles.display = "block"
            await self.load_chat(chat_id)
            self.query_one("#input").focus()

    async def append_to_feed(self, sender: str, text: str, jump_to_start: bool = False) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.append_message(sender, text, jump_to_start=jump_to_start)

    async def on_expanding_input_submitted(self, event: ExpandingInput.Submitted) -> None:
        user_msg = event.value
        await self.append_to_feed("You", user_msg, jump_to_start=False)

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        self.history.append({"turn_id": new_turn_id, "role": "user", "text": user_msg})
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id
        self.save_current_chat()

        self.ask_gemini()

    @work(exclusive=True, thread=True)
    def ask_gemini(self) -> None:
        chat_id_snapshot = self.current_chat_id

        payload = []
        for t in self.history:
            if payload and payload[-1]["role"] == t["role"]:
                payload[-1]["parts"][0]["text"] += "\n\n" + t["text"]
            else:
                payload.append({"role": t["role"], "parts": [{"text": t["text"]}]})

        if payload and payload[0]["role"] != "user":
            payload.insert(0, {"role": "user", "parts": [{"text": FORK_HEADER_TEXT}]})

        self.app.call_from_thread(self._start_status_ticker)
        self.app.call_from_thread(self.post_message, RequestPhaseUpdate("connecting"))

        start_time = time.monotonic()

        try:
            self.app.call_from_thread(self.post_message, RequestPhaseUpdate("waiting"))
            response = self.client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=payload,
            )

            if self.current_chat_id != chat_id_snapshot:
                return

            reply = response.text or ""
            elapsed = max(time.monotonic() - start_time, 0.1)
            total_words = len(reply.split())

            self.app.call_from_thread(
                self.post_message, RequestFinished(reply, elapsed, total_words)
            )

        except Exception as e:
            if self.current_chat_id != chat_id_snapshot:
                return
            self.app.call_from_thread(
                self.post_message, RequestFailed(str(e))
            )

if __name__ == "__main__":
    ChatApp().run()
