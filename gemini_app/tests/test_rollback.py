"""Unit tests for the autonomous safety supervisor and rollback engine."""

import json
from pathlib import Path
import tempfile
import unittest

from gemini_app.storage.rollback import (
    get_current_git_commit,
    get_last_stable_commit,
    is_reboot_in_progress,
    mark_reboot_in_progress,
    mark_startup_successful,
    perform_git_rollback,
    record_stable_commit,
    run_with_guardian,
)


class TestRollbackEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp_dir.name)
        self.state_file = self.base / "state.json"

        # Monkey-patch STATE_FILE for isolated testing
        import gemini_app.storage.rollback as rb
        self.orig_state_file = rb.STATE_FILE
        rb.STATE_FILE = self.state_file

    def tearDown(self):
        import gemini_app.storage.rollback as rb
        rb.STATE_FILE = self.orig_state_file
        self.tmp_dir.cleanup()

    def test_record_and_get_stable_commit(self):
        record_stable_commit("commit_abc12345")
        self.assertEqual(get_last_stable_commit(), "commit_abc12345")

    def test_reboot_flags_lifecycle(self):
        self.assertFalse(is_reboot_in_progress())
        mark_reboot_in_progress(target_commit="commit_xyz98765")
        self.assertTrue(is_reboot_in_progress())

        # Simulate successful startup
        mark_startup_successful()
        self.assertFalse(is_reboot_in_progress())

    def test_guardian_normal_execution(self):
        executed = []

        def dummy_app():
            executed.append(True)

        run_with_guardian(dummy_app)
        self.assertEqual(len(executed), 1)

    def test_guardian_catches_non_reboot_exception(self):
        def crashing_app():
            raise RuntimeError("Fatal initialization bug")

        with self.assertRaises(RuntimeError):
            run_with_guardian(crashing_app)


if __name__ == "__main__":
    unittest.main()
