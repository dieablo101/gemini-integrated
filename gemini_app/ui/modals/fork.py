"""Modal dialog for titling a branched chat fork."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Label

from gemini_app.ui.modals.base import ResponsiveModalScreen


class ForkModal(ResponsiveModalScreen[str | None]):
    """Modal prompting the user for the new title of a forked chat."""

    DEFAULT_CSS = """
    ForkModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #fork_dialog {
        padding: 1 2;
        width: 66;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #fork_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #fork_prefix_hint {
        margin-bottom: 1;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #fork_title_input {
        margin-bottom: 1;
        background: #000000;
        color: #ffffff;
    }
    #fork_buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
    }
    #fork_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    ForkModal.-mobile #fork_dialog {
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

    def __init__(self, default_title: str = "") -> None:
        super().__init__()
        clean_default = default_title
        if clean_default.startswith("Fork: "):
            clean_default = clean_default[6:]
        self.default_title = clean_default

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="fork_dialog"):
            yield Label("Name forked chat:")
            yield Label("Prefix 'Fork: ' will be permanently attached to the title.", id="fork_prefix_hint")
            yield Input(
                value=self.default_title,
                placeholder="Enter topic/name...",
                id="fork_title_input",
            )
            with Horizontal(id="fork_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Fork It", id="fork_btn")

    def on_mount(self) -> None:
        super().on_mount()
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
