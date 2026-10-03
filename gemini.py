#!/opt/gemini/.venv/bin/python3

import asyncio
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
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, Markdown, OptionList, TextArea
from textual.widgets.markdown import MarkdownFence
from textual.widgets.option_list import Option
from textual.widgets.text_area import Selection

CHATS_DIR = Path("chats")
CHATS_DIR.mkdir(exist_ok=True)
SOCKET_PATH = Path("/tmp/gemini_textual.sock")

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

        # Scan previous siblings for snippet line metadata: (Lines 123-145)
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
        event.stop()  # Stop event from bubbling up to ChatApp history handler
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
        self.call_after_refresh(self._update_layout)
        return tag, current_num

    def reset_snippets(self) -> None:
        self._snippets.clear()
        self._snippet_counter = 1

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

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.call_after_refresh(self._update_layout)

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

class FeedArea(Markdown):
    """Feed Markdown viewer with code snippet navigation and touch selection."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._raw_markdown = ""
        self.selected_snippet_index: int = -1

    def clear(self) -> None:
        self._raw_markdown = ""
        self.selected_snippet_index = -1
        self.update("")

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)

    async def set_messages(self, messages: list[dict]) -> None:
        blocks = []
        for turn in messages:
            label = "You" if turn["role"] == "user" else "Gemini"
            blocks.append(f"### {label}\n\n{turn['text']}")
        self._raw_markdown = "\n\n---\n\n".join(blocks)
        self.selected_snippet_index = -1
        await self.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    async def append_message(self, sender: str, text: str) -> None:
        prefix = "\n\n---\n\n" if self._raw_markdown else ""
        header = f"### {sender}\n\n"
        self._raw_markdown += f"{prefix}{header}{text}"
        await self.update(self._raw_markdown)
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
        return None

    @on(events.Click)
    def _on_feed_click(self, event: events.Click) -> None:
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
        if self.app.handle_c_c_prefix(event):
            return

        if event.key == "ctrl+c":
            event.prevent_default(); event.stop()
            self.app.set_c_c_prefix()
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
        Binding("ctrl+y", "copy_last_response", "C-c y (Yank/Emacs)", show=True),
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
        self.history: list[dict] = []
        self._server: asyncio.AbstractServer | None = None
        self._prefix_c_c: bool = False

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        self._prefix_c_c = True
        self.notify("C-c-", timeout=1.5)

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
        elif event.key in ("ctrl+t", "t"):
            event.prevent_default(); event.stop()
            self.action_rename_chat()
            return True
        elif event.key in ("ctrl+c", "ctrl+g", "escape"):
            event.prevent_default(); event.stop()
            self.notify("Quit", timeout=1.0)
            return True

        return False

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
        history_widget = self.query_one("#history", HistoryList)
        history_widget.clear_options()

        files = self._get_sorted_files()
        for idx, f in enumerate(files):
            try:
                data = json.loads(f.read_text())
                title = data.get("title", f.stem)
                active = " (Active)" if data["id"] == self.current_chat_id else ""
                history_widget.add_option(
                    Option(prompt=f"{idx + 1}. {title}{active}", id=data["id"])
                )
            except Exception:
                continue

    async def load_chat(self, chat_id: str) -> None:
        self.current_chat_id = chat_id
        path = self._get_chat_file(chat_id)
        if path.exists():
            data = json.loads(path.read_text())
            self.history = data.get("messages", [])
            self.current_chat_title = data.get("title", "")
        else:
            self.history = []
            self.current_chat_title = ""

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
            "updated_at": time.time(),
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

    def action_toggle_focus(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        preview_box = self.query_one("#snippet_preview", SnippetPreview)
        input_widget = self.query_one("#input", ExpandingInput)

        if feed.has_focus:
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
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()

    def _get_emacs_frames(self) -> list[dict]:
        """Queries Emacs for active frames and their open windows."""
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
        """Injects text into target buffer, or active window if None."""
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

        # If only 1 frame is open, ignore window splits and paste into cursor location
        if len(frames) <= 1:
            success = self._send_to_emacs_buffer(text_to_send)
            if success:
                self.notify("Yanked & sent to active Emacs window")
            else:
                self.notify("Yanked to clipboard")
            return

        # More than 1 frame open: show hierarchical selection modal
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
        payload = [
            {"role": t["role"], "parts": [{"text": t["text"]}]}
            for t in self.history
        ]

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
