"""Unit tests for Bilateral Console Dual Status Bar (#feed_status & #runner_status)."""

import unittest
from unittest.mock import MagicMock
from textual.app import App, ComposeResult
from textual.widgets import Static

from gemini_app.ui.app import ChatApp


class TestDualStatusBar(unittest.IsolatedAsyncioTestCase):
    async def test_dual_status_widgets_exist_and_operate_independently(self):
        app = ChatApp()
        async with app.run_test() as pilot:
            feed_status = app.query_one("#feed_status", Static)
            runner_status = app.query_one("#runner_status", Static)

            # Initially hidden
            self.assertEqual(feed_status.styles.display, "none")
            self.assertEqual(runner_status.styles.display, "none")

            # Update Gemini status
            app.set_status_text("⠋ AI Thinking...")
            self.assertEqual(feed_status.styles.display, "block")
            self.assertEqual(runner_status.styles.display, "none")

            # Update Runner status
            app.set_runner_status_text("⚡ [gemini-runner:blender] Compiling...")
            self.assertEqual(feed_status.styles.display, "block")
            self.assertEqual(runner_status.styles.display, "block")

            # Hide Gemini status, runner status remains visible
            app.hide_status()
            self.assertEqual(feed_status.styles.display, "none")
            self.assertEqual(runner_status.styles.display, "block")

            # Hide runner status
            app.hide_runner_status()
            self.assertEqual(feed_status.styles.display, "none")
            self.assertEqual(runner_status.styles.display, "none")


if __name__ == "__main__":
    unittest.main()
