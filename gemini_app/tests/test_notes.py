"""Unit tests for the Unified Gemini Managed Notes Engine and Silent Quota Reconnect."""

import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.storage.notes_manager import NoteItem, NotesManager


class TestNotesManager(unittest.TestCase):
    def setUp(self):
        self.mgr = NotesManager(working_notes="Initial working plan", active_topic="UI")

    def test_initialization_and_properties(self):
        self.assertEqual(self.mgr.working_notes, "Initial working plan")
        self.assertEqual(self.mgr.active_topic, "ui")
        self.assertEqual(self.mgr.current_topic, "ui")

        self.mgr.active_topic = "audio"
        self.assertEqual(self.mgr.active_topic, "audio")
        self.assertEqual(self.mgr.current_topic, "audio")

    def test_record_note_and_topics(self):
        item1 = self.mgr.record_note("Add volume fader", topic="audio", status="working", author="gemini")
        self.assertEqual(item1.topic, "audio")
        self.assertEqual(item1.status, "working")
        self.assertEqual(item1.author, "gemini")

        item2 = self.mgr.record_note("Remember to test mono output", topic="audio", status="get_back_to", author="user")
        self.assertEqual(item2.topic, "audio")
        self.assertEqual(item2.status, "get_back_to")
        self.assertEqual(item2.author, "user")

        item3 = self.mgr.record_note("Consider spatial audio shaders", topic="audio", status="think_about", author="user")
        self.assertEqual(item3.status, "think_about")

        # Check retrieval by category
        back_items = self.mgr.get_notes_to_get_back_to()
        self.assertEqual(len(back_items), 1)
        self.assertEqual(back_items[0].content, "Remember to test mono output")

        think_items = self.mgr.get_notes_to_think_about()
        self.assertEqual(len(think_items), 1)
        self.assertEqual(think_items[0].content, "Consider spatial audio shaders")

        # Check topics catalog
        all_topics = self.mgr.get_all_topics()
        self.assertTrue(any(t == "audio" for t, _ in all_topics))

    def test_consume_user_input(self):
        # 1. Plain text with implied todo
        items1 = self.mgr.consume_user_input("Todo: fix scroll velocity on mobile #touch", default_topic="input")
        self.assertEqual(len(items1), 1)
        self.assertEqual(items1[0].status, "get_back_to")
        self.assertEqual(items1[0].topic, "input")
        self.assertEqual(items1[0].author, "user")
        self.assertIn("touch", items1[0].tags)

        # 2. Plain text with topic directive
        items2 = self.mgr.consume_user_input("Topic: network Need to implement exponential backoff on 429")
        self.assertEqual(len(items2), 1)
        self.assertEqual(items2[0].topic, "network")
        self.assertEqual(items2[0].status, "get_back_to")

        # 3. Markdown template input (user edited notes in the editor)
        template_text = (
            "# 🧠 Gemini Working Notes [Topic: network]\n"
            "Active task: tuning socket heartbeat\n\n"
            "# 📌 Relevant Notes in Relation to Current Work (1)\n"
            "• [👤 User] (network): Check reconnect latency"
        )
        self.mgr.consume_user_input(raw_text=template_text, active_topic="network")
        self.assertEqual(self.mgr.working_notes, "Active task: tuning socket heartbeat")
        rel_notes = self.mgr.get_relevant_notes("network")
        self.assertTrue(any("latency" in n.content.lower() for n in rel_notes))

    def test_scan_chat_for_notes(self):
        history = [
            {"turn_id": "t1", "role": "user", "text": "Hello, let's work on boot.\nNote: keep glyph matrix strictly 3 rows."},
            {"turn_id": "t2", "role": "model", "text": "Sure!\nTODO: calibrate sine shader frequency.\nRemember to test 60hz display."},
            {"turn_id": "t3", "role": "user", "text": "Topic: shaders\nThink about: adding phosphor green mode."},
        ]

        found = self.mgr.scan_chat_for_notes(history, default_topic="boot")
        self.assertGreaterEqual(len(found), 3)

        # Verify topic association and status categorization
        glyph_note = next((n for n in self.mgr.notes if "matrix strictly 3 rows" in n.content), None)
        self.assertIsNotNone(glyph_note)
        self.assertEqual(glyph_note.author, "user")

        todo_note = next((n for n in self.mgr.notes if "sine shader frequency" in n.content), None)
        self.assertIsNotNone(todo_note)
        self.assertEqual(todo_note.status, "get_back_to")

        shader_note = next((n for n in self.mgr.notes if "phosphor green" in n.content), None)
        self.assertIsNotNone(shader_note)
        self.assertEqual(shader_note.topic, "shaders")
        self.assertEqual(shader_note.status, "think_about")

    def test_format_working_view(self):
        self.mgr.set_working_notes("Implementing bilateral reconnection protocol")
        self.mgr.record_note("Check Wi-Fi drop test", topic=self.mgr.active_topic, status="get_back_to", author="user")

        view = self.mgr.format_working_view("working")
        self.assertIn("Gemini Working Notes", view)
        self.assertIn("Implementing bilateral reconnection protocol", view)
        self.assertIn("Relevant Notes in Relation to Current Work", view)
        self.assertIn("Check Wi-Fi drop test", view)

    def test_format_prompt_summary(self):
        self.mgr.record_note("Add test coverage for quota retry", topic="tests", status="get_back_to", author="user")
        self.mgr.record_note("Explore trio integration", topic="async", status="think_about", author="user")

        summary = self.mgr.format_prompt_summary()
        self.assertIn("ACTIVE TOPIC:", summary)
        self.assertIn("NOTES TO GET BACK TO:", summary)
        self.assertIn("NOTES TO THINK ABOUT:", summary)
        self.assertIn("TOPICS INDEX:", summary)

    def test_serialization_roundtrip(self):
        self.mgr.set_working_notes("Persistent working state")
        self.mgr.record_note("Verify audio buffers", topic="audio", status="working", author="gemini")
        self.mgr.record_note("Review snapshot storage", topic="snapshots", status="get_back_to", author="user")

        data = self.mgr.to_dict()
        loaded = NotesManager.from_dict(data)

        self.assertEqual(loaded.working_notes, "Persistent working state")
        self.assertEqual(len(loaded.notes), 2)
        self.assertEqual(len(loaded.get_notes_to_get_back_to()), 1)


class TestSilentQuotaReconnect(unittest.TestCase):
    def test_quota_retry_logic(self):
        call_count = 0

        def flaky_api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("ResourceExhausted: 429 Resource has been exhausted (e.g. check quota).")
            return "SUCCESS_RESPONSE"

        # Simulate the silent reconnect retry helper
        def _simulate_retry(call_fn, max_retries=5):
            attempt = 0
            while True:
                try:
                    return call_fn()
                except Exception as exc:
                    err_str = str(exc)
                    is_quota = (
                        "ResourceExhausted" in err_str
                        or "429" in err_str
                        or "quota" in err_str.lower()
                    )
                    if not is_quota or attempt >= max_retries:
                        raise exc
                    attempt += 1

        result = _simulate_retry(flaky_api_call, max_retries=5)
        self.assertEqual(result, "SUCCESS_RESPONSE")
        self.assertEqual(call_count, 3)

    def test_non_quota_error_not_swallowed(self):
        def hard_failure():
            raise ValueError("Invalid schema formatting")

        def _simulate_retry(call_fn, max_retries=5):
            attempt = 0
            while True:
                try:
                    return call_fn()
                except Exception as exc:
                    err_str = str(exc)
                    is_quota = "ResourceExhausted" in err_str or "429" in err_str
                    if not is_quota or attempt >= max_retries:
                        raise exc
                    attempt += 1

        with self.assertRaises(ValueError):
            _simulate_retry(hard_failure)


if __name__ == "__main__":
    unittest.main()
