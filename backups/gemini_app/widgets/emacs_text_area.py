"""Base TextArea with standard Emacs keys, cursor selection synchronization, and clipboard."""

import pyperclip
from textual import events
from textual.widgets import TextArea
from textual.widgets.text_area import Selection


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
