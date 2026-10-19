"""Tests for autonomous project scaffolding and Kyle Gallagher copyright enforcement."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gemini_app.projects as projects_module
from gemini_app.projects import (
    DEFAULT_COPYRIGHT_HOLDER,
    generate_mit_license,
    generate_readme,
    get_user_realname,
    scaffold_project,
    set_user_realname,
)


class TestProjectScaffolding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_projects_dir = Path(self.temp_dir.name)
        self.test_state_file = self.test_projects_dir / "test_state.json"
        self._orig_state_file = projects_module.STATE_FILE
        projects_module.STATE_FILE = self.test_state_file

    def tearDown(self):
        projects_module.STATE_FILE = self._orig_state_file
        self.temp_dir.cleanup()

    def test_default_copyright_holder(self):
        self.assertEqual(DEFAULT_COPYRIGHT_HOLDER, "Kyle Gallagher")
        self.assertEqual(get_user_realname(), "Kyle Gallagher")

    def test_generate_license_contains_copyright(self):
        lic = generate_mit_license("Kyle Gallagher", year=2025)
        self.assertIn("Copyright (c) 2025 Kyle Gallagher", lic)
        self.assertIn("MIT License", lic)

    def test_generate_readme_structure(self):
        readme = generate_readme("test-tool", "A sample CLI tool", "Kyle Gallagher", year=2025)
        self.assertIn("# test-tool", readme)
        self.assertIn("A sample CLI tool", readme)
        self.assertIn("Copyright (c) 2025 Kyle Gallagher", readme)

    def test_scaffold_project_files_created(self):
        target = self.test_projects_dir / "my_new_app"
        res = scaffold_project(
            name="my_new_app",
            description="Testing project scaffolding",
            target_dir=target,
            git_init=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["project_name"], "my_new_app")
        self.assertEqual(res["copyright_holder"], "Kyle Gallagher")

        # Verify files exist on disk
        self.assertTrue((target / "README.md").exists())
        self.assertTrue((target / "LICENSE").exists())
        self.assertTrue((target / ".gitignore").exists())

        # Verify content of license
        lic_content = (target / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c)", lic_content)
        self.assertIn("Kyle Gallagher", lic_content)

        # Verify git repository was initialized
        self.assertTrue((target / ".git").exists())

    def test_scaffold_custom_author(self):
        target = self.test_projects_dir / "custom_app"
        res = scaffold_project(
            name="custom_app",
            author="Custom Creator",
            target_dir=target,
            git_init=False,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["copyright_holder"], "Custom Creator")
        lic_content = (target / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Custom Creator", lic_content)


if __name__ == "__main__":
    unittest.main()
