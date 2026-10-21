"""Tests for SystemRunner and gemini_app.build_runner."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_app.build_runner import SystemRunner, cli_main, run_detached_runner


class TestBuildRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "test_run.log"

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("gemini_app.build_runner.update_status")
    def test_run_command_success(self, mock_status):
        runner = SystemRunner(
            task_name="test_task",
            log_path=self.log_path,
            nice_level=0,
            enable_notifications=True,
        )
        res = runner.run_command("echo 'hello from build runner'", cwd=self.temp_dir.name)
        self.assertEqual(res.returncode, 0)
        self.assertIn("hello from build runner", res.stdout)
        self.assertTrue(self.log_path.exists())
        log_content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("hello from build runner", log_content)

    @patch("gemini_app.build_runner.update_status")
    def test_run_command_failure(self, mock_status):
        runner = SystemRunner(
            task_name="test_task_fail",
            log_path=self.log_path,
            nice_level=0,
            enable_notifications=False,
        )
        with self.assertRaises(RuntimeError):
            runner.run_command("false")

    @patch("gemini_app.build_runner.notify_chat")
    @patch("gemini_app.build_runner.update_status")
    def test_run_pipeline(self, mock_status, mock_chat):
        runner = SystemRunner(
            task_name="test_pipeline",
            log_path=self.log_path,
            nice_level=0,
            enable_notifications=True,
        )
        stages = [
            {"name": "Stage 1", "cmd": "echo 'step 1'"},
            {"name": "Stage 2", "cmd": "echo 'step 2'"},
        ]
        success = runner.run_pipeline(stages, chat_report=True)
        self.assertTrue(success)
        mock_chat.assert_called_once()

    @patch("gemini_app.build_runner.update_status")
    def test_cli_main_success(self, mock_status):
        exit_code = cli_main(["echo cli_test", "--name", "cli_test_task", "--log", str(self.log_path), "--no-notify"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(self.log_path.exists())
        self.assertIn("cli_test", self.log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
