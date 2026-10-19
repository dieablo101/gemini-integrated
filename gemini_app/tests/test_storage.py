"""Unit tests for ChatStore and ForkEngine."""

import json
import tempfile
import unittest
from pathlib import Path

from gemini_app.storage.chat_store import ChatStore
from gemini_app.storage.fork_engine import ForkEngine


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp_dir.name)
        self.chats_dir = self.base / "chats"
        self.archive_dir = self.chats_dir / ".archive"
        self.state_file = self.base / "state.json"
        self.store = ChatStore(
            chats_dir=self.chats_dir,
            archive_dir=self.archive_dir,
            state_file=self.state_file,
        )
        self.fork_engine = ForkEngine(self.store)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load_sharded_chat(self):
        chat_id = "test_chat_01"
        history = [
            {"role": "user", "text": "Hello Gemini", "turn_id": "turn_1"},
            {"role": "model", "text": "Hello User!", "turn_id": "turn_2"},
        ]
        self.store.save_chat(
            chat_id=chat_id,
            title="Greeting Session",
            history=history,
            notes="Initial greeting notes",
            working_dir="/tmp/test",
            mind_map={"gemini_state": "Initialized", "user_state": "Testing"},
            is_legacy=False,
        )

        chat_dir = self.store.get_chat_dir(chat_id)
        self.assertTrue(chat_dir.is_dir())
        self.assertTrue((chat_dir / "meta.json").exists())
        self.assertTrue((chat_dir / "segment_0.json").exists())

        loaded = self.store.load_chat(chat_id)
        self.assertEqual(loaded["id"], chat_id)
        self.assertEqual(loaded["title"], "Greeting Session")
        self.assertEqual(loaded["notes"], "Initial greeting notes")
        self.assertEqual(len(loaded["history"]), 2)
        self.assertEqual(loaded["history"][0]["text"], "Hello Gemini")
        self.assertEqual(loaded["mind_map"]["gemini_state"], "Initialized")

    def test_multi_segment_sharding(self):
        chat_id = "long_chat"
        # Create 250 turns to force 2 segments (TURNS_PER_SEGMENT = 200)
        history = [
            {"role": "user" if i % 2 == 0 else "model", "text": f"Turn {i}", "turn_id": f"t_{i}"}
            for i in range(250)
        ]
        self.store.save_chat(
            chat_id=chat_id,
            title="Long Session",
            history=history,
            is_legacy=False,
        )

        chat_dir = self.store.get_chat_dir(chat_id)
        self.assertTrue((chat_dir / "segment_0.json").exists())
        self.assertTrue((chat_dir / "segment_1.json").exists())

        loaded = self.store.load_chat(chat_id)
        self.assertEqual(len(loaded["history"]), 250)
        self.assertEqual(loaded["history"][-1]["text"], "Turn 249")

    def test_legacy_flat_json_compatibility(self):
        chat_id = "legacy_001"
        legacy_file = self.store.get_legacy_chat_file(chat_id)
        legacy_data = {
            "id": chat_id,
            "title": "Old Flat Chat",
            "messages": [
                {"role": "user", "text": "Old message"},
            ],
            "notes": "Old notes",
        }
        legacy_file.write_text(json.dumps(legacy_data), encoding="utf-8")

        loaded = self.store.load_chat(chat_id)
        self.assertTrue(loaded["is_legacy"])
        self.assertEqual(loaded["title"], "Old Flat Chat")
        self.assertEqual(len(loaded["history"]), 1)
        self.assertTrue(loaded["history"][0]["turn_id"].startswith("turn_"))

    def test_fork_engine(self):
        parent_id = "parent_001"
        history = [
            {"role": "user", "text": "Turn 0", "turn_id": "p0"},
            {"role": "model", "text": "Turn 1", "turn_id": "p1"},
            {"role": "user", "text": "Turn 2", "turn_id": "p2"},
            {"role": "model", "text": "Turn 3", "turn_id": "p3"},
        ]
        self.store.save_chat(parent_id, "Parent Chat", history, notes="Parent notes")

        # Fork turns 1 and 2
        fork_id, forked_turns = self.fork_engine.create_fork(
            parent_id=parent_id,
            parent_history=history,
            selected_indices=[1, 2],
            fork_title="Forked Branch",
        )

        self.assertNotEqual(fork_id, parent_id)
        self.assertEqual(len(forked_turns), 2)
        self.assertIn("This chat is a fork", forked_turns[0]["text"])

        loaded_fork = self.store.load_chat(fork_id)
        self.assertEqual(loaded_fork["parent_id"], parent_id)
        self.assertEqual(loaded_fork["title"], "Forked Branch")

        # Test lineage traversal from parent_id
        lineage = self.fork_engine.get_parent_lineage(loaded_fork["parent_id"])
        self.assertEqual(len(lineage), 1)
        self.assertEqual(lineage[0]["id"], parent_id)

    def test_archive_and_delete(self):
        chat_id = "chat_to_archive"
        self.store.save_chat(chat_id, "Archive Me", [{"role": "user", "text": "Hi"}])
        self.assertTrue(self.store.get_chat_dir(chat_id).exists())

        archived = self.store.archive_chat(chat_id)
        self.assertTrue(archived)
        self.assertFalse(self.store.get_chat_dir(chat_id).exists())
        self.assertTrue((self.archive_dir / chat_id).exists())

    def test_state_persistence(self):
        self.store.save_state_key("active_chat", "abc_123")
        state = self.store.load_state()
        self.assertEqual(state.get("active_chat"), "abc_123")


if __name__ == "__main__":
    unittest.main()
