"""
test_cortex_ingest.py - Tests for Live Chat Ingestion into Relational Cortex.

Validates:
1. Ingesting single and multi-turn chats into SQLite Relational Cortex.
2. Invariant rule extraction and auto-linking hyperedges.
3. Topic horizon index calculation.
4. Clean handling of empty history and edge cases.
"""

import unittest
import os
import shutil
import tempfile
from pathlib import Path

from sandbox.mind_twin.core.relational_cortex import RelationalCortex
from sandbox.mind_twin.core.cortex_ingest import CortexIngestPipeline, IngestionReport
from gemini_app.storage.chat_store import ChatStore


class TestCortexIngestPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.chats_dir = os.path.join(self.temp_dir, "chats")
        self.db_path = os.path.join(self.temp_dir, "test_cortex.db")
        os.makedirs(self.chats_dir, exist_ok=True)

        self.cortex = RelationalCortex(db_path=self.db_path)
        self.chat_store = ChatStore(chats_dir=self.chats_dir)
        self.pipeline = CortexIngestPipeline(
            cortex=self.cortex,
            db_path=self.db_path,
            chats_dir=self.chats_dir
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ingest_synthetic_chat_with_invariant_rules(self):
        """
        Creates a synthetic chat containing invariant rules and verifies full ingestion.
        """
        chat_id = "test_chat_01"
        history = [
            {"turn_id": "t1", "role": "user", "text": "Starting Blender 3D pipeline setup."},
            {"turn_id": "t2", "role": "model", "text": "Understood. Blender uses Z-up orientation."},
            {"turn_id": "t3", "role": "user", "text": "Invariant rule: Gram-Schmidt orthogonalization must run every 50 frames to prevent basis drift."},
            {"turn_id": "t4", "role": "model", "text": "Understood, added drift correction to the loop."},
            {"turn_id": "t5", "role": "user", "text": "Also make sure port 7331 is reserved for mothership telemetry."}
        ]
        self.chat_store.save_chat(
            chat_id=chat_id,
            title="3D Pipeline and Telemetry",
            history=history,
            notes="Initial tests"
        )

        report = self.pipeline.ingest_chat_by_id(chat_id)
        self.assertEqual(report.chats_scanned, 1)
        self.assertEqual(report.total_turns_processed, 5)
        self.assertGreater(report.shards_created, 0)
        self.assertGreaterEqual(report.invariant_rules_count, 1)

        # Query cortex for the invariant rule
        rules = self.cortex.query_shards(category="invariant_rule")
        self.assertGreaterEqual(len(rules), 1)
        all_rule_contents = " ".join(r["content"] for r in rules)
        self.assertIn("Gram-Schmidt", all_rule_contents)

    def test_topic_horizon_calculation(self):
        """
        Verifies topic horizon identifies domain boundary.
        """
        history = [
            {"turn_id": "t1", "role": "user", "text": "Configuring the Emacs scratch buffer dojo."},
            {"turn_id": "t2", "role": "model", "text": "Avy and cadence metrics enabled."},
            {"turn_id": "t3", "role": "user", "text": "Switching to Blender 3D mesh modeling."},
            {"turn_id": "t4", "role": "model", "text": "Bmesh and armature generator active."},
            {"turn_id": "t5", "role": "user", "text": "Now Godot shader pipeline setup."},
        ]
        horizon = self.pipeline._calculate_topic_horizon(history)
        # Shift occurs after turn 1 (between Emacs and Blender/Godot)
        self.assertGreater(horizon, 0)

    def test_empty_chat_handling(self):
        """
        Verifies pipeline handles empty chats without error.
        """
        report = self.pipeline.ingest_chat_by_id("nonexistent_chat_id")
        self.assertEqual(report.chats_scanned, 1)
        self.assertEqual(report.total_turns_processed, 0)
        self.assertEqual(report.shards_created, 0)


if __name__ == "__main__":
    unittest.main()
