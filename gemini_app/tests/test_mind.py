"""Unit tests for mind map system instruction building and footer parsing."""

import unittest

from gemini_app.mind.parser import (
    build_system_instruction,
    extract_mind_map,
)


class TestMind(unittest.TestCase):
    def test_build_system_instruction(self):
        prompt = build_system_instruction(
            working_dir="/opt/gemini",
            total_turns=15,
            gemini_state="Refactoring runner",
            user_state="Wants modular directory",
            tree_state=["T1", "F:app.py"],
            tree_content="└── gemini_app",
        )
        self.assertIn("Working directory: /opt/gemini", prompt)
        self.assertIn("Total conversation turns on record: 15", prompt)
        self.assertIn("• GEMINI MIND STATE: Refactoring runner", prompt)
        self.assertIn("• USER MIND STATE: Wants modular directory", prompt)
        self.assertIn("• TREE ANCHOR STATE: [T1, F:app.py]", prompt)
        self.assertIn("└── gemini_app", prompt)
        self.assertIn("json:mind_map", prompt)

    def test_extract_mind_map_valid(self):
        reply = (
            "Here is the code you asked for:\n"
            "```python\nprint('hello')\n```\n\n"
            "```json:mind_map\n"
            "{\n"
            '  "gemini_state": "Code generated",\n'
            '  "user_state": "Executing code",\n'
            '  "tree_state": ["T1", "T2"],\n'
            '  "tree_content": "└── root"\n'
            "}\n"
            "```"
        )
        clean_text, meta = extract_mind_map(reply)

        self.assertNotIn("json:mind_map", clean_text)
        self.assertIn("print('hello')", clean_text)
        self.assertEqual(meta["gemini_state"], "Code generated")
        self.assertEqual(meta["user_state"], "Executing code")
        self.assertEqual(meta["tree_state"], ["T1", "T2"])
        self.assertEqual(meta["tree_content"], "└── root")

    def test_extract_mind_map_missing(self):
        reply = "Just a regular response without metadata footer."
        clean_text, meta = extract_mind_map(
            reply,
            default_gemini_state="Default Gem",
            default_user_state="Default User",
        )
        self.assertEqual(clean_text, reply)
        self.assertEqual(meta["gemini_state"], "Default Gem")
        self.assertEqual(meta["user_state"], "Default User")


if __name__ == "__main__":
    unittest.main()
