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
            # Make sure it's broken across lines
            self.assertNotIn("gemini-integrated", render_text)

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
            await app.workers.wait_for_complete()
            self.assertFalse(app.notes_open)
            app.action_toggle_notes()
            await app.workers.wait_for_complete()
            self.assertTrue(app.notes_open)

    async def test_commands_modal(self):
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_commands_modal()
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandsModal)
            app.pop_screen()
            await pilot.pause()

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
