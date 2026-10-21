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

    async def test_password_modal_salted_file_access(self):
        """Verifies that passkey submitted via PasswordModal successfully decrypts a salted payload."""
        from gemini_app.vault import encrypt_bytes, decrypt_bytes

        secret_data = b"INTEGRITY_CHECK_OK: salted-vault-node-payload-42"
        test_passkey = "S3cur3P@ssw0rd!2025"

        # Encrypt with PBKDF2-HMAC-SHA256 salt
        encrypted_salted_file = encrypt_bytes(secret_data, test_passkey)
        self.assertTrue(
            encrypted_salted_file.startswith(b"F1:") or encrypted_salted_file.startswith(b"S1:"),
            "Payload must contain salted format header",
        )

        modal = PasswordModal(
            title="🔐 Salted File Decryption Test",
            message="Enter passkey to decrypt test file:",
        )
        app = PasswordModalTestApp(modal)
        async with app.run_test(size=(100, 30)) as pilot:
            inp = modal.query_one("#password_input", Input)
            inp.value = test_passkey
            await pilot.click("#password_submit_btn")
            await pilot.pause()

            # Verify passkey returned
            self.assertEqual(app.dismissed_result, test_passkey)

            # Access and decrypt salted file
            decrypted = decrypt_bytes(encrypted_salted_file, app.dismissed_result)
            self.assertEqual(decrypted, secret_data)

            # Verify invalid passkey fails integrity check
            with self.assertRaises((ValueError, Exception)):
                decrypt_bytes(encrypted_salted_file, "wrong_password_attempt")



if __name__ == "__main__":
    unittest.main()
