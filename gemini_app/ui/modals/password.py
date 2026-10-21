"""Interactive password and passkey modal dialog using our modal system."""

from __future__ import annotations

from typing import Optional
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from gemini_app.ui.modals.base import ResponsiveModalScreen


class PasswordModal(ResponsiveModalScreen[Optional[str]]):
    """Modal dialog prompting the user for a masked password or vault passkey."""

    DEFAULT_CSS = """
    PasswordModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #password_dialog {
        width: 68;
        max-width: 95%;
        height: auto;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #password_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    #password_reason_box {
        background: #141f2d;
        border-left: thick #3399ff;
        padding: 1;
        margin-bottom: 1;
    }
    #password_reason_title {
        color: #3399ff;
        text-style: bold;
    }
    #password_reason_text {
        color: #e0e0e0;
    }
    #password_desc {
        color: #aaaaaa;
        margin-bottom: 1;
    }
    #password_input {
        width: 100%;
        margin-bottom: 1;
        border: solid #3399ff;
    }
    #password_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #password_buttons Button {
        margin-left: 1;
    }
    PasswordModal.-mobile #password_dialog {
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

    def __init__(
        self,
        title: str = "🔐 Passkey Required",
        message: str = "Please enter your password or passkey:",
        reason: str = "",
        placeholder: str = "••••••••",
        submit_label: str = "Confirm",
        allow_empty: bool = False,
    ) -> None:
        super().__init__()
        self.dialog_title = title
        # Infer explicit reason if provided or passed in message
        if reason:
            self.dialog_reason = reason
            self.dialog_message = message if message != "Please enter your password or passkey:" else ""
        elif any(w in message.lower() for w in ("why", "purpose", "reason", "sync", "access", "unlock", "salted", "fleet", "vault", "decrypt")):
            self.dialog_reason = message
            self.dialog_message = ""
        else:
            self.dialog_reason = ""
            self.dialog_message = message

        self.dialog_placeholder = placeholder
        self.submit_label = submit_label
        self.allow_empty = allow_empty

    def compose(self) -> ComposeResult:
        with Vertical(id="password_dialog"):
            yield Static(self.dialog_title, id="password_title")
            if self.dialog_reason:
                with Vertical(id="password_reason_box"):
                    yield Static("Why this window is open / Purpose:", id="password_reason_title")
                    yield Static(self.dialog_reason, id="password_reason_text")
            if self.dialog_message:
                yield Static(self.dialog_message, id="password_desc")
            yield Input(
                placeholder=self.dialog_placeholder,
                password=True,
                id="password_input",
            )
            with Horizontal(id="password_buttons"):
                yield Button("Cancel", variant="error", id="password_cancel_btn")
                yield Button(self.submit_label, variant="primary", id="password_submit_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#password_input", Input).focus()

    @on(Input.Submitted, "#password_input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._handle_submit()

    @on(Button.Pressed, "#password_submit_btn")
    def on_submit_button(self) -> None:
        self._handle_submit()

    @on(Button.Pressed, "#password_cancel_btn")
    def on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _handle_submit(self) -> None:
        val = self.query_one("#password_input", Input).value
        if not val and not self.allow_empty:
            self.notify("Password cannot be empty.", severity="error")
            return
        self.dismiss(val)


# Alias for backward and interchangeable semantic compatibility
PasswordPromptModal = PasswordModal
