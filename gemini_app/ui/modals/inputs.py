"""Input widgets with tab auto-completion and title prompt dialogs."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Callable

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Label

from gemini_app.ui.modals.base import ResponsiveModalScreen


class DirectoryPathInput(Input):
    """Input widget featuring double-tab directory auto-completion."""

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
    """Input widget featuring tab path auto-completion relative to working directory."""

    def __init__(self, base_dir_getter: Callable[[], str | None] | None = None, **kwargs) -> None:
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


class TitlePromptModal(ResponsiveModalScreen[str | None]):
    """Modal prompt for renaming or setting the chat topic."""

    DEFAULT_CSS = """
    TitlePromptModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #dialog {
        padding: 1 2;
        width: 60;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #dialog Input {
        margin-bottom: 1;
        background: #000000;
        color: #ffffff;
    }
    #dialog-buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
    }
    #dialog-buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    TitlePromptModal.-mobile #dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
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
        with VerticalScroll(id="dialog"):
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
        super().on_mount()
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
