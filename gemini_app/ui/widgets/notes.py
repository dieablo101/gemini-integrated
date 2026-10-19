"""Unified Gemini-Managed Notes Panel.

Displays Gemini working notes, relevant user & topic notes, follow-ups (get back to),
brainstorms (think about), topics catalog, and archived notes. Automatically consumes user-submitted notes.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static, TextArea

from gemini_app.ui.widgets.text_areas import EmacsBaseTextArea, ExpandingInput
from gemini_app.ui.widgets.feed import FeedArea

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp


class NotesEditorArea(EmacsBaseTextArea):
    """Read-only display area displaying Gemini managed notes."""

    can_focus = False

    def __init__(self, **kwargs) -> None:
        kwargs["read_only"] = True
        super().__init__(**kwargs)
        self.read_only = True
        self._last_nav_time: float = 0.0
        self._nav_cooldown: float = 0.022
        self._suppress_change_sync: bool = False
        self._initial_rendered_text: str = ""

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = False
        self.read_only = True

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._suppress_change_sync or not self.has_focus:
            return

        app: ChatApp = self.app  # type: ignore
        app.schedule_notes_flush()

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        # Fast filter shortcuts: Alt+1..6
        panel: NotesPanel = self.app.query_one("#notes_panel", NotesPanel)  # type: ignore

        if event.key in ("alt+1", "meta+1"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("working")
            return
        elif event.key in ("alt+2", "meta+2"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("relevant")
            return
        elif event.key in ("alt+3", "meta+3"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("get_back_to")
            return
        elif event.key in ("alt+4", "meta+4"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("think_about")
            return
        elif event.key in ("alt+5", "meta+5"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("topics")
            return
        elif event.key in ("alt+6", "meta+6"):
            event.prevent_default()
            event.stop()
            panel.switch_filter("archived")
            return

        if event.key in ("ctrl+j", "shift+enter", "shift+return"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        if event.key in ("enter", "return"):
            event.prevent_default()
            event.stop()
            self.app.flush_current_notes(consume_input=True)
            self.app.action_toggle_notes()
            return

        if event.key in ("escape", "ctrl+g"):
            event.prevent_default()
            event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.flush_current_notes(consume_input=True)
                self.app.action_toggle_notes()
            return

        if event.key in ("tab", "shift+tab"):
            event.prevent_default()
            event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            self.app.cycle_global_focus(direction=direction)
            return

        # Feed navigation keys while in notes panel for lock-step inspection
        feed = self.app.query_one("#feed", FeedArea)
        now = time.monotonic()
        if event.key in ("down", "up", "shift+up", "shift+down"):
            if now - self._last_nav_time < self._nav_cooldown:
                event.prevent_default()
                event.stop()
                return
            self._last_nav_time = now

        if event.key in ("shift+up", "shift+down"):
            event.prevent_default()
            event.stop()
            direction = -1 if event.key == "shift+up" else 1
            feed.viewport_page_navigate(direction)
            return
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            feed.arrow_navigate(1)
            return
        elif event.key == "up":
            event.prevent_default()
            event.stop()
            feed.arrow_navigate(-1)
            return
        elif event.key == "pagedown":
            event.prevent_default()
            event.stop()
            feed.step_card(1)
            return
        elif event.key == "pageup":
            event.prevent_default()
            event.stop()
            feed.step_card(-1)
            return
        elif event.key in ("alt+n", "meta+n"):
            event.prevent_default()
            event.stop()
            feed.navigate_snippet(1)
            return
        elif event.key in ("alt+p", "meta+p"):
            event.prevent_default()
            event.stop()
            feed.navigate_snippet(-1)
            return
        elif event.key == "home":
            event.prevent_default()
            event.stop()
            feed.jump_to_home()
            return
        elif event.key == "end":
            event.prevent_default()
            event.stop()
            feed.jump_to_end()
            return

        super()._on_key(event)


class TopicChip(Static):
    """Clickable topic chip for switching active notes context without ID collisions."""

    def __init__(self, topic: str, count: int, is_active: bool = False, **kwargs) -> None:
        self.topic_name: str = topic
        active_class = " chip-active" if is_active else ""
        super().__init__(f"{topic} ({count})", classes=f"note_chip{active_class}", **kwargs)

    def update_topic(self, topic: str, count: int, is_active: bool) -> None:
        self.topic_name = topic
        self.update(f"{topic} ({count})")
        if is_active:
            self.add_class("chip-active")
        else:
            self.remove_class("chip-active")


class NotesPanel(Vertical):
    """Unified Gemini-Managed Notes Panel with topic association and cognitive view filters."""

    FILTER_MODES = ("working", "relevant", "get_back_to", "think_about", "topics", "archived")

    def __init__(self, **kwargs) -> None:
        super().__init__(id="notes_panel", **kwargs)
        self.border_title = " 🧠 Gemini Managed Notes "
        self.active_filter: str = "working"

    def clear_session_expansion_states(self) -> None:
        """Compatibility helper for session reset."""
        pass

    def refresh_display(self) -> None:
        """Refreshes the rendered Markdown notes in the editor based on current filter."""
        self.switch_filter(self.active_filter)

    def compose(self) -> ComposeResult:
        with Horizontal(id="notes_tabs_row"):
            yield Static("⚡ Working", id="tab_working", classes="notes_tab tab-active")
            yield Static("📌 Relevant", id="tab_relevant", classes="notes_tab")
            yield Static("⏳ Get Back", id="tab_get_back_to", classes="notes_tab")
            yield Static("💡 Think", id="tab_think_about", classes="notes_tab")
            yield Static("📚 Topics", id="tab_topics", classes="notes_tab")
            yield Static("📦 Archive", id="tab_archived", classes="notes_tab")
        with Horizontal(id="notes_chips_row"):
            yield Static("Topics:", id="notes_chips_title", classes="notes_chips_title")
        yield Static("🧠 Gemini Managed Notes | Alt+1..6 to filter | Esc / C-c [ to close", id="notes_header_info")
        yield NotesEditorArea(id="notes_editor")
        yield ExpandingInput(id="notes_input")

    def refresh_topic_chips(self) -> None:
        """Refreshes horizontal topic filter chips in-place from the notes catalog."""
        app: ChatApp = self.app  # type: ignore
        try:
            chips_row = self.query_one("#notes_chips_row", Horizontal)
        except Exception:
            return

        manager = getattr(app, "notes_manager", None)
        if not manager:
            chips_row.styles.display = "none"
            return

        topics = manager.get_all_topics()
        if not topics:
            chips_row.styles.display = "none"
            for child in list(chips_row.children):
                if isinstance(child, TopicChip) or "note_chip" in child.classes:
                    child.remove()
            return

        chips_row.styles.display = "block"
        topics_to_show = topics[:6]

        # Purge any legacy non-TopicChip widgets with class note_chip
        for child in list(chips_row.children):
            if "note_chip" in child.classes and not isinstance(child, TopicChip):
                child.remove()

        existing_chips = [c for c in chips_row.children if isinstance(c, TopicChip)]

        # Update existing chips in place to prevent DOM churn and ID collisions
        for i, (t_name, count) in enumerate(topics_to_show):
            is_active = (t_name == manager.current_topic)
            if i < len(existing_chips):
                existing_chips[i].update_topic(t_name, count, is_active)
            else:
                new_chip = TopicChip(t_name, count, is_active)
                chips_row.mount(new_chip)

        # Remove any extra chips if topics count reduced
        if len(existing_chips) > len(topics_to_show):
            for surplus_chip in existing_chips[len(topics_to_show):]:
                surplus_chip.remove()

    def refresh_related_chips(self) -> None:
        """Compatibility alias for refresh_topic_chips."""
        self.refresh_topic_chips()

    def switch_mode(self, mode: str) -> None:
        """Compatibility method for legacy callers."""
        mode_clean = mode.lower().strip()
        mapping = {
            "gemini": "working",
            "turn": "relevant",
            "global": "topics",
            "working": "working",
            "relevant": "relevant",
            "get_back_to": "get_back_to",
            "think_about": "think_about",
            "topics": "topics",
            "archived": "archived",
            "archive": "archived",
        }
        self.switch_filter(mapping.get(mode_clean, "working"))

    def switch_filter(self, new_filter: str) -> None:
        app: ChatApp = self.app  # type: ignore
        manager = getattr(app, "notes_manager", None)

        # 1. Flush any existing editor changes first without re-consuming template as new user notes
        app.flush_current_notes(consume_input=False)

        # 2. Update active filter state
        self.active_filter = new_filter
        app.active_notes_mode = new_filter

        # 3. Update tab active highlight
        for tab_id, f in (
            ("tab_working", "working"),
            ("tab_relevant", "relevant"),
            ("tab_get_back_to", "get_back_to"),
            ("tab_think_about", "think_about"),
            ("tab_topics", "topics"),
            ("tab_archived", "archived"),
        ):
            try:
                w = self.query_one(f"#{tab_id}", Static)
                if f == new_filter:
                    w.add_class("tab-active")
                else:
                    w.remove_class("tab-active")
            except Exception:
                pass

        # 4. Render and load content into editor
        editor = self.query_one("#notes_editor", NotesEditorArea)
        hint = self.query_one("#notes_header_info", Static)

        current_topic = manager.current_topic if manager else "general"

        if new_filter == "working":
            self.border_title = f" 🧠 Working Notes [{current_topic}] "
            hint.update(f"Active Topic: {current_topic} | Working & Relevant Notes | Esc / C-c [ to close")
        elif new_filter == "relevant":
            self.border_title = f" 📌 Relevant Notes [{current_topic}] "
            hint.update(f"Relevant notes in relation to '{current_topic}' | Esc / C-c [ to close")
        elif new_filter == "get_back_to":
            self.border_title = " ⏳ Notes to Get Back To "
            hint.update("Action items & follow-ups to get back to | Esc / C-c [ to close")
        elif new_filter == "think_about":
            self.border_title = " 💡 Notes to Think About "
            hint.update("Brainstorms & considerations to think about | Esc / C-c [ to close")
        elif new_filter == "archived":
            self.border_title = " 📦 Archived Notes "
            hint.update("Archived notes catalog | Esc / C-c [ to close")
        else:  # topics
            self.border_title = " 📚 All Notes by Topic "
            hint.update("Unified notes organized across all project topics | Esc / C-c [ to close")

        editor._suppress_change_sync = True
        try:
            rendered = manager.format_working_view(view_mode=new_filter) if manager else ""
            editor._initial_rendered_text = rendered
            editor.load_text(rendered)
            editor.move_cursor((0, 0), select=False)
            editor.scroll_home(animate=False)
        finally:
            editor._suppress_change_sync = False

        self.refresh_topic_chips()

    def on_turn_changed(self, turn_idx: int, turn_id: str, sender: str = "") -> None:
        """Called whenever the active card in the feed changes."""
        app: ChatApp = self.app  # type: ignore
        manager = getattr(app, "notes_manager", None)
        app.current_focused_turn_index = turn_idx
        app.current_focused_turn_id = turn_id

        # If notes panel is open and in relevant filter, update display
        if self.active_filter == "relevant" and manager:
            editor = self.query_one("#notes_editor", NotesEditorArea)
            if not editor.has_focus:
                editor._suppress_change_sync = True
                try:
                    rendered = manager.format_working_view(view_mode="relevant")
                    editor.load_text(rendered)
                finally:
                    editor._suppress_change_sync = False

        self.refresh_topic_chips()

    @on(events.Click, "#tab_working")
    def on_working_tab_click(self) -> None:
        self.switch_filter("working")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, "#tab_relevant")
    def on_relevant_tab_click(self) -> None:
        self.switch_filter("relevant")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, "#tab_get_back_to")
    def on_get_back_to_tab_click(self) -> None:
        self.switch_filter("get_back_to")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, "#tab_think_about")
    def on_think_about_tab_click(self) -> None:
        self.switch_filter("think_about")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, "#tab_topics")
    def on_topics_tab_click(self) -> None:
        self.switch_filter("topics")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, "#tab_archived")
    def on_archived_tab_click(self) -> None:
        self.switch_filter("archived")
        self.query_one("#notes_input", ExpandingInput).focus()

    @on(events.Click, ".note_chip")
    def on_topic_chip_click(self, event: events.Click) -> None:
        chip = event.widget
        target_topic = getattr(chip, "topic_name", "")
        if not target_topic:
            # Fallback for legacy id
            chip_id = getattr(chip, "id", "") or ""
            if chip_id.startswith("chip_topic_"):
                target_topic = chip_id.replace("chip_topic_", "").strip()

        if target_topic:
            app: ChatApp = self.app  # type: ignore
            manager = getattr(app, "notes_manager", None)
            if manager:
                manager.set_current_topic(target_topic)
                self.switch_filter(self.active_filter)
                self.query_one("#notes_input", ExpandingInput).focus()
                app.notify(f"Active notes topic set to: {target_topic}", timeout=2.0)
