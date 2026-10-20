"""Unit tests for Vault interactive modal screens and dashboard."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from textual.app import App
from textual.widgets import Checkbox, Input, TextArea

from gemini_app import vault
from gemini_app.ui.modals.vault import (
    VaultAuthModal,
    VaultChangePasskeyModal,
    VaultDashboardModal,
    VaultFileEntryModal,
    VaultPasswordEntryModal,
    VaultSecretEntryModal,
)


class ModalTestHarness(App[None]):
    """Generic test harness for mounting any vault modal."""

    def __init__(self, modal) -> None:
        super().__init__()
        self._test_modal = modal
        self.dismissed_result = "NOT_CALLED"

    def on_mount(self) -> None:
        def _cb(res) -> None:
            self.dismissed_result = res
        self.push_screen(self._test_modal, _cb)


class TestVaultModals(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_dir = Path(self.temp_dir.name) / "vault"
        self.state_file = Path(self.temp_dir.name) / "state.json"
        self.meta_file = self.vault_dir / ".vault_meta.json"
        self.passwords_dir = self.vault_dir / "passwords"
        self.secrets_dir = self.vault_dir / "secrets"
        self.files_dir = self.vault_dir / "files"

        self.p_vault = patch("gemini_app.vault.VAULT_DIR", self.vault_dir)
        self.p_meta = patch("gemini_app.vault.VAULT_META_FILE", self.meta_file)
        self.p_state = patch("gemini_app.vault.STATE_FILE", self.state_file)
        self.p_pass = patch("gemini_app.vault.PASSWORDS_DIR", self.passwords_dir)
        self.p_sec = patch("gemini_app.vault.SECRETS_DIR", self.secrets_dir)
        self.p_files = patch("gemini_app.vault.FILES_DIR", self.files_dir)

        self.p_vault.start()
        self.p_meta.start()
        self.p_state.start()
        self.p_pass.start()
        self.p_sec.start()
        self.p_files.start()

        vault.clear_session_passkey()
        vault.set_vault_passkey("test_passkey_123")

    def tearDown(self):
        vault.clear_session_passkey()
        self.p_files.stop()
        self.p_sec.stop()
        self.p_pass.stop()
        self.p_state.stop()
        self.p_meta.stop()
        self.p_vault.stop()
        self.temp_dir.cleanup()

    async def test_vault_auth_modal_success(self):
        modal = VaultAuthModal(reason="Decrypt PyPI token for package upload")
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            inp = modal.query_one("#vault_auth_input", Input)
            inp.value = "test_passkey_123"
            await pilot.click("#vault_auth_submit")
            await pilot.pause()
            self.assertEqual(app.dismissed_result, "test_passkey_123")
            self.assertTrue(vault.is_session_unlocked())

    async def test_vault_auth_modal_incorrect_passkey(self):
        vault.clear_session_passkey()
        modal = VaultAuthModal(reason="Testing bad key")
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            inp = modal.query_one("#vault_auth_input", Input)
            inp.value = "wrong_password"
            await pilot.click("#vault_auth_submit")
            await pilot.pause()
            self.assertEqual(app.dismissed_result, "NOT_CALLED")
            self.assertFalse(vault.is_session_unlocked())

    async def test_vault_change_passkey_mismatch_fails(self):
        modal = VaultChangePasskeyModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            modal.query_one("#curr_pass", Input).value = "test_passkey_123"
            modal.query_one("#new_pass", Input).value = "new_secret_123"
            modal.query_one("#confirm_pass", Input).value = "mismatched_secret"
            await pilot.click("#rotate_submit")
            await pilot.pause()
            self.assertEqual(app.dismissed_result, "NOT_CALLED")
            # Old passkey still valid
            self.assertTrue(vault.verify_vault_passkey("test_passkey_123"))

    async def test_vault_change_passkey_2x_confirmation_succeeds(self):
        modal = VaultChangePasskeyModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            modal.query_one("#curr_pass", Input).value = "test_passkey_123"
            modal.query_one("#new_pass", Input).value = "new_secret_confirmed"
            modal.query_one("#confirm_pass", Input).value = "new_secret_confirmed"
            await pilot.click("#rotate_submit")
            await pilot.pause()
            self.assertEqual(app.dismissed_result, True)
            self.assertTrue(vault.verify_vault_passkey("new_secret_confirmed"))

    async def test_vault_password_entry_modal(self):
        modal = VaultPasswordEntryModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            modal.query_one("#pass_title", Input).value = "GitHub Account"
            modal.query_one("#pass_user", Input).value = "octocat"
            modal.query_one("#pass_val", Input).value = "ghp_secure_pass_456"
            modal.query_one("#pass_notes", Input).value = "2FA enabled on mobile"
            await pilot.click("#pass_save")
            await pilot.pause()

            self.assertIsInstance(app.dismissed_result, dict)
            self.assertEqual(app.dismissed_result.get("title"), "GitHub Account")

            # Check that password was encrypted in storage
            retrieved = vault.get_password("GitHub Account", passkey="test_passkey_123")
            self.assertEqual(retrieved["password"], "ghp_secure_pass_456")

    async def test_vault_secret_entry_modal(self):
        modal = VaultSecretEntryModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            modal.query_one("#sec_title", Input).value = "Production Webhook"
            modal.query_one("#sec_val", TextArea).text = "whsec_999888777666555444"
            await pilot.click("#sec_save")
            await pilot.pause()

            self.assertIsInstance(app.dismissed_result, dict)
            retrieved = vault.get_secret("Production Webhook", passkey="test_passkey_123")
            self.assertEqual(retrieved["secret"], "whsec_999888777666555444")

    async def test_vault_file_entry_modal(self):
        # Create temp file to encrypt
        sample = Path(self.temp_dir.name) / "db_creds.env"
        sample.write_text("DB_PASS=production_vault_99\n", encoding="utf-8")

        modal = VaultFileEntryModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            modal.query_one("#file_title", Input).value = "Database Env"
            modal.query_one("#file_path_input", Input).value = str(sample)
            modal.query_one("#file_shred_check", Checkbox).value = False
            await pilot.click("#file_save")
            await pilot.pause()

            self.assertIsInstance(app.dismissed_result, dict)
            files = vault.list_categorized_files(passkey="test_passkey_123")
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["title"], "Database Env")

    async def test_vault_dashboard_modal(self):
        # Store items
        vault.store_password("Email", "pw123", username="test@test.com", passkey="test_passkey_123")
        vault.store_secret("Key", "sec123", passkey="test_passkey_123")

        modal = VaultDashboardModal()
        app = ModalTestHarness(modal)
        async with app.run_test(size=(100, 35)) as pilot:
            # Check cards rendered
            self.assertIn("Email", [p["title"] for p in vault.list_passwords(passkey="test_passkey_123")])

            # Lock vault via lock button
            await pilot.click("#dash_lock")
            await pilot.pause()
            self.assertFalse(vault.is_session_unlocked())


if __name__ == "__main__":
    unittest.main()
