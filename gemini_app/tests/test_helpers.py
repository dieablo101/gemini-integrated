"""Tests for formatting, language detection, ray casting, and ASCII trees."""

import tempfile
import unittest
from pathlib import Path

from gemini_app.helpers import (
    build_ascii_tree,
    cast_ray_from_center,
    detect_language,
    extract_retry_delay,
    format_reconnect_countdown,
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

    def test_build_ascii_tree_max_depth(self):
        files = ["src/nested/sub/deep.py", "src/nested/file.py", "README.md"]
        tree_depth1 = build_ascii_tree(files, root_name="project", max_depth=1)
        self.assertIn("src/ ...", tree_depth1)
        self.assertNotIn("deep.py", tree_depth1)

        tree_depth2 = build_ascii_tree(files, root_name="project", max_depth=2)
        self.assertIn("nested/ ...", tree_depth2)
        self.assertNotIn("deep.py", tree_depth2)

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

    def test_extract_retry_delay_high_precision(self):
        # Protobuf with seconds + nanos
        self.assertEqual(
            extract_retry_delay("ResourceExhausted: 429 [retry_delay { seconds: 12 nanos: 500000000 }]"),
            12.5,
        )
        self.assertEqual(
            extract_retry_delay("seconds: 7 nanos: 250000000"),
            7.25,
        )
        # Protobuf with only seconds
        self.assertEqual(
            extract_retry_delay("retry_delay { seconds: 20 }"),
            20.0,
        )
        # JSON / quotaResetDelay / retryDelay
        self.assertEqual(
            extract_retry_delay('{"error": {"quotaResetDelay": "15.5s"}}'),
            15.5,
        )
        self.assertEqual(
            extract_retry_delay('{"retryDelay": "8s"}'),
            8.0,
        )
        # Natural language patterns
        self.assertEqual(
            extract_retry_delay("Resource exhausted. Please retry in 18.2s."),
            18.2,
        )
        self.assertEqual(
            extract_retry_delay("Rate limit exceeded. Please retry after 14 seconds."),
            14.0,
        )
        self.assertEqual(
            extract_retry_delay("Rate limit hit, wait 4.5 seconds"),
            4.5,
        )
        # Retry-After header
        self.assertEqual(
            extract_retry_delay("HTTP/1.1 429 Too Many Requests\nRetry-After: 30"),
            30.0,
        )
        # Exception object
        exc = Exception("Quota exceeded, retry in 10s")
        self.assertEqual(extract_retry_delay(exc), 10.0)
        # Composite minutes + seconds
        self.assertEqual(extract_retry_delay('{"retryDelay": "1m25.4s"}'), 85.4)
        # Google RPC retryInfo format
        self.assertEqual(
            extract_retry_delay("{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '18.423s'}"),
            18.423,
        )
        # None when no hint is present
        self.assertIsNone(extract_retry_delay("Random unparseable error"))

    def test_format_reconnect_countdown(self):
        self.assertEqual(format_reconnect_countdown(0.0), "0.0s")
        self.assertEqual(format_reconnect_countdown(-5.0), "0.0s")
        self.assertEqual(format_reconnect_countdown(float("nan")), "0.0s")
        self.assertEqual(format_reconnect_countdown(float("inf")), "0.0s")
        self.assertEqual(format_reconnect_countdown(0.04), "0.0s")
        self.assertEqual(format_reconnect_countdown(0.82), "0.8s")
        self.assertEqual(format_reconnect_countdown(12.5), "12.5s")
        self.assertEqual(format_reconnect_countdown(59.94), "59.9s")
        self.assertEqual(format_reconnect_countdown(60.0), "1m 0.0s")
        self.assertEqual(format_reconnect_countdown(75.32), "1m 15.3s")
        self.assertEqual(format_reconnect_countdown(134.8), "2m 14.8s")



if __name__ == "__main__":
    unittest.main()
