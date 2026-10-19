"""Unit tests for project scaffolding, OS dependency detection, and onboarding."""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.onboarding import (
    ensure_first_time_onboarding,
    get_git_config,
    get_stored_api_key,
    get_stored_git_email,
    get_stored_user_real_name,
    is_first_boot_pending,
    mark_onboarding_completed,
    persist_api_key_to_shell,
    save_gemini_api_key,
    set_git_config,
    setup_git_credentials,
)
from gemini_app.projects import (
    generate_gitignore,
    generate_mit_license,
    generate_readme,
    get_user_real_name,
    scaffold_project,
    set_user_real_name,
)
from gemini_app.system_deps import (
    check_command_installed,
    check_dependencies,
    detect_os,
    ensure_system_dependencies,
    get_missing_binaries,
)
from gemini_app.tools.registry import ToolRegistry


class TestProjectsScaffolding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.projects_dir = Path(self.temp_dir) / "Projects"

        # Patch paths
        self.p_state = patch("gemini_app.projects.STATE_FILE", self.state_file)
        self.p_proj = patch("gemini_app.projects.PROJECTS_DIR", self.projects_dir)
        self.p_state.start()
        self.p_proj.start()

    def tearDown(self):
        self.p_state.stop()
        self.p_proj.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_user_real_name(self):
        name = get_user_real_name()
        self.assertEqual(name, "Kyle Gallagher")

    def test_set_and_get_user_real_name(self):
        set_user_real_name("Kyle Gallagher")
        self.assertEqual(get_user_real_name(), "Kyle Gallagher")
        self.assertTrue(self.state_file.exists())

    def test_generate_mit_license(self):
        lic = generate_mit_license("Kyle Gallagher", year=2026)
        self.assertIn("Copyright (c) 2026 Kyle Gallagher", lic)
        self.assertIn("MIT License", lic)

    def test_generate_readme(self):
        readme = generate_readme("MyTestProject", "A great test project", "Kyle Gallagher")
        self.assertIn("# MyTestProject", readme)
        self.assertIn("A great test project", readme)
        self.assertIn("Kyle Gallagher", readme)

    def test_scaffold_project_creation(self):
        result = scaffold_project(
            "DemoScaffold",
            description="Testing project generation",
            target_dir=self.projects_dir / "DemoScaffold",
            init_git=True,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["author"], "Kyle Gallagher")
        self.assertTrue(result["git_initialized"])

        target = Path(result["project_path"])
        self.assertTrue((target / "README.md").exists())
        self.assertTrue((target / "LICENSE").exists())
        self.assertTrue((target / ".gitignore").exists())
        self.assertTrue((target / ".git").is_dir())

        # Check license copyright
        lic_text = (target / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c)", lic_text)
        self.assertIn("Kyle Gallagher", lic_text)


class TestSystemDependencies(unittest.TestCase):
    def test_detect_os(self):
        info = detect_os()
        self.assertIn("distro_id", info)
        self.assertIn("package_manager", info)
        self.assertIn("install_command", info)

    def test_check_dependencies(self):
        res = check_dependencies(["python3"])
        self.assertTrue(res.get("python3"))

    def test_get_missing_binaries(self):
        missing = get_missing_binaries(["python3", "nonexistent_binary_xyz_123"])
        self.assertIn("nonexistent_binary_xyz_123", missing)
        self.assertNotIn("python3", missing)

    def test_ensure_dependencies_already_present(self):
        res = ensure_system_dependencies(required=["python3"])
        self.assertTrue(res["all_installed"])
        self.assertEqual(res["status"], "success")


class TestOnboarding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.env_file = Path(self.temp_dir) / ".env"
        self.bashrc = Path(self.temp_dir) / ".bashrc"
        self.bashrc.touch()

        self.p_state = patch("gemini_app.onboarding.STATE_FILE", self.state_file)
        self.p_env = patch("gemini_app.onboarding.DOTENV_FILE", self.env_file)
        self.p_shells = patch("gemini_app.onboarding.SHELL_CONFIG_FILES", [self.bashrc])
        self.p_state.start()
        self.p_env.start()
        self.p_shells.start()

    def tearDown(self):
        self.p_state.stop()
        self.p_env.stop()
        self.p_shells.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_retrieve_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            test_key = "test_key_12345"
            res = save_gemini_api_key(test_key)
            self.assertEqual(res["status"], "success")
            self.assertEqual(get_stored_api_key(), test_key)

            # Check shell persistence
            bashrc_content = self.bashrc.read_text(encoding="utf-8")
            self.assertIn(f'export GEMINI_API_KEY="{test_key}"', bashrc_content)

    def test_setup_git_credentials(self):
        with patch("gemini_app.onboarding.set_git_config", return_value=True):
            res = setup_git_credentials(real_name="Alice Dev", email="alice@example.com")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["real_name"], "Alice Dev")
            self.assertEqual(res["git_email"], "alice@example.com")

            # Check that state.json was updated
            self.assertTrue(self.state_file.exists())
            self.assertEqual(get_stored_user_real_name(), "Alice Dev")
            self.assertEqual(get_stored_git_email(), "alice@example.com")

    def test_is_first_boot_pending_and_completed(self):
        self.assertTrue(is_first_boot_pending())
        mark_onboarding_completed()
        self.assertFalse(is_first_boot_pending())

    def test_ensure_first_time_onboarding_interactive(self):
        with patch("builtins.input", side_effect=["Bob Coder", "bob@example.com"]):
            with patch("getpass.getpass", return_value="dummy_key_777"):
                with patch("gemini_app.onboarding.set_git_config", return_value=True):
                    with patch("sys.stdin.isatty", return_value=True):
                        res = ensure_first_time_onboarding(interactive=True)
                        self.assertEqual(res["real_name"], "Bob Coder")
                        self.assertEqual(res["git_email"], "bob@example.com")
                        self.assertTrue(res["api_key_configured"])
                        self.assertFalse(is_first_boot_pending())

    def test_ensure_first_time_onboarding_vault_confirmation(self):
        # API key, then passkey, then mismatch confirmation, then passkey, then matching confirmation
        with patch("builtins.input", side_effect=["Alice Dev", "alice@dev.org"]):
            with patch(
                "getpass.getpass",
                side_effect=[
                    "dummy_api_key",
                    "secret123",
                    "secretWrong",
                    "secret123",
                    "secret123",
                ],
            ):
                with patch("gemini_app.onboarding.set_git_config", return_value=True):
                    with patch("sys.stdin.isatty", return_value=True):
                        res = ensure_first_time_onboarding(interactive=True)
                        self.assertTrue(res.get("vault_configured"))


class TestToolRegistryExtensions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.registry = ToolRegistry(working_dir=self.temp_dir, history=[])

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_new_tools_present_in_registry(self):
        tools_list, tools_dict = self.registry.get_tool_callables()
        self.assertIn("scaffold_project", tools_dict)
        self.assertIn("manage_system_dependencies", tools_dict)

    def test_scaffold_project_via_tool(self):
        _, tools_dict = self.registry.get_tool_callables()
        proj_dir = Path(self.temp_dir) / "ToolScaffolded"
        res = tools_dict["scaffold_project"](
            project_name="ToolScaffolded",
            target_dir=str(proj_dir),
            author="Kyle Gallagher",
        )
        self.assertEqual(res["status"], "success")
        self.assertTrue((proj_dir / "LICENSE").exists())
        self.assertIn("Kyle Gallagher", (proj_dir / "LICENSE").read_text(encoding="utf-8"))

    def test_manage_system_deps_check(self):
        _, tools_dict = self.registry.get_tool_callables()
        res = tools_dict["manage_system_dependencies"](action="check", packages=["python3"])
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["dependencies"]["python3"])


if __name__ == "__main__":
    unittest.main()
