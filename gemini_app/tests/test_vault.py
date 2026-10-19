"""Unit tests for the local secure vault and passkey authentication."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gemini_app import vault


class TestVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_dir = Path(self.temp_dir.name) / "vault"
        self.state_file = Path(self.temp_dir.name) / "state.json"
        self.meta_file = self.vault_dir / ".vault_meta.json"

        self.p_vault = patch("gemini_app.vault.VAULT_DIR", self.vault_dir)
        self.p_meta = patch("gemini_app.vault.VAULT_META_FILE", self.meta_file)
        self.p_state = patch("gemini_app.vault.STATE_FILE", self.state_file)

        self.p_vault.start()
        self.p_meta.start()
        self.p_state.start()

    def tearDown(self):
        self.p_state.stop()
        self.p_meta.stop()
        self.p_vault.stop()
        self.temp_dir.cleanup()

    def test_vault_init(self):
        self.assertFalse(self.vault_dir.exists())
        res = vault.init_vault()
        self.assertTrue(self.vault_dir.is_dir())
        self.assertEqual(res, self.vault_dir)

    def test_set_and_verify_passkey(self):
        self.assertFalse(vault.is_vault_configured())
        self.assertFalse(vault.verify_vault_passkey("mypassword"))

        res = vault.set_vault_passkey("secret_passkey_123")
        self.assertEqual(res["status"], "success")
        self.assertTrue(vault.is_vault_configured())

        # Correct passkey verifies
        self.assertTrue(vault.verify_vault_passkey("secret_passkey_123"))

        # Incorrect passkey fails
        self.assertFalse(vault.verify_vault_passkey("wrong_passkey"))
        self.assertFalse(vault.verify_vault_passkey(""))

    def test_empty_passkey_rejected(self):
        res = vault.set_vault_passkey("   ")
        self.assertEqual(res["status"], "error")

    def test_store_and_retrieve_secret_encrypted(self):
        passkey = "super_vault_key"
        vault.set_vault_passkey(passkey)

        secret_data = "recovery-code-alpha-beta-gamma\nrecovery-code-1234"
        dest = vault.store_in_vault("recovery.txt", secret_data, passkey=passkey)
        self.assertTrue(dest.is_file())
        self.assertTrue(dest.name.endswith(".enc"))

        # Raw file on disk does NOT contain plaintext
        on_disk = dest.read_bytes()
        self.assertNotIn(b"recovery-code-alpha", on_disk)

        # Retrieve with correct passkey succeeds
        recovered = vault.retrieve_from_vault("recovery.txt", passkey)
        self.assertEqual(recovered.decode("utf-8"), secret_data)

        # Retrieve with incorrect passkey raises PermissionError
        with self.assertRaises(PermissionError):
            vault.retrieve_from_vault("recovery.txt", "wrong_key")

    def test_store_unencrypted(self):
        dest = vault.store_in_vault("plain.txt", "plain content")
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), "plain content")

    def test_retrieve_missing_file_raises(self):
        vault.set_vault_passkey("mypass")
        with self.assertRaises(FileNotFoundError):
            vault.retrieve_from_vault("non_existent.txt", "mypass")

    def test_list_vault_files(self):
        vault.set_vault_passkey("mypass")
        vault.store_in_vault("file_a.txt", "content a", passkey="mypass")
        vault.store_in_vault("file_b.txt", "content b")

        files = vault.list_vault_files()
        self.assertIn("file_a.txt.enc", files)
        self.assertIn("file_b.txt", files)
        self.assertNotIn(".vault_meta.json", files)


if __name__ == "__main__":
    unittest.main()
