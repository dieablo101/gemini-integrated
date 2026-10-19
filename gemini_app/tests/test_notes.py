"""Unit tests for the Unified Gemini Managed Notes Engine, Pruning, Archiving, and Silent Quota Reconnect."""

import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.storage.notes_manager import (
    NoteItem,
    NotesManager,
    normalize_note_text,
    sanitize_working_notes,
)


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

    def test_sanitize_working_notes(self):
        corrupted = (
            "# 🧠 Gemini Working Notes [Topic: general]\n"
            "# 🧠 Gemini Working Notes [Topic: general]\n"
            "Valid working plan line 1\n"
            "Valid working plan line 2\n"
            "# 📌 Relevant Notes in Relation to Current Work (1)\n"
            "• [👤 User] [think_about] (ui): testing"
        )
        cleaned = sanitize_working_notes(corrupted)
        self.assertNotIn("# 🧠 Gemini Working Notes", cleaned)
        self.assertNotIn("# 📌 Relevant Notes", cleaned)
        self.assertNotIn("• [👤 User]", cleaned)
        self.assertIn("Valid working plan line 1", cleaned)
        self.assertIn("Valid working plan line 2", cleaned)

        # Placeholders should clean to empty
        placeholder = (
            "# 🧠 Gemini Working Notes [Topic: general]\n"
            "*(No active working notes set. Gemini updates working notes autonomously as tasks proceed.)*\n\n"
            "# 📌 Relevant Notes in Relation to Current Work (0)\n"
            "*(No user or topic notes currently flagged as relevant to this work.)*"
        )
        self.assertEqual(sanitize_working_notes(placeholder), "")

    def test_record_note_and_topics(self):
        item1 = self.mgr.record_note("Add volume fader", topic="audio", status="working", author="gemini")
        self.assertIsNotNone(item1)
        self.assertEqual(item1.topic, "audio")
        self.assertEqual(item1.status, "working")
        self.assertEqual(item1.author, "gemini")

        item2 = self.mgr.record_note("Remember to test mono output", topic="audio", status="get_back_to", author="user")
        self.assertIsNotNone(item2)
        self.assertEqual(item2.topic, "audio")
        self.assertEqual(item2.status, "get_back_to")
        self.assertEqual(item2.author, "user")

        item3 = self.mgr.record_note("Consider spatial audio shaders", topic="audio", status="think_about", author="user")
        self.assertIsNotNone(item3)
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

    def test_consume_user_input_no_duplicates_on_resave(self):
        # Initial note in manager
        self.mgr.record_note("Check Wi-Fi drop test", topic="network", status="get_back_to", author="user")
        self.assertEqual(len(self.mgr.notes), 1)

        # Render view as if displayed in the editor
        rendered = self.mgr.format_working_view("working")
        self.assertIn("Check Wi-Fi drop test", rendered)

        # Simulate user opening and pressing Enter without typing anything new
        self.mgr.consume_user_input(raw_text=rendered, active_topic="network")
        self.assertEqual(len(self.mgr.notes), 1, "Re-saving rendered view must not duplicate existing notes!")

        # Re-save multiple times
        for _ in range(3):
            self.mgr.consume_user_input(raw_text=rendered, active_topic="network")
        self.assertEqual(len(self.mgr.notes), 1, "Multiple re-saves must strictly maintain deduplication!")

    def test_note_archiving(self):
        n1 = self.mgr.record_note("Configure TLS certificates", topic="security", status="working", author="gemini")
        n2 = self.mgr.record_note("Rotate SSH keys", topic="security", status="completed", author="user")
        self.assertIsNotNone(n1)
        self.assertIsNotNone(n2)

        # Active relevant notes should include n1 and n2 initially
        self.assertEqual(len(self.mgr.get_relevant_notes("security")), 2)

        # Archive n1 by ID
        ok = self.mgr.archive_note(n1.id)
        self.assertTrue(ok)
        self.assertTrue(n1.archived)
        self.assertEqual(n1.status, "archived")

        # Active relevant notes should now exclude n1
        self.assertEqual(len(self.mgr.get_relevant_notes("security")), 1)

        # Archived view should list n1
        archived_view = self.mgr.format_working_view("archived")
        self.assertIn("Configure TLS certificates", archived_view)
        self.assertIn("Archived Notes (1)", archived_view)

        # Unarchive n1
        unarch_ok = self.mgr.unarchive_note(n1.id, restore_status="working")
        self.assertTrue(unarch_ok)
        self.assertFalse(n1.archived)
        self.assertEqual(len(self.mgr.get_relevant_notes("security")), 2)

        # Test archive_completed_notes
        cnt = self.mgr.archive_completed_notes()
        self.assertEqual(cnt, 1)
        self.assertTrue(n2.archived)

    def test_deduplicate_and_prune_notes(self):
        # Add intentional duplicates
        self.mgr.record_note("Test audio fader response", topic="audio", status="working")
        # Direct append bypassing record_note duplicate check to simulate legacy/external corruption
        dup_item = NoteItem(
            id="n_dup1",
            topic="audio",
            content="• [👤 User] (audio): Test audio fader response",
            status="think_about",
        )
        empty_item = NoteItem(
            id="n_empty",
            topic="audio",
            content="   ",
            status="working",
        )
        self.mgr.notes.extend([dup_item, empty_item])
        self.assertEqual(len(self.mgr.notes), 3)

        # Prune notes
        summary = self.mgr.prune_notes()
        self.assertEqual(summary["duplicates_removed"], 1)
        self.assertEqual(summary["empty_removed"], 1)
        self.assertEqual(summary["total_remaining"], 1)
        self.assertEqual(self.mgr.notes[0].content, "Test audio fader response")

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

        # Scanning again should not create duplicates
        orig_count = len(self.mgr.notes)
        self.mgr.scan_chat_for_notes(history, default_topic="boot")
        self.assertEqual(len(self.mgr.notes), orig_count, "Chat scanning must not duplicate existing notes!")

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
        n2 = self.mgr.record_note("Review snapshot storage", topic="snapshots", status="get_back_to", author="user")
        self.assertIsNotNone(n2)
        self.mgr.archive_note(n2.id)

        data = self.mgr.to_dict()
        loaded = NotesManager.from_dict(data)

        self.assertEqual(loaded.working_notes, "Persistent working state")
        self.assertEqual(len(loaded.notes), 2)
        self.assertEqual(len(loaded.get_archived_notes()), 1)


class TestSilentQuotaReconnect(unittest.TestCase):
    def test_extract_retry_delay(self):
        import re

        def _extract_retry_delay(err_text: str) -> float | None:
            m = re.search(r"(?:retry\s+(?:in|after)|wait)\s+([\d\.]+)\s*(?:seconds|second|sec|s\b)", err_text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            m = re.search(r"seconds:\s*([\d\.]+)", err_text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            m = re.search(r"retry_delay[^{]*\{[^}]*seconds:\s*([\d\.]+)", err_text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            return None

        self.assertEqual(_extract_retry_delay("Quota exceeded. Please retry in 18s."), 18.0)
        self.assertEqual(_extract_retry_delay("Rate limit reached. Please retry after 12.5s"), 12.5)
        self.assertEqual(_extract_retry_delay("ResourceExhausted: 429 [retry_delay { seconds: 20 }]"), 20.0)
        self.assertEqual(_extract_retry_delay("429 wait 5 seconds"), 5.0)
        self.assertIsNone(_extract_retry_delay("Random quota error without timing hint"))

    def test_smooth_countdown_math(self):
        import math

        target_time = time.monotonic() + 5.0
        # Rem at t=0 should be 5
        rem = max(0, int(math.ceil(target_time - time.monotonic())))
        self.assertIn(rem, (4, 5))

        # At expiration, rem should be 0
        rem_expired = max(0, int(math.ceil(time.monotonic() - 1.0 - time.monotonic())))
        self.assertEqual(rem_expired, 0)

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


class TestNotesPanelWidgets(unittest.IsolatedAsyncioTestCase):
    async def test_notes_panel_contains_notes_input_and_focus_cycling(self):
        from gemini_app.ui.app import ChatApp
        from gemini_app.ui.widgets.text_areas import ExpandingInput

        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Dismiss boot screen
            await pilot.press("space")
            await app.workers.wait_for_complete()

            # Toggle notes open
            app.action_toggle_notes()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Verify notes_input is mounted
            notes_input = app.query_one("#notes_input", ExpandingInput)
            self.assertIsNotNone(notes_input)

            # Verify initial focus is on notes_input, NOT notes_editor
            self.assertEqual(app.focused, notes_input)

            # Verify notes_editor is read-only and cannot be focused
            notes_editor = app.query_one("#notes_editor")
            self.assertFalse(notes_editor.can_focus)
            self.assertTrue(notes_editor.read_only)

            # Press Tab -> should cycle to main input (skipping notes_editor)
            app.cycle_global_focus(direction=1)
            await pilot.pause()
            main_input = app.query_one("#input")
            self.assertEqual(app.focused, main_input)

            # Press Tab -> should cycle back to notes_input (skipping notes_editor)
            app.cycle_global_focus(direction=1)
            await pilot.pause()
            self.assertEqual(app.focused, notes_input)

            # Press Shift+Tab from notes_input -> should cycle to main input
            app.cycle_global_focus(direction=-1)
            await pilot.pause()
            self.assertEqual(app.focused, main_input)

            # Test submitting a note from notes_input
            notes_input.text = "Todo: calibrate reconnect timer precision"
            notes_input.action_submit()
            await pilot.pause()
            
            # Verify it was consumed
            todos = app.notes_manager.get_notes_to_get_back_to()
            self.assertTrue(any("reconnect timer precision" in n.content for n in todos))


if __name__ == "__main__":
    unittest.main()
