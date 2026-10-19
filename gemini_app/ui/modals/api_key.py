"""Interactive modal dialog for configuring GEMINI_API_KEY on first boot."""

from __future__ import annotations

import os
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from gemini_app.bootstrap import persist_api_key
from gemini_app.ui.modals.base import ResponsiveModalScreen


class ApiKeyModal(ResponsiveModalScreen[str | None]):
    """Modal dialog prompting the user for their Google Gemini API Key."""

    DEFAULT_CSS = """
    ApiKeyModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #api_key_dialog {
        width: 72;
        max-width: 95%;
        height: auto;
        border: thick red;
        background: #0d0d0d;
        padding: 1 2;
    }
    #api_key_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    #api_key_desc {
        color: #aaaaaa;
        margin-bottom: 1;
    }
    #api_key_link {
        color: #3399ff;
        margin-bottom: 1;
        text-style: italic;
    }
    #api_key_input {
        width: 100%;
        margin-bottom: 1;
        border: solid red;
    }
    #api_key_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #api_key_buttons Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="api_key_dialog"):
            yield Static("🔑 Google Gemini API Key Required", id="api_key_title")
            yield Static(
                "Welcome to Gemini Integrated! To enable AI inference, please enter your API key.\n"
                "It will be stored in your environment and user state automatically.",
                id="api_key_desc",
            )
            yield Static("Get a free API key at: https://aistudio.google.com/app/apikey", id="api_key_link")
            yield Input(
                placeholder="AIzaSy...",
                password=True,
                id="api_key_input",
            )
            with Horizontal(id="api_key_buttons"):
                yield Button("Quit", variant="error", id="api_key_cancel_btn")
                yield Button("Save & Launch", variant="primary", id="api_key_save_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#api_key_input", Input).focus()

    @on(Input.Submitted, "#api_key_input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._handle_save()

    @on(Button.Pressed, "#api_key_save_btn")
    def on_save_button(self) -> None:
        self._handle_save()

    @on(Button.Pressed, "#api_key_cancel_btn")
    def on_cancel_button(self) -> None:
        self.dismiss(None)

    def _handle_save(self) -> None:
        val = self.query_one("#api_key_input", Input).value.strip()
        if not val:
            self.notify("API key cannot be empty.", severity="error")
            return
        persist_api_key(val)
        self.dismiss(val)
