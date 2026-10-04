"""OptionList with Vim/Emacs navigation, instant deletion, and renaming."""

from textual import events
from textual.widgets import OptionList


class HistoryList(OptionList):

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
