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
from textual.widgets import Button, Checkbox, Input, Label, Static

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
    is_session_finalized,
    check_in_progress_snapshot_exists,
    check_snapshot_off_sync,
    restore_snapshot_for_device,
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
        align-vertical: middle;
    }
    #mode_row_label {
        color: #bb55ff;
        text-style: bold;
        margin-right: 1;
        height: auto;
        align-vertical: middle;
    }
    #mode_studies_check, #mode_production_check {
        margin-right: 2;
        background: transparent;
        border: none;
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
    #verification_reel_container {
        width: 100%;
        height: auto;
        background: #090912;
        border: tall #2c1e40;
        padding: 0 1;
        margin-bottom: 1;
    }
    #reel_divider {
        color: #bb55ff;
        text-style: bold;
        margin-top: 1;
    }
    #event_history_list {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #event_history_list Label {
        color: #8899aa;
    }
    #most_recent_card {
        width: 100%;
        height: auto;
        background: #11111c;
        border: solid #442a66;
        padding: 1;
        margin-bottom: 1;
    }
    #recent_card_title {
        text-style: bold;
        color: #55ffaa;
        margin-bottom: 1;
    }
    #recent_card_content {
        width: 100%;
        height: auto;
    }
    #recent_snapshot_preview {
        width: 38;
        height: 14;
        background: #07070f;
        border: solid #222238;
        margin-right: 2;
    }
    #recent_meta_column {
        width: 1fr;
        height: auto;
        align-vertical: middle;
    }
    #recent_desc_label {
        color: #ffffff;
        text-style: bold;
        margin-bottom: 1;
    }
    #recent_audio_label {
        color: #ffaa33;
        margin-bottom: 1;
    }
    #play_audio_btn {
        background: #1e3328;
        color: #55ffaa;
        text-style: bold;
        min-width: 24;
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
        self._off_sync_notified: bool = False

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
                yield Label("Session Type:", id="mode_row_label")
                yield Checkbox("Studies", value=(self.active_mode == "studies"), id="mode_studies_check")
                yield Checkbox("Production", value=(self.active_mode == "production"), id="mode_production_check")

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

            with Vertical(id="verification_reel_container"):
                yield Label("── VERIFICATION & CHRONOLOGICAL REEL (LAST 3 EVENTS) ──────", id="reel_divider")
                with Vertical(id="event_history_list"):
                    yield Label("• [Event #1] Standby - Waiting for first stroke or voice monologue...", id="hist_event_1")
                    yield Label("• [Event #2] Standby", id="hist_event_2")
                with Vertical(id="most_recent_card"):
                    yield Label("✦ MOST RECENT EVENT (STANDBY)", id="recent_card_title")
                    with Horizontal(id="recent_card_content"):
                        yield Static("", id="recent_snapshot_preview")
                        with Vertical(id="recent_meta_column"):
                            yield Label("No gestures or voice captured yet in this session.", id="recent_desc_label")
                            yield Label("Audio: Standby", id="recent_audio_label")
                            yield Button("▶ Play Synced Audio (Headphones)", id="play_audio_btn")

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

        # 3. Mode checkboxes synchronization
        studies_cb = self.query_one("#mode_studies_check", Checkbox)
        prod_cb = self.query_one("#mode_production_check", Checkbox)
        if self.active_mode == "studies":
            if not studies_cb.value:
                studies_cb.value = True
            if prod_cb.value:
                prod_cb.value = False
        elif self.active_mode == "production":
            if not prod_cb.value:
                prod_cb.value = True
            if studies_cb.value:
                studies_cb.value = False

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

        # Update verification reel & chronological snapshots
        v_events = self.mgr.verification_events
        hist_1 = self.query_one("#hist_event_1", Label)
        hist_2 = self.query_one("#hist_event_2", Label)
        card_title = self.query_one("#recent_card_title", Label)
        snap_preview = self.query_one("#recent_snapshot_preview", Static)
        desc_label = self.query_one("#recent_desc_label", Label)
        audio_label = self.query_one("#recent_audio_label", Label)
        play_btn = self.query_one("#play_audio_btn", Button)

        if not v_events:
            hist_1.update("• [Event #1] Standby - Waiting for first stroke or voice monologue...")
            hist_2.update("• [Event #2] Standby")
            card_title.update("✦ MOST RECENT EVENT (STANDBY)")
            snap_preview.update("")
            desc_label.update("No gestures or voice captured yet in this session.")
            audio_label.update("Audio: Standby")
            play_btn.disabled = True
        else:
            if len(v_events) >= 3:
                e1 = v_events[-3]
                e2 = v_events[-2]
                hist_1.update(f"• [{e1.iso_time}] Event #{e1.event_id}: {e1.title} ── {e1.summary}")
                hist_2.update(f"• [{e2.iso_time}] Event #{e2.event_id}: {e2.title} ── {e2.summary}")
            elif len(v_events) == 2:
                e1 = v_events[-2]
                hist_1.update(f"• [{e1.iso_time}] Event #{e1.event_id}: {e1.title} ── {e1.summary}")
                hist_2.update("• [Session Initialized] Recording in progress...")
            else:
                hist_1.update("• [Prior Event] None (First event active)")
                hist_2.update("• [Session Initialized] Recording in progress...")

            recent = v_events[-1]
            card_title.update(f"✦ MOST RECENT: Event #{recent.event_id} ── {recent.title}")
            snap_preview.update(recent.snapshot_ansi_preview or "")
            desc_label.update(f"● {recent.summary}")

            if recent.audio_filename:
                audio_label.update(f"🎙 Synced Audio: {recent.audio_filename}")
                play_btn.disabled = False
                if recent.event_type == "stroke_chunk":
                    play_btn.label = "▶ Play Synced Audio (Headphones)"
                else:
                    play_btn.label = "▶ Play Audio Snippet (Headphones)"
            else:
                audio_label.update("🎙 Audio: Awaiting stream chunk...")
                play_btn.disabled = True

        # Snapshot button presentation: maintain neutral standby unless put into restore state
        snap_btn = self.query_one("#snapshot_btn", Button)
        if snap_btn.label != "Restore Snapshot":
            snap_btn.label = "In-Progress Snapshot"
            snap_btn.disabled = False
            snap_btn.styles.background = "#182230"
            snap_btn.styles.color = "#55aaff"

    @on(Button.Pressed, "#play_audio_btn")
    def on_play_audio_pressed(self) -> None:
        ok, msg = self.mgr.play_most_recent_audio()
        if ok:
            self.app.notify(msg, timeout=5.0)
        else:
            self.app.notify(msg, severity="warning", timeout=5.0)

    def _check_name_and_collision(self, session_name: str) -> tuple[bool, str, str, str]:
        mode = self.active_mode or "studies"
        val_ok, err, folder, filename = validate_session_name(session_name)
        if not val_ok:
            self.app.notify(err, severity="error", timeout=4.0)
            return False, err, "", ""

        # ACTIVE SESSION IMMUNITY: If this is the active session in this cockpit, permit freely
        if self.mgr.current_session_name == f"{folder}/{filename}":
            return True, "", folder, filename

        if check_session_collision(mode, folder, filename):
            snap_exists = check_in_progress_snapshot_exists(mode, folder, filename)
            if not snap_exists:
                finalized = is_session_finalized(mode, folder, filename)
                msg = "session already exists with no saved snapshot, and finalized" if finalized else "session already exists with no saved snapshot"
                self.app.notify(msg, severity="error", timeout=5.0)
                return False, msg, folder, filename
            else:
                # Check off-sync
                is_off_sync = False
                if self.mgr.engine and self.mgr.engine.twin and self.mgr.engine.twin.vertex_count > 0:
                    is_off_sync = check_snapshot_off_sync(mode, folder, filename, self.mgr.engine.twin)
                if is_off_sync:
                    snap_btn = self.query_one("#snapshot_btn", Button)
                    snap_btn.label = "Restore Snapshot"
                    snap_btn.styles.background = "#882233"
                    snap_btn.styles.color = "#ffdddd"
                    warn = "your snapshot is offsync with your local device, click restore snapshot"
                    self.app.notify(warn, severity="warning", timeout=6.0)
                    return False, warn, folder, filename

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

    @on(Checkbox.Changed, "#mode_studies_check")
    def on_studies_check(self, event: Checkbox.Changed) -> None:
        if event.value:
            prod_cb = self.query_one("#mode_production_check", Checkbox)
            if prod_cb.value:
                prod_cb.value = False
            self.active_mode = "studies"
        else:
            prod_cb = self.query_one("#mode_production_check", Checkbox)
            if not prod_cb.value:
                self.query_one("#mode_studies_check", Checkbox).value = True
                self.active_mode = "studies"
        self._refresh_ui_state()

    @on(Checkbox.Changed, "#mode_production_check")
    def on_production_check(self, event: Checkbox.Changed) -> None:
        if event.value:
            studies_cb = self.query_one("#mode_studies_check", Checkbox)
            if studies_cb.value:
                studies_cb.value = False
            self.active_mode = "production"
        else:
            studies_cb = self.query_one("#mode_studies_check", Checkbox)
            if not studies_cb.value:
                self.query_one("#mode_production_check", Checkbox).value = True
                self.active_mode = "production"
        self._refresh_ui_state()

    def action_toggle_recording(self) -> None:
        if self.mgr.is_recording:
            # Stop recording / Pause (auto-syncs progress to snapshot controller if snapshot active)
            ok, msg = self.mgr.stop_recording()
            self.app.notify(msg, timeout=3.0)
            self._refresh_ui_state()
            return

        # Start / Resume recording
        inp = self.query_one("#session_name_input", LivewireSessionInput)
        raw_name = inp.value.strip() or self.mgr.current_session_name
        if not raw_name:
            self.app.notify("please name your livewire session", severity="error", timeout=4.0)
            return

        val_ok, err, folder, filename = self._check_name_and_collision(raw_name)
        if not val_ok:
            return

        mode = self.active_mode or "studies"
        snap_exists = check_in_progress_snapshot_exists(mode, folder, filename)
        ok, msg = self.mgr.start_recording(raw_name, mode)
        if ok:
            if snap_exists:
                self.app.notify(f"Resuming LiveWire session from snapshot! [{mode.upper()}]", timeout=3.5)
            else:
                self.app.notify(f"LiveWire recording started! [{mode.upper()}]", timeout=3.0)
        else:
            self.app.notify(msg, severity="error", timeout=4.0)
        self._refresh_ui_state()

    @on(Button.Pressed, "#record_btn")
    def on_record_pressed(self) -> None:
        self.action_toggle_recording()

    @on(Button.Pressed, "#snapshot_btn")
    def action_snapshot(self) -> None:
        snap_btn = self.query_one("#snapshot_btn", Button)
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

        # Check if button is in "Restore Snapshot" state (recovering from accidental brush stroke)
        if snap_btn.label == "Restore Snapshot":
            ok, msg, restored_file = self.mgr.restore_snapshot_for_device(mode, folder, filename)
            if ok:
                toast_msg = f"snapshot restored and placed in your nomad projects folder as \"{restored_file}\""
                self.app.notify(toast_msg, timeout=6.0)
                self._off_sync_notified = False
            else:
                self.app.notify(msg, severity="error", timeout=5.0)
            self._refresh_ui_state()
            return

        # Normal snapshot capture
        if not self.mgr.is_connected:
            self.app.notify("Nomad Sculpt link must be active to capture snapshot.", severity="warning", timeout=4.0)
            return

        self.mgr.current_session_name = raw_name
        self.mgr.current_mode = mode
        ok, msg = self.mgr.in_progress_snapshot()
        if ok:
            self.app.notify(f"In-Progress Snapshot saved: '{folder}/{filename}'", timeout=4.0)
            self._off_sync_notified = False
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
