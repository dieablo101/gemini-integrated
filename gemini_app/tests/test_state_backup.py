"""Unit tests for automated continuous backup of ~/.gemini to private GitHub repo."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.storage import state_backup


class TestStateBackup(unittest.TestCase):
    """Validates state repository initialization, 24-hr check interval, and backup mechanics."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_gemini_home = Path(self.temp_dir.name) / ".gemini"
        self.mock_gemini_home.mkdir(parents=True, exist_ok=True)
        self.mock_state_file = self.mock_gemini_home / "state.json"
        self.mock_vault_dir = self.mock_gemini_home / "vault"
        self.mock_vault_dir.mkdir(parents=True, exist_ok=True)

        self.orig_home = state_backup.GEMINI_HOME
        self.orig_state = state_backup.STATE_FILE
        self.orig_vault = state_backup.VAULT_DIR
        self.orig_log = state_backup.BACKUP_LOG_FILE

        state_backup.GEMINI_HOME = self.mock_gemini_home
        state_backup.STATE_FILE = self.mock_state_file
        state_backup.VAULT_DIR = self.mock_vault_dir
        state_backup.BACKUP_LOG_FILE = self.mock_gemini_home / "backup.log"

    def tearDown(self) -> None:
        state_backup.GEMINI_HOME = self.orig_home
        state_backup.STATE_FILE = self.orig_state
        state_backup.VAULT_DIR = self.orig_vault
        state_backup.BACKUP_LOG_FILE = self.orig_log
        self.temp_dir.cleanup()

    def test_ensure_state_repo_initialized(self) -> None:
        """Verifies repository is created, gitignore written, and remote configured."""
        repo_path = state_backup.ensure_state_repo_initialized("test-repo")
        self.assertTrue(repo_path.is_dir())
        self.assertTrue((self.mock_gemini_home / ".git").is_dir())

        gitignore = (self.mock_gemini_home / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("vault/*.txt", gitignore)
        self.assertIn("!vault/*.enc", gitignore)
        self.assertIn("!vault/.vault_meta.json", gitignore)
        self.assertIn("screenshots/", gitignore)

    def test_gitignore_protects_plaintext_vault_secrets(self) -> None:
        """Ensures plaintext token files are untracked by git while encrypted tokens are tracked."""
        state_backup.ensure_state_repo_initialized(".gemini")

        # Create unencrypted secret and encrypted secret
        plaintext_token = self.mock_vault_dir / "secret_token.txt"
        plaintext_token.write_text("raw_secret_value", encoding="utf-8")

        encrypted_token = self.mock_vault_dir / "secret_token.txt.enc"
        encrypted_token.write_text("F1:cipher_payload", encoding="utf-8")

        # Verify plaintext token is ignored by git check-ignore
        check_ignored = subprocess.run(
            ["git", "check-ignore", "vault/secret_token.txt"],
            cwd=str(self.mock_gemini_home),
            capture_output=True,
            text=True,
        )
        self.assertEqual(check_ignored.returncode, 0)
        self.assertIn("vault/secret_token.txt", check_ignored.stdout)

        # Verify encrypted token is NOT ignored
        check_not_ignored = subprocess.run(
            ["git", "check-ignore", "vault/secret_token.txt.enc"],
            cwd=str(self.mock_gemini_home),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(check_not_ignored.returncode, 0)

        # Check git status -uall
        status_res = subprocess.run(
            ["git", "status", "--porcelain", "-uall", "vault/"],
            cwd=str(self.mock_gemini_home),
            capture_output=True,
            text=True,
        )
        self.assertNotIn("secret_token.txt\n", status_res.stdout)
        self.assertIn("secret_token.txt.enc", status_res.stdout)

    def test_backup_metadata_persistence(self) -> None:
        """Verifies recording and retrieving backup timestamps and status."""
        state_backup.update_backup_metadata("success")
        meta = state_backup.get_backup_metadata()
        self.assertEqual(meta.get("last_backup_status"), "success")
        self.assertGreater(meta.get("last_backup_timestamp", 0), 0)

        state_backup.update_backup_metadata("failed", error="Network unreachable")
        data = json.loads(self.mock_state_file.read_text(encoding="utf-8"))
        self.assertEqual(data.get("last_backup_status"), "failed")
        self.assertEqual(data.get("last_backup_error"), "Network unreachable")

    def test_is_daily_backup_due(self) -> None:
        """Verifies 24-hr threshold logic."""
        # Never run before -> should be due
        self.assertTrue(state_backup.is_daily_backup_due())

        # Just ran -> not due
        state_backup.update_backup_metadata("success")
        self.assertFalse(state_backup.is_daily_backup_due())

        # Ran 25 hours ago -> due
        st = json.loads(self.mock_state_file.read_text(encoding="utf-8"))
        st["last_backup_timestamp"] = time.time() - 90000
        self.mock_state_file.write_text(json.dumps(st), encoding="utf-8")
        self.assertTrue(state_backup.is_daily_backup_due())

    @patch("gemini_app.storage.state_backup.check_remote_repo_exists", return_value=False)
    def test_perform_backup_awaiting_remote(self, mock_remote: MagicMock) -> None:
        """Verifies backup commits locally and detects missing remote repo."""
        state_backup.ensure_state_repo_initialized(".gemini")

        # Create a sample file to trigger commit
        sample_file = self.mock_gemini_home / "sample.txt"
        sample_file.write_text("Hello backup", encoding="utf-8")

        res = state_backup.perform_backup()
        self.assertEqual(res.get("status"), "awaiting_remote_repo")
        self.assertTrue(res.get("committed"))
        self.assertFalse(res.get("pushed"))
        self.assertIn("not found on GitHub", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()
