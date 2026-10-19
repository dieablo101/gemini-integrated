"""Configuration, paths, constants, and themes for Gemini App."""

from __future__ import annotations

import getpass
from pathlib import Path

CURRENT_USER: str = getpass.getuser()

GEMINI_HOME: Path = Path.home() / ".gemini"
GEMINI_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)

CHATS_DIR: Path = GEMINI_HOME / "chats"
CHATS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

ARCHIVE_DIR: Path = CHATS_DIR / ".archive"
ARCHIVE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

SCREENSHOTS_DIR: Path = GEMINI_HOME / "screenshots"
SCREENSHOTS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

STATE_FILE: Path = GEMINI_HOME / "state.json"
SOCKET_PATH: Path = GEMINI_HOME / "gemini_textual.sock"

FORK_HEADER_TEXT: str = "## This chat is a fork of another / previous chat"
WIRE_CONTINUATION_PROMPT: str = "[Continuing conversation context]"

SPINNER_FRAMES: list[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

CENTER_SCREEN_MODE: bool = True
MOBILE_BREAKPOINT: int = 80

DEFAULT_WINDOW_CAPACITY: int = 10
DEFAULT_MODEL: str = "gemini-3.8-flash"
MAX_SNIPPET_LINES_ON_WIRE: int = 25
TURNS_PER_SEGMENT: int = 200

THEMES: dict[str, dict[str, str]] = {
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

DEFAULT_PALETTE: str = "red"

GATED_NAV_KEYS: set[str] = {
    "home",
    "end",
    "pageup",
    "pagedown",
    "up",
    "down",
    "shift+up",
    "shift+down",
    "alt+n",
    "meta+n",
    "alt+p",
    "meta+p",
}


def generate_theme_css_rules() -> str:
    blocks: list[str] = []
    for name, cfg in THEMES.items():
        acc = cfg["accent"]
        acc_dim = cfg["accent_dim"]
        acc_bright = cfg["accent_bright"]
        banner = cfg["banner_bg"]
        active_card = cfg["card_active_bg"]

        blocks.append(f"""
        .theme-{name} ScrollBar {{
            color: {acc};
            background: #181818;
        }}
        .theme-{name} ScrollBar:hover {{
            color: {acc_bright};
            background: #252525;
        }}
        .theme-{name} ScrollBarCorner {{
            background: #000000;
        }}

        .theme-{name} Toast {{
            border: solid {acc};
        }}
        .theme-{name} #feed_loader_banner {{
            color: #ffffff;
            background: {banner};
        }}
        .theme-{name} #feed {{
            border: round {acc};
        }}
        .theme-{name} .turn_card.card-active .turn_header {{
            background: {active_card};
        }}
        .theme-{name} .turn_card.card-active .turn_box_label {{
            color: {acc};
        }}
        .theme-{name} MarkdownHorizontalRule {{
            border-bottom: solid {acc};
            color: {acc};
        }}
        .theme-{name} #feed_status {{
            color: {acc};
            border-bottom: solid {acc};
        }}
        .theme-{name} #feed_nav_banner {{
            color: #ffffff;
            background: #141414;
        }}
        .theme-{name} #feed_nav_banner.fork-active {{
            background: {banner};
        }}
        .theme-{name} #feed MarkdownFence.active-snippet {{
            border: solid {acc} !important;
        }}
        .theme-{name} .notes_tab.tab-active {{
            background: {banner};
            color: #ffffff;
        }}
        .theme-{name} .notes_tab:hover {{
            color: {acc_bright};
        }}
        .theme-{name} .note_chip.chip-active {{
            background: {active_card};
            color: {acc_bright};
        }}
        .theme-{name} .note_chip:hover {{
            color: {acc_bright};
            background: #252525;
        }}
        .theme-{name} #notes_panel {{
            border: round {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} .parent_note_card:focus {{
            border: none;
        }}
        .theme-{name} .parent_note_card:focus .parent_note_title {{
            background: {active_card};
            color: {acc_bright};
        }}
        .theme-{name} .parent_note_card .parent_note_title {{
            color: {acc};
        }}
        .theme-{name} #snippet_preview {{
            border: round {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #input,
        .theme-{name} #notes_input {{
            border: solid {acc};
        }}
        .theme-{name} #input:focus,
        .theme-{name} #notes_input:focus {{
            border: solid {acc};
        }}
        .theme-{name} Button {{
            border: solid {acc};
            color: #ffffff;
            text-style: none;
        }}
        .theme-{name} Button:hover {{
            color: {acc};
            background: #141414;
            text-style: none;
        }}
        .theme-{name} Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        /* Modal dialog borders, scrollbars & inputs */
        .theme-{name} #confirm_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #confirm_buttons Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #confirm_buttons Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #confirm_buttons Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        .theme-{name} #fork_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #fork_prefix_hint {{
            color: {acc};
        }}
        .theme-{name} #fork_title_input {{
            border: solid {acc};
        }}
        .theme-{name} #fork_buttons Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #fork_buttons Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #fork_buttons Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        .theme-{name} #save_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #save_dialog Input {{
            border: solid {acc};
        }}
        .theme-{name} #dialog_buttons Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #dialog_buttons Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #dialog_buttons Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        .theme-{name} #insert_file_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #insert_file_dialog Input {{
            border: solid {acc};
        }}

        .theme-{name} #git_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #git_repo_row DirectoryPathInput {{
            border: solid {acc};
        }}
        .theme-{name} #git_repo_row Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #git_repo_row Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #git_repo_row Button:focus {{
            border: double {acc};
            text-style: none;
        }}
        .theme-{name} .tree_pane Tree {{
            border: solid {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #status_label {{
            color: {acc};
        }}
        .theme-{name} #git_buttons Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #git_buttons Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #git_buttons Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        /* Radio Buttons themed color */
        .theme-{name} RadioButton.-selected > .toggle--button {{
            color: {acc};
            background: {acc};
        }}
        .theme-{name} RadioButton > .toggle--button {{
            color: #555555;
            background: #222222;
            border: none;
        }}
        .theme-{name} RadioButton:focus > .toggle--label {{
            color: {acc_bright};
        }}

        .theme-{name} #dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #dialog Input {{
            border: solid {acc};
        }}
        .theme-{name} #dialog-buttons Button {{
            border: solid {acc};
            text-style: none;
        }}
        .theme-{name} #dialog-buttons Button:hover {{
            color: {acc};
            text-style: none;
        }}
        .theme-{name} #dialog-buttons Button:focus {{
            border: double {acc};
            text-style: none;
        }}

        .theme-{name} #frame_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} #frame_options {{
            border: solid {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}

        .theme-{name} #commands_dialog {{
            border: thick {acc};
            scrollbar-color: {acc} #181818;
            scrollbar-color-hover: {acc_bright} #252525;
        }}
        .theme-{name} .cmd_section_title {{
            color: {acc};
        }}
        .theme-{name} .cmd_key {{
            color: {acc_bright};
        }}
        .theme-{name} #cmd_footer_hint {{
            color: {acc_dim};
        }}

        /* Mind Map Screen Theming */
        .theme-{name} #mind_states_column {{
            border-right: solid {acc};
        }}
        .theme-{name} #gemini_mind_card {{
            border-bottom: solid {acc};
        }}
        .theme-{name} .mind_header {{
            color: {acc};
        }}
        .theme-{name} #mind_input {{
            border: solid {acc};
        }}
        .theme-{name} #mind_input:focus {{
            border: solid {acc};
        }}

        /* Boot Screen Theming */
        .theme-{name} #boot_box {{
            border: double {acc};
            background: #080808;
        }}
        .theme-{name} #boot_footer_quit {{
            color: {acc};
        }}
        .theme-{name} #boot_footer_commands {{
            color: {acc};
        }}
        .theme-{name} #boot_footer_sep {{
            color: {acc};
        }}
        """)
    return "\n".join(blocks)
