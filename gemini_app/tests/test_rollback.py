"""Unit tests for the autonomous safety supervisor and rollback engine."""

import json
from pathlib import Path
import tempfile
import unittest

from gemini_app.storage.rollback import (
    check_reboot_guard,
    create_safety_checkpoint,
    get_current_git_commit,
    get_last_stable_commit,
    is_reboot_in_progress,
    mark_reboot_in_progress,
    mark_startup_successful,
    perform_git_rollback,
    record_stable_commit,
    restore_safety_checkpoint,
    run_with_guardian,
    verify_offline_preflight,
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

    def test_verify_offline_preflight_valid(self):
        ok, msg = verify_offline_preflight()
        self.assertTrue(ok)
        self.assertIn("Pre-flight verification passed", msg)

    def test_verify_offline_preflight_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_dir = Path(tmp_dir) / "gemini_app"
            bad_dir.mkdir()
            bad_file = bad_dir / "broken.py"
            bad_file.write_text("def broken_syntax(:\n")
            ok, msg = verify_offline_preflight(cwd=tmp_dir)
            self.assertFalse(ok)
            self.assertIn("failed", msg.lower())

    def test_check_reboot_guard(self):
        # Fresh state -> allowed
        ok, msg = check_reboot_guard(min_interval_seconds=2.0)
        self.assertTrue(ok)

        # Mark reboot just now -> rate-limited
        mark_reboot_in_progress()
        ok, msg = check_reboot_guard(min_interval_seconds=2.0)
        self.assertFalse(ok)
        self.assertIn("rate-limited", msg.lower())

    def test_safety_checkpoints(self):
        ckpt = create_safety_checkpoint(label="unit_test_checkpoint")
        self.assertIn("id", ckpt)
        self.assertEqual(ckpt["label"], "unit_test_checkpoint")

        # Non-existent checkpoint restore returns False cleanly
        ok, msg = restore_safety_checkpoint("non_existent_ckpt")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())

    def test_safe_mode_consecutive_boot_failures(self):
        # Simulate consecutive startup crashes reaching Safe Mode threshold
        import os
        os.environ["GEMINI_TESTING"] = "1"
        try:
            def crashing():
                raise RuntimeError("Crash on start")

            # 1st crash
            with self.assertRaises(RuntimeError):
                run_with_guardian(crashing)
            # 2nd crash
            with self.assertRaises(RuntimeError):
                run_with_guardian(crashing)
            # 3rd crash -> should activate Safe Mode (and return cleanly without re-raising in test mode)
            run_with_guardian(crashing)

            # Successful startup resets counter
            mark_startup_successful()
            from gemini_app.storage.rollback import read_state
            self.assertEqual(read_state().get("boot_failures_count"), 0)
        finally:
            os.environ.pop("GEMINI_TESTING", None)

    def test_verify_offline_preflight_smoke_tests(self):
        ok, msg = verify_offline_preflight(run_smoke_tests=True)
        self.assertTrue(ok)
        self.assertIn("Pre-flight verification passed", msg)


if __name__ == "__main__":
    unittest.main()
