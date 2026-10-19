"""Tests for configuration, constants, and theme generation."""

import unittest

from gemini_app.config import (
    DEFAULT_MODEL,
    DEFAULT_PALETTE,
    THEMES,
    TURNS_PER_SEGMENT,
    generate_theme_css_rules,
)


class TestConfig(unittest.TestCase):
    def test_themes_defined(self):
        for name in ["red", "blue", "green", "orange", "purple", "yellow", "pink"]:
            self.assertIn(name, THEMES)
            cfg = THEMES[name]
            self.assertIn("accent", cfg)
            self.assertIn("accent_dim", cfg)
            self.assertIn("accent_bright", cfg)
            self.assertIn("banner_bg", cfg)
            self.assertIn("card_active_bg", cfg)

    def test_default_constants(self):
        self.assertEqual(DEFAULT_PALETTE, "red")
        self.assertEqual(DEFAULT_MODEL, "gemini-3.8-flash")
        self.assertEqual(TURNS_PER_SEGMENT, 200)

    def test_generate_theme_css_rules(self):
        css = generate_theme_css_rules()
        self.assertIsInstance(css, str)
        self.assertIn(".theme-red", css)
        self.assertIn(".theme-blue", css)
        self.assertIn(".turn_card.card-active", css)


if __name__ == "__main__":
    unittest.main()
