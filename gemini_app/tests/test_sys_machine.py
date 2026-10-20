"""Unit tests for system-level infrastructure (~/.sys directory and ssh_machine.sh)."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from gemini_app import sys_machine


class TestSysMachine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="gemini_sys_test_")
        self.fake_home = Path(self.test_dir)
        self.fake_sys = self.fake_home / ".sys"
        self.fake_gemini = self.fake_home / ".gemini"
        self.fake_gemini.mkdir(parents=True, exist_ok=True)

        self.orig_sys_dir = sys_machine.SYS_DIR
        self.orig_ssh_machine = sys_machine.SSH_MACHINE_PATH
        self.orig_shell_profiles = sys_machine.SHELL_PROFILES

        sys_machine.SYS_DIR = self.fake_sys
        sys_machine.SSH_MACHINE_PATH = self.fake_sys / "ssh_machine.sh"
        sys_machine.SHELL_PROFILES = [
            self.fake_home / ".bashrc",
            self.fake_home / ".profile",
        ]

    def tearDown(self):
        sys_machine.SYS_DIR = self.orig_sys_dir
        sys_machine.SSH_MACHINE_PATH = self.orig_ssh_machine
        sys_machine.SHELL_PROFILES = self.orig_shell_profiles
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ensure_sys_directory(self):
        d = sys_machine.ensure_sys_directory()
        self.assertTrue(d.exists())
        self.assertTrue(d.is_dir())
        self.assertEqual(d, self.fake_sys)

    def test_build_ssh_machine_script_content(self):
        fake_key = self.fake_home / ".ssh" / "id_ed25519"
        script = sys_machine.build_ssh_machine_script(fake_key)
        self.assertIn("#!/bin/sh", script)
        self.assertIn(str(fake_key), script)
        self.assertIn("agent_healthy()", script)
        self.assertIn("ssh-add -l", script)
        self.assertIn("2>&1", script)
        self.assertNotIn("2&>1", script)

    def test_install_ssh_machine(self):
        fake_key = self.fake_home / "custom_key"
        fake_key.touch()
        path = sys_machine.install_ssh_machine(fake_key)
        self.assertTrue(path.exists())
        self.assertTrue(path.is_file())
        content = path.read_text(encoding="utf-8")
        self.assertIn(str(fake_key), content)
        # Check permissions: executable
        self.assertTrue(os.access(str(path), os.X_OK))

    def test_hook_ssh_machine_to_shells(self):
        bashrc = self.fake_home / ".bashrc"
        bashrc.write_text("# existing bashrc\nexport FOO=1\n", encoding="utf-8")
        profile = self.fake_home / ".profile"
        profile.write_text("# existing profile\n", encoding="utf-8")

        hooked = sys_machine.hook_ssh_machine_to_shells()
        self.assertIn(str(bashrc), hooked)
        self.assertIn(str(profile), hooked)

        # Check content
        b_content = bashrc.read_text(encoding="utf-8")
        self.assertIn("ssh_machine.sh", b_content)

        # Calling again should not create duplicate entries
        hooked_again = sys_machine.hook_ssh_machine_to_shells()
        self.assertEqual(hooked_again, [])

    def test_sync_system_ssh_machine(self):
        priv_key = self.fake_home / "test_id_cluster"
        priv_key.write_text("dummy_key", encoding="utf-8")
        pub_key = self.fake_home / "test_id_cluster.pub"
        pub_key.write_text("ssh-ed25519 AAAATESTPUBKEY test@example.com\n", encoding="utf-8")

        result = sys_machine.sync_system_ssh_machine(priv_key)
        self.assertTrue(Path(result["sys_dir"]).exists())
        self.assertTrue(Path(result["ssh_machine_script"]).exists())
        self.assertEqual(result["target_key"], str(priv_key))
        self.assertEqual(result["public_key"], "ssh-ed25519 AAAATESTPUBKEY test@example.com")


if __name__ == "__main__":
    unittest.main()
