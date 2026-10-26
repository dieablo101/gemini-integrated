"""Wingman Access Request Confirmation & Connection Manager Modal."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static

from gemini_app.ui.modals.base import ResponsiveModalScreen


class WingmanAuthModal(ResponsiveModalScreen[str]):
    """Modal prompting the operator to Accept, Trust, or Deny Wingman session requests.
    Supports both single-request confirmation and multi-request connection manager view.
    """

    DEFAULT_CSS = """
    WingmanAuthModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #wingman_dialog {
        padding: 1 2;
        width: 74;
        max-width: 94vw;
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
    .section-title {
        color: #60a5fa;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }
    .wingman-card {
        background: #080c14;
        border: solid #1f293d;
        padding: 1;
        margin-bottom: 1;
        width: 100%;
        height: auto;
    }
    .wingman-paired-card {
        background: #0d131f;
        border: solid #1e3a5f;
        padding: 1;
        margin-bottom: 1;
        width: 100%;
        height: auto;
    }
    .wingman-card-meta {
        color: #d1d5db;
        margin-bottom: 1;
    }
    #wingman_prompt {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        color: #f3f4f6;
        text-wrap: wrap;
    }
    .wingman-card-buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 1;
    }
    .wingman-card-buttons Button {
        margin: 0 1;
        text-style: bold;
    }
    #wingman_footer_buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 1;
        border-top: solid #1f293d;
        padding-top: 1;
    }
    #wingman_footer_buttons Button {
        margin: 0 1;
    }
    .empty-notice {
        text-align: center;
        color: #9ca3af;
        margin: 1 1;
        width: 100%;
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
        Binding("escape", "dismiss_modal", "Close"),
        Binding("ctrl+g", "dismiss_modal", "Close"),
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
        pending_requests: Optional[List[Dict[str, Any]]] = None,
        paired_devices: Optional[List[Dict[str, Any]]] = None,
        on_resolve: Optional[Callable[..., None]] = None,
        on_revoke: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        data = auth_data or {}
        self.node_id = data.get("node_id") or node_id
        self.client_ip = data.get("client_ip") or client_ip
        self.auth_req_id = data.get("auth_req_id") or auth_req_id or "wauth-unknown"
        self.user_agent = data.get("user_agent") or user_agent or "Web Browser"
        self.timestamp = data.get("timestamp") or timestamp or time.time()
        self.on_resolve = on_resolve
        self.on_revoke = on_revoke
        self.paired_devices = list(paired_devices or [])

        if pending_requests is not None or paired_devices is not None:
            self.is_multi_manager = True
            self.pending_requests = list(pending_requests or [])
        else:
            self.is_multi_manager = False
            self.pending_requests = [
                {
                    "node_id": self.node_id,
                    "client_ip": self.client_ip,
                    "auth_req_id": self.auth_req_id,
                    "user_agent": self.user_agent,
                    "timestamp": self.timestamp,
                }
            ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="wingman_dialog"):
            if self.is_multi_manager:
                yield Label("⚡ WINGMAN CONNECTION MANAGER", classes="modal-title")
            else:
                yield Label("⚡ WINGMAN ACCESS REQUEST", classes="modal-title")

            if self.is_multi_manager:
                yield Label(f"Pending Approvals ({len(self.pending_requests)}):", classes="section-title")

            if not self.pending_requests:
                yield Static(
                    "No pending connection requests waiting for authorization.",
                    classes="empty-notice",
                )
            else:
                if not self.is_multi_manager:
                    prompt = (
                        f"Wingman portal access requested on node '{self.node_id}'.\n"
                        "Select Accept for one-time session access, Pair to remember device, or Deny."
                    )
                    yield Label(prompt, id="wingman_prompt")

                for idx, req in enumerate(self.pending_requests):
                    rid = req.get("auth_req_id") or req.get("session_id") or f"req-{idx}"
                    nid = req.get("node_id") or "mothership"
                    cip = req.get("client_ip") or "127.0.0.1"
                    ua = req.get("user_agent") or "Web Browser"
                    ts = req.get("timestamp") or time.time()
                    time_str = time.strftime("%H:%M:%S UTC", time.gmtime(ts))
                    safe_rid = rid.replace(":", "_").replace("/", "_").replace(".", "_")

                    with Vertical(classes="wingman-card", id=f"card__{safe_rid}"):
                        meta_text = (
                            f"• Node:    {nid}\n"
                            f"• IP:      {cip}\n"
                            f"• Request: {rid}\n"
                            f"• Client:  {ua[:42]}\n"
                            f"• Time:    {time_str}"
                        )
                        yield Static(meta_text, classes="wingman-card-meta", id=f"meta__{safe_rid}")

                        with Horizontal(classes="wingman-card-buttons"):
                            if not self.is_multi_manager and idx == 0:
                                yield Button("Accept [A]", id="accept_btn", variant="primary")
                                yield Button("Pair [P]", id="pair_btn", variant="warning")
                                yield Button("Deny [D]", id="deny_btn", variant="error")
                            else:
                                yield Button("Accept [A]", id=f"accept__{safe_rid}", variant="primary")
                                yield Button("Pair [P]", id=f"pair__{safe_rid}", variant="warning")
                                yield Button("Deny [D]", id=f"deny__{safe_rid}", variant="error")

            # Paired / Trusted devices section
            if self.is_multi_manager and self.paired_devices:
                yield Label(f"Trusted Paired Devices ({len(self.paired_devices)}):", classes="section-title")
                for dev in self.paired_devices:
                    dev_id = dev.get("device_id", "unknown")
                    label = dev.get("label") or dev.get("user_agent", "Paired Device")
                    cip = dev.get("client_ip", "remote")
                    safe_did = dev_id.replace(":", "_").replace("/", "_").replace(".", "_")
                    with Vertical(classes="wingman-paired-card", id=f"paired__{safe_did}"):
                        dev_meta = (
                            f"• Device ID: {dev_id}\n"
                            f"• Label:     {label[:40]}\n"
                            f"• IP:        {cip}"
                        )
                        yield Static(dev_meta, classes="wingman-card-meta")
                        with Horizontal(classes="wingman-card-buttons"):
                            yield Button("Revoke Trust", id=f"revoke__{safe_did}", variant="error")

            with Horizontal(id="wingman_footer_buttons"):
                if self.is_multi_manager and len(self.pending_requests) > 1:
                    yield Button("Accept All", id="accept_all_btn", variant="primary")
                    yield Button("Deny All", id="deny_all_btn", variant="error")
                yield Button("Close [Esc]", id="close_btn", variant="default")

    def on_mount(self) -> None:
        super().on_mount()
        try:
            if not self.is_multi_manager:
                self.query_one("#accept_btn", Button).focus()
            elif self.pending_requests:
                first_rid = self.pending_requests[0].get("auth_req_id") or self.pending_requests[0].get("session_id")
                safe_rid = first_rid.replace(":", "_").replace("/", "_").replace(".", "_")
                self.query_one(f"#accept__{safe_rid}", Button).focus()
            else:
                self.query_one("#close_btn", Button).focus()
        except Exception:
            pass

    def dismiss(self, result: Any = None) -> None:
        """Defensive dismissal guarding Textual's screen stack against ScreenStackError."""
        try:
            if self.is_mounted and getattr(self.app, "_screen_stack", None) and len(self.app._screen_stack) > 1:
                super().dismiss(result)
        except Exception:
            pass

    def action_dismiss_modal(self) -> None:
        self.dismiss("close")

    def add_or_update_request(self, auth_data: Dict[str, Any]) -> None:
        """Dynamically appends a new request into pending list if not already present."""
        rid = auth_data.get("auth_req_id") or auth_data.get("session_id")
        if not rid:
            return
        for r in self.pending_requests:
            if (r.get("auth_req_id") or r.get("session_id")) == rid:
                return
        self.pending_requests.append(dict(auth_data))

    def _resolve_one(self, idx: int, decision: str) -> None:
        """Resolves request by index."""
        if 0 <= idx < len(self.pending_requests):
            req = self.pending_requests[idx]
            rid = req.get("auth_req_id") or req.get("session_id")
            if rid:
                self._resolve_single_req(rid, decision)

    def _resolve_one(self, idx: int, decision: str) -> None:
        """Resolves a pending request by index."""
        if 0 <= idx < len(self.pending_requests):
            req = self.pending_requests[idx]
            rid = req.get("auth_req_id") or req.get("session_id") or ""
            self._resolve_single_req(rid, decision)

    def _resolve_single_req(self, req_id: str, decision: str) -> None:
        match_req = None
        for r in self.pending_requests:
            rid = r.get("auth_req_id") or r.get("session_id")
            safe_rid = rid.replace(":", "_").replace("/", "_").replace(".", "_") if rid else ""
            if rid == req_id or safe_rid == req_id:
                match_req = r
                break

        actual_rid = match_req.get("auth_req_id") or match_req.get("session_id") or req_id if match_req else req_id

        if self.on_resolve:
            try:
                import inspect
                sig = inspect.signature(self.on_resolve)
                if len(sig.parameters) >= 3:
                    self.on_resolve(actual_rid, decision, match_req or {})
                else:
                    self.on_resolve(actual_rid, decision)
            except Exception:
                try:
                    self.on_resolve(actual_rid, decision)
                except Exception:
                    pass

        self.pending_requests = [
            r for r in self.pending_requests
            if (r.get("auth_req_id") or r.get("session_id")) not in (actual_rid, req_id)
        ]
        safe_id = actual_rid.replace(":", "_").replace("/", "_").replace(".", "_")
        try:
            self.query_one(f"#card__{safe_id}").remove()
        except Exception:
            pass

        if not self.pending_requests:
            self.dismiss(decision)

    @on(Button.Pressed)
    def handle_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "close_btn":
            self.dismiss("close")
            return
        elif bid == "accept_btn":
            self.action_accept()
            return
        elif bid == "pair_btn":
            self.action_pair()
            return
        elif bid == "deny_btn":
            self.action_deny()
            return
        elif bid == "accept_all_btn":
            for req in list(self.pending_requests):
                rid = req.get("auth_req_id") or req.get("session_id")
                if rid and self.on_resolve:
                    try:
                        self.on_resolve(rid, "accept", req)
                    except TypeError:
                        self.on_resolve(rid, "accept")
                    except Exception:
                        pass
            self.pending_requests.clear()
            self.dismiss("accept_all")
            return
        elif bid == "deny_all_btn":
            for req in list(self.pending_requests):
                rid = req.get("auth_req_id") or req.get("session_id")
                if rid and self.on_resolve:
                    try:
                        self.on_resolve(rid, "deny", req)
                    except TypeError:
                        self.on_resolve(rid, "deny")
                    except Exception:
                        pass
            self.pending_requests.clear()
            self.dismiss("deny_all")
            return
        elif bid.startswith("accept__"):
            rid = bid[len("accept__"):]
            self._resolve_single_req(rid, "accept")
        elif bid.startswith("pair__"):
            rid = bid[len("pair__"):]
            self._resolve_single_req(rid, "pair")
        elif bid.startswith("deny__"):
            rid = bid[len("deny__"):]
            self._resolve_single_req(rid, "deny")
        elif bid.startswith("revoke__"):
            did = bid[len("revoke__"):]
            match_dev = None
            for d in self.paired_devices:
                raw_did = d.get("device_id", "")
                safe_d = raw_did.replace(":", "_").replace("/", "_").replace(".", "_")
                if raw_did == did or safe_d == did:
                    match_dev = d
                    break
            actual_did = match_dev.get("device_id", did) if match_dev else did
            if self.on_revoke:
                try:
                    self.on_revoke(actual_did)
                except Exception:
                    pass
            self.paired_devices = [d for d in self.paired_devices if d.get("device_id") != actual_did]
            try:
                self.query_one(f"#paired__{did}").remove()
            except Exception:
                pass

    def action_accept(self) -> None:
        if not self.is_multi_manager:
            self.dismiss("accept")
        elif self.pending_requests:
            first_rid = self.pending_requests[0].get("auth_req_id") or self.pending_requests[0].get("session_id")
            if first_rid:
                self._resolve_single_req(first_rid, "accept")
        else:
            self.dismiss("accept")

    def action_pair(self) -> None:
        if not self.is_multi_manager:
            self.dismiss("pair")
        elif self.pending_requests:
            first_rid = self.pending_requests[0].get("auth_req_id") or self.pending_requests[0].get("session_id")
            if first_rid:
                self._resolve_single_req(first_rid, "pair")
        else:
            self.dismiss("pair")

    def action_trust(self) -> None:
        """Alias for pairing."""
        self.action_pair()

    def action_deny(self) -> None:
        if not self.is_multi_manager:
            self.dismiss("deny")
        elif self.pending_requests:
            first_rid = self.pending_requests[0].get("auth_req_id") or self.pending_requests[0].get("session_id")
            if first_rid:
                self._resolve_single_req(first_rid, "deny")
        else:
            self.dismiss("deny")
