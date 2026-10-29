"""Unit tests for LiveWire Modals and Slash Commands."""

import os
import sys
import unittest
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Label

from gemini_app.ui.modals.live_wire_modal import (
    LivewireSessionInput,
    LiveWireModal,
)
from gemini_app.ui.modals.live_wire_settings import LiveWireSettingsModal
from live_wire_engine import (
    LiveWireSessionManager,
    validate_session_name,
    cancel_and_scrub_session,
    STUDIES_ROOT,
    PRODUCTION_ROOT
)


class TestLiveWireInputApp(App):
    def __init__(self, mode: str = "studies"):
        super().__init__()
        self.mode = mode
        self.input_widget = None

    def compose(self) -> ComposeResult:
        self.input_widget = LivewireSessionInput(
            mode_getter=lambda: self.mode,
            id="session_input"
        )
        yield self.input_widget


class TestLiveWireModalApp(App):
    def compose(self) -> ComposeResult:
        yield Label("Base Screen")


class TestLiveWireUI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mgr = LiveWireSessionManager.get_instance()
        self.mgr.current_session_name = ""
        self.mgr.is_recording = False
        self.mgr.is_connected = False

    def test_session_name_validation_rules(self):
        # 1. Reject without subfolder
        ok, err, f, fn = validate_session_name("pirate")
        self.assertFalse(ok)
        self.assertIn("must add subfolder", err)

        # 2. Reject empty
        ok, err, f, fn = validate_session_name("")
        self.assertFalse(ok)
        self.assertIn("please name your livewire session", err)

        # 3. Accept valid folder/filename
        ok, err, f, fn = validate_session_name("creatures/alien_stalker")
        self.assertTrue(ok)
        self.assertEqual(f, "creatures")
        self.assertEqual(fn, "alien_stalker")

    async def test_livewire_session_input_tab_autocomplete(self):
        test_folder = STUDIES_ROOT / "test_alien"
        test_folder.mkdir(parents=True, exist_ok=True)
        try:
            app = TestLiveWireInputApp(mode="studies")
            async with app.run_test() as pilot:
                inp = app.query_one("#session_input", LivewireSessionInput)
                inp.value = "test_al"
                await pilot.press("tab")
                self.assertEqual(inp.value, "test_alien/")
        finally:
            if test_folder.exists():
                test_folder.rmdir()

    async def test_livewire_modals_lifecycle_in_app(self):
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            # Push Settings Modal
            settings_modal = LiveWireSettingsModal()
            await app.push_screen(settings_modal)
            self.assertIsInstance(app.screen, LiveWireSettingsModal)
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, LiveWireSettingsModal)

            # Push LiveWire Cockpit Modal
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)
            self.assertIsInstance(app.screen, LiveWireModal)

            # Check subfolder gate
            val_ok, err, _, _ = cockpit._check_name_and_collision("nakedfilename")
            self.assertFalse(val_ok)
            self.assertIn("must add subfolder", err)

            # Dismiss cockpit
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, LiveWireModal)

    async def test_active_session_pause_resume_and_snapshot_restore(self):
        """Verifies active session immunity, snapshot auto-sync on pause, and restore trigger."""
        import numpy as np
        import shutil
        from live_wire_engine import (
            LiveWireSessionManager,
            LiveSculptTwin,
            save_in_progress_snapshot,
            check_in_progress_snapshot_exists,
            check_snapshot_off_sync,
            restore_snapshot_for_device,
            get_session_dir
        )

        mgr = LiveWireSessionManager.get_instance()
        test_session = "test_guard/test_alien"
        s_dir = get_session_dir("studies", "test_guard", "test_alien")
        if s_dir.exists():
            shutil.rmtree(s_dir)

        # 1. Start recording
        ok, msg = mgr.start_recording(test_session, "studies")
        self.assertTrue(ok)
        self.assertTrue(mgr.is_recording)

        # 2. Pause recording
        ok, msg = mgr.stop_recording()
        self.assertTrue(ok)
        self.assertFalse(mgr.is_recording)

        # 3. Active Session Immunity: resume recording immediately without collision error
        ok, msg = mgr.start_recording(test_session, "studies")
        self.assertTrue(ok, f"Expected active session immunity but got error: {msg}")
        self.assertTrue(mgr.is_recording)

        # Setup mock twin with geometry
        twin = LiveSculptTwin(sculpt_id="alien_sculpt")
        twin.positions = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]])
        twin.faces = [[0, 1, 2]]
        mgr.engine.twin = twin

        # 4. Save in-progress snapshot
        meta_p = save_in_progress_snapshot("studies", "test_guard", "test_alien", twin, None)
        self.assertTrue(meta_p.exists())
        self.assertTrue(check_in_progress_snapshot_exists("studies", "test_guard", "test_alien"))

        # Snapshot in-sync check
        self.assertFalse(check_snapshot_off_sync("studies", "test_guard", "test_alien", twin))

        # 5. Simulate accidental brush stroke divergence (off-sync)
        diverged_twin = LiveSculptTwin(sculpt_id="alien_sculpt")
        diverged_twin.positions = np.array([[0.0, 1.5, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        diverged_twin.faces = [[0, 1, 2], [0, 2, 3]]
        mgr.engine.twin = diverged_twin

        # Verify auto-detection identifies off-sync divergence!
        self.assertTrue(check_snapshot_off_sync("studies", "test_guard", "test_alien", diverged_twin))

        # 6. Test restore snapshot generates restored .nom and .obj files
        r_ok, r_msg, r_name = restore_snapshot_for_device("studies", "test_guard", "test_alien")
        self.assertTrue(r_ok)
        self.assertEqual(r_name, "test_alien")
        self.assertTrue((s_dir / "restored" / "test_alien.nom").exists())
        self.assertTrue((s_dir / "restored" / "test_alien.obj").exists())

        # Cleanup
        mgr.stop_recording()
        if s_dir.exists():
            shutil.rmtree(s_dir)

    async def test_checkbox_session_type_selection(self):
        """Verifies session type checkboxes default to studies and toggle mutually exclusively."""
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)

            studies_cb = cockpit.query_one("#mode_studies_check", Checkbox)
            prod_cb = cockpit.query_one("#mode_production_check", Checkbox)

            # Default must be studies checked, production unchecked
            self.assertTrue(studies_cb.value)
            self.assertFalse(prod_cb.value)
            self.assertEqual(cockpit.active_mode, "studies")

            # Check production
            prod_cb.value = True
            await pilot.pause()
            self.assertFalse(studies_cb.value)
            self.assertTrue(prod_cb.value)
            self.assertEqual(cockpit.active_mode, "production")

            # Check studies again
            studies_cb.value = True
            await pilot.pause()
            self.assertTrue(studies_cb.value)
            self.assertFalse(prod_cb.value)
            self.assertEqual(cockpit.active_mode, "studies")

            await pilot.press("escape")

    async def test_record_time_collision_and_snapshot_sync_gates(self):
        """Tests deferred checking: no premature check while typing; strict gate on record."""
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)

            # 1. Existing session with NO snapshot (testing/testing2 in studies)
            cockpit.active_mode = "studies"
            ok, msg, f, fn = cockpit._check_name_and_collision("testing/testing2")
            self.assertFalse(ok)
            self.assertEqual(msg, "session already exists with no saved snapshot")

            # 2. Switch to production mode -> testing/testing2 does NOT exist under production
            cockpit.active_mode = "production"
            ok_prod, msg_prod, f_p, fn_p = cockpit._check_name_and_collision("testing/testing2")
            self.assertTrue(ok_prod)
            self.assertEqual(msg_prod, "")

            # 3. Existing session WITH snapshot (testing/testing in studies)
            cockpit.active_mode = "studies"
            # If off-sync:
            import numpy as np
            from live_wire_engine import LiveSculptTwin
            twin = LiveSculptTwin("mismatch")
            twin.positions = np.array([[100.0, 100.0, 100.0]])
            twin.faces = []
            cockpit.mgr.engine.twin = twin

            ok_snap, msg_snap, _, _ = cockpit._check_name_and_collision("testing/testing")
            self.assertFalse(ok_snap)
            self.assertIn("your snapshot is offsync", msg_snap)
            self.assertEqual(cockpit.query_one("#snapshot_btn").label, "Restore Snapshot")

            await pilot.press("escape")

    async def test_scan_session_fills_cockpit_and_toast_if_nonexistent(self):
        """Tests Scan button next to session name: fills cockpit with data & records, toasts if nonexistent."""
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)

            # 1. Verify Scan button exists
            scan_btn = cockpit.query_one("#scan_session_btn")
            self.assertIsNotNone(scan_btn)
            self.assertEqual(scan_btn.label, "Scan")

            # 2. Scan nonexistent session -> notifications contain 'no such session exists on disk yet'
            inp = cockpit.query_one("#session_name_input", LivewireSessionInput)
            inp.value = "nonexistent/ghost_session"
            await pilot.click("#scan_session_btn")
            await pilot.pause()

            # Verify notification
            notifs = [n.message for n in app._notifications]
            self.assertTrue(any("no such session exists on disk yet" in str(msg) for msg in notifs))

            # 3. Scan existing session with telemetry & records (testing/testing)
            inp.value = "testing/testing"
            await pilot.click("#scan_session_btn")
            await pilot.pause()

            # Cockpit should be filled with accurate data from disk
            self.assertGreater(cockpit.mgr.engine.twin.vertex_count, 0)
            self.assertEqual(cockpit.mgr.engine.stats.total_strokes, 7)
            self.assertGreaterEqual(len(cockpit.mgr.verification_events), 3)

            # Verification reel labels should reflect loaded records
            hist_1 = cockpit.query_one("#hist_event_1", Label)
            card_title = cockpit.query_one("#recent_card_title", Label)
            self.assertNotIn("Standby - Waiting for first stroke", str(hist_1.render()))
            self.assertNotIn("✦ MOST RECENT EVENT (STANDBY)", str(card_title.render()))

            await pilot.press("escape")

    async def test_open_full_view_image_button_and_action(self):
        """Verifies that the Open Full View Image button and 'o' binding exist and function."""
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)
            await pilot.pause()

            # 1. Verify Open Full View Image button exists
            open_btn = cockpit.query_one("#open_image_btn")
            self.assertIsNotNone(open_btn)
            self.assertIn("Open Full View Image", str(open_btn.label))

            # 2. Verify 'o' binding exists
            binding_keys = [b.key for b in cockpit.BINDINGS]
            self.assertIn("o", binding_keys)

            # 3. Trigger action when no image exists -> warning notification
            cockpit.action_open_full_view_image()
            await pilot.pause()
            notifs = [n.message for n in app._notifications]
            self.assertTrue(any("No snapshot image available" in str(msg) or "Launched viewer" in str(msg) for msg in notifs))

            await pilot.press("escape")

    async def test_play_audio_button_non_blocking(self):
        """Verifies play audio button executes asynchronously without freezing event loop."""
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)
            await pilot.pause()

            # Load testing/testing session
            cockpit.mgr.load_session_from_disk("studies", "testing", "testing")
            cockpit._refresh_ui_state()
            play_btn = cockpit.query_one("#play_audio_btn")
            self.assertFalse(play_btn.disabled)

            # Trigger play button pressed - must not raise or hang event loop
            cockpit.on_play_audio_pressed()
            await pilot.pause()

            notifs = [n.message for n in app._notifications]
            self.assertTrue(any("Dispatching headphone audio" in str(msg) or "Playing" in str(msg) for msg in notifs))

            await pilot.press("escape")


if __name__ == "__main__":
    unittest.main()
