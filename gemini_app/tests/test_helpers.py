"""Tests for formatting, language detection, ray casting, and ASCII trees."""

import tempfile
import unittest
from pathlib import Path

from gemini_app.helpers import (
    build_ascii_tree,
    cast_ray_from_center,
    detect_language,
    truncate_wire_snippets,
    write_code_to_disk,
)


class TestHelpers(unittest.TestCase):
    def test_detect_language(self):
        self.assertEqual(detect_language("script.py"), "python")
        self.assertEqual(detect_language("main.rs"), "rust")
        self.assertEqual(detect_language("app.jsx"), "jsx")
        self.assertEqual(detect_language("config.toml"), "toml")
        self.assertEqual(detect_language("layout.xml"), "xml")
        self.assertEqual(detect_language("unknown.xyz"), "")

    def test_cast_ray_from_center(self):
        # Empty header map
        self.assertEqual(cast_ray_from_center(50, {}), (0, "", 0))

        # Single header at y=20
        header_map = {20: (1, "turn_abc")}
        t_idx, t_id, offset = cast_ray_from_center(20, header_map)
        self.assertEqual((t_idx, t_id, offset), (1, "turn_abc", 0))

        # Center above lowest header
        t_idx, t_id, offset = cast_ray_from_center(10, header_map)
        self.assertEqual((t_idx, t_id, offset), (1, "turn_abc", -10))

        # Center below highest header
        t_idx, t_id, offset = cast_ray_from_center(35, header_map)
        self.assertEqual((t_idx, t_id, offset), (1, "turn_abc", 15))

        # Multiple headers
        headers = {
            10: (0, "turn_0"),
            30: (1, "turn_1"),
            60: (2, "turn_2"),
        }
        # Center near 30
        t_idx, t_id, offset = cast_ray_from_center(32, headers)
        self.assertEqual(t_id, "turn_1")
        self.assertEqual(offset, 2)

    def test_build_ascii_tree(self):
        files = ["src/main.py", "src/utils.py", "README.md"]
        tree = build_ascii_tree(files, root_name="project")
        self.assertIn("project/", tree)
        self.assertIn("README.md", tree)
        self.assertIn("src/", tree)
        self.assertIn("main.py", tree)
        self.assertIn("utils.py", tree)

    def test_truncate_wire_snippets(self):
        # Snippet within limit (<25 lines)
        short_code = "```python\nprint(1)\nprint(2)\n```"
        self.assertEqual(truncate_wire_snippets(short_code, max_lines=25), short_code)

        # Snippet exceeding limit
        long_lines = [f"line_{i}" for i in range(50)]
        long_code = "```python\n" + "\n".join(long_lines) + "\n```"
        truncated = truncate_wire_snippets(long_code, max_lines=5)
        self.assertIn("line_0", truncated)
        self.assertIn("line_4", truncated)
        self.assertNotIn("line_49", truncated)
        self.assertIn("lines truncated from wire", truncated)

    def test_write_code_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = write_code_to_disk(tmpdir, "subdir/test.py", "print('hello')\n")
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.read_text(encoding="utf-8"), "print('hello')\n")


if __name__ == "__main__":
    unittest.main()
