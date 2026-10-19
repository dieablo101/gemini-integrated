"""Tests for autonomous Linux distro detection and environment bootstrapping."""

import os
from pathlib import Path
import tempfile
import unittest

from gemini_app.bootstrap import (
    check_python_dependencies,
    detect_linux_distro,
    is_running_in_venv,
    persist_api_key,
)
from gemini_app.system_deps import detect_os, parse_os_release


class TestBootstrap(unittest.TestCase):
    def test_detect_linux_distro_returns_structure(self):
        distro = detect_linux_distro()
        self.assertIn("system", distro)
        self.assertIn("id", distro)
        self.assertIn("family", distro)
        self.assertIn("pkg_manager", distro)

    def test_detect_os_from_system_deps(self):
        os_info = detect_os()
        self.assertIn("distro_id", os_info)
        self.assertIn("package_manager", os_info)

    def test_running_in_venv_check(self):
        # We know we are running in .venv
        in_venv = is_running_in_venv()
        self.assertIsInstance(in_venv, bool)

    def test_python_dependencies_check(self):
        # All required dependencies (textual, google-genai, rich, pyperclip) should be satisfied
        missing = check_python_dependencies()
        self.assertEqual(missing, [])

    def test_persist_api_key(self):
        test_key = "test_key_12345_sample"
        persist_api_key(test_key)
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), test_key)


if __name__ == "__main__":
    unittest.main()
