"""LiveWire Settings Modal
Configures the remote Nomad Sculpt Link IP and port with local network discovery.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option

from gemini_app.ui.modals.base import ResponsiveModalScreen

# Import LiveWire engine helpers
ENGINES_DIR = Path(__file__).resolve().parents[3] / "Projects" / "3drealms" / "engines" / "study_engine"
if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))

try:
    from live_wire_engine import (
        load_livewire_settings,
        save_livewire_settings,
        discover_nomad_devices,
        DEFAULT_HOST,
        DEFAULT_PORT
    )
except ImportError:
    DEFAULT_HOST = "192.168.1.38"
    DEFAULT_PORT = 48312
    def load_livewire_settings() -> dict:
        return {"host": DEFAULT_HOST, "port": DEFAULT_PORT}
    def save_livewire_settings(host: str, port: int = DEFAULT_PORT) -> dict:
        return {"host": host, "port": port}
    def discover_nomad_devices(timeout: float = 0.4) -> list:
        return []


class LiveWireSettingsModal(ResponsiveModalScreen[Optional[dict]]):
    """Modal for configuring remote Nomad Sculpt link IP and discovering network devices."""

    DEFAULT_CSS = """
    LiveWireSettingsModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #settings_dialog {
        padding: 1 2;
        width: 72;
        max-width: 95vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
        border: thick #bb55ff;
    }
    #settings_dialog Label.title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        width: 100%;
        text-align: center;
    }
    #settings_dialog Label.section {
        text-style: bold;
        color: #bb55ff;
        margin-top: 1;
        margin-bottom: 0;
    }
    #settings_dialog Label.hint {
        color: #888888;
        margin-bottom: 1;
    }
    #ip_input {
        background: #0d0d12;
        color: #ffffff;
        border: tall #333333;
        margin-bottom: 1;
    }
    #device_list {
        height: 7;
        background: #0d0d12;
        color: #ffffff;
        border: tall #333333;
        margin-bottom: 1;
    }
    #settings_buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    #settings_buttons Button {
        margin-left: 1;
        background: #1a1a24;
        color: #ffffff;
    }
    #settings_buttons Button#save_btn {
        background: #bb55ff;
        color: #ffffff;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_livewire_settings()
        self.current_host = self.settings.get("host", DEFAULT_HOST)
        self.current_port = self.settings.get("port", DEFAULT_PORT)
        self.devices: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings_dialog"):
            yield Label("✦ LiveWire Settings & Device Link", classes="title")
            
            yield Label("Nomad Sculpt Link IP / Host:", classes="section")
            yield Label("Enter the IP of the iPad/device running Nomad Sculpt link (e.g. 192.168.1.38:48312):", classes="hint")
            curr_target = f"{self.current_host}:{self.current_port}"
            yield Input(
                value=curr_target,
                placeholder="192.168.1.38:48312",
                id="ip_input"
            )

            yield Label("Discovered Network Devices:", classes="section")
            yield Label("Select an active device below or manually type the IP above:", classes="hint")
            yield OptionList(id="device_list")

            with Horizontal(id="settings_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Save Settings", id="save_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#ip_input", Input).focus()
        self.refresh_devices_async()

    def refresh_devices_async(self) -> None:
        opt_list = self.query_one("#device_list", OptionList)
        opt_list.clear_options()
        opt_list.add_option(Option("Scanning local network for Nomad Link devices...", disabled=True))

        def _scan():
            devs = discover_nomad_devices(timeout=0.3)
            self.app.call_from_thread(self._populate_devices, devs)

        import threading
        t = threading.Thread(target=_scan, daemon=True)
        t.start()

    def _populate_devices(self, devices: List[Dict[str, Any]]) -> None:
        self.devices = devices
        try:
            opt_list = self.query_one("#device_list", OptionList)
            opt_list.clear_options()
            if not devices:
                opt_list.add_option(Option("No remote devices detected automatically (Enter IP manually above)", disabled=True))
                return

            for d in devices:
                status_icon = "🟢" if d.get("status") == "online" else "⚪"
                label = f"{status_icon} {d.get('device_name')} - {d.get('host')}:{d.get('port')} [{d.get('status')}]"
                opt_list.add_option(Option(label, id=f"{d.get('host')}:{d.get('port')}"))
        except Exception:
            pass

    @on(OptionList.OptionSelected, "#device_list")
    def on_device_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            inp = self.query_one("#ip_input", Input)
            inp.value = str(event.option_id)
            inp.focus()

    @on(Button.Pressed, "#save_btn")
    @on(Input.Submitted, "#ip_input")
    def action_save(self) -> None:
        raw = self.query_one("#ip_input", Input).value.strip()
        if not raw:
            raw = f"{DEFAULT_HOST}:{DEFAULT_PORT}"

        if ":" in raw:
            parts = raw.split(":", 1)
            host = parts[0].strip()
            port = int(parts[1].strip()) if parts[1].strip().isdigit() else DEFAULT_PORT
        else:
            host = raw
            port = DEFAULT_PORT

        saved = save_livewire_settings(host, port)
        self.app.notify(f"LiveWire settings saved: {host}:{port}", timeout=3.0)
        self.dismiss(saved)

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)
