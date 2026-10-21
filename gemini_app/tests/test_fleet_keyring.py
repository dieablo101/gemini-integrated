"""Unit tests for FleetKeyring in-memory session encryption and node sync."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gemini_app.fleet.keyring import FleetKeyring
from gemini_app import vault


class TestFleetKeyring(unittest.TestCase):
    """Verifies that FleetKeyring securely stores keys in volatile RAM and locks cleanly."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_dir = Path(self.temp_dir.name) / "vault"
        self.state_file = Path(self.temp_dir.name) / "state.json"
        self.meta_file = self.vault_dir / ".vault_meta.json"
        self.fleet_vault_dir = self.vault_dir / "fleet"

        self.p_vault = patch("gemini_app.vault.VAULT_DIR", self.vault_dir)
        self.p_meta = patch("gemini_app.vault.VAULT_META_FILE", self.meta_file)
        self.p_state = patch("gemini_app.vault.STATE_FILE", self.state_file)
        self.p_fdir = patch("gemini_app.fleet.keyring.FLEET_VAULT_DIR", self.fleet_vault_dir)
        self.p_fkey = patch("gemini_app.fleet.keyring.FLEET_KEY_ENC", self.fleet_vault_dir / "fleet_key.enc")
        self.p_ckey = patch("gemini_app.fleet.keyring.CLUSTER_KEY_ENC", self.fleet_vault_dir / "id_cluster.enc")

        self.p_vault.start()
        self.p_meta.start()
        self.p_state.start()
        self.p_fdir.start()
        self.p_fkey.start()
        self.p_ckey.start()

        self.test_passkey = "TestFleetPasskey-9988"
        vault.init_vault()
        vault.set_vault_passkey(self.test_passkey)
        FleetKeyring.lock()
        vault.clear_session_passkey()

    def tearDown(self) -> None:
        FleetKeyring.lock()
        vault.clear_session_passkey()
        self.p_vault.stop()
        self.p_meta.stop()
        self.p_state.stop()
        self.p_fdir.stop()
        self.p_fkey.stop()
        self.p_ckey.stop()
        self.temp_dir.cleanup()

    def test_keyring_lock_unlock_lifecycle(self) -> None:
        """Keyring starts locked, unlocks with valid passkey, and clears on lock."""
        self.assertFalse(FleetKeyring.is_unlocked())

        with self.assertRaises(PermissionError):
            FleetKeyring.unlock("WrongPasskey-123")

        res = FleetKeyring.unlock(self.test_passkey)
        self.assertEqual(res.get("status"), "unlocked")
        self.assertTrue(FleetKeyring.is_unlocked())
        self.assertIsNotNone(FleetKeyring.get_fleet_key())

        FleetKeyring.lock()
        self.assertFalse(FleetKeyring.is_unlocked())
        self.assertIsNone(FleetKeyring.get_fleet_key())

    def test_sync_nodes_flow(self) -> None:
        """Verifies sync_nodes decrypts keyring and queries fleet snapshot."""
        sync_res = FleetKeyring.sync_nodes(self.test_passkey)
        self.assertEqual(sync_res.get("status"), "success")
        self.assertTrue(sync_res.get("keyring_unlocked"))
        self.assertIn("active_nodes_count", sync_res)
        self.assertIn("nodes", sync_res)
        self.assertTrue(FleetKeyring.is_unlocked())
