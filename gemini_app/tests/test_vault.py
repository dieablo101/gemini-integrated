"""Unit tests for the local secure vault, categorized items, passkey authentication, and rotation."""

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

    def tearDown(self):
        vault.clear_session_passkey()
        self.p_files.stop()
        self.p_sec.stop()
        self.p_pass.stop()
        self.p_state.stop()
        self.p_meta.stop()
        self.p_vault.stop()
        self.temp_dir.cleanup()

    def test_vault_init(self):
        self.assertFalse(self.vault_dir.exists())
        res = vault.init_vault()
        self.assertTrue(self.vault_dir.is_dir())
        self.assertTrue(self.passwords_dir.is_dir())
        self.assertTrue(self.secrets_dir.is_dir())
        self.assertTrue(self.files_dir.is_dir())
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

    def test_session_passkey_cache(self):
        vault.set_vault_passkey("cached_key_123")
        self.assertTrue(vault.is_session_unlocked())
        self.assertEqual(vault.get_session_passkey(), "cached_key_123")

        vault.clear_session_passkey()
        self.assertFalse(vault.is_session_unlocked())
        self.assertIsNone(vault.get_session_passkey())

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

    def test_password_crud(self):
        vault.set_vault_passkey("master_key")
        # Store
        path = vault.store_password(
            title="Google Mail",
            password="my_gmail_password_99!",
            username="user@gmail.com",
            notes="Primary personal email",
            passkey="master_key",
        )
        self.assertTrue(path.is_file())

        # Raw file encrypted
        self.assertNotIn(b"my_gmail_password_99!", path.read_bytes())

        # Retrieve
        entry = vault.get_password("Google Mail", passkey="master_key")
        self.assertEqual(entry["title"], "Google Mail")
        self.assertEqual(entry["username"], "user@gmail.com")
        self.assertEqual(entry["password"], "my_gmail_password_99!")
        self.assertEqual(entry["notes"], "Primary personal email")

        # List
        pass_list = vault.list_passwords(passkey="master_key")
        self.assertEqual(len(pass_list), 1)
        self.assertEqual(pass_list[0]["title"], "Google Mail")
        self.assertEqual(pass_list[0]["password"], "my_gmail_password_99!")

        # Delete
        self.assertTrue(vault.delete_password("Google Mail"))
        self.assertEqual(len(vault.list_passwords(passkey="master_key")), 0)

    def test_secret_crud(self):
        vault.set_vault_passkey("master_key")
        long_secret = "-----BEGIN RSA PRIVATE KEY-----\n" + ("A" * 128) + "\n-----END RSA PRIVATE KEY-----"
        path = vault.store_secret("Stripe Webhook", long_secret, passkey="master_key")
        self.assertTrue(path.is_file())

        entry = vault.get_secret("Stripe Webhook", passkey="master_key")
        self.assertEqual(entry["title"], "Stripe Webhook")
        self.assertEqual(entry["secret"], long_secret)

        secrets_list = vault.list_secrets(passkey="master_key")
        self.assertEqual(len(secrets_list), 1)
        self.assertEqual(secrets_list[0]["title"], "Stripe Webhook")

        self.assertTrue(vault.delete_secret("Stripe Webhook"))
        self.assertEqual(len(vault.list_secrets(passkey="master_key")), 0)

    def test_file_crud_and_export(self):
        vault.set_vault_passkey("master_key")
        sample_file = Path(self.temp_dir.name) / "sample.pdf"
        sample_file.write_bytes(b"%PDF-1.4 test binary stream 123456789")

        # Store with shred_original=True
        enc_target = vault.store_file(
            title="Important Contract",
            file_path=sample_file,
            passkey="master_key",
            shred_original=True,
        )
        self.assertTrue(enc_target.is_file())
        self.assertFalse(sample_file.exists())  # Shredded

        # List
        files_list = vault.list_categorized_files(passkey="master_key")
        self.assertEqual(len(files_list), 1)
        self.assertEqual(files_list[0]["title"], "Important Contract")
        self.assertEqual(files_list[0]["original_name"], "sample.pdf")

        # Export
        export_dest = Path(self.temp_dir.name) / "restored.pdf"
        vault.export_file("Important Contract", export_dest, passkey="master_key")
        self.assertTrue(export_dest.is_file())
        self.assertEqual(export_dest.read_bytes(), b"%PDF-1.4 test binary stream 123456789")

        # Delete
        self.assertTrue(vault.delete_vault_file("Important Contract"))
        self.assertEqual(len(vault.list_categorized_files(passkey="master_key")), 0)

    def test_legacy_vault_files_listing_and_export(self):
        vault.set_vault_passkey("master_key")
        # Store legacy file directly in VAULT_DIR
        vault.store_in_vault("pypi_recovery_codes.txt", "code-alpha-bravo-1234", passkey="master_key")

        # Must appear in list_categorized_files
        files = vault.list_categorized_files(passkey="master_key")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["title"], "pypi_recovery_codes.txt")
        self.assertTrue(files[0]["is_legacy"])

        # Can be retrieved via retrieve_from_vault
        retrieved = vault.retrieve_from_vault("pypi_recovery_codes.txt", "master_key")
        self.assertEqual(retrieved.decode("utf-8"), "code-alpha-bravo-1234")

        # Can be exported via export_file
        dest = Path(self.temp_dir.name) / "exported_codes.txt"
        exported = vault.export_file("pypi_recovery_codes.txt", dest, passkey="master_key")
        self.assertTrue(exported.is_file())
        self.assertEqual(exported.read_text(encoding="utf-8"), "code-alpha-bravo-1234")

        # Can be deleted via delete_vault_file
        self.assertTrue(vault.delete_vault_file("pypi_recovery_codes.txt"))
        self.assertEqual(len(vault.list_categorized_files(passkey="master_key")), 0)

    def test_retrieve_from_vault_categorized_file(self):
        vault.set_vault_passkey("master_key")
        sample_file = Path(self.temp_dir.name) / "test_notes.md"
        sample_file.write_text("# Test Notes", encoding="utf-8")

        vault.store_file(title="Project Notes", file_path=sample_file, passkey="master_key")
        # retrieve_from_vault should unpack categorized file
        recovered = vault.retrieve_from_vault("Project Notes", passkey="master_key")
        self.assertEqual(recovered.decode("utf-8"), "# Test Notes")

    def test_rotate_vault_passkey(self):
        old_pass = "old_passkey_abc"
        new_pass = "new_passkey_xyz"

        vault.set_vault_passkey(old_pass)
        # Store items across all categories
        vault.store_in_vault("legacy_token.txt", "token_12345", passkey=old_pass)
        vault.store_password("GitHub", "gh_pass_99", username="octocat", passkey=old_pass)
        vault.store_secret("API Key", "sk_live_123456789", passkey=old_pass)

        # Rotate
        res = vault.rotate_vault_passkey(old_pass, new_pass)
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["rotated_count"], 3)

        # Old passkey no longer works
        self.assertFalse(vault.verify_vault_passkey(old_pass))
        # New passkey works
        self.assertTrue(vault.verify_vault_passkey(new_pass))

        # Stored items can now be decrypted with new passkey
        recovered_token = vault.retrieve_from_vault("legacy_token.txt", new_pass)
        self.assertEqual(recovered_token.decode("utf-8"), "token_12345")

        recovered_pass = vault.get_password("GitHub", passkey=new_pass)
        self.assertEqual(recovered_pass["password"], "gh_pass_99")

        recovered_sec = vault.get_secret("API Key", passkey=new_pass)
        self.assertEqual(recovered_sec["secret"], "sk_live_123456789")


if __name__ == "__main__":
    unittest.main()
