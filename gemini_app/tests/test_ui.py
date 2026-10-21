"""UI Smoke and Integration Tests for Gemini Textual App."""

import asyncio
from pathlib import Path
import tempfile
import unittest
import gemini_app.config
from gemini_app.tools import snapshots
from gemini_app.ui.app import ChatApp
from gemini_app.ui.boot import BootScreen
from gemini_app.ui.modals.commands import CommandsModal
from textual.widgets import Static


class TestUIApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_screenshots_dir = tempfile.TemporaryDirectory()
        self.screenshots_path = Path(self.temp_screenshots_dir.name)

        self.orig_screenshots_dir = snapshots.SCREENSHOTS_DIR
        self.orig_index_file = snapshots.INDEX_FILE
        self.orig_config_screenshots = gemini_app.config.SCREENSHOTS_DIR

        snapshots.SCREENSHOTS_DIR = self.screenshots_path
        snapshots.INDEX_FILE = self.screenshots_path / "snapshots_index.json"
        gemini_app.config.SCREENSHOTS_DIR = self.screenshots_path

    def tearDown(self):
        try:
            snapshots.cleanup_test_snapshots()
        except Exception:
            pass
        snapshots.SCREENSHOTS_DIR = self.orig_screenshots_dir
        snapshots.INDEX_FILE = self.orig_index_file
        gemini_app.config.SCREENSHOTS_DIR = self.orig_config_screenshots
        self.temp_screenshots_dir.cleanup()
    async def test_boot_screen_desktop_display(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            boot_screen = app.screen
            self.assertIsInstance(boot_screen, BootScreen)
            title_widget = boot_screen.query_one("#boot_title_widget", Static)
            render_text = str(title_widget.content)
            self.assertIn("gemini-integrated", render_text)
            self.assertIn("█", render_text)
            self.assertIn("░", render_text)
            self.assertFalse(boot_screen.has_class("-mobile"))

    async def test_boot_screen_mobile_display(self):
        app = ChatApp()
        async with app.run_test(size=(60, 30)) as pilot:
            await pilot.pause()
            boot_screen = app.screen
            self.assertIsInstance(boot_screen, BootScreen)
            self.assertTrue(boot_screen.has_class("-mobile"))
            title_widget = boot_screen.query_one("#boot_title_widget", Static)
            render_text = str(title_widget.content)
            self.assertIn("gemini", render_text)
            self.assertIn("integrated", render_text)
            self.assertIn("█", render_text)
            self.assertIn("░", render_text)
            # Make sure it's broken across lines
            self.assertNotIn("gemini-integrated", render_text)

    def test_block_typography_and_shadow_generation(self):
        from gemini_app.ui.boot import render_block_text_with_shadow, lerp_color

        # Test color lerping
        self.assertEqual(lerp_color("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(lerp_color("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(lerp_color("#000000", "#ffffff", 0.5), "#7f7f7f")

        # Test block rendering
        lines = render_block_text_with_shadow("GEMINI", frame_idx=0, acc="#dc2626", acc_bright="#ffffff", acc_dim="#4a0000")
        self.assertEqual(len(lines), 4)  # 3 text rows + 1 shadow baseline row
        # Check presence of block characters and stippled shadow
        combined = "\n".join(lines)
        self.assertIn("█", combined)
        self.assertIn("▀", combined)
        self.assertIn("░", combined)

    async def test_boot_screen_auto_dismiss(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, BootScreen)
            # Fast-forward / wait for boot screen duration
            await asyncio.sleep(2.1)
            await pilot.pause()
            # Once dismissed, the active screen is the base screen (ChatApp)
            self.assertNotIsInstance(app.screen, BootScreen)

    async def test_app_lifecycle_and_mount(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertIsNotNone(app.screen)
            # Verify critical UI components are mounted
            feed = app.query_one("#feed")
            self.assertIsNotNone(feed)
            notes_panel = app.query_one("#notes_panel")
            self.assertIsNotNone(notes_panel)
            input_widget = app.query_one("#input")
            self.assertIsNotNone(input_widget)

    async def test_notes_toggle(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Dismiss boot screen so interval timer stops
            await pilot.press("space")
            await app.workers.wait_for_complete()
            self.assertFalse(app.notes_open)

            # 1. First toggle open
            app.action_toggle_notes()
            await app.workers.wait_for_complete()
            self.assertTrue(app.notes_open)

            # Verify no worker errors occurred
            worker_errors = [w.error for w in app.workers if w.error is not None]
            self.assertEqual(worker_errors, [])

            # 2. Switch filters across modes
            notes_panel = app.query_one("#notes_panel")
            for mode in ("relevant", "get_back_to", "think_about", "topics", "working"):
                notes_panel.switch_filter(mode)

            # 3. Toggle closed
            app.action_toggle_notes()
            await app.workers.wait_for_complete()
            self.assertFalse(app.notes_open)

            # 4. Toggle open again (verifying no duplicate ID collisions on remount)
            app.action_toggle_notes()
            await app.workers.wait_for_complete()
            self.assertTrue(app.notes_open)

            worker_errors = [w.error for w in app.workers if w.error is not None]
            self.assertEqual(worker_errors, [])

    async def test_commands_modal(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("space")
            app.action_open_commands_modal()
            self.assertIsInstance(app.screen, CommandsModal)
            app.pop_screen()

    async def test_reboot_status_report_toast(self):
        app = ChatApp()
        # Simulate reboot report stored in state
        app._save_to_state("pending_reboot_report", "✓ Test Reboot Complete: 100% operational.")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            # Verify the reboot report was consumed and cleared
            cleared_report = app._read_and_clear_reboot_report()
            self.assertIsNone(cleared_report, "Pending reboot report should be cleared after mount")
            # Verify post-reboot snapshot was created
            from gemini_app.tools.snapshots import get_snapshot_index
            index = get_snapshot_index()
            audit_entries = [e for e in index if e.get("label") == "post_reboot_audit"]
            self.assertTrue(len(audit_entries) >= 1, "Expected post_reboot_audit snapshot entry")
            # Verify post-reboot status message was injected directly into active chat feed
            self.assertEqual(len(app.history), 1)
            self.assertEqual(app.history[0]["role"], "model")
            self.assertIn("✓ Test Reboot Complete: 100% operational.", app.history[0]["text"])

    async def test_nav_indicator_and_accent_talk(self):
        from gemini_app.introspection import apply_accent_talk
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("space")

            # Test direct trigger_nav_indicator
            app.trigger_nav_indicator("edge_home", toast_message="▲ Test edge top", duration=0.2)
            self.assertEqual(app._nav_indicator_action, "edge_home")
            banner = app.query_one("#feed_nav_banner", Static)
            self.assertIn("Home", str(banner.content))

            # Test apply_accent_talk with nav indicator target
            res = apply_accent_talk(app, target="edge", palette="green", duration=0.2, message="At the edge!")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["target"], "edge")
            self.assertEqual(app._nav_indicator_action, "edge")

    async def test_git_setup_modal_flow(self):
        from gemini_app.ui.modals.git_setup import GitSetupModal
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("space")  # dismiss boot
            app.action_configure_git()
            await pilot.pause()
            self.assertIsInstance(app.screen, GitSetupModal)
            modal = app.screen
            name_input = modal.query_one("#git_name_input")
            email_input = modal.query_one("#git_email_input")
            self.assertIsNotNone(name_input)
            self.assertIsNotNone(email_input)
            await pilot.click("#git_setup_cancel_btn")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, GitSetupModal)

    async def test_emergency_interrupt_action(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("space")
            # Put app into reconnecting phase
            app._request_phase = "reconnecting"
            app._reconnect_target_time = 999999.0
            app.lock.acquire("test")

            # Fire emergency interrupt
            app.action_emergency_interrupt()
            await pilot.pause()

            self.assertTrue(app._abort_requested)
            self.assertEqual(app._request_phase, "idle")
            self.assertEqual(app._reconnect_target_time, 0.0)
            self.assertFalse(app.lock.is_locked)

            # Test command registry dispatch
            self.assertIn("abort", app._commands_registry)
            self.assertIn("interrupt", app._commands_registry)
            self.assertIn("cancel", app._commands_registry)

    async def test_blank_message_prevention(self):
        from gemini_app.events import RequestFinished
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("space")
            init_turns = len(app.history)

            # Post a blank message RequestFinished
            app.post_message(RequestFinished("", 0.2, 0))
            await pilot.pause()

            self.assertEqual(len(app.history), init_turns + 1)
            last_turn = app.history[-1]
            self.assertTrue(bool(last_turn["text"].strip()))
            self.assertNotEqual(last_turn["text"].strip(), "")

