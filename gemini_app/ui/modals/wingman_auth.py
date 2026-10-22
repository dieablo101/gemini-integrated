"""Wingman Access Request Confirmation Modal."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label, Static

from gemini_app.ui.modals.base import ResponsiveModalScreen


class WingmanAuthModal(ResponsiveModalScreen[str]):
    """Modal prompting the operator to Accept, Trust, or Deny a Wingman session request."""

    DEFAULT_CSS = """
    WingmanAuthModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #wingman_dialog {
        padding: 1 2;
        width: 64;
        max-width: 92vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
        border: solid #3399ff;
    }
    #wingman_dialog .modal-title {
        margin-bottom: 1;
        text-style: bold;
        text-align: center;
        width: 100%;
        color: #3399ff;
    }
    #wingman_meta {
        background: #080c14;
        border: solid #1f293d;
        padding: 1;
        margin-bottom: 1;
        width: 100%;
        height: auto;
        color: #d1d5db;
    }
    #wingman_prompt {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        color: #f3f4f6;
        text-wrap: wrap;
    }
    #wingman_buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 1;
    }
    #wingman_buttons Button {
        margin: 0 1;
        text-style: bold;
    }
    WingmanAuthModal.-mobile #wingman_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny"),
        Binding("ctrl+g", "deny", "Deny"),
        Binding("a", "accept", "Accept"),
        Binding("p", "pair", "Pair"),
        Binding("d", "deny", "Deny"),
    ]

    def __init__(
        self,
        node_id: str = "node",
        client_ip: str = "127.0.0.1",
        auth_req_id: str = "",
        user_agent: str = "",
        timestamp: Optional[float] = None,
        auth_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        data = auth_data or {}
        self.node_id = data.get("node_id") or node_id
        self.client_ip = data.get("client_ip") or client_ip
        self.auth_req_id = data.get("auth_req_id") or auth_req_id or "wauth-unknown"
        self.user_agent = data.get("user_agent") or user_agent or "Web Browser"
        self.timestamp = data.get("timestamp") or timestamp or time.time()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="wingman_dialog"):
            yield Label("⚡ WINGMAN ACCESS REQUEST", classes="modal-title")

            time_str = time.strftime("%H:%M:%S UTC", time.gmtime(self.timestamp))
            meta_text = (
                f"• Node ID:    {self.node_id}\n"
                f"• Client IP:  {self.client_ip}\n"
                f"• Request ID: {self.auth_req_id}\n"
                f"• Client:     {self.user_agent[:45]}\n"
                f"• Time:       {time_str}"
            )
            yield Static(meta_text, id="wingman_meta")

            prompt = (
                f"Wingman portal access requested on node '{self.node_id}'.\n"
                "Select Accept for one-time session access, Pair to remember device, or Deny."
            )
            yield Label(prompt, id="wingman_prompt")

            with Horizontal(id="wingman_buttons"):
                yield Button("Accept [A]", id="accept_btn", variant="primary")
                yield Button("Pair [P]", id="pair_btn", variant="warning")
                yield Button("Deny [D]", id="deny_btn", variant="error")

    def on_mount(self) -> None:
        super().on_mount()
        try:
            self.query_one("#accept_btn", Button).focus()
        except Exception:
            pass

    @on(Button.Pressed, "#accept_btn")
    def action_accept(self) -> None:
        self.dismiss("accept")

    @on(Button.Pressed, "#pair_btn")
    def action_pair(self) -> None:
        self.dismiss("pair")

    def action_trust(self) -> None:
        """Alias for pairing."""
        self.dismiss("pair")

    @on(Button.Pressed, "#deny_btn")
    def action_deny(self) -> None:
        self.dismiss("deny")
