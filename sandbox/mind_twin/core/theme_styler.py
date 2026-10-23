"""
theme_styler.py - Theme Palette and Shade Engine for Cognitive Interludes.

Uses shades and tints of the current bilateral theme palette to render
cognitive cards, memory interludes, and fold indicators without breaking visual harmony.
"""

from __future__ import annotations
from typing import Dict, Any, Optional

# Mirrors the theme definitions in production config.py
THEMES: Dict[str, Dict[str, str]] = {
    "red": {
        "accent": "#ff3333",
        "accent_dim": "#aa1111",
        "accent_bright": "#ff6666",
        "banner_bg": "#8b0000",
        "card_active_bg": "#2a0808",
    },
    "blue": {
        "accent": "#3399ff",
        "accent_dim": "#1155aa",
        "accent_bright": "#66b3ff",
        "banner_bg": "#003388",
        "card_active_bg": "#08182a",
    },
    "green": {
        "accent": "#33cc66",
        "accent_dim": "#118833",
        "accent_bright": "#66e08a",
        "banner_bg": "#005522",
        "card_active_bg": "#082a12",
    },
    "orange": {
        "accent": "#ff8800",
        "accent_dim": "#aa5500",
        "accent_bright": "#ffa333",
        "banner_bg": "#884400",
        "card_active_bg": "#2a1608",
    },
    "purple": {
        "accent": "#bb55ff",
        "accent_dim": "#7722aa",
        "accent_bright": "#cc77ff",
        "banner_bg": "#551188",
        "card_active_bg": "#22082a",
    },
    "yellow": {
        "accent": "#ffcc00",
        "accent_dim": "#aa8800",
        "accent_bright": "#ffdb33",
        "banner_bg": "#886600",
        "card_active_bg": "#2a2208",
    },
    "pink": {
        "accent": "#ff55aa",
        "accent_dim": "#aa2266",
        "accent_bright": "#ff77bb",
        "banner_bg": "#881144",
        "card_active_bg": "#2a081a",
    },
}

DEFAULT_THEME = "purple"


class ThemeShadeLens:
    """
    Computes theme-shaded styles and CSS tokens for cognitive cards and fold indicators.
    """
    def __init__(self, current_theme: str = DEFAULT_THEME):
        self.current_theme = current_theme if current_theme in THEMES else DEFAULT_THEME

    def set_theme(self, theme_name: str) -> None:
        if theme_name in THEMES:
            self.current_theme = theme_name

    def get_palette(self) -> Dict[str, str]:
        return THEMES.get(self.current_theme, THEMES[DEFAULT_THEME])

    def get_shade(self, shade_key: str) -> str:
        palette = self.get_palette()
        return palette.get(shade_key, palette["accent"])

    def format_card_header(self, badge: str, shade_key: str = "accent") -> str:
        """
        Formats header with Rich markup using the active theme's appropriate shade.
        """
        hex_color = self.get_shade(shade_key)
        return f"[{hex_color} bold]{badge}[/]"

    def format_fold_label(self, count: int, category: str) -> str:
        """
        Formats a dynamic fold indicator using the theme's accent_dim shade.
        Strictly does NOT mention 'turns', using 'messages' or 'entries'.
        """
        hex_dim = self.get_shade("accent_dim")
        return f"[{hex_dim}]⋯ Folded {count} prior messages ({category} / background) ⋯[/]"
