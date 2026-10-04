"""Customized CommandPalette acting as the M-x Emacs-style menu."""

from textual.command import CommandPalette
from textual.widgets import Input


class MenuPalette(CommandPalette):

    def on_mount(self) -> None:
        super().on_mount()
        try:
            palette_input = self.query_one("CommandInput", Input)
            palette_input.placeholder = "Menu (M-x)..."
        except Exception:
            pass
