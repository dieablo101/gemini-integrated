"""Text area components: EmacsBaseTextArea, SnippetPreview, and ExpandingInput."""

from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING

import pyperclip
from textual import events, on
from textual.message import Message
from textual.widgets import TextArea
from textual.widgets.text_area import Selection

from gemini_app.config import GATED_NAV_KEYS
from gemini_app.events import RemoteInsert
from gemini_app.ui.widgets.feed import FeedArea

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp

class EmacsBaseTextArea(TextArea):
    def on_mount(self) -> None:
        self.soft_wrap = True
        self._mark_point: tuple[int, int] | None = None

    def undo(self) -> None:
        try:
            if hasattr(self, "history") and self.history._undo_stack:
                next_batch = self.history._undo_stack[-1]
                if next_batch:
                    target_loc = next_batch[0].from_location
                    self.move_cursor(target_loc, select=False)

            super().undo()
        except Exception:
            try:
                max_lines = max(1, self.document.line_count)
                safe_row = max(0, min(self.cursor_location[0], max_lines - 1))
                line_len = len(self.document.get_line(safe_row)) if safe_row < max_lines else 0
                safe_col = max(0, min(self.cursor_location[1], line_len))
                self.move_cursor((safe_row, safe_col), select=False)
                if hasattr(self, "_rewrap_and_refresh_virtual_size"):
                    self._rewrap_and_refresh_virtual_size()
            except Exception:
                pass

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

        if event.key == "ctrl+f":
            event.prevent_default(); event.stop()
            self.action_cursor_right(select=is_selecting)
            self._sync_selection()
            return
        elif event.key == "ctrl+b":
            event.prevent_default(); event.stop()
            self.action_cursor_left(select=is_selecting)
            self._sync_selection()
            return
        elif event.key == "ctrl+n":
            event.prevent_default(); event.stop()
            self.action_cursor_down(select=is_selecting)
            self._sync_selection()
            return
        elif event.key == "ctrl+p":
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
        elif event.key == "ctrl+v":
            event.prevent_default(); event.stop()
            self.action_cursor_page_down()
            self._sync_selection()
            return
        elif event.key in ("alt+v", "meta+v"):
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
    can_focus = True

    def __init__(self, **kwargs) -> None:
        kwargs["show_line_numbers"] = True
        super().__init__(**kwargs)
        self.active_tag: str = ""
        self._last_nav_time: float = 0.0
        self._nav_cooldown: float = 0.022

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

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        if event.key in ("tab", "shift+tab"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            self.app.cycle_global_focus(direction=direction)
            return

        feed = self.app.query_one("#feed", FeedArea)

        if event.key == "ctrl+q":
            event.prevent_default(); event.stop()
            self.app.action_quit()
            return

        now = time.monotonic()
        if event.key in ("down", "up", "shift+up", "shift+down"):
            if now - self._last_nav_time < self._nav_cooldown:
                event.prevent_default(); event.stop()
                return
            self._last_nav_time = now

        if event.key in ("shift+up", "shift+down"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+up" else 1
            feed.viewport_page_navigate(direction)
            return
        elif event.key == "down":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(1)
            return
        elif event.key == "up":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(-1)
            return
        elif event.key == "pagedown":
            event.prevent_default(); event.stop()
            feed.step_card(1)
            return
        elif event.key == "pageup":
            event.prevent_default(); event.stop()
            feed.step_card(-1)
            return
        elif event.key in ("alt+n", "meta+n"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(1)
            return
        elif event.key in ("alt+p", "meta+p"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(-1)
            return
        elif event.key == "home":
            event.prevent_default(); event.stop()
            feed.jump_to_home()
            return
        elif event.key == "end":
            event.prevent_default(); event.stop()
            feed.jump_to_end()
            return

        if event.key in ("shift+enter", "shift+return", "ctrl+j"):
            event.prevent_default(); event.stop()
            self.insert("\n")
            return

        if event.key in ("escape", "ctrl+g"):
            event.prevent_default(); event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.query_one("#input", ExpandingInput).focus()
            return

        super()._on_key(event)


class ExpandingInput(EmacsBaseTextArea):
    can_focus = True

    class Submitted(Message):
        def __init__(self, value: str, input: ExpandingInput | None = None) -> None:
            super().__init__()
            self.value = value
            self._input = input

        @property
        def control(self) -> ExpandingInput | None:
            return self._input or getattr(self, "_sender", None)

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
        if self.app.intercept_c_c_key(event):
            return

        feed = self.app.query_one("#feed", FeedArea)
        fork_active = feed.fork_ui_active

        if event.key in ("tab", "shift+tab"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            self.app.cycle_global_focus(direction=direction)
            return

        # Fast filter shortcuts: Alt+1..6 when in notes_input or notes_panel is open
        if self.id == "notes_input" or (getattr(self.app, "notes_open", False)):
            if event.key in ("alt+1", "meta+1"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("working")
                except Exception:
                    pass
                return
            elif event.key in ("alt+2", "meta+2"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("relevant")
                except Exception:
                    pass
                return
            elif event.key in ("alt+3", "meta+3"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("get_back_to")
                except Exception:
                    pass
                return
            elif event.key in ("alt+4", "meta+4"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("think_about")
                except Exception:
                    pass
                return
            elif event.key in ("alt+5", "meta+5"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("topics")
                except Exception:
                    pass
                return
            elif event.key in ("alt+6", "meta+6"):
                event.prevent_default(); event.stop()
                try:
                    self.app.query_one("#notes_panel").switch_filter("archived")
                except Exception:
                    pass
                return

        if self.id == "notes_input":
            if event.key in ("ctrl+g", "escape"):
                event.prevent_default(); event.stop()
                if self._mark_point is not None or self.selected_text:
                    self._clear_mark()
                    self.app.notify("Quit", timeout=1.0)
                else:
                    self.app.action_toggle_notes()
                return

        if event.key == "ctrl+q":
            event.prevent_default(); event.stop()
            self.app.action_quit()
            return

        now = time.monotonic()
        if event.key in ("down", "up", "shift+up", "shift+down"):
            if now - self._last_nav_time < self._nav_cooldown:
                event.prevent_default(); event.stop()
                return
            self._last_nav_time = now

        if event.key in ("shift+up", "shift+down"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+up" else 1
            feed.viewport_page_navigate(direction)
            return
        elif event.key == "down":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(1)
            return
        elif event.key == "up":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(-1)
            return
        elif event.key == "pagedown":
            event.prevent_default(); event.stop()
            feed.step_card(1)
            return
        elif event.key == "pageup":
            event.prevent_default(); event.stop()
            feed.step_card(-1)
            return
        elif event.key in ("alt+n", "meta+n"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(1)
            return
        elif event.key in ("alt+p", "meta+p"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(-1)
            return
        elif event.key == "home":
            event.prevent_default(); event.stop()
            feed.jump_to_home()
            return
        elif event.key == "end":
            event.prevent_default(); event.stop()
            feed.jump_to_end()
            return

        if fork_active:
            if event.key in ("escape", "ctrl+g"):
                event.prevent_default(); event.stop()
                feed.toggle_fork_ui()
                self.app.update_feed_nav_banner()
                self.app.notify("Exited fork mode")
                return

            if event.key == "space":
                event.prevent_default(); event.stop()
                feed.toggle_current_card_selection()
                return

            if event.key == "a":
                event.prevent_default(); event.stop()
                feed.toggle_all_fork_checkboxes()
                return

            if event.key in ("enter", "return"):
                event.prevent_default(); event.stop()
                self.app.action_confirm_fork()
                return

            event.prevent_default(); event.stop()
            return

        if event.key in ("shift+enter", "shift+return", "ctrl+j", "alt+enter", "meta+enter"):
            event.prevent_default(); event.stop()
            self.action_newline()
            return
        elif event.key in ("enter", "return"):
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

        if raw_text.startswith("!/"):
            self.app.execute_command(raw_text)
            self.clear()
            self.reset_snippets()
            self._clear_mark()
            self.call_after_refresh(self._update_layout)
            self.app.query_one("#snippet_preview", SnippetPreview).hide_preview()
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

        self.post_message(self.Submitted(resolved_text, input=self))
        self.clear()
        self.reset_snippets()
        self._clear_mark()
        self.call_after_refresh(self._update_layout)

        self.app.query_one("#snippet_preview", SnippetPreview).hide_preview()

# ---------------------------------------------------------------------------
# Dedicated Mind Map Screen (Bilateral Cognition & Steering Console)
# ---------------------------------------------------------------------------

