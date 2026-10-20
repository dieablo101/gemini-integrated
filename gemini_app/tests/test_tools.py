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

    def test_scan_workspace_tree_max_depth(self):
        tree_str = scan_workspace_tree(self.work_dir, include_ignored=True, max_depth=1)
        self.assertIn("src/ ...", tree_str)
        self.assertNotIn("main.py", tree_str)

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

    def test_expand_mind_slice_and_outline(self):
        sample_code = (
            "class Engine:\n"
            "    def start(self):\n"
            "        return True\n\n"
            "def run():\n"
            "    e = Engine()\n"
            "    return e.start()\n"
        )
        (self.work_dir / "src" / "engine.py").write_text(sample_code, encoding="utf-8")

        # Test line slice
        res_slice = expand_mind(
            self.work_dir,
            history=[],
            file_paths=["src/engine.py:2-3"],
        )
        self.assertIn("src/engine.py:2-3", res_slice["files"])
        slice_text = res_slice["files"]["src/engine.py:2-3"]
        self.assertIn("lines 2 to 3", slice_text)
        self.assertIn("def start(self):", slice_text)
        self.assertNotIn("class Engine:", slice_text)

        # Test symbol outline
        res_outline = expand_mind(
            self.work_dir,
            history=[],
            file_paths=["src/engine.py:outline"],
        )
        self.assertIn("src/engine.py:outline", res_outline["files"])
        outline_text = res_outline["files"]["src/engine.py:outline"]
        self.assertIn("Outline of src/engine.py", outline_text)
        self.assertIn("class Engine:", outline_text)
        self.assertIn("def start(self):", outline_text)
        self.assertIn("def run():", outline_text)

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

        self.assertEqual(len(tools_list), 16)
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
        self.assertIn("manage_notes", tools_dict)
        self.assertIn("scaffold_project", tools_dict)
        self.assertIn("manage_system_dependencies", tools_dict)
        self.assertIn("introspect_console", tools_dict)
        self.assertIn("interact_ui", tools_dict)
        self.assertIn("manage_fleet_nodes", tools_dict)

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

    def test_tool_registry_detailed_phase_callback(self):
        phase_records = []

        def on_phase_detailed(phase: str, details: str = ""):
            phase_records.append((phase, details))

        registry = ToolRegistry(
            working_dir=self.work_dir,
            history=[],
            phase_callback=on_phase_detailed,
            memory_index=self.memory_index,
        )
        _, tools_dict = registry.get_tool_callables()

        # Call write_file
        tools_dict["write_file"](path="sample.py", content="# code")
        self.assertTrue(any(p[0] == "writing" and "sample.py" in p[1] for p in phase_records))

        # Call execute_shell
        tools_dict["execute_shell"](command="echo 'phase test'")
        self.assertTrue(any(p[0] == "executing" and "echo" in p[1] for p in phase_records))

    def test_introspection_and_ui_interaction_tools(self):
        def dummy_intro(tier: str):
            return {"status": "success", "tier": tier, "active_theme": "blue"}

        def dummy_ui(action: str, target: str = "all", palette: str = "", effect: str = "none", duration: float = 3.0, message: str = ""):
            return {"status": "success", "action": action, "target": target, "palette": palette, "effect": effect}

        registry = ToolRegistry(
            working_dir=self.work_dir,
            history=[],
            introspection_callback=dummy_intro,
            ui_interact_callback=dummy_ui,
        )
        _, tools_dict = registry.get_tool_callables()

        # Call introspect_console
        intro_res = tools_dict["introspect_console"](tier="visual")
        self.assertEqual(intro_res["status"], "success")
        self.assertEqual(intro_res["tier"], "visual")
        self.assertEqual(intro_res["active_theme"], "blue")

        # Call interact_ui
        ui_res = tools_dict["interact_ui"](
            action="accent_talk",
            target="feed",
            palette="purple",
            duration=4.0,
            message="Testing UI talk",
        )
        self.assertEqual(ui_res["status"], "success")
        self.assertEqual(ui_res["action"], "accent_talk")
        self.assertEqual(ui_res["target"], "feed")
        self.assertEqual(ui_res["palette"], "purple")

        # Test interact_ui with pulse_nav target
        nav_res = tools_dict["interact_ui"](
            action="pulse_nav",
            target="edge",
            palette="green",
            duration=2.0,
            message="At the edge / top of stream!",
        )
        self.assertEqual(nav_res["status"], "success")
        self.assertEqual(nav_res["action"], "pulse_nav")
        self.assertEqual(nav_res["target"], "edge")


if __name__ == "__main__":
    unittest.main()
