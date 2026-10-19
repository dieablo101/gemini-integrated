"""Main Textual Chat Application for Gemini Bilateral Console."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable
from uuid import uuid4

import pyperclip
from google import genai
from google.genai import types
from rich.cells import cell_len
from rich.console import RenderableType
from rich.syntax import Syntax
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    Markdown,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
    Tree,
)
from textual.widgets.markdown import MarkdownFence
from textual.widgets.text_area import Selection
from textual.widgets.tree import TreeNode

from gemini_app.config import (
    ARCHIVE_DIR,
    CENTER_SCREEN_MODE,
    CHATS_DIR,
    CURRENT_USER,
    DEFAULT_MODEL,
    DEFAULT_PALETTE,
    DEFAULT_WINDOW_CAPACITY,
    FORK_HEADER_TEXT,
    GEMINI_HOME,
    GATED_NAV_KEYS,
    MAX_SNIPPET_LINES_ON_WIRE,
    MOBILE_BREAKPOINT,
    SCREENSHOTS_DIR,
    SOCKET_PATH,
    SPINNER_FRAMES,
    STATE_FILE,
    THEMES,
    TURNS_PER_SEGMENT,
    WIRE_CONTINUATION_PROMPT,
)
from gemini_app.helpers import (
    build_ascii_tree,
    cast_ray_from_center,
    detect_language,
    get_git_files_catalog,
    truncate_wire_snippets,
    write_code_to_disk,
)
from gemini_app.events import (
    AppLockController,
    AppLockEngaged,
    AppLockReleased,
    MindMapRecalibrated,
    RemoteInsert,
    RequestFailed,
    RequestFinished,
    RequestPhaseUpdate,
)
from gemini_app.mind.screen import MindMapScreen
from gemini_app.storage.memory_index import MemoryIndex
from gemini_app.storage.notes_manager import NoteItem, NotesManager, sanitize_working_notes
from gemini_app.storage.rollback import (
    mark_reboot_in_progress,
    mark_startup_successful,
    perform_git_rollback,
    record_stable_commit,
)
from gemini_app.tools.registry import ToolRegistry
from gemini_app.tools.snapshots import capture_ui_snapshot, cleanup_stale_ephemerals, list_held_snapshots
from gemini_app.ui.boot import BootScreen
from gemini_app.ui.modals import (
    CommandsModal,
    ConfirmModal,
    DirectoryPathInput,
    FilePathInput,
    ForkModal,
    FrameSelectModal,
    GitTreeModal,
    InsertFileModal,
    ResponsiveModalScreen,
    TitlePromptModal,
    WriteSnippetModal,
)
from gemini_app.ui.widgets import (
    EmacsBaseTextArea,
    ExpandingInput,
    FeedArea,
    NotesEditorArea,
    NotesPanel,
    SnippetPreview,
    TurnCard,
)
from gemini_app.ui.styles import get_full_app_css


class ChatApp(App):
    ENABLE_COMMAND_PALETTE = False
    COMMAND_PALETTE_BINDING = None
    COMMANDS = set()

    def action_command_palette(self) -> None:
        pass

    CSS = get_full_app_css()

    BINDINGS = [
        Binding("ctrl+c", "c_c_prefix_stub", "^c Commands", show=False),
        Binding("ctrl+q", "quit", "^q Quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client()
        self.lock = AppLockController(self)
        self.memory_index = MemoryIndex()

        self.active_palette_name: str = DEFAULT_PALETTE
        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.current_chat_parent_id: str | None = None
        self.current_chat_working_dir: str | None = None
        self.current_chat_last_index: int = 0
        self.current_chat_center_marker: str = ""
        
        # Unified Notes System (Gemini Managed Notes)
        self.gemini_notes: str = ""
        self.global_notes: str = ""
        self.relational_notes: dict[str, str] = {}
        self.active_notes_mode: str = "gemini"  # "gemini", "turn", "global"
        self.current_focused_turn_id: str = ""
        self.current_focused_turn_index: int = 0
        self._notes_flush_timer: Timer | None = None
        self.notes_manager: NotesManager = NotesManager(working_notes="", active_topic="General")

        # Cognitive Mind State & Topology Tracking
        self.is_legacy_chat: bool = False
        self.active_task_title: str = "Unifying Notes System & Relational Anchors"
        self.current_gemini_state: str = "Unifying Notes System & Relational Anchors"
        self.current_user_state: str = "Collaborating on unified bilateral console session."
        self.current_tree_state: list[str | int] = ["T1", "F:gemini_app/"]
        self.current_tree_content: str = "└── Unified Stream [Active]"
        self.saved_prompt_draft: str = ""

        self.notes_open: bool = False
        self._last_focused_input_id: str = "input"
        self._last_non_notes_input_id: str = "input"
        self._seen_chats_in_session: set[str] = set()

        self.history: list[dict] = []
        self._server: asyncio.AbstractServer | None = None

        self._prefix_c_c: bool = False
        self._c_c_timer: Timer | None = None

        self._request_phase: str = "idle"
        self._request_details: str = ""
        self._request_start_time: float = 0.0
        self._spinner_idx: int = 0
        self._status_timer: Timer | None = None

        self._nav_indicator_action: str | None = None
        self._nav_indicator_timer: Timer | None = None

        self._commands_registry: dict[str, Callable[[str], None]] = {
            "ui-theme": self._cmd_ui_theme,
            "reboot": lambda arg: self.action_reboot(status_report=arg if arg else None),
            "restart": lambda arg: self.action_reboot(status_report=arg if arg else None),
        }

    def consume_notes_editor(self) -> None:
        """Consumes text typed into the notes editor by the user into Gemini-managed notes."""
        if getattr(self, "_consuming_notes", False):
            return
        self._consuming_notes = True
        try:
            editor = self.query_one("#notes_editor", NotesEditorArea)
            raw_text = editor.text
            if not raw_text.strip():
                return
            # If editor text matches initial rendered template, nothing new was typed by the user
            if getattr(editor, "_initial_rendered_text", "") and raw_text.strip() == editor._initial_rendered_text.strip():
                return
            curr_topic = getattr(self, "active_task_title", "") or self.notes_manager.active_topic
            added = self.notes_manager.consume_user_input(
                raw_text=raw_text,
                active_topic=curr_topic,
                turn_id=getattr(self, "current_focused_turn_id", ""),
            )
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.schedule_notes_flush()
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.refresh_display()
            if added:
                topics_str = ", ".join(set(n.topic for n in added))
                self.notify(f"✓ Note consumed & indexed under topic: '{topics_str}'", timeout=3.5)
            else:
                self.notify("✓ Working notes updated.", timeout=2.0)
        except Exception as e:
            self.notify(f"Error consuming note: {e}", severity="error")
        finally:
            self._consuming_notes = False

    def schedule_notes_flush(self) -> None:
        if self._notes_flush_timer:
            self._notes_flush_timer.stop()
        self._notes_flush_timer = self.set_timer(0.3, self._do_notes_flush)

    def _do_notes_flush(self) -> None:
        self._notes_flush_timer = None
        if self.current_chat_id:
            notes_payload = self.notes_manager.to_dict() if hasattr(self, "notes_manager") else {
                "gemini_notes": self.gemini_notes or "",
                "global_notes": self.global_notes or "",
                "relational_notes": self.relational_notes or {},
            }
            self._direct_flush_chat_to_disk(self.current_chat_id, notes_payload)
        self._save_to_state("global_notes", self.global_notes or "")

    def schedule_chat_notes_flush(self) -> None:
        self.schedule_notes_flush()

    def schedule_global_notes_flush(self) -> None:
        self.schedule_notes_flush()

    def clear_toasts(self) -> None:
        try:
            seen_toasts = set()
            stack = getattr(self, "screen_stack", None) or getattr(self, "_screen_stack", [])
            for screen in list(stack):
                if hasattr(screen, "query"):
                    for toast in list(screen.query("Toast")):
                        if toast not in seen_toasts:
                            seen_toasts.add(toast)
                            try:
                                toast.dismiss()
                            except Exception:
                                pass
        except Exception:
            pass

    def push_screen(self, screen: Screen[ModalResultType] | str, callback: Callable[[ModalResultType], None] | None = None, wait_for_dismiss: bool = False):
        self.clear_toasts()
        if hasattr(screen, "add_class") and hasattr(self, "active_palette_name"):
            for t in THEMES:
                screen.remove_class(f"theme-{t}")
            screen.add_class(f"theme-{self.active_palette_name}")
        return super().push_screen(screen, callback=callback, wait_for_dismiss=wait_for_dismiss)

    @property
    def accent_color(self) -> str:
        return THEMES.get(self.active_palette_name, THEMES[DEFAULT_PALETTE])["accent"]

    def set_theme(self, palette_name: str, notify_user: bool = True) -> bool:
        theme_clean = palette_name.strip().lower()
        if theme_clean not in THEMES:
            return False

        self.active_palette_name = theme_clean
        self._save_to_state("ui_theme", theme_clean)

        stack = getattr(self, "screen_stack", None) or getattr(self, "_screen_stack", [])
        for sc in list(stack):
            for t in THEMES:
                sc.remove_class(f"theme-{t}")
            sc.add_class(f"theme-{theme_clean}")

        self.update_feed_nav_banner()
        self._update_footer_markup()

        if notify_user:
            self.notify(f"Theme set to '{theme_clean}'", timeout=2.5)
        return True

    def _read_theme_from_state(self) -> str:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                stored = data.get("ui_theme")
                if stored in THEMES:
                    return stored
            except Exception:
                pass
        return DEFAULT_PALETTE

    def _read_global_notes_from_state(self) -> str:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                return data.get("global_notes", "") or ""
            except Exception:
                pass
        return ""

    def _save_to_state(self, key: str, value: str) -> None:
        try:
            state: dict = {}
            if STATE_FILE.exists():
                try:
                    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
            state[key] = value
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            STATE_FILE.chmod(0o600)
        except Exception:
            pass

    def _flush_global_notes_to_state(self) -> None:
        self.flush_current_notes()
        self._save_to_state("global_notes", self.global_notes or "")

    def _update_footer_markup(self) -> None:
        try:
            c = self.accent_color
            self.query_one("#footer_quit", Static).update(f"[bold {c}]^q:[/] [white]quit[/]")
            self.query_one("#footer_sep", Static).update(f"[{c}]|[/]")
            self.query_one("#footer_commands", Static).update(f"[bold {c}]^c + c:[/] [white]commands[/]")
        except Exception:
            pass

    def is_history_open(self) -> bool:
        return False

    def flush_current_notes(self, consume_input: bool = False) -> None:
        if consume_input:
            self.consume_notes_editor()
            return
        try:
            editors = list(self.query("#notes_editor"))
            if editors and editors[0].has_focus:
                text_val = editors[0].text
                # Only sync working notes if editor is currently in working filter, and sanitize it!
                if getattr(self, "active_notes_mode", "working") in ("working", "gemini"):
                    clean_w = sanitize_working_notes(text_val)
                    if clean_w:
                        self.gemini_notes = clean_w
                        if hasattr(self, "notes_manager"):
                            self.notes_manager.working_notes = clean_w
        except Exception:
            pass

    def on_feed_turn_focused(self, turn_idx: int, turn_id: str, sender: str = "") -> None:
        self.current_focused_turn_index = turn_idx
        self.current_focused_turn_id = turn_id
        try:
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.on_turn_changed(turn_idx, turn_id, sender)
        except Exception:
            pass

    def execute_command(self, raw_input: str) -> bool:
        cmd_text = raw_input.strip()
        if not cmd_text.startswith("!/"):
            return False

        body = cmd_text[2:].strip()
        if not body:
            self.notify("Empty command specified.", severity="error")
            return True

        if ":" in body:
            program, arg = body.split(":", 1)
            program = program.strip().lower()
            arg = arg.strip()
        else:
            program = body.lower()
            arg = ""

        handler = self._commands_registry.get(program)
        if handler:
            handler(arg)
        else:
            valid_cmds = ", ".join(self._commands_registry.keys())
            self.notify(f"Unknown command '{program}'. Available: {valid_cmds}", severity="error")

        return True

    def _cmd_ui_theme(self, arg: str) -> None:
        if not arg:
            valid_themes = ", ".join(THEMES.keys())
            self.notify(f"Usage: !/ui-theme:<color>. Options: {valid_themes}", severity="warning")
            return

        success = self.set_theme(arg)
        if not success:
            valid_themes = ", ".join(THEMES.keys())
            self.notify(f"Invalid theme '{arg}'. Choose from: {valid_themes}", severity="error")

    def trigger_nav_indicator(self, action: str) -> None:
        self._nav_indicator_action = action
        self.update_feed_nav_banner()

        if self._nav_indicator_timer:
            self._nav_indicator_timer.stop()

        self._nav_indicator_timer = self.set_timer(0.20, self._clear_nav_indicator)

    def _clear_nav_indicator(self) -> None:
        self._nav_indicator_action = None
        self._nav_indicator_timer = None
        self.update_feed_nav_banner()

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None
        self._prefix_c_c = True
        self._c_c_timer = self.set_timer(3.5, self._expire_c_c_prefix)

    def _expire_c_c_prefix(self) -> None:
        self._prefix_c_c = False
        self._c_c_timer = None

    def intercept_c_c_key(self, event: events.Key) -> bool:
        if event.key == "ctrl+c":
            if self._prefix_c_c:
                event.prevent_default()
                event.stop()
                self.handle_c_c_prefix(event)
                return True
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
        self.clear_toasts()

        key = event.key.lower()
        char = (event.character or "").lower()

        if key in ("ctrl+g", "escape"):
            return True

        if key in ("ctrl+c", "c") or char == "c":
            self.action_open_commands_modal()
            return True
        elif key in ("ctrl+m", "m") or char == "m":
            self.action_open_mind_map()
            return True
        elif key in ("bracketleft", "left_bracket", "bracket_left", "[") or char == "[":
            self.action_toggle_notes()
            return True
        elif key in ("ctrl+e", "e") or char == "e":
            self.action_send_to_emacs()
            return True
        elif key in ("ctrl+w", "w") or char == "w":
            self.action_copy_active_snippet()
            return True
        elif key in ("ctrl+y", "y") or char == "y":
            self.action_yank_to_input()
            return True
        elif key in ("ctrl+t", "t") or char == "t":
            def on_title_entered(new_title: str | None) -> None:
                if new_title and new_title.strip():
                    self.set_feed_title(new_title.strip())
                    self.notify(f"Feed active task title updated to: {new_title.strip()}")
            self.push_screen(
                TitlePromptModal(
                    prompt="Set active work / feed section title:",
                    default_title=getattr(self, "active_task_title", "") or self.current_gemini_state,
                ),
                callback=on_title_entered,
            )
            return True
        elif key in ("ctrl+r", "r") or char == "r":
            self.action_save_snippet_to_disk()
            return True
        elif key in ("ctrl+f", "f") or char == "f":
            self.action_insert_file_from_disk()
            return True
        elif key in ("ctrl+g", "g") or char == "g":
            self.action_open_git_tree()
            return True
        elif key in ("period", "full_stop", ".") or char == ".":
            self.action_fork_chat()
            return True
        elif key in ("grave", "backtick", "`") or char == "`":
            self.action_take_snapshot(label="", taken_by="user", source="shortcut")
            return True

        self.notify(f"C-c {key} is undefined", timeout=2.0)
        return False

    def action_c_c_prefix_stub(self) -> None:
        self.set_c_c_prefix()

    def action_open_commands_modal(self) -> None:
        self.push_screen(CommandsModal())

    def action_open_mind_map(self) -> None:
        if isinstance(self.screen, MindMapScreen):
            self.pop_screen()
            return

        if self.notes_open:
            self.action_toggle_notes()

        try:
            preview = self.query_one("#snippet_preview", SnippetPreview)
            preview.hide_preview()
        except Exception:
            pass

        try:
            input_box = self.query_one("#input", ExpandingInput)
            self.saved_prompt_draft = input_box.text
            input_box.clear()
        except Exception:
            self.saved_prompt_draft = ""

        def on_mind_map_closed(_) -> None:
            try:
                inp = self.query_one("#input", ExpandingInput)
                if self.saved_prompt_draft:
                    inp.text = self.saved_prompt_draft
                    inp.move_cursor(inp.document.end, select=False)
                    self.saved_prompt_draft = ""
                inp.focus()
            except Exception:
                pass

        self.push_screen(MindMapScreen(), callback=on_mind_map_closed)

    def action_take_snapshot(
        self, label: str = "", taken_by: str = "user", source: str = "shortcut"
    ) -> dict[str, Any]:
        """Captures, indexes, and holds a UI snapshot for bilateral communication."""
        try:
            entry = capture_ui_snapshot(self, label=label, taken_by=taken_by, source=source)
            idx = entry.get("index", 1)
            snap_id = entry.get("id", "")
            lbl_info = f" ('{label}')" if label else ""
            policy_info = " [saved permanently]" if entry.get("persistent") else " [ephemeral, deleted upon review]"
            self.notify(f"Snapshot #{idx}{lbl_info} captured & held{policy_info}! [{snap_id}]", timeout=4.0)
            return entry
        except Exception as e:
            self.notify(f"Snapshot error: {e}", severity="error")
            return {"status": "error", "message": str(e)}

    def action_take_svg_screenshot(self) -> None:
        self.action_take_snapshot(label="", taken_by="user", source="shortcut")

    def _render_flow_nav_banner(self, items: list[str], sep_markup: str, sep_plain: str, available_w: int) -> str:
        lines: list[str] = []

        def clean_markup(s: str) -> str:
            return re.sub(r"\[[^\]]*\]", "", s)

        sep_cells = cell_len(sep_plain)
        curr_line_markup: list[str] = []
        curr_len = 0

        for item in items:
            item_plain = clean_markup(item)
            item_cells = cell_len(item_plain)

            is_start_of_line = (curr_len == 0)

            if is_start_of_line:
                needed = item_cells
            else:
                needed = sep_cells + 2 + item_cells

            if curr_len + needed <= available_w:
                if is_start_of_line:
                    curr_line_markup.append(item)
                    curr_len = item_cells
                else:
                    curr_line_markup.append(f"{sep_markup} {item}")
                    curr_len += sep_cells + 2 + item_cells
            else:
                if not is_start_of_line:
                    lines.append(" ".join(curr_line_markup))
                    curr_line_markup = [item]
                    curr_len = item_cells
                else:
                    curr_line_markup.append(item)
                    lines.append(" ".join(curr_line_markup))
                    curr_line_markup = []
                    curr_len = 0

        if curr_line_markup:
            lines.append(" ".join(curr_line_markup))

        return "\n".join(lines)

    def update_feed_nav_banner(self) -> None:
        try:
            banner = self.query_one("#feed_nav_banner", Static)
            feed = self.query_one("#feed", FeedArea)

            avail_w = self.size.width - 2 if self.size and self.size.width > 2 else 78
            accent = self.accent_color

            if feed.fork_ui_active:
                banner.add_class("fork-active")
                sep_markup = "[bold black]|[/]"
                sep_plain = "|"
                items = [
                    "Space: Toggle [X]",
                    "a: Select All",
                    "Enter: Confirm Fork",
                    "Esc / C-c .: Cancel",
                ]
                content = self._render_flow_nav_banner(items, sep_markup, sep_plain, avail_w)
            else:
                banner.remove_class("fork-active")
                sep_markup = f"[not bold {accent}]|[/]"
                sep_plain = "|"

                up_scroll = f"[bold {accent}]↑[/]" if self._nav_indicator_action == "scroll_up" else "↑"
                dn_scroll = f"[bold {accent}]↓[/]" if self._nav_indicator_action == "scroll_down" else "↓"
                up_page = f"[bold {accent}]↑[/]" if self._nav_indicator_action == "page_up" else "↑"
                dn_page = f"[bold {accent}]↓[/]" if self._nav_indicator_action == "page_down" else "↓"

                items = [
                    f"{up_scroll}/{dn_scroll}: Scroll",
                    f"Shift+{up_page}/{dn_page}: Viewport",
                    "PgUp/PgDn: Cards",
                    "Home/End: Edge",
                    "M-n/M-p: Snippets",
                    "C-c m: Mind",
                    "C-c .: Fork",
                ]
                content = self._render_flow_nav_banner(items, sep_markup, sep_plain, avail_w)

            banner.update(content)
        except Exception:
            pass

    def on_resize(self, event: events.Resize) -> None:
        is_mobile = event.size.width <= MOBILE_BREAKPOINT
        if self.screen:
            self.screen.set_class(is_mobile, "-mobile")
        self.call_after_refresh(self.update_feed_nav_banner)

    def on_app_focus(self) -> None:
        try:
            target = self.query_one(f"#{self._last_focused_input_id}")
            if target and target.is_mounted and target.can_focus:
                target.focus()
        except Exception:
            pass

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        w = event.widget
        wid = getattr(w, "id", None)
        if wid in ("input", "snippet_preview"):
            self._last_non_notes_input_id = wid
        if wid in ("input", "notes_editor", "snippet_preview"):
            self._last_focused_input_id = wid

    def on_key(self, event: events.Key) -> None:
        key_name = event.key.lower()

        if self.lock.is_locked:
            if key_name in GATED_NAV_KEYS:
                event.prevent_default()
                event.stop()
                return

        if self.intercept_c_c_key(event):
            return

    def set_feed_title(self, title: str) -> None:
        """Sets the active work title displayed on the feed border."""
        clean = title.strip().replace("\n", " ")
        if len(clean) > 70:
            clean = clean[:67] + "..."
        self.active_task_title = clean
        self.current_gemini_state = clean
        self.update_feed_title()

    def update_feed_title(self) -> None:
        """Dynamically updates the feed border title based on current work Gemini is doing."""
        try:
            feed = self.query_one("#feed", FeedArea)
            work_desc = (getattr(self, "active_task_title", "") or self.current_gemini_state or "").strip()
            if work_desc and work_desc not in ("Legacy active session.", "None"):
                clean_work = work_desc.replace("\n", " ").strip()
                if len(clean_work) > 65:
                    clean_work = clean_work[:62] + "..."
                feed.border_title = f" ⚡ {clean_work} "
            else:
                feed.border_title = " ⚡ Unified Console: Bilateral Mind & Notes Engine "
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            yield Static("▲ Loading messages...", id="feed_loader_banner")
            with Horizontal(id="middle_split"):
                yield FeedArea(id="feed")
                yield NotesPanel()
            yield Static("", id="feed_status")
            yield Static("", id="feed_nav_banner")
            yield SnippetPreview(id="snippet_preview")
            yield ExpandingInput(id="input")
        with Horizontal(id="custom_footer"):
            yield Static("[bold red]^q:[/] [white]quit[/]", id="footer_quit")
            yield Static("[red]|[/]", id="footer_sep")
            yield Static("[bold red]^c + c:[/] [white]commands[/]", id="footer_commands")

    @on(events.Click, "#footer_quit")
    def on_footer_quit_click(self) -> None:
        self.action_quit()

    @on(events.Click, "#footer_commands")
    def on_footer_commands_click(self) -> None:
        self.action_open_commands_modal()

    async def on_mount(self) -> None:
        cleanup_stale_ephemerals()
        saved_theme = self._read_theme_from_state()
        self.set_theme(saved_theme, notify_user=False)

        self.global_notes = self._read_global_notes_from_state()

        if self.size and self.size.width <= MOBILE_BREAKPOINT and self.screen:
            self.screen.add_class("-mobile")

        await self.start_socket_server()
        self.push_screen(BootScreen())
        self.call_after_refresh(self._initial_startup_load)

    async def _initial_startup_load(self) -> None:
        mark_startup_successful()
        last_active_id = self._read_active_chat_from_state()

        if last_active_id and (self._get_legacy_chat_file(last_active_id).exists() or self._get_chat_dir(last_active_id).exists()):
            # Read prior session meta & mind map to boot directly into our cognitive anchors
            legacy_file = self._get_legacy_chat_file(last_active_id)
            chat_dir = self._get_chat_dir(last_active_id)
            prev_meta = {}
            if legacy_file.exists():
                try:
                    prev_meta = json.loads(legacy_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            elif chat_dir.is_dir() and (chat_dir / "meta.json").exists():
                try:
                    prev_meta = json.loads((chat_dir / "meta.json").read_text(encoding="utf-8"))
                except Exception:
                    pass

            notes_raw = prev_meta.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.global_notes = ""
            self.relational_notes = {}
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)

            mind_map = prev_meta.get("mind_map", {})
            if mind_map:
                self.current_gemini_state = mind_map.get("gemini_state") or self.current_gemini_state
                self.current_user_state = mind_map.get("user_state") or self.current_user_state
                self.current_tree_state = mind_map.get("tree_state") or self.current_tree_state
                self.current_tree_content = mind_map.get("tree_content") or self.current_tree_content
                self.active_task_title = prev_meta.get("title") or self.current_gemini_state

            # Start fresh chat session for this boot while tracking lineage
            self._start_new_chat(title="", parent_id=last_active_id)
        else:
            files = self._get_all_chat_entries()
            if files:
                first_id = files[0]["id"]
                self._start_new_chat(title="", parent_id=first_id)
            else:
                self._start_new_chat(title="")

        self.update_feed_nav_banner()
        self.update_feed_title()
        self._update_footer_markup()
        self.query_one("#input").focus()

        # Background index all historical chats into SQLite FTS5 Memory Index
        asyncio.create_task(asyncio.to_thread(self.memory_index.index_all_existing_chats))

        reboot_report = self._read_and_clear_reboot_report()
        if reboot_report:
            snap_idx = 1
            try:
                snap_entry = capture_ui_snapshot(
                    self,
                    label="post_reboot_audit",
                    taken_by="gemini",
                    source="command",
                    persistent=True,
                )
                snap_idx = snap_entry.get("index", 1)
                self.notify(
                    f"📸 Snapshot #{snap_idx} captured: Post-reboot visual layout audited.",
                    title="Visual Audit",
                    timeout=4.0,
                )
            except Exception:
                pass
            self.set_timer(0.4, lambda: self.notify(reboot_report, title="Update Notes", timeout=8.0))
            def _post_boot_notify(idx=snap_idx, rep=reboot_report):
                self.notify(
                    f"📸 Snapshot #{idx} captured: Post-reboot visual layout audited.",
                    title="Visual Audit",
                    timeout=4.0,
                )
                self.set_timer(0.4, lambda: self.notify(rep, title="Update Notes", timeout=8.0))
            self.set_timer(2.1, _post_boot_notify)

    def show_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            banner.update("▲ Loading messages...")
            banner.styles.display = "block"
            banner.refresh(layout=True)
        except Exception:
            pass

    def hide_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            banner.styles.display = "none"
        except Exception:
            pass

    def set_status_text(self, text: str) -> None:
        try:
            status_lbl = self.query_one("#feed_status", Static)
            status_lbl.update(text)
            status_lbl.styles.display = "block"
        except Exception:
            pass

    def hide_status(self) -> None:
        try:
            status_lbl = self.query_one("#feed_status", Static)
            status_lbl.update("")
            status_lbl.styles.display = "none"
        except Exception:
            pass

    def _start_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
        self._request_start_time = time.monotonic()
        self._spinner_idx = 0
        self._tick_status()
        self._status_timer = self.set_interval(0.1, self._tick_status)

    def _stop_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None
        self._request_phase = "idle"
        self._request_details = ""

    def _tick_status(self) -> None:
        if self._request_phase == "idle":
            return

        elapsed = time.monotonic() - self._request_start_time
        frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
        self._spinner_idx += 1

        if self._request_details:
            status_text = f"{frame} {self._request_details}... ({elapsed:.1f}s)"
        elif self._request_phase == "reconnecting":
            status_text = f"{frame} {self._request_details or 'Quota limit reached — reconnecting silently'}... ({elapsed:.1f}s)"
        elif self._request_phase == "connecting":
            status_text = f"{frame} Connecting / Sending request... ({elapsed:.1f}s)"
        elif self._request_phase == "waiting":
            status_text = f"{frame} Waiting on Gemini response... ({elapsed:.1f}s)"
        elif self._request_phase == "probing":
            status_text = f"{frame} AI Mind Expanding (Seeking context & tools)... ({elapsed:.1f}s)"
        else:
            status_text = f"{frame} Working... ({elapsed:.1f}s)"

        self.set_status_text(status_text)

    @on(RequestPhaseUpdate)
    def on_request_phase_update(self, event: RequestPhaseUpdate) -> None:
        self._request_phase = event.phase
        self._request_details = getattr(event, "details", "") or ""
        self._tick_status()

    @on(MindMapRecalibrated)
    def on_mind_map_recalibrated(self, event: MindMapRecalibrated) -> None:
        self.current_gemini_state = event.gemini_state
        self.current_user_state = event.user_state
        self.current_tree_content = event.tree_content
        self.current_tree_state = event.tree_state
        self.save_current_chat()
        self.update_feed_title()

        try:
            self.memory_index.save_mind_map(
                chat_id=self.current_chat_id,
                gemini_state=event.gemini_state,
                user_state=event.user_state,
                tree_state=event.tree_state,
                tree_content=event.tree_content,
                active_task_title=getattr(self, "active_task_title", ""),
            )
        except Exception:
            pass

        # Update MindMapScreen if it is anywhere in the screen stack
        for sc in self.screen_stack:
            if isinstance(sc, MindMapScreen):
                sc.refresh_display()

    @on(RequestFinished)
    async def on_request_finished(self, event: RequestFinished) -> None:
        self._stop_status_ticker()

        feed = self.query_one("#feed", FeedArea)
        await feed.append_message("gemini", event.full_text, jump_to_start=True)

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        self.history.append({"turn_id": new_turn_id, "role": "model", "text": event.full_text})
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id
        self.save_current_chat()

        self.set_status_text(f"✓ Response complete ({event.words} words in {event.elapsed:.1f}s)")
        self.set_timer(1.2, self.hide_status)

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

    # -----------------------------------------------------------------------
    # Dual Storage Engine (Legacy Flat Files vs. Sharded Directories)
    # -----------------------------------------------------------------------

    def _get_legacy_chat_file(self, chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    def _get_chat_dir(self, chat_id: str) -> Path:
        return CHATS_DIR / chat_id

    def _get_all_chat_entries(self) -> list[dict]:
        entries: list[dict] = []

        # 1. New Sharded Directories
        for p in CHATS_DIR.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                meta_file = p / "meta.json"
                if meta_file.exists():
                    try:
                        m_data = json.loads(meta_file.read_text(encoding="utf-8"))
                        entries.append({
                            "id": m_data.get("id", p.name),
                            "title": m_data.get("title", p.name),
                            "parent_id": m_data.get("parent_id"),
                            "updated_at": m_data.get("updated_at", meta_file.stat().st_mtime),
                            "is_legacy": False,
                            "path": p,
                        })
                    except Exception:
                        pass

        # 2. Legacy Flat JSON Files
        for f in CHATS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                cid = data.get("id", f.stem)
                entries.append({
                    "id": cid,
                    "title": data.get("title", cid),
                    "parent_id": data.get("parent_id"),
                    "updated_at": data.get("updated_at", f.stat().st_mtime),
                    "is_legacy": True,
                    "path": f,
                })
            except Exception:
                pass

        entries.sort(key=lambda d: d.get("updated_at", 0), reverse=True)
        return entries

    def _direct_flush_chat_to_disk(self, chat_id: str, notes_payload: str | dict) -> None:
        if not chat_id:
            return

        chat_dir = self._get_chat_dir(chat_id)
        if chat_dir.is_dir():
            meta_path = chat_dir / "meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    data["notes"] = notes_payload
                    data["updated_at"] = time.time()
                    meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
            return

        legacy_path = self._get_legacy_chat_file(chat_id)
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
                data["notes"] = notes_payload
                data["updated_at"] = time.time()
                legacy_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

    def action_reboot(self, status_report: str | None = None) -> None:
        """Saves current state and notes cleanly, marks reboot safety flag, and execs the application process."""
        try:
            self.flush_current_notes()
            self._do_notes_flush()
            self.save_current_chat()
            if self.current_chat_id:
                self._save_to_state("active_chat", self.current_chat_id)
            report = status_report or "✓ Reboot complete: Console reloaded, session restored, UI operational."
            self._save_to_state("pending_reboot_report", report)
            mark_reboot_in_progress()
        except Exception:
            pass

        try:
            if hasattr(self, "_driver") and self._driver is not None:
                self._driver.stop_application_mode()
        except Exception:
            pass

        try:
            if self._server:
                self._server.close()
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink(missing_ok=True)
        except Exception:
            pass

        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)

    def _read_and_clear_reboot_report(self) -> str | None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                report = data.pop("pending_reboot_report", None)
                if report:
                    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    return report
            except Exception:
                pass
        return None

    def action_quit(self) -> None:
        self.flush_current_notes()
        self._do_notes_flush()
        self.save_current_chat()
        self.exit()

    def on_unmount(self) -> None:
        self._stop_status_ticker()
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None

        if self._nav_indicator_timer:
            self._nav_indicator_timer.stop()
            self._nav_indicator_timer = None

        self.flush_current_notes()
        self._do_notes_flush()
        self.save_current_chat()

        if self._server:
            self._server.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink(missing_ok=True)

    def _get_ancestor_lineage(self, parent_id: str | None) -> list[dict]:
        ancestors: list[dict] = []
        visited = set()
        curr_id = parent_id

        while curr_id and curr_id not in visited:
            visited.add(curr_id)

            p_dir = self._get_chat_dir(curr_id)
            p_file = self._get_legacy_chat_file(curr_id)

            p_data = {}
            if p_dir.is_dir() and (p_dir / "meta.json").exists():
                try:
                    p_data = json.loads((p_dir / "meta.json").read_text(encoding="utf-8"))
                except Exception:
                    break
            elif p_file.exists():
                try:
                    p_data = json.loads(p_file.read_text(encoding="utf-8"))
                except Exception:
                    break
            else:
                break

            notes_val = str(p_data.get("notes", "") or "").strip()
            if notes_val:
                ancestors.append({
                    "id": curr_id,
                    "title": p_data.get("title", curr_id),
                    "notes": notes_val,
                    "parent_id": p_data.get("parent_id"),
                })
            curr_id = p_data.get("parent_id")

        ancestors.reverse()
        for idx, anc in enumerate(ancestors):
            anc["depth"] = idx

        return ancestors

    def sync_notes_ui(self) -> None:
        try:
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.switch_mode(self.active_notes_mode)
        except Exception:
            pass

    def action_toggle_notes(self) -> None:
        if self.lock.is_locked or isinstance(self.screen, MindMapScreen):
            return
        self._toggle_notes_lockstep()

    @work(exclusive=True)
    async def _toggle_notes_lockstep(self) -> None:
        self.lock.acquire("dom_load")
        self.show_loader_banner()

        feed = self.query_one("#feed", FeedArea)
        notes_panel = self.query_one("#notes_panel", NotesPanel)

        target_snap = feed._get_center_raycast_target()
        opening = not self.notes_open
        self.notes_open = opening

        try:
            if opening:
                notes_panel.styles.display = "block"
                if self.screen:
                    self.screen.add_class("-notes-open")
                notes_panel.switch_mode(self.active_notes_mode)
            else:
                self.flush_current_notes()
                self._do_notes_flush()
                notes_panel.styles.display = "none"
                if self.screen:
                    self.screen.remove_class("-notes-open")

            settle_event = asyncio.Event()

            def _on_notes_toggle_settle() -> None:
                try:
                    feed._sync_header_map()
                    if target_snap:
                        t_idx, t_id, delta = target_snap
                        card = feed._get_target_widget(t_idx) or feed._get_target_widget_by_id(t_id)
                        if card:
                            feed._scroll_to_turn_widget(card, center=CENTER_SCREEN_MODE, line_offset=delta)

                    if opening:
                        try:
                            self.query_one("#notes_editor", NotesEditorArea).focus()
                        except Exception:
                            pass
                    else:
                        target_id = self._last_non_notes_input_id
                        if target_id == "snippet_preview":
                            try:
                                preview = self.query_one("#snippet_preview", SnippetPreview)
                                if preview.styles.display != "none":
                                    preview.focus()
                                else:
                                    self.query_one("#input", ExpandingInput).focus()
                            except Exception:
                                self.query_one("#input", ExpandingInput).focus()
                        else:
                            try:
                                self.query_one("#input", ExpandingInput).focus()
                            except Exception:
                                pass
                finally:
                    settle_event.set()

            self.call_after_refresh(_on_notes_toggle_settle)
            try:
                await asyncio.wait_for(settle_event.wait(), timeout=0.6)
            except asyncio.TimeoutError:
                feed._sync_header_map()

        finally:
            self.hide_loader_banner()
            self.lock.release("dom_load")

    def cycle_global_focus(self, direction: int = 1, escape_parents: bool = False) -> None:
        ring: list[Widget] = []

        try:
            input_widget = self.query_one("#input", ExpandingInput)
            snippet_widget = self.query_one("#snippet_preview", SnippetPreview)
            notes_panel = self.query_one("#notes_panel", NotesPanel)
        except Exception:
            return

        ring.append(input_widget)

        if self.notes_open:
            try:
                notes_editor = self.query_one("#notes_editor", NotesEditorArea)
                ring.append(notes_editor)
            except Exception:
                pass

        if snippet_widget.styles.display != "none":
            ring.append(snippet_widget)

        if len(ring) <= 1:
            if ring:
                ring[0].focus()
            return

        current_focused = self.focused
        curr_idx = -1
        for idx, w in enumerate(ring):
            if w is current_focused:
                curr_idx = idx
                break

        if curr_idx == -1:
            next_idx = 0 if direction > 0 else (len(ring) - 1)
        else:
            next_idx = (curr_idx + direction) % len(ring)

        target = ring[next_idx]
        target.focus()

    async def load_chat(self, chat_id: str) -> None:
        self._stop_status_ticker()
        self.hide_status()

        if self.current_chat_id and self.current_chat_id != chat_id:
            if self.active_notes_mode == "chat":
                self.flush_current_notes()
                self._direct_flush_chat_to_disk(self.current_chat_id, self.current_chat_notes)
                self.save_current_chat()

        self.current_chat_id = chat_id
        self._save_to_state("active_chat", chat_id)

        legacy_file = self._get_legacy_chat_file(chat_id)
        chat_dir = self._get_chat_dir(chat_id)

        saved_marker: str = ""
        saved_turn_idx: int | None = None

        if legacy_file.exists():
            # Legacy Single JSON File Mode
            self.is_legacy_chat = True
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
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
            
            notes_raw = data.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.relational_notes = {}
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)

            saved_marker = data.get("center_marker", "")
            saved_turn_idx = data.get("last_turn_index")

            self.active_task_title = "Unifying Notes System & Relational Anchors"
            self.current_gemini_state = "Unifying Notes System & Relational Anchors"
            self.current_user_state = "Collaborating in unified bilateral console session."
            self.current_tree_state = ["T100", "F:gemini_app/ui/widgets/notes.py", "F:gemini_app/ui/app.py"]
            self.current_tree_content = "└── Unified Console [Active]\n    ├── Notes System [Tri-modal: Gemini / Relational Turn / Global]\n    └── Feed Stream [Dynamic Task Title & 10-Card Lockstep]"

        elif chat_dir.is_dir() and (chat_dir / "meta.json").exists():
            # Modern Sharded Directory Mode
            self.is_legacy_chat = False
            meta_path = chat_dir / "meta.json"
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))

            self.current_chat_title = meta_data.get("title", "")
            self.current_chat_working_dir = meta_data.get("working_dir")
            self.current_chat_parent_id = meta_data.get("parent_id")

            notes_raw = meta_data.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.relational_notes = {}

            viewport = meta_data.get("viewport", {})
            saved_marker = viewport.get("center_marker", "")
            saved_turn_idx = viewport.get("last_turn_index")

            mind_map = meta_data.get("mind_map", {})
            gem_state = mind_map.get("gemini_state", "")
            if not gem_state or gem_state == "Legacy active session.":
                gem_state = "Unifying Notes System & Relational Anchors"
            self.active_task_title = gem_state
            self.current_gemini_state = gem_state
            self.current_user_state = mind_map.get("user_state", "") or "Collaborating in unified bilateral console session."
            self.current_tree_state = mind_map.get("tree_state", []) or ["T100", "F:gemini_app/ui/widgets/notes.py"]
            self.current_tree_content = mind_map.get("tree_content", "") or "└── Unified Stream [Active]"

            # Load message segments in order
            self.history = []
            segment_files = sorted(chat_dir.glob("segment_*.json"), key=lambda f: int(f.stem.split("_")[1]))
            for sf in segment_files:
                try:
                    seg_turns = json.loads(sf.read_text(encoding="utf-8"))
                    self.history.extend(seg_turns)
                except Exception:
                    pass
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)
        else:
            self.is_legacy_chat = False
            self.history = []
            self.current_chat_title = ""
            self.current_chat_working_dir = None
            self.current_chat_parent_id = None
            self.gemini_notes = ""
            self.relational_notes = {}
            self.current_chat_last_index = 0
            self.current_chat_center_marker = ""
            self.current_gemini_state = "Unified Console: Autonomous Relational Mind & Archival Engine"
            self.current_user_state = "Collaborating in unified bilateral console session."
            self.current_tree_state = ["T1", "F:gemini_app/"]
            self.current_tree_content = "└── Unified Stream [Active]"

        if saved_marker:
            self.current_chat_center_marker = saved_marker
        elif saved_turn_idx is not None and self.history:
            self.current_chat_last_index = max(0, min(len(self.history) - 1, saved_turn_idx))
            self.current_chat_center_marker = self.history[self.current_chat_last_index].get("turn_id", "")
        else:
            self.current_chat_last_index = max(0, len(self.history) - 1)
            self.current_chat_center_marker = self.history[-1].get("turn_id", "") if self.history else ""

        feed = self.query_one("#feed", FeedArea)
        if feed.styles.display == "none":
            feed.styles.display = "block"

        self.update_feed_title()

        marker_target = self.current_chat_center_marker or self.current_chat_last_index
        feed.set_messages(self.history, initial_target_marker=marker_target)

        notes_panel = self.query_one("#notes_panel", NotesPanel)
        notes_panel.clear_session_expansion_states()
        self.sync_notes_ui()

        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        self.update_feed_nav_banner()

    def save_current_chat(self) -> None:
        if not self.current_chat_id:
            return

        self.flush_current_notes()

        title = (getattr(self, "active_task_title", "") or self.current_chat_title or "Unified Stream").strip()
        self.current_chat_title = title
        self.update_feed_title()

        for m in self.history:
            if "turn_id" not in m or not m["turn_id"]:
                m["turn_id"] = f"turn_{uuid4().hex[:8]}"

        final_marker = self.current_chat_center_marker
        if final_marker.endswith(":+0") or final_marker.endswith(":-0"):
            final_marker = final_marker.split(":")[0] + ":0"
        elif not CENTER_SCREEN_MODE and ":" in final_marker:
            final_marker = final_marker.split(":")[0]

        notes_payload = {
            "gemini_notes": self.gemini_notes or "",
            "global_notes": self.global_notes or "",
            "relational_notes": self.relational_notes or {},
        }

        if self.is_legacy_chat:
            # Save strictly to legacy flat JSON file
            path = self._get_legacy_chat_file(self.current_chat_id)
            existing_data = {}
            if path.exists():
                try:
                    existing_data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing_data = {}

            data = {
                **existing_data,
                "id": self.current_chat_id,
                "title": self.current_chat_title,
                "parent_id": self.current_chat_parent_id,
                "updated_at": time.time(),
                "working_dir": self.current_chat_working_dir,
                "last_turn_index": self.current_chat_last_index,
                "center_marker": final_marker,
                "notes": notes_payload,
                "messages": self.history,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            # Save to Sharded Directory
            chat_dir = self._get_chat_dir(self.current_chat_id)
            chat_dir.mkdir(parents=True, exist_ok=True)

            total_turns = len(self.history)
            seg_count = max(1, (total_turns + TURNS_PER_SEGMENT - 1) // TURNS_PER_SEGMENT) if total_turns > 0 else 1
            active_seg = max(0, seg_count - 1)

            meta_data = {
                "id": self.current_chat_id,
                "title": self.current_chat_title,
                "parent_id": self.current_chat_parent_id,
                "updated_at": time.time(),
                "working_dir": self.current_chat_working_dir,
                "notes": notes_payload,
                "viewport": {
                    "last_turn_index": self.current_chat_last_index,
                    "center_marker": final_marker,
                },
                "storage": {
                    "total_turns": total_turns,
                    "segment_count": seg_count,
                    "active_segment": active_seg,
                    "max_segment_size": TURNS_PER_SEGMENT,
                },
                "mind_map": {
                    "gemini_state": self.current_gemini_state,
                    "user_state": self.current_user_state,
                    "tree_state": self.current_tree_state,
                    "tree_content": self.current_tree_content,
                },
            }
            (chat_dir / "meta.json").write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

            # Write segments of 200 turns
            for s_idx in range(seg_count):
                start = s_idx * TURNS_PER_SEGMENT
                end = start + TURNS_PER_SEGMENT
                seg_slice = self.history[start:end]
                seg_file = chat_dir / f"segment_{s_idx}.json"
                seg_file.write_text(json.dumps(seg_slice, indent=2), encoding="utf-8")

        self._save_to_state("active_chat", self.current_chat_id)

        # Incrementally index newly added turns into SQLite FTS5 Memory Index
        if self.history:
            last_turn = self.history[-1]
            try:
                self.memory_index.index_turn(
                    turn_id=last_turn.get("turn_id", ""),
                    chat_id=self.current_chat_id,
                    turn_number=len(self.history),
                    role=last_turn.get("role", "user"),
                    content=last_turn.get("text", ""),
                    project_dir=self.current_chat_working_dir,
                    title=self.current_chat_title,
                )
            except Exception:
                pass

    def action_fork_chat(self) -> None:
        feed = self.query_one("#feed", FeedArea)

        if not feed.fork_ui_active:
            feed.toggle_fork_ui()
            self.update_feed_nav_banner()
            self.notify("Fork selection active: Space toggles, 'a' selects all, Enter confirms, Esc / C-c .: Cancel.", timeout=3.5)
            return

        feed.toggle_fork_ui()
        self.update_feed_nav_banner()
        self.notify("Exited fork mode")

    def action_confirm_fork(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        if not feed.fork_ui_active:
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

        self.flush_current_notes()
        self._direct_flush_chat_to_disk(self.current_chat_id, self.current_chat_notes)
        self.save_current_chat()

        parent_chat_id = self.current_chat_id
        parent_working_dir = self.current_chat_working_dir
        new_chat_id = uuid4().hex[:8]

        self.is_legacy_chat = False
        self.current_chat_id = new_chat_id
        self.current_chat_title = fork_title
        self.current_chat_parent_id = parent_chat_id
        self.current_chat_working_dir = parent_working_dir
        self.current_chat_last_index = 0
        self.current_chat_center_marker = selected_turns[0].get("turn_id", "")
        self.current_chat_notes = ""
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

        self.update_feed_title()

        notes_panel = self.query_one("#notes_panel", NotesPanel)
        notes_panel.clear_session_expansion_states()
        self.sync_notes_ui()

        input_widget.focus()
        self.update_feed_nav_banner()
        self.notify(f"Fork created: '{self.current_chat_title}' (Awaiting response)", timeout=4.0)

    def _start_new_chat(self, title: str, parent_id: str | None = None) -> None:
        self._stop_status_ticker()
        self.hide_status()

        self.flush_current_notes()
        self.save_current_chat()

        self.is_legacy_chat = False
        self.active_notes_mode = "gemini"

        self.current_chat_id = uuid4().hex[:8]
        self.current_chat_title = title or "Unified Stream"
        self.current_chat_parent_id = parent_id
        self.current_chat_working_dir = None
        self.current_chat_last_index = 0
        self.current_chat_center_marker = ""
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        self.update_feed_title()

        notes_panel = self.query_one("#notes_panel", NotesPanel)
        notes_panel.clear_session_expansion_states()
        self.sync_notes_ui()

        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()
        self.update_feed_nav_banner()
        self.save_current_chat()

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
            fn_path = Path(os.path.expanduser(filename.strip()))
            if fn_path.is_absolute():
                target = fn_path.resolve()
            else:
                target = (base / fn_path).resolve()

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

    async def append_to_feed(self, sender: str, text: str, jump_to_start: bool = False) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.append_message(sender, text, jump_to_start=jump_to_start)

    def _handle_slash_command(self, raw_cmd: str) -> bool:
        """Handles client-side slash commands instantly without sending to API."""
        cmd = raw_cmd.lstrip("!").lstrip("/").strip()
        parts = cmd.split(None, 1)
        verb = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if verb in ("theme", "ui-theme"):
            if not arg:
                valid = ", ".join(THEMES.keys())
                self.notify(f"Active theme: '{self.active_palette_name}'. Options: {valid}", timeout=4.0)
                return True
            if self.set_theme(arg):
                self.notify(f"Theme switched to '{arg}'.", timeout=2.5)
            else:
                valid = ", ".join(THEMES.keys())
                self.notify(f"Unknown theme '{arg}'. Choose from: {valid}", severity="error")
            return True

        elif verb == "themes":
            all_themes = ", ".join(THEMES.keys())
            self.notify(f"Available themes: {all_themes} (Active: {self.active_palette_name})", timeout=5.0)
            return True

        elif verb in ("title", "task"):
            if not arg:
                curr = getattr(self, "active_task_title", "") or self.current_gemini_state
                self.notify(f"Current active work title: {curr}", timeout=3.5)
                return True
            self.set_feed_title(arg)
            self.notify(f"Feed active task title updated to: {arg}", timeout=2.5)
            return True

        elif verb == "diff":
            try:
                working_dir = self.get_effective_working_dir()
                stat = subprocess.run(["git", "diff", "--stat"], cwd=working_dir, capture_output=True, text=True, timeout=5)
                status = subprocess.run(["git", "status", "-s"], cwd=working_dir, capture_output=True, text=True, timeout=5)
                status_out = status.stdout.strip() or "No untracked or modified files."
                stat_out = stat.stdout.strip() or "No staged or unstaged diffs."
                output = (
                    f"### Working Tree Status\n```text\n{status_out}\n```\n\n"
                    f"### Diff Stat\n```text\n{stat_out}\n```"
                )
                self.call_after_refresh(lambda: self.append_to_feed("system", output, jump_to_start=False))
            except Exception as e:
                self.notify(f"Git diff error: {e}", severity="error")
            return True

        elif verb in ("recall", "memory"):
            if not arg:
                self.notify("Usage: /recall <search terms>", severity="warning")
                return True
            matches = self.memory_index.search(arg, limit=5)
            if not matches:
                self.notify(f"No memory matches for '{arg}'.", timeout=3.0)
            else:
                lines = [f"### Fast Memory Matches for '{arg}':"]
                for m in matches:
                    role_str = m.get("role", "user")
                    t_num = m.get("turn_number", 0)
                    t_title = m.get("title") or m.get("chat_id")
                    lines.append(f"- **Turn #{t_num}** ({role_str}) in *{t_title}*:\n  > {m.get('snippet')}")
                self.call_after_refresh(lambda: self.append_to_feed("system", "\n".join(lines), jump_to_start=False))
            return True

        elif verb in ("tokens", "stats"):
            total_words = sum(len(m.get("text", "").split()) for m in self.history)
            approx_tokens = int(total_words * 1.33)
            turns_count = len(self.history)
            self.notify(
                f"Session Stats: {turns_count} turns | ~{total_words} words (~{approx_tokens} tokens) | Model: {DEFAULT_MODEL}",
                timeout=4.5,
            )
            return True

        elif verb in ("snapshot", "snap"):
            label = arg.strip()
            self.action_take_snapshot(label=label, taken_by="user", source="command")
            return True

        elif verb in ("snapshots", "snaps"):
            held = list_held_snapshots(only_held=True)
            total = list_held_snapshots(only_held=False)
            if not total:
                self.notify("No snapshots recorded yet. Use C-c ` or /snapshot to capture one.", timeout=4.0)
            else:
                held_count = len(held)
                held_indices = ", ".join(f"#{e.get('index')}" for e in held) if held else "None"
                self.notify(
                    f"Snapshots: {len(total)} total, {held_count} held for Gemini review ({held_indices}).",
                    timeout=5.0,
                )
            return True

        elif verb in ("reboot", "restart"):
            report = arg if arg else None
            self.action_reboot(status_report=report)
            return True

        elif verb in ("rollback", "revert"):
            success, msg = perform_git_rollback()
            if success:
                self.notify("Rollback completed. Rebooting...", timeout=2.0)
                self.set_timer(1.0, lambda: self.action_reboot(status_report="✓ Rolled back to previous stable version."))
            else:
                self.notify(f"Rollback failed: {msg}", severity="error")
            return True

        elif verb in ("notes", "note"):
            if not arg or arg == "stats":
                archived_cnt = len(self.notes_manager.get_archived_notes())
                topics_cnt = len(self.notes_manager.get_all_topics())
                self.notify(
                    f"Notes: {len(self.notes_manager.notes)} total across {topics_cnt} topics | "
                    f"{len(self.notes_manager.get_notes_to_get_back_to())} action items | "
                    f"{len(self.notes_manager.get_notes_to_think_about())} brainstorms | "
                    f"{archived_cnt} archived",
                    timeout=5.0,
                )
                return True
            parts = arg.split(None, 1)
            sub = parts[0].lower()
            sub_arg = parts[1].strip() if len(parts) > 1 else ""

            if sub in ("prune", "dedup", "clean"):
                res = self.notes_manager.prune_notes()
                self.gemini_notes = self.notes_manager.working_notes
                self.schedule_notes_flush()
                try:
                    self.query_one("#notes_panel", NotesPanel).refresh_display()
                except Exception:
                    pass
                self.notify(
                    f"✓ Notes pruned: {res['duplicates_removed']} duplicate(s) removed, {res['empty_removed']} empty removed. {res['total_remaining']} remaining.",
                    timeout=4.0,
                )
                return True

            elif sub in ("archive",):
                if not sub_arg or sub_arg == "completed":
                    cnt = self.notes_manager.archive_completed_notes()
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Archived {cnt} completed note(s).", timeout=3.0)
                    return True
                ok = self.notes_manager.archive_note(sub_arg)
                if ok:
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Note matching '{sub_arg}' archived.", timeout=3.0)
                else:
                    self.notify(f"No active note found matching '{sub_arg}'.", severity="warning")
                return True

            elif sub in ("unarchive", "restore"):
                if not sub_arg:
                    self.notify("Usage: /notes unarchive <id or query>", severity="warning")
                    return True
                ok = self.notes_manager.unarchive_note(sub_arg)
                if ok:
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Restored note matching '{sub_arg}' from archive.", timeout=3.0)
                else:
                    self.notify(f"No archived note found matching '{sub_arg}'.", severity="warning")
                return True

            elif sub in ("archived", "archive_list"):
                archived = self.notes_manager.get_archived_notes()
                if not archived:
                    self.notify("No archived notes on record.", timeout=3.0)
                else:
                    lines = [f"### Archived Notes ({len(archived)}):"]
                    for a in archived:
                        lines.append(f"- **[{a.id}]** ({a.topic}): {a.content}")
                    self.call_after_refresh(lambda: self.append_to_feed("system", "\n".join(lines), jump_to_start=False))
                return True

            else:
                self.notify(f"Unknown notes action '{sub}'. Use: prune, archive, unarchive, stats.", severity="error")
                return True

        elif verb == "clear":
            self.history = []
            feed = self.query_one("#feed", FeedArea)
            feed.clear()
            self.save_current_chat()
            self.notify("Chat cleared.")
            return True

        elif verb == "help":
            help_text = (
                "### Console Slash Commands\n"
                "- `/theme <name>`: Switch color theme (e.g. `/theme amber`, `/theme hacker`)\n"
                "- `/themes`: List all available color themes\n"
                "- `/notes [prune|archive|unarchive|stats]`: Manage, prune, or archive notes\n"
                "- `/snapshot [label]`: Capture UI snapshot held for Gemini review\n"
                "- `/snapshots`: View count and list of held snapshots\n"
                "- `/diff`: Preview uncommitted git changes\n"
                "- `/tokens`: Inspect approximate token count and session stats\n"
                "- `/clear`: Clear active chat feed\n"
                "- `/reboot`: Perform a clean in-place app reboot\n"
                "- `/help`: Show this command reference"
            )
            self.call_after_refresh(lambda: self.append_to_feed("system", help_text, jump_to_start=False))
            return True

        return False

    async def on_expanding_input_submitted(self, event: ExpandingInput.Submitted) -> None:
        user_msg = event.value.strip()
        if not user_msg:
            return

        # Check for slash commands or !/ prefix commands
        if user_msg.startswith("/") or user_msg.startswith("!/"):
            if self._handle_slash_command(user_msg):
                return

        await self.append_to_feed(CURRENT_USER, user_msg, jump_to_start=False)

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        self.history.append({"turn_id": new_turn_id, "role": "user", "text": user_msg})
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id

        # Auto-scan submitted user message for topical notes
        if hasattr(self, "notes_manager"):
            self.notes_manager.scan_chat_for_notes([{"role": "user", "text": user_msg, "turn_id": new_turn_id}])
            self.gemini_notes = self.notes_manager.working_notes

        self.save_current_chat()

        self.ask_gemini()

    # -----------------------------------------------------------------------
    # Cognitive Expansion & Collision Engine
    # -----------------------------------------------------------------------

    def steer_mind_state(self, steer_prompt: str) -> None:
        self.ask_gemini(is_mind_steer=True, steer_instruction=steer_prompt)

    @work(exclusive=True, thread=True)
    def ask_gemini(self, is_mind_steer: bool = False, steer_instruction: str = "") -> None:
        chat_id_snapshot = self.current_chat_id
        working_dir_snapshot = self.get_effective_working_dir()

        def _begin_request():
            self._request_phase = "connecting"
            self._start_status_ticker()

        self.app.call_from_thread(_begin_request)
        start_time = time.monotonic()

        # 1. Initialize Bilateral Tools via ToolRegistry
        def _schedule_reboot(delay_seconds: float = 1.5, status_report: str = "") -> dict:
            delay = max(0.5, float(delay_seconds))
            report = status_report.strip() if status_report else "✓ Reboot complete: Console reloaded, session restored, UI operational."
            def _trigger():
                self.notify(f"Rebooting application in {delay:.1f}s...", timeout=delay)
                self.set_timer(delay, lambda: self.action_reboot(status_report=report))
            self.app.call_from_thread(_trigger)
            return {
                "status": "scheduled",
                "message": f"Console reboot scheduled in {delay:.1f} seconds. Active turn and state will be committed before restart."
            }

        def _schedule_snapshot(label: str = "") -> dict:
            entry = capture_ui_snapshot(
                self,
                label=label,
                taken_by="gemini",
                source="command" if label else "shortcut",
            )
            def _toast():
                idx = entry.get("index", 1)
                self.notify(f"Gemini captured UI snapshot #{idx} ({entry.get('id')})", timeout=3.5)
            self.app.call_from_thread(_toast)
            return {
                "status": "success",
                "snapshot_id": entry.get("id"),
                "index": entry.get("index"),
                "screen_name": entry.get("screen_name"),
                "timestamp": entry.get("timestamp"),
                "label": label,
                "persistent": entry.get("persistent", False),
                "svg_path": entry.get("svg_path"),
                "txt_path": entry.get("txt_path"),
                "message": f"Snapshot #{entry.get('index')} captured and held successfully on Gemini's end."
            }

        def _manage_notes(
            action: str = "get",
            topic: str = "",
            content: str = "",
            status: str = "working",
            turn_id: str = "",
            mode: str = "gemini",
        ) -> dict:
            act = (action or "get").lower().strip()
            mode_clean = (mode or "gemini").lower().strip()
            target_topic = (topic or getattr(self.notes_manager, "active_topic", "general") or "general").strip().lower()

            if act in ("set_title", "title") or mode_clean == "title":
                self.app.call_from_thread(self.set_feed_title, content)
                return {"status": "success", "message": f"Updated feed active task title to '{content}'."}

            if act in ("record", "add"):
                item = self.notes_manager.record_note(
                    content=content,
                    topic=target_topic,
                    status=status or "working",
                    author="gemini",
                    turn_id=turn_id,
                )
                self.gemini_notes = self.notes_manager.working_notes
                self.app.call_from_thread(self.schedule_notes_flush)
                return {
                    "status": "success",
                    "message": f"Recorded note under topic '{item.topic}' with status '{item.status}'.",
                    "note": item.to_dict(),
                }

            elif act in ("set_working", "working"):
                self.notes_manager.set_working_notes(content)
                self.gemini_notes = content
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": "Updated Gemini working notes."}

            elif act in ("think_about", "think"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_to_think_about()]
                return {"status": "success", "category": "think_about", "count": len(items), "notes": items}

            elif act in ("get_back_to", "get_back", "todo"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_to_get_back_to()]
                return {"status": "success", "category": "get_back_to", "count": len(items), "notes": items}

            elif act in ("relevant",):
                items = [n.to_dict() for n in self.notes_manager.get_relevant_notes(topic=target_topic)]
                return {"status": "success", "topic": target_topic, "count": len(items), "notes": items}

            elif act in ("topic", "by_topic"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_by_topic(target_topic)]
                return {"status": "success", "topic": target_topic, "count": len(items), "notes": items}

            elif act in ("scan_chat", "scan"):
                added = self.notes_manager.scan_chat_for_notes(self.history)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "scanned_turns": len(self.history), "added_count": len(added), "notes": [n.to_dict() for n in added]}

            elif act in ("set_topic",):
                self.notes_manager.set_current_topic(target_topic)
                return {"status": "success", "active_topic": self.notes_manager.active_topic}

            elif act in ("delete", "remove"):
                deleted = self.notes_manager.delete_note(content or turn_id)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success" if deleted else "not_found", "deleted": deleted}

            elif act in ("prune", "dedup", "deduplicate"):
                res = self.notes_manager.prune_notes()
                self.gemini_notes = self.notes_manager.working_notes
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": "Pruned notes and sanitized working notes.", "stats": res}

            elif act in ("archive",):
                if not content or content == "completed":
                    cnt = self.notes_manager.archive_completed_notes()
                else:
                    cnt = 1 if self.notes_manager.archive_note(content or turn_id) else 0
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "archived_count": cnt}

            elif act in ("unarchive", "restore"):
                ok = self.notes_manager.unarchive_note(content or turn_id)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success" if ok else "not_found", "unarchived": ok}

            elif act in ("archived",):
                items = [n.to_dict() for n in self.notes_manager.get_archived_notes()]
                return {"status": "success", "count": len(items), "notes": items}

            elif act == "set":
                if mode_clean == "global":
                    self.notes_manager.record_note(content=content, topic="global", status="reference", author="user")
                elif mode_clean == "turn":
                    tid = turn_id or self.current_focused_turn_id or (self.history[-1].get("turn_id") if self.history else "")
                    if tid:
                        self.notes_manager.record_note(content=content, topic=target_topic, status="working", turn_id=tid)
                else:  # gemini
                    self.notes_manager.set_working_notes(content)
                    self.gemini_notes = content
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": f"Updated {mode_clean} notes."}

            else:  # get
                if mode_clean == "global":
                    text = self.notes_manager.get_global_notes_text()
                elif mode_clean == "turn":
                    tid = turn_id or self.current_focused_turn_id or (self.history[-1].get("turn_id") if self.history else "")
                    text = self.notes_manager.get_relational_notes_dict().get(tid, "")
                else:
                    text = self.notes_manager.working_notes
                return {
                    "status": "success",
                    "mode": mode_clean,
                    "content": text,
                    "active_topic": self.notes_manager.active_topic,
                    "relevant_notes": [n.to_dict() for n in self.notes_manager.get_relevant_notes()],
                }

        tool_reg = ToolRegistry(
            working_dir=working_dir_snapshot,
            history=self.history,
            phase_callback=lambda p, d="": self.app.call_from_thread(self.post_message, RequestPhaseUpdate(p, d)),
            reboot_callback=_schedule_reboot,
            snapshot_callback=_schedule_snapshot,
            memory_index=self.memory_index,
            notes_callback=_manage_notes,
        )
        tools_list, available_tools = tool_reg.get_tool_callables()

        # 2. Build Wire Payload (User Mind State: Last 10 Turns with truncated snippets)
        # Window alignment: ensure we slice on an alternating role boundary
        slice_count = 10
        if len(self.history) > slice_count and self.history[-slice_count]["role"] == "model":
            slice_count = 11

        recent_turns = list(self.history[-slice_count:])

        if is_mind_steer:
            steer_block = {
                "turn_id": f"steer_{uuid4().hex[:8]}",
                "role": "user",
                "text": (
                    f"## SYSTEM COGNITIVE RECALIBRATION REQUEST\n"
                    f"The user has submitted an explicit steering course-correction:\n"
                    f"\"{steer_instruction}\"\n\n"
                    f"Re-evaluate the project trajectory. Update your GEMINI MIND STATE, "
                    f"the USER MIND STATE, the tree_state anchor list, and the visual tree."
                ),
            }
            recent_turns.append(steer_block)

        payload = []
        for t in recent_turns:
            wire_text = truncate_wire_snippets(t["text"], max_lines=MAX_SNIPPET_LINES_ON_WIRE)
            if payload and payload[-1]["role"] == t["role"]:
                payload[-1]["parts"][0]["text"] += "\n\n" + wire_text
            else:
                payload.append({"role": t["role"], "parts": [{"text": wire_text}]})

        if payload and payload[0]["role"] != "user":
            payload.insert(0, {"role": "user", "parts": [{"text": WIRE_CONTINUATION_PROMPT}]})

        # 3. System Instruction Packaging (Injecting Mind State & 4 Anchors)
        tree_state_str = ", ".join(str(x) for x in self.current_tree_state) if self.current_tree_state else "None"
        notes_summary = self.notes_manager.format_prompt_summary() if hasattr(self, "notes_manager") else ""
        system_instruction = (
            f"You are Gemini running inside a bilateral terminal console.\n"
            f"Working directory: {working_dir_snapshot}\n"
            f"Total conversation turns on record: {len(self.history)}\n\n"
            f"### CURRENT COGNITIVE MIND MAP (PERSISTENT ANCHORS)\n"
            f"• GEMINI MIND STATE: {self.current_gemini_state or 'None'}\n"
            f"• USER MIND STATE: {self.current_user_state or 'None'}\n"
            f"• TREE ANCHOR STATE: [{tree_state_str}]\n\n"
            f"### VISUAL RELATION TREE:\n"
            f"```text\n{self.current_tree_content or '└── *[Session Start]*'}\n```\n\n"
            f"### UNIFIED GEMINI-MANAGED NOTES CONTEXT\n"
            f"{notes_summary}\n\n"
            f"### NOTES & TOPIC PROTOCOL\n"
            f"• You autonomously manage all project notes, organized strictly by topics.\n"
            f"• Automatically scan chat turns and associate notes with their relevant topics.\n"
            f"• When the user places or submits a note, consume it and display your current working notes, or their notes if relevant in relation to your work.\n"
            f"• When the user asks about notes they should think about, notes to get back to, or notes related to a topic, answer directly from the notes context or use `manage_notes`.\n"
            f"• Autonomously bring up relevant notes when they connect to the current topic being discussed.\n"
            f"• Use `manage_notes(action='record', topic='...', content='...', status='working'|'think_about'|'get_back_to')` to record topical notes.\n\n"
            f"### EXPANSION CAPABILITIES\n"
            f"You have tools available to inspect the environment, write files, and execute commands:\n"
            f"1. `scan_workspace_tree(include_ignored=True)`: Survey directory structure and dependencies.\n"
            f"2. `expand_mind(turn_numbers=[...], file_paths=[...], turn_ids=[...])`: Pull up to 50 items (turns or files) into thought memory.\n"
            f"3. `recall_memory(query='...', max_results=10)`: Fast indexed retrieval across entire conversational history, archived projects, and past discussions.\n"
            f"4. `write_file(path='...', content='...')`: Write or overwrite a file directly on disk.\n"
            f"5. `apply_patch(path='...', search_block='...', replace_block='...')`: Apply a surgical unique find-and-replace patch.\n"
            f"6. `search_codebase(query='...', path_pattern='*', max_matches=50)`: Search workspace files for text or regex pattern.\n"
            f"7. `execute_shell(command='...', timeout_seconds=60)`: Run shell commands (e.g. tests, linters, python scripts).\n"
            f"8. `reboot_console(delay_seconds=1.5, status_report='...')`: Restarts the console application cleanly in place when requested by the user or following code updates.\n"
            f"9. `take_snapshot(label='...')`: Captures a live UI snapshot of the console application on Gemini's end, indexed and held.\n"
            f"10. `review_snapshots(snapshot_ids=[...], only_held=True, count=5)`: Reviews UI snapshots captured by the user or Gemini, returning reconstructed screen text and layout metadata.\n"
            f"11. `manage_notes(action='record'|'get'|'think_about'|'get_back_to'|'relevant'|'topic'|'scan_chat'|'set_working', topic='...', content='...', status='...', turn_id='...'): Access, record, and query Gemini-managed topical notes.\n\n"
            f"### UI SNAPSHOT RETENTION & VALIDATION PROTOCOL\n"
            f"• Snapshot Retention Rules:\n"
            f"  - Snapshots captured via command with a name (`/snapshot <name>`) are saved permanently to disk without deleting them.\n"
            f"  - Ephemeral snapshots captured via `C-c ` ` (or without a name) are deleted from both disk and memory index once reviewed.\n"
            f"• Code Update, Testing & Reboot Standard:\n"
            f"  - Whenever updating codebase or self, always run the full test suite (`python3 -m unittest discover -s gemini_app/tests`).\n"
            f"  - Commit updates locally to git with a descriptive commit message (do not push to main).\n"
            f"  - Trigger `reboot_console(delay_seconds=1.5, status_report='...')` automatically whenever code updates are applied.\n"
            f"  - Visual audits are strictly POST-reboot: upon startup, the app autonomously audits the live UI with a snapshot toast, followed immediately by the toast displaying the update notes / git commit.\n"
            f"• When the user mentions taking a snapshot (or snapshots) or asks you to review their screen/UI, invoke `review_snapshots(only_held=True)` to inspect the held UI text and layout, then provide detailed observations, bug analysis, or UI feedback.\n"
            f"• When making UI updates, refactoring widgets, or testing UI screens, you can autonomously call `take_snapshot(label='...')` to audit your changes.\n\n"
            f"### REQUIRED METADATA FOOTER\n"
            f"At the very end of your response, always output this exact JSON block fenced in json:mind_map\n"
            f"{{\n"
            f'  "gemini_state": "<Summary of technical direction and active sub-tasks>",\n'
            f'  "user_state": "<Summary of inferred user intent and immediate constraints>",\n'
            f'  "tree_state": ["T...", "F:..."],\n'
            f'  "tree_content": "<ASCII tree showing where current conversation and files connect>"\n'
            f"}}\n"
            f"```\n"
            f"If this is a recalibration request, confirm the course correction in your response."
        )

        try:
            self.app.call_from_thread(self.post_message, RequestPhaseUpdate("waiting"))

            # Build the SDK-compliant Content history list
            sdk_history: list[types.Content] = []
            for h in payload[:-1] if len(payload) > 1 else []:
                sdk_history.append(
                    types.Content(
                        role=h["role"],
                        parts=[types.Part.from_text(text=p["text"]) for p in h["parts"]],
                    )
                )

            # Start Chat Session with history pre-loaded properly
            chat_session = self.client.chats.create(
                model=DEFAULT_MODEL,
                history=sdk_history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools_list,
                    temperature=0.2,
                ),
            )

            # Helper for silent reconnection and resume on quota limit / ResourceExhausted
            def _send_with_silent_quota_retry(send_call: Callable[[], Any], max_retries: int = 5, base_delay: float = 3.0) -> Any:
                attempt = 0
                while True:
                    try:
                        return send_call()
                    except Exception as call_err:
                        err_text = str(call_err)
                        is_quota = (
                            "ResourceExhausted" in err_text
                            or "429" in err_text
                            or "quota" in err_text.lower()
                            or "rate limit" in err_text.lower()
                            or "resource has been exhausted" in err_text.lower()
                        )
                        if not is_quota or attempt >= max_retries:
                            raise call_err

                        attempt += 1
                        wait_sec = base_delay * (2 ** (attempt - 1))
                        for rem in range(int(wait_sec), 0, -1):
                            if self.current_chat_id != chat_id_snapshot:
                                return None
                            self.app.call_from_thread(
                                self.post_message,
                                RequestPhaseUpdate(
                                    "reconnecting",
                                    f"Quota reached — reconnecting silently in {rem}s (retry {attempt}/{max_retries})"
                                )
                            )
                            time.sleep(1.0)

                        if self.current_chat_id != chat_id_snapshot:
                            return None

                        self.app.call_from_thread(
                            self.post_message,
                            RequestPhaseUpdate("waiting", f"Reconnected — resuming where left off (attempt {attempt})")
                        )

            # Send the latest turn with silent quota retry
            first_user_content = payload[-1]["parts"][0]["text"] if payload else ""
            response = _send_with_silent_quota_retry(lambda: chat_session.send_message(first_user_content))
            if response is None:
                return

            # Tool Loop (Handling Autonomous Mind Expansions)
            tool_iterations = 0
            max_tool_iterations = 10
            while response.candidates and response.candidates[0].content.parts and tool_iterations < max_tool_iterations:
                part = response.candidates[0].content.parts[0]
                if part.function_call:
                    tool_iterations += 1
                    fn_name = part.function_call.name
                    fn_args = dict(part.function_call.args) if part.function_call.args else {}

                    self.app.call_from_thread(self.post_message, RequestPhaseUpdate("probing"))

                    # Execute local tool
                    if fn_name in available_tools:
                        try:
                            fn_result = available_tools[fn_name](**fn_args)
                        except Exception as tool_err:
                            fn_result = {"error": str(tool_err)}
                    else:
                        fn_result = {"error": f"Tool '{fn_name}' not recognized."}

                    # Transition status UI back to waiting before sending the tool result back across the wire
                    self.app.call_from_thread(self.post_message, RequestPhaseUpdate("waiting", "waiting on Gemini response"))

                    # Feed tool response back into the active thought process with silent quota retry
                    part_resp = types.Part.from_function_response(
                        name=fn_name,
                        response={"result": fn_result},
                    )
                    response = _send_with_silent_quota_retry(lambda: chat_session.send_message(part_resp))
                    if response is None:
                        return
                else:
                    break

            if self.current_chat_id != chat_id_snapshot:
                return

            raw_reply = response.text or ""

            # 4. Parse Cognitive Mind Map Footer
            gemini_state = self.current_gemini_state
            user_state = self.current_user_state
            tree_content = self.current_tree_content
            tree_state = self.current_tree_state

            # Match  at the end of the reply
            tag_open = chr(96) * 3 + "json:mind_map"
            tag_close = chr(96) * 3
            mind_block_pattern = re.compile(
                re.escape(tag_open) + r"\s*\n(.*?)\n" + re.escape(tag_close),
                re.DOTALL,
            )
            match = mind_block_pattern.search(raw_reply)

            clean_reply = raw_reply
            if match:
                json_str = match.group(1).strip()
                clean_reply = mind_block_pattern.sub("", raw_reply).rstrip()
                try:
                    meta_dict = json.loads(json_str)
                    gemini_state = meta_dict.get("gemini_state", gemini_state)
                    user_state = meta_dict.get("user_state", user_state)
                    tree_content = meta_dict.get("tree_content", tree_content)
                    tree_state = meta_dict.get("tree_state", tree_state)

                    self.app.call_from_thread(
                        self.post_message,
                        MindMapRecalibrated(
                            gemini_state=gemini_state,
                            user_state=user_state,
                            tree_content=tree_content,
                            tree_state=tree_state,
                        )
                    )
                except Exception:
                    pass

            elapsed = max(time.monotonic() - start_time, 0.1)
            total_words = len(clean_reply.split())

            # 5. Dispatch completion to UI
            if is_mind_steer:
                def _finalize_steer():
                    self._stop_status_ticker()
                    self.hide_status()
                    self.notify("Cognitive alignment complete. Mind map updated.", timeout=3.5)
                    # Re-refresh active screen if user is still on MindMapScreen
                    if isinstance(self.screen, MindMapScreen):
                        self.screen.refresh_display()

                self.app.call_from_thread(_finalize_steer)
            else:
                self.app.call_from_thread(
                    self.post_message, RequestFinished(clean_reply, elapsed, total_words)
                )
        except Exception as e:
            if self.current_chat_id != chat_id_snapshot:
                return
            err_str = str(e)
            if "ResourceExhausted" in err_str or "429" in err_str or "quota" in err_str.lower():
                user_msg = "API Quota Limit reached (ResourceExhausted). Please wait a moment before sending another prompt."
            else:
                user_msg = err_str

            def _handle_err():
                self._stop_status_ticker()
                self.hide_status()
                self.post_message(RequestFailed(user_msg))
            self.app.call_from_thread(_handle_err)
