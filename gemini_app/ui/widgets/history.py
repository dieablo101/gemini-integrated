"""History list widget providing keyboard-driven chat session selection, renaming, and deletion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import events
from textual.widgets import OptionList

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp


class HistoryList(OptionList):
    """Drawer list displaying saved chat sessions with Emacs/Vim navigation keys."""

    async def _on_key(self, event: events.Key) -> None:
        if hasattr(self.app, "intercept_c_c_key") and self.app.intercept_c_c_key(event):
            return

        if event.key in ("tab", "shift+tab"):
            event.prevent_default()
            event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            if hasattr(self.app, "cycle_global_focus"):
                self.app.cycle_global_focus(direction=direction)
            return

        if event.key in ("escape", "ctrl+g", "q"):
            event.prevent_default()
            event.stop()
            if hasattr(self.app, "action_toggle_history"):
                self.app.action_toggle_history()
        elif event.key in ("delete", "backspace", "d", "x"):
            event.prevent_default()
            event.stop()
            if hasattr(self.app, "delete_highlighted_chat"):
                await self.app.delete_highlighted_chat()
        elif event.key in ("r",):
            event.prevent_default()
            event.stop()
            if hasattr(self.app, "rename_highlighted_chat"):
                self.app.rename_highlighted_chat()
        elif event.key in ("k", "ctrl+p", "up"):
            event.prevent_default()
            event.stop()
            self.action_cursor_up()
        elif event.key in ("j", "ctrl+n", "down"):
            event.prevent_default()
            event.stop()
            self.action_cursor_down()
        else:
            super()._on_key(event)
