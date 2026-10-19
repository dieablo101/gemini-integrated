"""UI Smoke and Integration Tests for Gemini Textual App."""

import asyncio
import unittest
from gemini_app.ui.app import ChatApp
from gemini_app.ui.boot import BootScreen
from gemini_app.ui.modals.commands import CommandsModal
from textual.widgets import Static


class TestUIApp(unittest.IsolatedAsyncioTestCase):
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
