"""Tests for emergency_terminal.py session tracker and cross-console continuity."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from emergency_terminal import EmergencySessionTracker, EmergencyToolbox
from gemini_app.introspection import get_tier_2_runtime, format_introspection_summary


class MockApp:
    def __init__(self, working_dir: str = "/opt/gemini"):
        self.working_dir = working_dir
        self.history = [{"role": "user", "text": "hello"}]
        self.current_chat_id = "test_chat"
        self.current_chat_parent_id = None
        self._request_phase = "idle"
        self._request_details = ""
        self.current_focused_turn_id = "t1"
        self.current_chat_center_marker = ""
        self.active_palette_name = "blue"
        self.active_task_title = "Testing emergency"
        self.current_gemini_state = "Armed"
        self.current_user_state = "Testing"
        self.current_tree_state = []
        self.current_tree_content = ""
        self.gemini_notes = ""
        self.notes_manager = None
        self.screen = None


class TestEmergencyTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp_dir.name) / "emergency_state.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_session_lifecycle(self):
        tracker = EmergencySessionTracker(state_file=self.state_file)
        self.assertEqual(tracker.data["total_runs"], 0)

        # 1. Start session
        run_no = tracker.start_session()
        self.assertEqual(run_no, 1)
        self.assertEqual(tracker.data["total_runs"], 1)
        self.assertEqual(tracker.current_session["status"], "in_progress")

        # 2. Record turn
        tracker.record_turn(
            user_msg="My app froze on reboot",
            assistant_reply="Checking logs and git status",
            tools_used=["git_repair", "run_tests"],
        )
        self.assertEqual(tracker.current_session["turns_count"], 1)
        self.assertIn("git_repair", tracker.current_session["tools_invoked"])
        self.assertIn("run_tests", tracker.current_session["tools_invoked"])

        # 3. End session
        tracker.end_session("completed")
        self.assertEqual(tracker.current_session["status"], "completed")
        self.assertIsNotNone(tracker.current_session["ended_at"])

        # Reload from disk
        tracker2 = EmergencySessionTracker(state_file=self.state_file)
        self.assertEqual(tracker2.data["total_runs"], 1)
        self.assertEqual(len(tracker2.data["sessions"]), 1)
        last = tracker2.data["last_session"]
        self.assertEqual(last["run_number"], 1)
        self.assertEqual(last["turns_count"], 1)

        # 4. Check continuity summary for subsequent run
        tracker2.start_session()
        summary = tracker2.get_continuity_summary()
        self.assertIn("Total Runs Executed: 1", summary)
        self.assertIn("Last Session: #1", summary)
        self.assertIn("git_repair, run_tests", summary)

    def test_emergency_toolbox_local(self):
        toolbox = EmergencyToolbox(Path(self.tmp_dir.name))
        test_file = Path(self.tmp_dir.name) / "hello.txt"
        
        # Write
        w_res = toolbox.write_file("hello.txt", "line1\nline2\nline3\n")
        self.assertEqual(w_res["status"], "success")

        # Read
        r_res = toolbox.read_file("hello.txt")
        self.assertEqual(r_res["status"], "success")
        self.assertIn("line2", r_res["content"])

        # Apply patch
        p_res = toolbox.apply_patch("hello.txt", "line2", "patched_line2")
        self.assertEqual(p_res["status"], "success")
        self.assertIn("patched_line2", test_file.read_text(encoding="utf-8"))

        # Search
        s_res = toolbox.search_codebase("patched_line")
        self.assertEqual(s_res["status"], "success")
        self.assertGreaterEqual(s_res["total_matches"], 1)

    def test_introspection_tier2_emergency_integration(self):
        # Write a mock emergency_state.json to GEMINI_HOME
        from gemini_app.config import GEMINI_HOME
        emg_file = GEMINI_HOME / "emergency_state.json"
        
        original_content = None
        if emg_file.exists():
            original_content = emg_file.read_text(encoding="utf-8")

        try:
            emg_file.write_text(json.dumps({
                "total_runs": 3,
                "last_session": {
                    "run_number": 3,
                    "started_at": "2026-03-31T10:00:00Z",
                    "status": "completed",
                    "turns_count": 2,
                    "tools_invoked": ["run_tests"],
                },
                "sessions": [],
            }), encoding="utf-8")

            app = MockApp()
            t2 = get_tier_2_runtime(app)
            self.assertEqual(t2["emergency_runs"], 3)
            self.assertEqual(t2["last_emergency_session"]["run_number"], 3)

            summary = format_introspection_summary(app)
            self.assertIn("Emergency Bridge: 3 run(s) logged (Last: Session #3 - completed)", summary)
        finally:
            if original_content is not None:
                emg_file.write_text(original_content, encoding="utf-8")
            elif emg_file.exists():
                emg_file.unlink()


if __name__ == "__main__":
    unittest.main()
