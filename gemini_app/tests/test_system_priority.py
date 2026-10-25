"""Unit tests for system-level CPU and I/O scheduling priority manager."""

import os
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.system_priority import (
    _get_ioprio_syscall_num,
    elevate_system_priority,
    format_priority_summary,
    get_system_priority,
)


class TestSystemPriority(unittest.TestCase):
    """Tests priority elevation, inspection, and formatting."""

    def test_ioprio_syscall_num_detection(self) -> None:
        """Verifies syscall number resolution returns valid integer."""
        num = _get_ioprio_syscall_num()
        self.assertIsInstance(num, int)
        self.assertIn(num, (30, 251, 289, 314))

    def test_get_system_priority_structure(self) -> None:
        """Verifies get_system_priority inspects current process and returns expected fields."""
        info = get_system_priority()
        self.assertIn("pid", info)
        self.assertEqual(info["pid"], os.getpid())
        self.assertIn("nice", info)
        self.assertIsInstance(info["nice"], int)
        self.assertIn("is_high_priority", info)
        self.assertIsInstance(info["is_high_priority"], bool)

    def test_format_priority_summary(self) -> None:
        """Verifies priority summary string includes nice value and PID."""
        summary = format_priority_summary()
        self.assertIsInstance(summary, str)
        self.assertIn("nice:", summary)
        self.assertIn(f"PID: {os.getpid()}", summary)

    def test_elevate_system_priority_live_execution(self) -> None:
        """Verifies elevate_system_priority executes safely without raising exceptions."""
        res = elevate_system_priority(target_nice=-10)
        self.assertIn("status", res)
        self.assertIn(res["status"], ("elevated", "improved", "standard", "unsupported_platform"))
        self.assertIn("current_nice", res)
        self.assertIn("ioprio_method", res)

    @patch("gemini_app.system_priority.platform.system", return_value="Windows")
    def test_unsupported_platform_graceful_handling(self, mock_plat) -> None:
        """Verifies non-Linux platforms return unsupported_platform cleanly."""
        res = elevate_system_priority()
        self.assertEqual(res["status"], "unsupported_platform")


if __name__ == "__main__":
    unittest.main()
