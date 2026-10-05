#!/opt/gemini/.venv/bin/python3

import asyncio
import copy
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
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    Markdown,
    OptionList,
    RadioButton,
    RadioSet,
    TextArea,
    Tree,
)
from textual.widgets.markdown import MarkdownFence
from textual.widgets.option_list import Option
from textual.widgets.text_area import Selection
from textual.widgets.tree import TreeNode

CHATS_DIR = Path("chats")
CHATS_DIR.mkdir(exist_ok=True)
SOCKET_PATH = Path("/tmp/gemini_textual.sock")

FORK_HEADER_TEXT = "## This chat is a fork of another / previous chat"

# ---------------------------------------------------------------------------
# Reusable Core File & Git Services (UI & Gemini Tool Use)
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
    """Infers markdown syntax language from file extension."""
    ext = Path(filepath).suffix.lower()
    return EXTENSION_LANG_MAP.get(ext, "")

def write_code_to_disk(working_dir: str | Path, filename: str, content: str) -> Path:
    """Reusable utility to safely write snippet content to disk."""
    base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
    target = (base / filename.strip()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target

def get_git_files_catalog(repo_dir: str | Path) -> dict[str, list[str]]:
    """Returns sorted relative paths for both Git-tracked and .gitignore-ignored files."""
    base = Path(os.path.expanduser(str(repo_dir).strip())).resolve()
    check = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0 or check.stdout.strip() != "true":
        raise ValueError(f"Directory '{base}' is not a valid Git repository.")

    # 1. Tracked files
    res_tracked = subprocess.run(
        ["git", "-C", str(base), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [f.strip() for f in res_tracked.stdout.splitlines() if f.strip()]

    # 2. Ignored files via .gitignore (excluding internal .git metadata)
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

def get_git_tracked_files(repo_dir: str | Path) -> list[str]:
    """Backward-compatible helper returning tracked files."""
    return get_git_files_catalog(repo_dir)["tracked"]

def build_ascii_tree(files: list[str], root_name: str = ".", ignored_set: set[str] | None = None) -> str:
    """Builds clean ASCII folder/file tree visualization from a list of relative paths."""
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
# Dynamic MarkdownFence Hook for Accurate Line Numbers in the Feed
# ---------------------------------------------------------------------------
_orig_markdown_fence_render = MarkdownFence.render

def _enhanced_markdown_fence_render(self: MarkdownFence) -> RenderableType:
    renderable = _orig_markdown_fence_render(self)
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
                            if hasattr(child, "text"):
                                s_text += " " + str(child.text)
                    m = re.search(r"\(Lines?\s+(\d+)", s_text)
                    if m:
                        start_line = int(m.group(1))
                        break
                    if isinstance(s, MarkdownFence):
                        break

        renderable.start_line = start_line
    return renderable

MarkdownFence.render = _enhanced_markdown_fence_render

class RemoteInsert(Message):
    """Event posted when external process sends text to insert."""
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

class MenuPalette(CommandPalette):
    """Command palette customized as the Emacs-style Menu (M-x)."""

    def on_mount(self) -> None:
        super().on_mount()
        try:
            palette_input = self.query_one("CommandInput", Input)
            palette_input.placeholder = "Menu (M-x)..."
        except Exception:
            pass

class DirectoryPathInput(Input):
    """Input widget featuring 1x Tab directory auto-completion and 2x quick Tab to navigate UI."""

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
    """Input widget for file/folder auto-completion (1x Tab auto-complete, 2x Tab navigate)."""

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
    """Modal dialog prompting user for confirmation (Yes / No)."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    #confirm_dialog {
        padding: 1 2;
        width: 52;
        height: auto;
        border: thick red;
        background: $surface;
    }
    #confirm_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    #confirm_buttons {
        width: 100%;
        align-horizontal: center;
    }
    #confirm_buttons Button {
        margin: 0 1;
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
                yield Button("No", variant="default", id="no_btn")
                yield Button("Yes", variant="error", id="yes_btn")

    def on_mount(self) -> None:
        self.query_one("#no_btn", Button).focus()

    @on(Button.Pressed, "#yes_btn")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no_btn")
    def action_cancel(self) -> None:
        self.dismiss(False)

class ForkModal(ModalScreen[str | None]):
    """Modal dialog prompting the user to name the forked chat, enforcing permanent 'Fork: ' prefix."""

    DEFAULT_CSS = """
    ForkModal {
        align: center middle;
    }
    #fork_dialog {
        padding: 1 2;
        width: 66;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }
    #fork_dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #fork_prefix_hint {
        color: cyan;
        margin-bottom: 1;
    }
    #fork_title_input {
        margin-bottom: 1;
    }
    #fork_buttons {
        width: 100%;
        align-horizontal: right;
    }
    #fork_buttons Button {
        margin-left: 1;
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
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Fork It", variant="primary", id="fork_btn")

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

class ForkTurnCard(Vertical):
    """Focusable container representing a single response turn during Fork mode."""

    can_focus = True

    def __init__(self, index: int, sender: str, text: str, **kwargs) -> None:
        super().__init__(classes="fork_turn_card", **kwargs)
        self.turn_index = index
        self.sender = sender
        self.text_content = text
        self.is_selected = True

    def compose(self) -> ComposeResult:
        with Horizontal(classes="fork_turn_header"):
            yield Label(self._get_box_label(), classes="fork_turn_box_label")
        yield Markdown(self.text_content, classes="fork_turn_preview")

    def _get_box_label(self) -> str:
        box = "[✓]" if self.is_selected else "[ ]"
        return f"{box}  {self.sender}  (#{self.turn_index + 1})"

    def toggle(self) -> None:
        self.is_selected = not self.is_selected
        self.query_one(".fork_turn_box_label", Label).update(self._get_box_label())
        self.refresh()

    def set_selected(self, value: bool) -> None:
        self.is_selected = value
        self.query_one(".fork_turn_box_label", Label).update(self._get_box_label())
        self.refresh()

    def _on_key(self, event: events.Key) -> None:
        if event.key == "space":
            event.prevent_default(); event.stop()
            self.toggle()
            return
        elif event.key in ("enter", "return"):
            event.prevent_default(); event.stop()
            self.app.action_fork_chat()
            return
        elif event.key in ("alt+n", "alt+down", "j", "down"):
            event.prevent_default(); event.stop()
            feed = self.app.query_one("#feed", FeedArea)
            feed.navigate_fork_cards(1)
            return
        elif event.key in ("alt+p", "alt+up", "k", "up"):
            event.prevent_default(); event.stop()
            feed = self.app.query_one("#feed", FeedArea)
            feed.navigate_fork_cards(-1)
            return
        elif event.key == "a":
            event.prevent_default(); event.stop()
            feed = self.app.query_one("#feed", FeedArea)
            feed.toggle_all_fork_checkboxes()
            return
        elif event.key in ("escape", "ctrl+g"):
            event.prevent_default(); event.stop()
            feed = self.app.query_one("#feed", FeedArea)
            feed.exit_fork_mode()
            self.app.notify("Fork cancelled.")
            return

        super()._on_key(event)

    @on(events.Click)
    def on_card_click(self, event: events.Click) -> None:
        event.stop()
        self.focus()
        # If clicking specifically on or within the header bar, toggle the selection
        curr = event.widget
        while curr and curr is not self:
            if "fork_turn_header" in curr.classes:
                self.toggle()
                return
            curr = curr.parent

class WriteSnippetModal(ModalScreen[dict | None]):
    """Modal dialog prompting for working directory and filename to write code to disk."""

    DEFAULT_CSS = """
    WriteSnippetModal {
        align: center middle;
    }
    #save_dialog {
        padding: 1 2;
        width: 72;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }
    #save_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    #save_dialog Input {
        margin-bottom: 1;
    }
    #chat_scoped_cb {
        margin: 1 0;
    }
    #dialog_buttons {
        width: 100%;
        align-horizontal: right;
    }
    #dialog_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        snippet_content: str,
        initial_dir: str,
        is_chat_scoped: bool = False,
    ) -> None:
        super().__init__()
        self.snippet_content = snippet_content
        self.initial_dir = initial_dir
        self.is_chat_scoped = is_chat_scoped

    def compose(self) -> ComposeResult:
        with Vertical(id="save_dialog"):
            yield Label("Working Directory (Tab: auto-complete, 2x Tab: navigate):")
            yield DirectoryPathInput(value=self.initial_dir, id="dir_input")
            yield Label("Filename to write:")
            yield Input(placeholder="e.g. main.py, server.go, script.sh", id="filename_input")
            yield Checkbox("Chat session specific working directory", value=self.is_chat_scoped, id="chat_scoped_cb")
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Write to Disk", variant="primary", id="confirm_btn")

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
        chat_scoped = self.query_one("#chat_scoped_cb", Checkbox).value

        if not filename:
            self.notify("Filename cannot be blank.", severity="error")
            self.query_one("#filename_input", Input).focus()
            return

        if not working_dir:
            working_dir = os.getcwd()

        self.dismiss({
            "working_dir": working_dir,
            "filename": filename,
            "chat_scoped": chat_scoped,
            "content": self.snippet_content,
        })

class InsertFileModal(ModalScreen[dict | None]):
    """Modal dialog prompting for working directory and file path to insert into prompt."""

    DEFAULT_CSS = """
    InsertFileModal {
        align: center middle;
    }
    #insert_file_dialog {
        padding: 1 2;
        width: 76;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }
    #insert_file_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    #insert_file_dialog Input {
        margin-bottom: 1;
    }
    #insert_chat_scoped_cb {
        margin: 1 0;
    }
    #dialog_buttons {
        width: 100%;
        align-horizontal: right;
    }
    #dialog_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str, is_chat_scoped: bool = False) -> None:
        super().__init__()
        self.initial_dir = initial_dir
        self.is_chat_scoped = is_chat_scoped

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
            yield Checkbox("Chat session specific working directory", value=self.is_chat_scoped, id="insert_chat_scoped_cb")
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Insert File", variant="primary", id="confirm_btn")

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
        chat_scoped = self.query_one("#insert_chat_scoped_cb", Checkbox).value

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
            "chat_scoped": chat_scoped,
        })

class GitTreeModal(ModalScreen[dict | None]):
    """Modal explorer for browsing Git tracked & .gitignore files with fully expanded trees and folder toggling."""

    DEFAULT_CSS = """
    GitTreeModal {
        align: center middle;
    }
    #git_dialog {
        padding: 1 2;
        width: 110;
        height: 92vh;
        max-height: 95vh;
        border: thick dodgerblue;
        background: $surface;
    }
    #git_repo_row {
        height: auto;
        margin-bottom: 1;
    }
    #git_repo_row DirectoryPathInput {
        width: 1fr;
    }
    #git_repo_row Button {
        margin-left: 1;
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
    }
    .tree_pane Tree {
        border: solid #555555;
        height: 1fr;
        min-height: 5;
    }
    #tree_ignored {
        border: solid #334444;
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
    }
    #git_chat_scoped_cb {
        height: auto;
        margin-top: 0;
        margin-bottom: 0;
    }
    #status_label {
        height: auto;
        color: #888888;
        margin-top: 0;
        margin-bottom: 1;
    }
    #git_buttons {
        height: auto;
        width: 100%;
        align-horizontal: right;
    }
    #git_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str, is_chat_scoped: bool = False) -> None:
        super().__init__()
        self.repo_dir = initial_dir
        self.is_chat_scoped = is_chat_scoped
        self.tracked_files: list[str] = []
        self.ignored_files: list[str] = []
        self.selected_files: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="git_dialog"):
            yield Label("Git Repository Path (Tab: auto-complete, 2x Tab: navigate):")
            with Horizontal(id="git_repo_row"):
                yield DirectoryPathInput(value=self.repo_dir, id="git_dir_input")
                yield Button("Scan Tree", variant="default", id="scan_btn")

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

            yield Checkbox("Chat session specific working directory", value=self.is_chat_scoped, id="git_chat_scoped_cb")
            yield Label("0 files selected. [Space]/Click to toggle file/folder, [a] all in tree", id="status_label")

            with Horizontal(id="git_buttons"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Insert Selected & Tree", variant="primary", id="insert_btn")

    def on_mount(self) -> None:
        self.query_one("#tree_tracked", Tree).show_root = False
        self.query_one("#tree_ignored", Tree).show_root = False
        self._scan_and_populate()
        self.query_one("#tree_tracked").focus()

    def _scan_and_populate(self) -> None:
        raw_dir = self.query_one("#git_dir_input", DirectoryPathInput).value.strip()
        expanded = os.path.expanduser(raw_dir) if raw_dir else os.getcwd()
        self.repo_dir = expanded

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
        """Recursively synchronizes checkbox labels for files and folders."""
        data = root_node.data or {}
        if data.get("is_file"):
            is_sel = data["path"] in self.selected_files
            part = data.get("name", Path(data["path"]).name)
            root_node.set_label(f"[{'✓' if is_sel else ' '}] {part}")
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
        """Prevent folders from ever collapsing—keep them permanently expanded."""
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
        chat_scoped = self.query_one("#git_chat_scoped_cb", Checkbox).value

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
            "chat_scoped": chat_scoped,
        })

class TitlePromptModal(ModalScreen[str | None]):
    """Modal dialog prompting the user for a chat topic/title."""

    DEFAULT_CSS = """
    TitlePromptModal {
        align: center middle;
    }
    #dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #dialog Input {
        margin-bottom: 1;
    }
    #dialog-buttons {
        width: 100%;
        align-horizontal: right;
    }
    #dialog-buttons Button {
        margin-left: 1;
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
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Confirm", variant="primary", id="confirm_btn")

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
    """Modal dialog prompting user to pick an Emacs frame & sub-window to paste into."""

    DEFAULT_CSS = """
    FrameSelectModal {
        align: center middle;
    }
    #frame_dialog {
        padding: 1 2;
        width: 70;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }
    #frame_dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #frame_options {
        height: auto;
        max-height: 14;
        margin-bottom: 1;
        border: solid #444444;
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
                yield Button("Cancel", variant="error", id="cancel_btn")

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
    """Base TextArea with standard Emacs keys, cursor selection synchronization, and clipboard."""

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
        if self.app.handle_c_c_prefix(event):
            return

        if event.key == "ctrl+c":
            event.prevent_default(); event.stop()
            self.app.set_c_c_prefix()
            return

        if event.key in ("ctrl+space", "ctrl+at", "ctrl+tilde") or (
            event.character and ord(event.character) == 0
        ):
            event.prevent_default(); event.stop()
            self._mark_point = self.cursor_location
            self.selection = Selection(self._mark_point, self._mark_point)
            self.app.notify("Mark set", timeout=1.5)
            return

        if event.key in ("alt+x", "meta+x"):
            event.prevent_default(); event.stop()
            self.app.action_command_palette()
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
                self._clear_mark()
                self.app.notify("Copied region", timeout=1.5)
            return
        elif event.key in ("ctrl+slash", "ctrl+underscore"):
            event.prevent_default(); event.stop()
            self.action_undo()
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
    """Editable preview box displaying the most recent snippet with accurate file line numbers."""

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

    def _on_key(self, event: events.Key) -> None:
        if self.app.handle_c_c_prefix(event):
            return

        if event.key in ("shift+enter", "ctrl+j"):
            event.prevent_default(); event.stop()
            self.app.query_one("#input", ExpandingInput).action_submit()
            return

        row, _ = self.cursor_location
        if row == self.document.line_count - 1 and event.key in ("down", "ctrl+n"):
            event.prevent_default(); event.stop()
            self.app.query_one("#input", ExpandingInput).focus()
            return

        if event.key in ("ctrl+g", "escape"):
            event.prevent_default(); event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.query_one("#input", ExpandingInput).focus()
            return

        super()._on_key(event)

class ExpandingInput(EmacsBaseTextArea):
    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = False
        self._snippets: dict[str, dict] = {}
        self._snippet_counter: int = 1
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
        if self.app.handle_c_c_prefix(event):
            return

        if event.key in ("shift+enter", "shift+return", "ctrl+j", "alt+enter", "meta+enter"):
            event.prevent_default(); event.stop()
            self.action_newline()
            return
        elif event.key == "enter":
            event.prevent_default(); event.stop()
            self.action_submit()
            return

        row, _ = self.cursor_location
        if row == 0 and event.key in ("up", "ctrl+p"):
            preview_box = self.app.query_one("#snippet_preview", SnippetPreview)
            if preview_box.styles.display != "none":
                event.prevent_default(); event.stop()
                preview_box.focus()
                return

        if event.key in ("ctrl+g", "escape"):
            event.prevent_default(); event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.query_one("#feed", FeedArea).focus()
            return

        elif event.key in ("alt+n", "alt+down"):
            event.prevent_default(); event.stop()
            self.app.action_next_snippet()
            return
        elif event.key in ("alt+p", "alt+up"):
            event.prevent_default(); event.stop()
            self.app.action_prev_snippet()
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
                return f"\n\n{title}\n```{lang}\n{code}\n```\n\n"
            return match.group(0)

        resolved_text = re.sub(r"\{\s*&snippet\d+\s*\}", replacer, raw_text)
        resolved_text = re.sub(r"\n{3,}", "\n\n", resolved_text).strip()

        self.post_message(self.Submitted(resolved_text))
        self.clear()
        self.reset_snippets()
        self._clear_mark()
        self.call_after_refresh(self._update_layout)

        self.app.query_one("#snippet_preview", SnippetPreview).hide_preview()

class FeedArea(VerticalScroll):
    """Feed container supporting standard rich Markdown views, code snippet navigation,

    and an interactive checkbox mode for chat forking.
    """

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._raw_markdown = ""
        self.selected_snippet_index: int = -1
        self.fork_mode: bool = False

    def compose(self) -> ComposeResult:
        yield Markdown(id="feed_markdown")
        yield Vertical(id="fork_view")

    def on_mount(self) -> None:
        self.query_one("#fork_view").styles.display = "none"

    def clear(self) -> None:
        self.exit_fork_mode()
        self._raw_markdown = ""
        self.selected_snippet_index = -1
        try:
            self.query_one("#feed_markdown", Markdown).update("")
        except Exception:
            pass

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)

    async def set_messages(self, messages: list[dict]) -> None:
        self.exit_fork_mode()
        blocks = []
        for turn in messages:
            label = "You" if turn["role"] == "user" else "Gemini"
            blocks.append(f"### {label}\n\n{turn['text']}")
        self._raw_markdown = "\n\n---\n\n".join(blocks)
        self.selected_snippet_index = -1
        md = self.query_one("#feed_markdown", Markdown)
        await md.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    async def append_message(self, sender: str, text: str) -> None:
        prefix = "\n\n---\n\n" if self._raw_markdown else ""
        header = f"### {sender}\n\n"
        self._raw_markdown += f"{prefix}{header}{text}"
        md = self.query_one("#feed_markdown", Markdown)
        await md.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

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

    def select_snippet(self, index: int, scroll: bool = True) -> None:
        fences = self._get_fences()
        if not (0 <= index < len(fences)):
            return

        self.selected_snippet_index = index

        for idx, f in enumerate(fences):
            if idx == self.selected_snippet_index:
                f.add_class("active-snippet")
                if scroll:
                    f.scroll_visible(animate=True)
                f.refresh()
            else:
                f.remove_class("active-snippet")
                f.refresh()

    def navigate_snippet(self, delta: int) -> None:
        if self.fork_mode:
            self.navigate_fork_cards(delta)
            return

        fences = self._get_fences()
        if not fences:
            return

        total = len(fences)
        if self.selected_snippet_index == -1:
            new_idx = 0 if delta > 0 else total - 1
        else:
            new_idx = (self.selected_snippet_index + delta) % total

        self.select_snippet(new_idx, scroll=True)

    def get_active_snippet(self) -> str | None:
        fences = self._get_fences()
        if 0 <= self.selected_snippet_index < len(fences):
            return self._extract_code_from_fence(fences[self.selected_snippet_index])
        elif fences:
            return self._extract_code_from_fence(fences[-1])
        return None

    # --- Fork Selection Operations ---

    def enter_fork_mode(self, messages: list[dict]) -> None:
        """Enters fork mode without instruction banner and presents focusable turn cards."""
        if not messages:
            return

        self.fork_mode = True
        md = self.query_one("#feed_markdown", Markdown)
        md.styles.display = "none"

        fork_view = self.query_one("#fork_view", Vertical)
        fork_view.remove_children()
        fork_view.styles.display = "block"

        for idx, turn in enumerate(messages):
            sender = "You" if turn["role"] == "user" else "Gemini"
            card = ForkTurnCard(
                index=idx,
                sender=sender,
                text=turn["text"],
                id=f"fork_card_{idx}",
            )
            fork_view.mount(card)

        self.scroll_home(animate=False)
        self.call_after_refresh(self._focus_first_fork_card)

    def _focus_first_fork_card(self) -> None:
        cards = list(self.query_one("#fork_view").query(ForkTurnCard))
        if cards:
            cards[0].focus()

    def exit_fork_mode(self) -> None:
        """Restores standard markdown feed."""
        if not self.fork_mode:
            return

        self.fork_mode = False
        fork_view = self.query_one("#fork_view", Vertical)
        fork_view.styles.display = "none"
        fork_view.remove_children()

        md = self.query_one("#feed_markdown", Markdown)
        md.styles.display = "block"
        self.focus()

    def get_selected_fork_indices(self) -> list[int]:
        fork_view = self.query_one("#fork_view", Vertical)
        cards = list(fork_view.query(ForkTurnCard))
        return [card.turn_index for card in cards if card.is_selected]

    def toggle_all_fork_checkboxes(self) -> None:
        fork_view = self.query_one("#fork_view", Vertical)
        cards = list(fork_view.query(ForkTurnCard))
        if not cards:
            return
        all_checked = all(c.is_selected for c in cards)
        for c in cards:
            c.set_selected(not all_checked)

    def navigate_fork_cards(self, delta: int) -> None:
        cards = list(self.query_one("#fork_view").query(ForkTurnCard))
        if not cards:
            return

        curr_focused = self.app.focused
        idx = -1
        if curr_focused in cards:
            idx = cards.index(curr_focused)

        if idx == -1:
            target_idx = 0 if delta > 0 else len(cards) - 1
        else:
            target_idx = (idx + delta) % len(cards)

        target = cards[target_idx]
        target.focus()
        target.scroll_visible(animate=True)

    @on(events.Click)
    def _on_feed_click(self, event: events.Click) -> None:
        if self.fork_mode:
            return

        curr = event.widget
        while curr and curr is not self:
            if isinstance(curr, MarkdownFence):
                fences = self._get_fences()
                if curr in fences:
                    self.select_snippet(fences.index(curr), scroll=False)
                    self.focus()
                    event.stop()
                    return
            curr = curr.parent

    def _on_key(self, event: events.Key) -> None:
        if event.key in ("ctrl+full_stop", "ctrl+period", "ctrl+."):
            event.prevent_default(); event.stop()
            self.app.action_fork_chat()
            return

        if self.fork_mode:
            if event.key in ("escape", "ctrl+g"):
                event.prevent_default(); event.stop()
                self.exit_fork_mode()
                self.app.notify("Fork cancelled.")
                return
            elif event.key == "a":
                event.prevent_default(); event.stop()
                self.toggle_all_fork_checkboxes()
                self.app.notify("Toggled all selections.")
                return
            elif event.key in ("enter", "return"):
                event.prevent_default(); event.stop()
                self.app.action_fork_chat()
                return
            elif event.key in ("alt+n", "alt+down", "j", "down"):
                event.prevent_default(); event.stop()
                self.navigate_fork_cards(1)
                return
            elif event.key in ("alt+p", "alt+up", "k", "up"):
                event.prevent_default(); event.stop()
                self.navigate_fork_cards(-1)
                return

        # Fallback when terminal strips Ctrl from Ctrl+. on the feed container
        if not self.fork_mode and event.key in ("full_stop", ".", "f"):
            event.prevent_default(); event.stop()
            self.app.action_fork_chat()
            return

        if self.app.handle_c_c_prefix(event):
            return

        if event.key == "ctrl+c":
            event.prevent_default(); event.stop()
            self.app.set_c_c_prefix()
            return

        if event.key == "ctrl+r":
            event.prevent_default(); event.stop()
            self.app.action_save_snippet_to_disk()
            return

        if event.key == "ctrl+f":
            event.prevent_default(); event.stop()
            self.app.action_insert_file_from_disk()
            return

        if event.key in ("escape", "i", "ctrl+o"):
            event.prevent_default(); event.stop()
            self.app.query_one("#input", ExpandingInput).focus()
            return

        elif event.key in ("alt+n", "alt+down"):
            event.prevent_default(); event.stop()
            self.navigate_snippet(1)
        elif event.key in ("alt+p", "alt+up"):
            event.prevent_default(); event.stop()
            self.navigate_snippet(-1)

        elif event.key in ("down", "j"):
            event.prevent_default(); event.stop()
            self.scroll_down()
        elif event.key in ("up", "k"):
            event.prevent_default(); event.stop()
            self.scroll_up()
        elif event.key in ("pageup",):
            event.prevent_default(); event.stop()
            self.scroll_page_up()
        elif event.key in ("pagedown",):
            event.prevent_default(); event.stop()
            self.scroll_page_down()
        elif event.key in ("home",):
            event.prevent_default(); event.stop()
            self.scroll_home()
        elif event.key in ("end",):
            event.prevent_default(); event.stop()
            self.scroll_end()
        else:
            super()._on_key(event)

class HistoryList(OptionList):
    """OptionList with Vim/Emacs navigation, instant deletion, and renaming."""

    async def _on_key(self, event: events.Key) -> None:
        if self.app.handle_c_c_prefix(event):
            return

        if event.key == "ctrl+c":
            event.prevent_default(); event.stop()
            self.app.set_c_c_prefix()
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

class ChatApp(App):
    COMMAND_PALETTE_BINDING = "alt+x"
    COMMAND_PALETTE = MenuPalette

    CSS = """
    Screen {
        layout: vertical;
    }
    #feed {
        height: 1fr;
        border: solid green;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-gutter: stable;
        padding: 0 2 0 1;
        width: 100%;
        max-width: 100%;
    }
    #feed #feed_markdown {
        width: 100%;
        max-width: 100%;
        height: auto;
    }
    #feed #fork_view {
        width: 100%;
        max-width: 100%;
        height: auto;
    }
    .fork_turn_card {
        width: 100%;
        height: auto;
        margin-bottom: 1;
        padding: 0;
        border: solid #444444;
        background: $surface;
    }
    .fork_turn_card:focus {
        border: thick cyan;
        background: #101c28;
    }
    .fork_turn_header {
        width: 100%;
        height: auto;
        padding: 0 1;
        background: #1f3044;
        border-bottom: solid #334455;
    }
    .fork_turn_card:focus .fork_turn_header {
        background: dodgerblue;
    }
    .fork_turn_box_label {
        width: 100%;
        text-style: bold;
        color: #ffffff;
    }
    .fork_turn_preview {
        width: 100%;
        height: auto;
        padding: 1 1;
    }
    #feed MarkdownBlock,
    #feed MarkdownParagraph,
    #feed MarkdownTable {
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
    }
    #feed MarkdownFence {
        width: 100%;
        max-width: 100%;
        height: auto;
        overflow-x: hidden;
        margin: 1 0;
        border: solid #444444;
    }
    #feed MarkdownFence.active-snippet {
        border: thick yellow !important;
        background: #2b2600 !important;
    }
    #feed MarkdownFence > * {
        width: 100%;
        max-width: 100%;
    }
    #feed:focus {
        border: double lightgreen;
    }
    #history {
        height: 1fr;
        border: solid yellow;
        display: none;
    }
    #snippet_preview {
        width: 100%;
        max-height: 10;
        border: round dodgerblue;
        display: none;
        margin-bottom: 0;
    }
    #snippet_preview:focus {
        border: double cyan;
    }
    #input {
        border: solid dodgerblue;
    }
    #input:focus {
        border: double cyan;
    }
    """

    BINDINGS = [
        Binding("alt+x", "command_palette", "Menu (M-x)", show=True),
        Binding("ctrl+n", "new_chat", "C-c n (New)", show=True),
        Binding("ctrl+b", "toggle_history", "C-c b (History)", show=True),
        Binding("ctrl+full_stop", "fork_chat", "C-. (Fork)", show=True),
        Binding("ctrl+y", "copy_last_response", "C-c y (Yank/Emacs)", show=True),
        Binding("ctrl+r", "save_snippet_to_disk", "C-c r (Save File)", show=True),
        Binding("ctrl+f", "insert_file_from_disk", "C-c f (File)", show=True),
        Binding("ctrl+backslash", "open_git_tree", "C-c g (Git Tree)", show=True),
        Binding("ctrl+e", "open_in_editor", "C-c e (Editor)", show=True),
        Binding("ctrl+t", "rename_chat", "C-c t (Rename)", show=True),
        Binding("escape", "toggle_focus", "Focus Swap", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client()
        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.current_chat_parent_id: str | None = None
        self.history: list[dict] = []
        self._server: asyncio.AbstractServer | None = None
        self._prefix_c_c: bool = False

        self.global_working_dir: str = os.getcwd()
        self.current_chat_working_dir: str | None = None

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        self._prefix_c_c = True
        self.notify("C-c-", timeout=1.0)

    def handle_c_c_prefix(self, event: events.Key) -> bool:
        """Centralized Emacs C-c chord interceptor."""
        if not self._prefix_c_c:
            return False

        self._prefix_c_c = False

        if event.key in ("ctrl+n", "n"):
            event.prevent_default(); event.stop()
            self.action_new_chat()
            return True
        elif event.key in ("ctrl+b", "b"):
            event.prevent_default(); event.stop()
            self.action_toggle_history()
            return True
        elif event.key in ("ctrl+e", "e"):
            event.prevent_default(); event.stop()
            self.action_open_in_editor()
            return True
        elif event.key in ("ctrl+y", "y"):
            event.prevent_default(); event.stop()
            self.action_copy_last_response()
            return True
        elif event.key in ("ctrl+r", "r"):
            event.prevent_default(); event.stop()
            self.action_save_snippet_to_disk()
            return True
        elif event.key in ("ctrl+f", "f"):
            event.prevent_default(); event.stop()
            self.action_insert_file_from_disk()
            return True
        elif event.key in ("ctrl+g", "g"):
            event.prevent_default(); event.stop()
            self.action_open_git_tree()
            return True
        elif event.key in ("ctrl+t", "t"):
            event.prevent_default(); event.stop()
            self.action_rename_chat()
            return True
        elif event.key in ("period", "full_stop", "."):
            event.prevent_default(); event.stop()
            self.action_fork_chat()
            return True
        elif event.key in ("ctrl+c", "escape"):
            event.prevent_default(); event.stop()
            self.notify("Quit", timeout=1.0)
            return True

        return False

    def on_key(self, event: events.Key) -> None:
        """Application-level key interceptor guaranteeing chords resolve reliably."""
        feed = self.query_one("#feed", FeedArea)

        # In fork mode, prioritize Alt+n/p for navigating fork cards
        if feed.fork_mode and event.key in ("alt+n", "alt+down"):
            event.prevent_default(); event.stop()
            feed.navigate_fork_cards(1)
            return
        elif feed.fork_mode and event.key in ("alt+p", "alt+up"):
            event.prevent_default(); event.stop()
            feed.navigate_fork_cards(-1)
            return

        if self._prefix_c_c:
            if self.handle_c_c_prefix(event):
                event.prevent_default()
                event.stop()
                return

        # Centralized C-. / Ctrl+full_stop check
        if event.key in ("ctrl+full_stop", "ctrl+period", "ctrl+."):
            event.prevent_default()
            event.stop()
            self.action_fork_chat()
            return

        # If already in fork mode, pressing Enter confirms and prompts for naming
        if feed.fork_mode and event.key in ("enter", "return"):
            focused = self.focused
            if focused and (focused is feed or focused in feed.query("*")):
                event.prevent_default()
                event.stop()
                self.action_fork_chat()
                return

        if event.key == "ctrl+c":
            event.prevent_default()
            event.stop()
            self.set_c_c_prefix()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield FeedArea(id="feed")
            yield HistoryList(id="history")
            yield SnippetPreview(id="snippet_preview")
            yield ExpandingInput(id="input")
        yield Footer()

    async def on_mount(self) -> None:
        await self.start_socket_server()

        files = self._get_sorted_files()
        if files:
            first_id = files[0].stem
            await self.load_chat(first_id)
        else:
            self._start_new_chat(title="")

        self.query_one("#input").focus()

    # --- Working Directory Scope Management ---

    def get_effective_working_dir(self) -> str:
        if self.current_chat_working_dir:
            return self.current_chat_working_dir
        return self.global_working_dir or os.getcwd()

    def set_working_dir(self, directory: str, chat_scoped: bool) -> None:
        expanded = os.path.expanduser(directory.strip())
        if chat_scoped:
            self.current_chat_working_dir = expanded
        else:
            self.global_working_dir = expanded
            self.current_chat_working_dir = None
        self.save_current_chat()

    # --- Unix Domain Socket Server ---

    async def start_socket_server(self) -> None:
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_socket_client,
                path=str(SOCKET_PATH),
            )
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

    def on_unmount(self) -> None:
        if self._server:
            self._server.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink(missing_ok=True)

    # --- Storage & Persistence ---

    def _get_chat_file(self, chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    def _get_sorted_files(self) -> list[Path]:
        return sorted(
            CHATS_DIR.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

    def refresh_history_list(self) -> None:
        """Renders chats with sub-chat indentation and automatically un-subs orphans."""
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

        # If parent was deleted, auto turn sub-chat into a non-sub chat
        for cid, data in chats_by_id.items():
            parent_id = data.get("parent_id")
            if parent_id and parent_id not in chats_by_id:
                data["parent_id"] = None
                target_file = self._get_chat_file(cid)
                if target_file.exists():
                    target_file.write_text(json.dumps(data, indent=2))

        # Build hierarchy
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
        self.current_chat_id = chat_id
        path = self._get_chat_file(chat_id)
        if path.exists():
            data = json.loads(path.read_text())
            self.history = data.get("messages", [])
            self.current_chat_title = data.get("title", "")
            self.current_chat_working_dir = data.get("working_dir")
            self.current_chat_parent_id = data.get("parent_id")
        else:
            self.history = []
            self.current_chat_title = ""
            self.current_chat_working_dir = None
            self.current_chat_parent_id = None

        feed = self.query_one("#feed", FeedArea)
        await feed.set_messages(self.history)
        self.query_one("#input", ExpandingInput).reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()

    def save_current_chat(self) -> None:
        if not self.current_chat_id or not self.history:
            return

        path = self._get_chat_file(self.current_chat_id)

        title = self.current_chat_title.strip()
        if not title and self.history:
            title = self.history[0]["text"][:28].replace("\n", " ")
        if not title:
            title = "New Chat"

        self.current_chat_title = title

        data = {
            "id": self.current_chat_id,
            "title": self.current_chat_title,
            "parent_id": self.current_chat_parent_id,
            "updated_at": time.time(),
            "working_dir": self.current_chat_working_dir,
            "messages": self.history,
        }
        path.write_text(json.dumps(data, indent=2))

    async def delete_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)

        target_file = self._get_chat_file(target_id)
        if target_file.exists():
            target_file.unlink()

        # Update any sub-chats attached to this chat to become non-sub chats
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

    def action_next_snippet(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        feed.navigate_snippet(1)

    def action_prev_snippet(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        feed.navigate_snippet(-1)

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
        """Handles initiation and finalization of chat forking."""
        feed = self.query_one("#feed", FeedArea)

        if feed.fork_mode:
            selected_indices = feed.get_selected_fork_indices()
            if not selected_indices:
                self.notify("Please select at least one response to fork.", severity="warning")
                return

            def on_fork_named(fork_title: str | None) -> None:
                if not fork_title:
                    self.notify("Fork cancelled.")
                    feed.exit_fork_mode()
                    return
                self._execute_chat_fork(selected_indices, fork_title)

            self.push_screen(
                ForkModal(default_title=self.current_chat_title),
                callback=on_fork_named,
            )
            return

        if not self.history:
            self.notify("No conversation history to fork.", severity="warning")
            return

        feed.enter_fork_mode(self.history)
        self.notify("Fork mode: Select responses with Space/Click, Alt+n/p to navigate, Enter to fork.", timeout=4.0)

    def _execute_chat_fork(self, selected_indices: list[int], fork_title: str) -> None:
        """Constructs and switches to the new forked chat without triggering Gemini API call."""
        feed = self.query_one("#feed", FeedArea)
        feed.exit_fork_mode()

        selected_turns = [copy.deepcopy(self.history[i]) for i in selected_indices]
        if not selected_turns:
            return

        # Ensure Header is present at the very beginning of the chat
        if selected_turns[0]["role"] == "user":
            selected_turns[0]["text"] = f"{FORK_HEADER_TEXT}\n\n{selected_turns[0]['text']}"
        else:
            selected_turns.insert(0, {"role": "user", "text": FORK_HEADER_TEXT})

        # Save previous state
        self.save_current_chat()

        parent_chat_id = self.current_chat_id
        new_chat_id = uuid4().hex[:8]

        self.current_chat_id = new_chat_id
        self.current_chat_title = fork_title
        self.current_chat_parent_id = parent_chat_id
        self.history = selected_turns

        # Persist new forked chat
        self.save_current_chat()

        # Update feed and input without calling Gemini
        self.run_worker(self._render_forked_chat(selected_turns))

    async def _render_forked_chat(self, turns: list[dict]) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.set_messages(turns)
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()
        self.refresh_history_list()
        self.notify(f"Fork created: '{self.current_chat_title}' (Awaiting response)", timeout=4.0)

    def action_toggle_focus(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        preview_box = self.query_one("#snippet_preview", SnippetPreview)
        input_widget = self.query_one("#input", ExpandingInput)

        feed_focused = feed.has_focus or (self.focused is not None and self.focused in feed.query("*"))

        if feed_focused:
            if preview_box.styles.display != "none":
                preview_box.focus()
            else:
                input_widget.focus()
        elif preview_box.has_focus:
            input_widget.focus()
        else:
            feed.focus()

    def action_toggle_history(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        history_widget = self.query_one("#history", HistoryList)
        input_widget = self.query_one("#input", ExpandingInput)

        if history_widget.styles.display == "none":
            self.refresh_history_list()
            feed.styles.display = "none"
            history_widget.styles.display = "block"
            history_widget.focus()
        else:
            history_widget.styles.display = "none"
            feed.styles.display = "block"
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
        self.query_one("#history").styles.display = "none"
        self.query_one("#feed").styles.display = "block"

        self.current_chat_id = uuid4().hex[:8]
        self.current_chat_title = title
        self.current_chat_parent_id = None
        self.current_chat_working_dir = None
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()

    def action_save_snippet_to_disk(self) -> None:
        """Write active feed snippet directly to a file on disk with overwrite protection."""
        feed = self.query_one("#feed", FeedArea)
        content = feed.get_active_snippet()

        if not content:
            self.notify("No snippet selected to write.", severity="warning")
            return

        initial_dir = self.get_effective_working_dir()
        is_chat_scoped = self.current_chat_working_dir is not None

        def on_save_modal_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            filename = result["filename"]
            chat_scoped = result["chat_scoped"]
            code = result["content"]

            base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
            target = (base / filename.strip()).resolve()

            def do_write() -> None:
                try:
                    written_path = write_code_to_disk(working_dir, filename, code)
                    self.set_working_dir(working_dir, chat_scoped)
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
                is_chat_scoped=is_chat_scoped,
            ),
            callback=on_save_modal_result,
        )

    def action_insert_file_from_disk(self) -> None:
        """Prompt user to select a file from disk and insert it as a snippet."""
        initial_dir = self.get_effective_working_dir()
        is_chat_scoped = self.current_chat_working_dir is not None

        def on_file_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            file_path_str = result["file_path"]
            rel_path = result["rel_path"]
            chat_scoped = result["chat_scoped"]

            self.set_working_dir(working_dir, chat_scoped)

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
            InsertFileModal(initial_dir=initial_dir, is_chat_scoped=is_chat_scoped),
            callback=on_file_result,
        )

    def action_open_git_tree(self) -> None:
        """Scans and presents Git repository tree with selectable files."""
        initial_dir = self.get_effective_working_dir()
        is_chat_scoped = self.current_chat_working_dir is not None

        def on_git_tree_result(result: dict | None) -> None:
            if not result:
                return

            repo_dir = result["repo_dir"]
            selected_files: list[str] = result["selected_files"]
            tracked_files: list[str] = result["tracked_files"]
            ignored_files: list[str] = result["ignored_files"]
            tree_mode: str = result["tree_mode"]
            chat_scoped: bool = result["chat_scoped"]

            self.set_working_dir(repo_dir, chat_scoped)

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
            GitTreeModal(initial_dir=initial_dir, is_chat_scoped=is_chat_scoped),
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
        try:
            escaped_text = json.dumps(code_text)
            if target_buf:
                escaped_buf = json.dumps(target_buf)
                elisp = f'(gemini-insert-into-window {escaped_buf} {escaped_text})'
            else:
                elisp = f'(with-current-buffer (window-buffer (selected-window)) (insert {escaped_text}))'

            res = subprocess.run(
                ["emacsclient", "--eval", elisp],
                capture_output=True,
                timeout=1,
            )
            return res.returncode == 0
        except Exception:
            return False

    def action_copy_last_response(self) -> None:
        """Yank active snippet (or last response) to clipboard and targeted Emacs buffer."""
        feed = self.query_one("#feed", FeedArea)
        snippet_text = feed.get_active_snippet()

        text_to_send = ""
        if snippet_text is not None:
            text_to_send = snippet_text
        else:
            for turn in reversed(self.history):
                if turn["role"] == "model":
                    text_to_send = turn["text"]
                    break

        if not text_to_send:
            self.notify("Nothing to yank.", severity="warning")
            return

        self.copy_to_clipboard(text_to_send)
        frames = self._get_emacs_frames()

        if len(frames) <= 1:
            success = self._send_to_emacs_buffer(text_to_send)
            if success:
                self.notify("Yanked & sent to active Emacs window")
            else:
                self.notify("Yanked to clipboard")
            return

        def on_window_chosen(chosen: dict | None) -> None:
            if chosen:
                buf = chosen.get("buf_name")
                self._send_to_emacs_buffer(text_to_send, target_buf=buf)
                self.notify(f"Sent to {chosen.get('file_name')}")

        self.push_screen(FrameSelectModal(frames), callback=on_window_chosen)

    def action_open_in_editor(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        if not getattr(feed, "_raw_markdown", ""):
            self.notify("No conversation to open.", severity="warning")
            return

        editor = os.environ.get("EDITOR") or os.environ.get("PAGER") or "nano"

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False, encoding="utf-8") as tmp:
            tmp.write(feed._raw_markdown)
            tmp.flush()
            tmp_path = tmp.name

        try:
            with self.suspend():
                subprocess.run([editor, tmp_path])
        except Exception as e:
            self.notify(f"Failed to launch editor: {e}", severity="error")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @on(OptionList.OptionSelected, "#history")
    async def on_history_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            await self.load_chat(str(event.option_id))
            self.query_one("#history").styles.display = "none"
            self.query_one("#feed").styles.display = "block"
            self.query_one("#input").focus()

    async def append_to_feed(self, sender: str, text: str) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.append_message(sender, text)

    async def on_expanding_input_submitted(self, event: ExpandingInput.Submitted) -> None:
        user_msg = event.value
        await self.append_to_feed("You", user_msg)

        self.history.append({"role": "user", "text": user_msg})
        self.save_current_chat()

        self.ask_gemini()

    @work(exclusive=True)
    async def ask_gemini(self) -> None:
        chat_id_snapshot = self.current_chat_id

        # Normalize multiturn talk to ensure alternating turns and leading user role
        payload = []
        for t in self.history:
            if payload and payload[-1]["role"] == t["role"]:
                payload[-1]["parts"][0]["text"] += "\n\n" + t["text"]
            else:
                payload.append({"role": t["role"], "parts": [{"text": t["text"]}]})

        if payload and payload[0]["role"] != "user":
            payload.insert(0, {"role": "user", "parts": [{"text": FORK_HEADER_TEXT}]})

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.8-flash",
                contents=payload,
            )
            reply = response.text or ""
        except Exception as e:
            self.notify(f"API Error: {e}", severity="error")
            return

        if self.current_chat_id == chat_id_snapshot:
            self.history.append({"role": "model", "text": reply})
            self.save_current_chat()
            await self.append_to_feed("Gemini", reply)

if __name__ == "__main__":
    ChatApp().run()