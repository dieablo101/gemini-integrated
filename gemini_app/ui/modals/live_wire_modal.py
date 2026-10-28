"""LiveWire Modal Screen
Interactive terminal cockpit for Nomad Sculpt Link, In-Progress Checkpoints,
Strict Study Engine Ingestion, and Production Asset Pipeline Finalization.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from gemini_app.ui.modals.base import ResponsiveModalScreen

# Import LiveWire engine
ENGINES_DIR = Path(__file__).resolve().parents[3] / "Projects" / "3drealms" / "engines" / "study_engine"
if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))

from live_wire_engine import (
    LiveWireSessionManager,
    STUDIES_ROOT,
    PRODUCTION_ROOT,
    validate_session_name,
    check_session_collision,
    check_in_progress_snapshot_exists,
    cancel_and_scrub_session,
    finalize_livewire_session,
    load_livewire_settings,
    save_in_progress_snapshot,
    DEFAULT_HOST,
    DEFAULT_PORT
)


class LivewireSessionInput(Input):
    """Input widget featuring 1x tab directory autocompletion and 2x tab focus escape."""

    def __init__(self, mode_getter: Callable[[], str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode_getter = mode_getter
        self._last_tab_time: float = 0.0

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()

            now = time.monotonic()
            if now - self._last_tab_time < 0.35:
                self._last_tab_time = 0.0
                self.screen.focus_next()
                return
            else:
                self._last_tab_time = now
                self._autocomplete_session()
                return

        await super()._on_key(event)

    def _autocomplete_session(self) -> None:
        mode = self.mode_getter()
        base_dir = PRODUCTION_ROOT if mode == "production" else STUDIES_ROOT
        if not base_dir.exists():
            return

        raw = self.value.strip()
        if "/" in raw:
            # Completing inside a subfolder: e.g. "pirates/old"
            parts = raw.split("/", 1)
            parent_folder = parts[0]
            prefix = parts[1]
            target_dir = base_dir / parent_folder
            if not target_dir.exists() or not target_dir.is_dir():
                return
            try:
                matches = [
                    d.name for d in target_dir.iterdir()
                    if d.name.startswith(prefix) and not d.name.startswith(".")
                ]
            except Exception:
                return

            if not matches:
                return
            common = os.path.commonprefix(matches)
            target = matches[0] if len(matches) == 1 else common
            if target:
                self.value = f"{parent_folder}/{target}"
                self.cursor_position = len(self.value)
        else:
            # Completing top-level subfolder: e.g. "pi" -> "pirates/"
            prefix = raw
            try:
                matches = [
                    d.name for d in base_dir.iterdir()
                    if d.is_dir() and d.name.startswith(prefix) and not d.name.startswith(".")
                ]
            except Exception:
                return

            if not matches:
                return
            common = os.path.commonprefix(matches)
            target = matches[0] if len(matches) == 1 else common
            if target:
                self.value = f"{target}/"
                self.cursor_position = len(self.value)


class LiveWireModal(ResponsiveModalScreen[None]):
    """Cockpit modal for LiveWire real-time streaming, recording, snapshots, and finalization."""

    DEFAULT_CSS = """
    LiveWireModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #livewire_dialog {
        padding: 1 2;
        width: 90;
        max-width: 96vw;
        height: auto;
        max-height: 92vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
        border: thick #bb55ff;
    }
    #header_row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #modal_title {
        text-style: bold;
        color: #ffffff;
        width: 1fr;
    }
    #rec_badge {
        width: auto;
        text-style: bold;
        color: #555555;
    }
    #rec_badge.recording {
        color: #ff3344;
    }
    #link_bar {
        width: 100%;
        height: auto;
        padding: 0 1;
        background: #0d0d14;
        border: solid #222233;
        margin-bottom: 1;
        align-vertical: middle;
    }
    #link_status_label {
        width: 1fr;
        color: #aaaaaa;
    }
    #connect_btn {
        background: #1a1a28;
        color: #ffffff;
        min-width: 12;
    }
    #session_name_label {
        text-style: bold;
        color: #bb55ff;
        margin-top: 1;
    }
    #session_name_input {
        background: #0c0c12;
        color: #ffffff;
        border: tall #333344;
        margin-bottom: 1;
    }
    #mode_row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    .mode_btn {
        margin-right: 1;
        background: #151520;
        color: #888888;
        min-width: 16;
    }
    .mode_btn.active {
        background: #bb55ff;
        color: #ffffff;
        text-style: bold;
    }
    #telemetry_box {
        width: 100%;
        height: auto;
        min-height: 12;
        background: #090912;
        border: tall #2c1e40;
        padding: 0 1;
        margin-bottom: 1;
    }
    #telem_header_row {
        width: 100%;
        height: auto;
        margin-top: 1;
        margin-bottom: 0;
    }
    #telem_title {
        text-style: bold;
        color: #bb55ff;
        width: 1fr;
    }
    #telem_timer {
        text-style: bold;
        color: #55ffaa;
        width: auto;
    }
    #telem_stat_grid_1, #telem_stat_grid_2, #telem_stat_grid_3 {
        width: 100%;
        height: auto;
        margin-top: 0;
    }
    #telem_stat_grid_1 Label, #telem_stat_grid_2 Label, #telem_stat_grid_3 Label {
        width: 1fr;
        color: #dddddd;
    }
    #events_divider {
        color: #443355;
        margin-top: 1;
        height: 1;
    }
    #events_log_container {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #events_log_container Label {
        color: #8899aa;
    }
    #action_row {
        width: 100%;
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    #action_row Button {
        margin-left: 1;
    }
    #record_btn {
        background: #2a1215;
        color: #ff4455;
        text-style: bold;
    }
    #record_btn.active {
        background: #ff2233;
        color: #ffffff;
        text-style: bold;
    }
    #snapshot_btn {
        background: #182230;
        color: #55aaff;
    }
    #cancel_btn {
        background: #251818;
        color: #ff7777;
    }
    #finalize_btn {
        background: #122818;
        color: #55dd77;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close Modal"),
        Binding("p", "toggle_recording", "Toggle Record/Stop"),
        Binding("ctrl+c", "c_c_prefix_stub", "^c Commands", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.mgr = LiveWireSessionManager.get_instance()
        self.active_mode: Optional[str] = self.mgr.current_mode or "studies"
        self._c_c_prefix: bool = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="livewire_dialog"):
            with Horizontal(id="header_row"):
                yield Label("✦ LiveWire Interactive Cockpit", id="modal_title")
                yield Label("○ ready", id="rec_badge")

            with Horizontal(id="link_bar"):
                yield Label("Nomad Sculpt Link: [Disconnected]", id="link_status_label")
                yield Button("Connect", id="connect_btn")

            yield Label("Livewire Session Name (folder/filename):", id="session_name_label")
            yield LivewireSessionInput(
                mode_getter=lambda: self.active_mode or "studies",
                value=self.mgr.current_session_name,
                placeholder="e.g. pirates/oldcrazypirate or alien/alien2",
                id="session_name_input"
            )

            with Horizontal(id="mode_row"):
                yield Button("Studies", id="mode_studies_btn", classes="mode_btn")
                yield Button("Production", id="mode_production_btn", classes="mode_btn")

            with Vertical(id="telemetry_box"):
                with Horizontal(id="telem_header_row"):
                    yield Label("LIVEWIRE SESSION DATA STREAM", id="telem_title")
                    yield Label("⏱ 00:00:00", id="telem_timer")
                with Horizontal(id="telem_stat_grid_1"):
                    yield Label("Mesh Twin: None (Waiting for Nomad)", id="telem_twin")
                    yield Label("Stage: Stage 1 Gesture (50%)", id="telem_stage")
                with Horizontal(id="telem_stat_grid_2"):
                    yield Label("Kinetic: 0 strokes | Energy: 0.000", id="telem_kinetic")
                    yield Label("Brush: Standby | Hotspot: None", id="telem_brush")
                with Horizontal(id="telem_stat_grid_3"):
                    yield Label("Eye Inspection: Unknown", id="telem_camera")
                    yield Label("Audio Mic: ⚪ Standby", id="telem_audio")
                yield Label("── RECENT WIRE EVENTS ──────────────────────────────────", id="events_divider")
                with Vertical(id="events_log_container"):
                    yield Label("• LiveWire wire link standing by.", id="event_item_0")
                    yield Label("• Ready to stream Nomad Sculpt geometry and kinetic strokes.", id="event_item_1")
                    yield Label("• In-progress snapshots preserve 100% bit-exact geometry.", id="event_item_2")

            with Horizontal(id="action_row"):
                yield Button("Record (p)", id="record_btn")
                yield Button("In-Progress Snapshot", id="snapshot_btn")
                yield Button("Cancel Session", id="cancel_btn")
                yield Button("Finalize", id="finalize_btn")

    def on_mount(self) -> None:
        super().on_mount()
        # Auto-connect if Nomad Link is listening
        if not self.mgr.is_connected:
            self.mgr.connect_wire()
        self._refresh_ui_state()
        self.set_interval(0.25, self._tick_ui)
        self.query_one("#session_name_input", LivewireSessionInput).focus()

    def _tick_ui(self) -> None:
        self._refresh_ui_state()

    def _refresh_ui_state(self) -> None:
        # 1. Update Link status label & connect button
        link_lbl = self.query_one("#link_status_label", Label)
        conn_btn = self.query_one("#connect_btn", Button)
        if self.mgr.is_connected:
            link_lbl.update("Nomad Sculpt Link: [Connected 🟢]")
            link_lbl.styles.color = "#55ff77"
            conn_btn.label = "Connected"
            conn_btn.disabled = True
        else:
            link_lbl.update("Nomad Sculpt Link: [Disconnected 🔴]")
            link_lbl.styles.color = "#ff5566"
            conn_btn.label = "Connect"
            conn_btn.disabled = False

        # 2. Recording badge & record button
        rec_badge = self.query_one("#rec_badge", Label)
        rec_btn = self.query_one("#record_btn", Button)
        if self.mgr.is_recording:
            rec_badge.update("● recording...")
            rec_badge.add_class("recording")
            rec_btn.label = "Stop (p)"
            rec_btn.add_class("active")
        else:
            rec_badge.update("○ ready")
            rec_badge.remove_class("recording")
            rec_btn.label = "Record (p)"
            rec_btn.remove_class("active")

        # 3. Active Mode Buttons
        studies_btn = self.query_one("#mode_studies_btn", Button)
        prod_btn = self.query_one("#mode_production_btn", Button)
        if self.active_mode == "studies":
            studies_btn.add_class("active")
            prod_btn.remove_class("active")
        elif self.active_mode == "production":
            prod_btn.add_class("active")
            studies_btn.remove_class("active")
        else:
            studies_btn.remove_class("active")
            prod_btn.remove_class("active")

        # 4. Telemetry update
        telem_title = self.query_one("#telem_title", Label)
        telem_timer = self.query_one("#telem_timer", Label)
        telem_twin = self.query_one("#telem_twin", Label)
        telem_stage = self.query_one("#telem_stage", Label)
        telem_kinetic = self.query_one("#telem_kinetic", Label)
        telem_brush = self.query_one("#telem_brush", Label)
        telem_camera = self.query_one("#telem_camera", Label)
        telem_audio = self.query_one("#telem_audio", Label)

        # Title & Timer
        sess_name = self.mgr.current_session_name or "untitled"
        mode_str = (self.active_mode or "studies").upper()
        if self.mgr.is_recording:
            elapsed = int(time.time() - self.mgr.recording_start_epoch)
            hrs = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            telem_title.update(f"SESSION: {sess_name} [{mode_str}]")
            telem_timer.update(f"● REC [{hrs:02d}:{mins:02d}:{secs:02d}]")
            telem_timer.styles.color = "#ff3344"
        else:
            telem_title.update(f"LIVEWIRE COCKPIT [{mode_str}]")
            telem_timer.update("○ STANDBY")
            telem_timer.styles.color = "#55ffaa"

        # Audio status
        telem_audio.update(self.mgr.get_audio_status_display())

        # Engine vitals
        if self.mgr.engine:
            stats = self.mgr.engine.stats
            twin = self.mgr.engine.twin
            cam = self.mgr.engine.camera_state

            if twin.vertex_count > 0:
                telem_twin.update(f"Twin: '{twin.sculpt_id}' ({twin.vertex_count:,} v, {twin.face_count:,} f)")
            else:
                telem_twin.update("Twin: Waiting for scene sync...")

            stage_clean = stats.current_stage.replace("stage_", "Stage ").replace("_", " ").title()
            telem_stage.update(f"{stage_clean} ({stats.stage_confidence:.0%})")

            telem_kinetic.update(f"Kinetic: {stats.total_strokes} strokes | E: {stats.total_kinetic_energy:.3f}")

            if stats.recent_strokes:
                last_s = stats.recent_strokes[-1]
                brush_name = last_s.brush_archetype.replace("_", " ").title()
                telem_brush.update(f"Brush: {brush_name} ({last_s.brush_confidence:.0%}) | {last_s.anatomical_region}")
            else:
                telem_brush.update("Brush: Standby | Hotspot: Awaiting stroke")

            if cam:
                telem_camera.update(f"Camera: Orbit #{cam.orbit_count} | Pos {cam.camera_pos.round(1).tolist()} | FOV {cam.fov_y:.0f}°")
            else:
                telem_camera.update("Camera: Waiting for viewpoint sync...")

        # Update event stream
        evts = self.mgr.recent_events_log[-3:]
        for idx in range(3):
            item = self.query_one(f"#event_item_{idx}", Label)
            if idx < len(evts):
                item.update(evts[idx])
            else:
                item.update("")

    def _check_name_and_collision(self, session_name: str) -> tuple[bool, str, str, str]:
        mode = self.active_mode or "studies"
        val_ok, err, folder, filename = validate_session_name(session_name)
        if not val_ok:
            self.app.notify(err, severity="error", timeout=4.0)
            return False, err, "", ""

        if check_session_collision(mode, folder, filename) and not check_in_progress_snapshot_exists(mode, folder, filename):
            warn_msg = f"Warning: '{session_name}' already exists in that folder"
            self.app.notify(warn_msg, severity="error", timeout=4.0)
            return False, warn_msg, folder, filename

        return True, "", folder, filename

    @on(Button.Pressed, "#connect_btn")
    def action_connect(self) -> None:
        self.app.notify("Connecting to Nomad Sculpt Link on iPad...", timeout=2.5)
        ok = self.mgr.connect_wire()
        if ok:
            self.app.notify("Nomad Sculpt Link connected! 🟢", timeout=3.0)
        else:
            self.app.notify("Failed to connect to Nomad Sculpt Link. Check iPad IP & port in /livewire --settings", severity="error", timeout=5.0)
        self._refresh_ui_state()

    @on(Button.Pressed, "#mode_studies_btn")
    def on_mode_studies(self) -> None:
        self.active_mode = "studies"
        self._refresh_ui_state()

    @on(Button.Pressed, "#mode_production_btn")
    def on_mode_production(self) -> None:
        self.active_mode = "production"
        self._refresh_ui_state()

    def action_toggle_recording(self) -> None:
        if self.mgr.is_recording:
            # Stop recording
            ok, msg = self.mgr.stop_recording()
            self.app.notify(msg, timeout=3.0)
            self._refresh_ui_state()
            return

        # Start recording
        inp = self.query_one("#session_name_input", LivewireSessionInput)
        raw_name = inp.value.strip()
        if not raw_name:
            self.app.notify("please name your livewire session", severity="error", timeout=4.0)
            return

        val_ok, err, folder, filename = self._check_name_and_collision(raw_name)
        if not val_ok:
            return

        mode = self.active_mode or "studies"
        ok, msg = self.mgr.start_recording(raw_name, mode)
        if ok:
            self.app.notify(f"LiveWire recording started! [{mode.upper()}]", timeout=3.0)
        else:
            self.app.notify(msg, severity="error", timeout=4.0)
        self._refresh_ui_state()

    @on(Button.Pressed, "#record_btn")
    def on_record_pressed(self) -> None:
        self.action_toggle_recording()

    @on(Button.Pressed, "#snapshot_btn")
    def action_snapshot(self) -> None:
        if not self.mgr.is_connected:
            self.app.notify("Nomad Sculpt link must be active to capture snapshot.", severity="warning", timeout=4.0)
            return

        inp = self.query_one("#session_name_input", LivewireSessionInput)
        raw_name = inp.value.strip()
        if not raw_name:
            self.app.notify("please name your livewire session", severity="error", timeout=4.0)
            return

        val_ok, err, folder, filename = validate_session_name(raw_name)
        if not val_ok:
            self.app.notify(err, severity="error", timeout=4.0)
            return

        self.mgr.current_session_name = raw_name
        self.mgr.current_mode = self.active_mode or "studies"
        ok, msg = self.mgr.in_progress_snapshot()
        if ok:
            self.app.notify(f"In-Progress Snapshot saved: '{folder}/{filename}'", timeout=4.0)
            # Reset modal fields fresh
            inp.value = ""
            self.active_mode = None
            self.mgr.current_session_name = ""
        else:
            self.app.notify(msg, severity="error", timeout=4.0)
        self._refresh_ui_state()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel_session(self) -> None:
        inp = self.query_one("#session_name_input", LivewireSessionInput)
        raw_name = inp.value.strip() or self.mgr.current_session_name
        if not raw_name:
            self.app.notify("No active session name to cancel.", severity="warning", timeout=3.0)
            return

        self.mgr.current_session_name = raw_name
        self.mgr.current_mode = self.active_mode or "studies"
        ok, msg = self.mgr.cancel_current_session()
        if ok:
            self.app.notify(f"Livewire session '{raw_name}' cancelled and scrubbed from disk.", timeout=4.0)
            inp.value = ""
            self.active_mode = None
            self.mgr.current_session_name = ""
        else:
            self.app.notify(msg, severity="error", timeout=4.0)
        self._refresh_ui_state()

    @on(Button.Pressed, "#finalize_btn")
    def action_finalize_session(self) -> None:
        if not self.mgr.is_connected:
            self.app.notify("please open the file from your session on your local machine again before clicking finalize", severity="warning", timeout=5.0)
            return

        inp = self.query_one("#session_name_input", LivewireSessionInput)
        raw_name = inp.value.strip() or self.mgr.current_session_name
        if not raw_name:
            self.app.notify("please name your livewire session", severity="error", timeout=4.0)
            return

        val_ok, err, folder, filename = validate_session_name(raw_name)
        if not val_ok:
            self.app.notify(err, severity="error", timeout=4.0)
            return

        mode = self.active_mode or "studies"
        self.mgr.current_session_name = raw_name
        self.mgr.current_mode = mode

        ok, msg, audit = self.mgr.finalize_current_session()
        if ok:
            self.app.notify(msg, timeout=5.0)
            inp.value = ""
            self.mgr.current_session_name = ""
            self.dismiss()
        else:
            self.app.notify(msg, severity="warning", timeout=6.0)
        self._refresh_ui_state()

    def action_dismiss_modal(self) -> None:
        self.dismiss()

    async def _on_key(self, event: events.Key) -> None:
        key = event.key.lower()
        if self._c_c_prefix:
            self._c_c_prefix = False
            if key == "l":
                event.prevent_default()
                event.stop()
                self.dismiss()
                return
        if key == "ctrl+c":
            self._c_c_prefix = True
            event.prevent_default()
            event.stop()
            return
        await super()._on_key(event)
