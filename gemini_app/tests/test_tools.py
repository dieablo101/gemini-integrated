"""Unit tests for bilateral tools (workspace, execution, mind_tools, registry)."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from gemini_app.storage.memory_index import MemoryIndex
from gemini_app.tools.execution import execute_shell
from gemini_app.tools.mind_tools import expand_mind, recall_memory
from gemini_app.tools.registry import ToolRegistry
from gemini_app.tools.workspace import (
    apply_patch,
    scan_workspace_tree,
    search_codebase,
    write_file,
)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

        # Create dummy repo structure
        (self.work_dir / "src").mkdir()
        (self.work_dir / "src" / "main.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")
        (self.work_dir / "README.md").write_text("# Test Repo\nA project for testing.\n", encoding="utf-8")

        # Initialize git repo for tree scanning
        subprocess.run(["git", "init"], cwd=str(self.work_dir), capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(self.work_dir), capture_output=True)

        self.memory_index = MemoryIndex(self.work_dir / "mem.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_workspace_tree(self):
        tree_str = scan_workspace_tree(self.work_dir, include_ignored=True)
        self.assertIn("main.py", tree_str)
        self.assertIn("README.md", tree_str)

    def test_write_file(self):
        res = write_file(self.work_dir, path="src/sub/test.txt", content="Sample Content")
        self.assertEqual(res["status"], "success")
        target = self.work_dir / "src" / "sub" / "test.txt"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "Sample Content")

    def test_apply_patch_success(self):
        res = apply_patch(
            self.work_dir,
            path="src/main.py",
            search_block="print('world')",
            replace_block="print('universe')",
        )
        self.assertEqual(res["status"], "success")
        content = (self.work_dir / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn("print('universe')", content)
        self.assertNotIn("print('world')", content)

    def test_apply_patch_not_found(self):
        res = apply_patch(
            self.work_dir,
            path="src/main.py",
            search_block="print('nonexistent')",
            replace_block="print('universe')",
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("not found", res["message"])

    def test_search_codebase(self):
        res = search_codebase(self.work_dir, query="hello")
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["total_matches"], 1)
        self.assertTrue(any("main.py" in m and "hello" in m for m in res["matches"]))

    def test_execute_shell(self):
        res = execute_shell(self.work_dir, command="echo 'runner test'")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("runner test", res["stdout"])

    def test_expand_mind(self):
        history = [
            {"turn_id": "turn_1", "role": "user", "text": "Turn 1 content"},
            {"turn_id": "turn_2", "role": "model", "text": "Turn 2 content"},
        ]
        result = expand_mind(
            self.work_dir,
            history,
            turn_numbers=[1, 2],
            file_paths=["README.md"],
            memory_index=self.memory_index,
        )
        self.assertIn("T1", result["turns"])
        self.assertEqual(result["turns"]["T1"]["content"], "Turn 1 content")
        self.assertIn("T2", result["turns"])
        self.assertEqual(result["turns"]["T2"]["content"], "Turn 2 content")
        self.assertIn("README.md", result["files"])
        self.assertIn("# Test Repo", result["files"]["README.md"])

    def test_recall_memory(self):
        self.memory_index.index_turn(
            turn_id="tid_42",
            chat_id="chat_proj_x",
            turn_number=7,
            role="user",
            content="We built a custom AST parser in Cython",
            title="AST Cython Engine",
        )
        rec = recall_memory(
            query="Cython parser",
            max_results=5,
            memory_index=self.memory_index,
        )
        self.assertEqual(rec["matches_count"], 1)
        self.assertEqual(rec["matches"][0]["turn_id"], "tid_42")
        self.assertEqual(rec["matches"][0]["title"], "AST Cython Engine")

    def test_expand_mind_limit(self):
        history = []
        result = expand_mind(
            self.work_dir,
            history,
            turn_numbers=list(range(60)),
        )
        self.assertIn("error", result)

    def test_tool_registry(self):
        phases = []

        def on_phase(p: str):
            phases.append(p)

        history = [{"role": "user", "text": "Query"}]
        registry = ToolRegistry(
            working_dir=self.work_dir,
            history=history,
            phase_callback=on_phase,
            reboot_callback=lambda d: {"status": "scheduled", "delay": d},
            memory_index=self.memory_index,
        )
        tools_list, tools_dict = registry.get_tool_callables()

        self.assertEqual(len(tools_list), 10)
        self.assertIn("scan_workspace_tree", tools_dict)
        self.assertIn("expand_mind", tools_dict)
        self.assertIn("recall_memory", tools_dict)
        self.assertIn("write_file", tools_dict)
        self.assertIn("apply_patch", tools_dict)
        self.assertIn("search_codebase", tools_dict)
        self.assertIn("execute_shell", tools_dict)
        self.assertIn("reboot_console", tools_dict)
        self.assertIn("take_snapshot", tools_dict)
        self.assertIn("review_snapshots", tools_dict)

        # Call apply_patch through dict
        p_res = tools_dict["apply_patch"](
            path="src/main.py",
            search_block="print('hello')",
            replace_block="print('patched')",
        )
        self.assertEqual(p_res["status"], "success")

        # Call reboot_console through dict
        r_res = tools_dict["reboot_console"](delay_seconds=2.0)
        self.assertEqual(r_res["status"], "scheduled")
        self.assertEqual(r_res["delay"], 2.0)

        # Call reboot_console with status_report
        registry2 = ToolRegistry(
            working_dir=self.work_dir,
            history=history,
            reboot_callback=lambda d, r="": {"status": "scheduled", "delay": d, "report": r},
            memory_index=self.memory_index,
        )
        _, dict2 = registry2.get_tool_callables()
        r_res2 = dict2["reboot_console"](delay_seconds=1.0, status_report="Console Ready")
        self.assertEqual(r_res2["report"], "Console Ready")


if __name__ == "__main__":
    unittest.main()
