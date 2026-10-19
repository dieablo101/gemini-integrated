"""Unit tests for PasswordModal and password prompt flow."""

import unittest
from textual.app import App
from textual.widgets import Input

from gemini_app.ui.modals.password import PasswordModal, PasswordPromptModal


class PasswordModalTestApp(App[None]):
    """Test harness for mounting PasswordModal."""

    def __init__(self, modal: PasswordModal) -> None:
        super().__init__()
        self._test_modal = modal
        self.dismissed_result = "NOT_CALLED"

    def on_mount(self) -> None:
        def _cb(res: str | None) -> None:
            self.dismissed_result = res
        self.push_screen(self._test_modal, _cb)


class TestPasswordModal(unittest.IsolatedAsyncioTestCase):
    """Verifies PasswordModal rendering, masked input, submit, and cancel actions."""

    async def test_modal_composition_and_input_masking(self):
        modal = PasswordModal(
            title="Test Authentication",
            message="Enter secret passkey:",
            placeholder="test-placeholder",
        )
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            inp = modal.query_one("#password_input", Input)
            self.assertTrue(inp.password, "Input must have password=True to mask text")
            self.assertEqual(inp.placeholder, "test-placeholder")
            self.assertEqual(modal.dialog_title, "Test Authentication")

    async def test_modal_submission(self):
        modal = PasswordModal()
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            inp = modal.query_one("#password_input", Input)
            inp.value = "my_super_secret_123"
            await pilot.click("#password_submit_btn")
            await pilot.pause()
            self.assertEqual(app.dismissed_result, "my_super_secret_123")

    async def test_modal_cancellation(self):
        modal = PasswordModal()
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.click("#password_cancel_btn")
            await pilot.pause()
            self.assertIsNone(app.dismissed_result)

    async def test_modal_escape_key_cancel(self):
        modal = PasswordModal()
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsNone(app.dismissed_result)

    async def test_modal_empty_rejected_when_not_allowed(self):
        modal = PasswordModal(allow_empty=False)
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            inp = modal.query_one("#password_input", Input)
            inp.value = ""
            await pilot.click("#password_submit_btn")
            await pilot.pause()
            # Modal should not dismiss
            self.assertEqual(app.dismissed_result, "NOT_CALLED")

    async def test_alias_compatibility(self):
        self.assertIs(PasswordPromptModal, PasswordModal)


if __name__ == "__main__":
    unittest.main()
