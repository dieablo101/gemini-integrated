"""Confirmation dialog modal."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label

from gemini_app.ui.modals.base import ResponsiveModalScreen


class ConfirmModal(ResponsiveModalScreen[bool]):
    """Modal prompting the user for a Yes/No boolean decision."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #confirm_dialog {
        padding: 1 2;
        width: 50;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #confirm_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        text-align: center;
        width: 100%;
        height: auto;
        color: #ffffff;
        text-wrap: wrap;
    }
    #confirm_buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
    }
    #confirm_buttons Button {
        margin: 0 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    ConfirmModal.-mobile #confirm_dialog {
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
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    def __init__(self, message: str = "File already exists. Overwrite?") -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="confirm_dialog"):
            yield Label(self.message)
            with Horizontal(id="confirm_buttons"):
                yield Button("No", id="no_btn")
                yield Button("Yes", id="yes_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#no_btn", Button).focus()

    @on(Button.Pressed, "#yes_btn")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no_btn")
    def action_cancel(self) -> None:
        self.dismiss(False)
