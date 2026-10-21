"""Unit tests for FleetKeyring in-memory session encryption and node sync."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from gemini_app.fleet.keyring import FleetKeyring
from gemini_app.vault import (
    clear_session_passkey,
    init_vault,
    set_vault_passkey,
)


class TestFleetKeyring(unittest.TestCase):
    """Verifies that FleetKeyring securely stores keys in volatile RAM and locks cleanly."""

    def setUp(self) -> None:
        self.test_passkey = "TestFleetPasskey-9988"
        init_vault()
        set_vault_passkey(self.test_passkey)
        FleetKeyring.lock()
        clear_session_passkey()

    def tearDown(self) -> None:
        FleetKeyring.lock()
        clear_session_passkey()

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
