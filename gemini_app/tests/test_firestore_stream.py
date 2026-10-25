"""Unit tests for FirestoreStreamBridge."""

import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import json
import time

from gemini_app.cloud.firestore_stream import FirestoreStreamBridge


class TestFirestoreStreamBridge(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.bridge = FirestoreStreamBridge(db_client=self.mock_db, project_id="mock-gemini-source")

    def test_initialization(self):
        self.assertTrue(self.bridge.is_connected)
        self.assertEqual(self.bridge.project_id, "mock-gemini-source")

    def test_publish_thought(self):
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        self.mock_db.collection.return_value = mock_collection

        success = self.bridge.publish_thought(
            text="Autonomous thought stream test.",
            tag="HYPOTHESIS",
            topic="test-topic",
        )
        self.assertTrue(success)
        self.mock_db.collection.assert_called_with("observatory")

    def test_publish_telemetry(self):
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        self.mock_db.collection.return_value = mock_collection

        success = self.bridge.publish_telemetry({"uptime_seconds": 120, "shards": 50})
        self.assertTrue(success)

    def test_publish_epiphany(self):
        mock_doc = MagicMock()
        mock_subcol = MagicMock()
        mock_subcol.document.return_value = mock_doc
        mock_root_doc = MagicMock()
        mock_root_doc.collection.return_value = mock_subcol
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_root_doc
        self.mock_db.collection.return_value = mock_collection

        success = self.bridge.publish_epiphany(
            summary="Test epiphany",
            hypothesis="Decoupled daemons increase speed.",
            domains=["Fleet", "Telemetry"],
            novelty_score=0.92,
        )
        self.assertTrue(success)

    def test_sync_console_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir)
            state_file = home / "state.json"
            state_file.write_text(json.dumps({
                "active_chat": "chat_123",
                "active_topic": "unit testing"
            }), encoding="utf-8")

            chats_dir = home / "chats" / "chat_123"
            chats_dir.mkdir(parents=True)
            (chats_dir / "meta.json").write_text(json.dumps({
                "notes": {"notes": [{"topic": "unit testing", "text": "note 1"}]}
            }), encoding="utf-8")

            success = self.bridge.sync_console_state(gemini_home=home)
            self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
