"""Global UI stylesheet definitions for the Textual Gemini App."""

from gemini_app.config import generate_theme_css_rules

BASE_CSS = """
Screen {
        layout: vertical;
        layers: base toasts overlay;
        background: #000000;
    }
    ToastRack {
        dock: top;
        align: right top;
        layer: toasts;
        background: transparent;
    }
    ModalScreen ToastRack {
        display: none;
    }
    Toast {
        background: #141414;
        color: #ffffff;
        border: solid red;
    }
    #feed_loader_banner {
        width: 100%;
        height: 1;
        background: #8b0000;
        color: #ffffff;
        content-align: center middle;
        text-align: center;
        text-style: bold;
        display: none;
    }
    #main_container {
        height: 1fr;
        width: 100%;
        layout: vertical;
        background: #000000;
    }
    #middle_split {
        height: 1fr;
        width: 100%;
        layout: horizontal;
        background: #000000;
    }
    Screen.-mobile #middle_split {
        layout: vertical;
    }
    #feed {
        height: 100%;
        width: 1fr;
        border: round red;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
        scrollbar-gutter: auto;
        padding: 0 1;
        background: #000000;
    }
    #history {
        height: 100%;
        width: 1fr;
        border: solid red;
        background: #000000;
        color: #ffffff;
        display: none;
    }
    #notes_panel {
        height: 100%;
        width: 40%;
        border: round red;
        background: #000000;
        color: #ffffff;
        display: none;
        padding: 0;
    }
    Screen.-notes-open #feed,
    Screen.-notes-open #history {
        width: 60%;
    }
    Screen.-mobile #feed,
    Screen.-mobile #history {
        width: 100%;
        height: 1fr;
    }
    Screen.-mobile #notes_panel {
        width: 100%;
        height: 1fr;
    }
    Screen.-mobile.-notes-open #feed,
    Screen.-mobile.-notes-open #history {
        width: 100%;
        height: 1fr;
    }
    Screen.-mobile.-notes-open #notes_panel {
        width: 100%;
        height: 1fr;
    }
    #notes_parents_container {
        width: 100%;
        height: auto;
        background: #000000;
        margin: 0 0 1 0;
        padding: 0;
        border: none;
    }
    .parent_note_card {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
        border: none;
        background: #000000;
    }
    .parent_note_card .parent_note_title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        background: #141414;
        color: red;
    }
    .parent_note_card .parent_note_body {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0;
        display: none;
        background: #080808;
    }
    .parent_note_card .parent_note_body Markdown {
        margin: 0;
        padding: 0;
    }
    .parent_note_card .parent_note_body MarkdownParagraph {
        margin-bottom: 0;
        padding-bottom: 0;
    }
    #notes_editor {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0 1;
        background: #000000;
        color: #ffffff;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
        scrollbar-gutter: auto;
    }
    #notes_editor:focus {
        border: none;
        background: #000000;
    }

    #feed #turns_container {
        width: 100%;
        max-width: 100%;
        height: auto;
        background: #000000;
    }
    .turn_card {
        width: 100%;
        max-width: 100%;
        height: auto;
        margin-bottom: 1;
        padding: 0;
        background: #000000;
        border: none;
    }
    .turn_card .turn_header {
        width: 100%;
        height: 1;
        padding: 0 1;
        margin-bottom: 1;
        background: #141414;
    }
    .turn_card.card-active .turn_header {
        background: #2a0808;
    }
    .turn_box_label {
        width: 100%;
        text-style: bold;
        color: #ffffff;
    }
    .turn_card.card-active .turn_box_label {
        color: red;
    }
    .turn_card .turn_body {
        width: 100%;
        max-width: 100%;
        height: auto;
        background: #000000;
        color: #ffffff;
    }
    MarkdownHorizontalRule {
        border-bottom: solid red;
        color: red;
        margin: 1 0;
    }
    #feed_status {
        width: 100%;
        height: 2;
        padding: 0 1;
        color: red;
        text-style: bold;
        background: #141414;
        border-bottom: solid red;
        display: none;
    }
    #feed_nav_banner {
        width: 100%;
        height: auto;
        min-height: 1;
        background: #141414;
        color: #ffffff;
        text-style: bold;
        text-align: center;
        text-wrap: nowrap;
        padding: 0;
    }
    #feed_nav_banner.fork-active {
        background: #8b0000;
        color: #ffffff;
        text-style: bold;
        text-align: center;
        text-wrap: nowrap;
    }
    #feed MarkdownBlock,
    #feed MarkdownParagraph,
    #feed MarkdownTable {
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
        color: #ffffff;
    }
    #feed MarkdownFence {
        width: 100%;
        max-width: 100%;
        height: auto;
        overflow-x: hidden;
        margin: 1 0;
        border: solid transparent;
        background: #0a0a0a;
    }
    #feed MarkdownFence.active-snippet {
        border: solid red !important;
        background: #141414 !important;
    }
    #feed MarkdownFence > * {
        width: 100%;
        max-width: 100%;
    }
    #snippet_preview {
        width: 100%;
        max-height: 10;
        border: round red;
        background: #000000;
        color: #ffffff;
        display: none;
        margin-bottom: 0;
    }
    #input {
        border: solid red;
        background: #000000;
        color: #ffffff;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
        scrollbar-gutter: auto;
    }
    #input:focus {
        border: solid red;
        background: #000000;
    }
    TextArea > .text-area--cursor-line {
        background: #141414;
    }
    Button {
        background: #000000;
        color: #ffffff;
        border: solid red;
        text-style: none;
    }
    Button:hover {
        background: #141414;
        color: red;
        text-style: none;
    }
    Button:focus {
        border: double red;
        text-style: none;
    }

    #custom_footer {
        height: 1;
        width: 100%;
        background: #000000;
        padding: 0 1;
        align-vertical: middle;
    }
    #custom_footer Static {
        height: 1;
        width: auto;
        background: transparent;
    }
    #footer_quit:hover, #footer_commands:hover {
        background: #141414;
    }
    #footer_sep {
        margin: 0 1;
    }
"""

def get_full_app_css() -> str:
    """Combines static base styles with dynamic palette theme rules."""
    return BASE_CSS + "\n\n" + generate_theme_css_rules()
