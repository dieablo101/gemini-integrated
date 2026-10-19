"""Notes panel components: ParentNoteCard, NotesEditorArea, and NotesPanel."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Markdown, TextArea

from gemini_app.config import GATED_NAV_KEYS
from gemini_app.ui.widgets.text_areas import EmacsBaseTextArea
from gemini_app.ui.widgets.feed import FeedArea
from gemini_app.ui.widgets.history import HistoryList

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp

class ParentNoteCard(Vertical):
    can_focus = True

    def __init__(self, chat_id: str, title: str, notes_text: str, depth: int, is_expanded: bool = False, **kwargs) -> None:
        super().__init__(classes="parent_note_card", **kwargs)
        self.chat_id = chat_id
        self.raw_title = title
        self.notes_text = notes_text
        self.depth = depth
        self.is_expanded = is_expanded
        self._last_tab_time: float = 0.0

    def compose(self) -> ComposeResult:
        yield Label(self._get_title_display(), classes="parent_note_title")
        with Vertical(classes="parent_note_body"):
            yield Markdown(self.notes_text.strip())

    def on_mount(self) -> None:
        self.query_one(".parent_note_body", Vertical).styles.display = "block" if self.is_expanded else "none"

    def _get_title_display(self) -> str:
        arrow = "▼" if self.is_expanded else ">"
        indent = "   " * self.depth + "└─ " if self.depth > 0 else ""
        return f"{indent}{self.raw_title}: {arrow}"

    def toggle(self) -> None:
        self.is_expanded = not self.is_expanded
        body = self.query_one(".parent_note_body", Vertical)
        body.styles.display = "block" if self.is_expanded else "none"
        self.query_one(".parent_note_title", Label).update(self._get_title_display())
        notes_panel = self.app.query_one("#notes_panel", NotesPanel)
        notes_panel.record_parent_expanded_state(self.chat_id, self.is_expanded)

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        if event.key in ("space", "enter", "return"):
            event.prevent_default(); event.stop()
            self.toggle()
            return

        if event.key in ("shift+tab", "tab"):
            event.prevent_default(); event.stop()
            now = time.monotonic()
            if event.key == "tab" and (now - self._last_tab_time < 0.35):
                self._last_tab_time = 0.0
                self.app.cycle_global_focus(direction=1, escape_parents=True)
            else:
                self._last_tab_time = now
                direction = -1 if event.key == "shift+tab" else 1
                self.app.cycle_global_focus(direction=direction, escape_parents=False)
            return

        super()._on_key(event)

    @on(events.Click)
    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.focus()
        self.toggle()

class NotesEditorArea(EmacsBaseTextArea):
    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_nav_time: float = 0.0
        self._nav_cooldown: float = 0.022
        self._suppress_change_sync: bool = False

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = False

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._suppress_change_sync or not self.has_focus:
            return
        if getattr(self.app, "active_notes_mode", "chat") == "global":
            self.app.global_notes = self.text
            self.app.schedule_global_notes_flush()
        else:
            self.app.current_chat_notes = self.text
            self.app.schedule_chat_notes_flush()

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        if event.key in ("ctrl+j", "shift+enter", "shift+return"):
            event.prevent_default(); event.stop()
            self.insert("\n")
            return

        if event.key in ("enter", "return"):
            event.prevent_default(); event.stop()
            self.app.flush_current_notes()
            if self.app.active_notes_mode == "chat":
                self.app._direct_flush_chat_to_disk(self.app.current_chat_id, self.app.current_chat_notes)
                self.app.save_current_chat()
            else:
                self.app._flush_global_notes_to_state()
            self.app.action_toggle_notes()
            return

        if event.key in ("escape", "ctrl+g"):
            event.prevent_default(); event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.action_toggle_notes()
            return

        if event.key in ("tab", "shift+tab"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            self.app.cycle_global_focus(direction=direction)
            return

        if getattr(self.app, "active_notes_mode", "chat") == "global":
            try:
                history_list = self.app.query_one("#history", HistoryList)
                if event.key in ("up", "ctrl+p", "k"):
                    event.prevent_default(); event.stop()
                    history_list.action_cursor_up()
                    return
                elif event.key in ("down", "ctrl+n", "j"):
                    event.prevent_default(); event.stop()
                    history_list.action_cursor_down()
                    return
                elif event.key in ("pageup",):
                    event.prevent_default(); event.stop()
                    history_list.action_cursor_page_up()
                    return
                elif event.key in ("pagedown",):
                    event.prevent_default(); event.stop()
                    history_list.action_cursor_page_down()
                    return
                elif event.key == "home":
                    event.prevent_default(); event.stop()
                    history_list.action_first()
                    return
                elif event.key == "end":
                    event.prevent_default(); event.stop()
                    history_list.action_last()
                    return
            except Exception:
                pass

        feed = self.app.query_one("#feed", FeedArea)
        now = time.monotonic()
        if event.key in ("down", "up", "shift+up", "shift+down"):
            if now - self._last_nav_time < self._nav_cooldown:
                event.prevent_default(); event.stop()
                return
            self._last_nav_time = now

        if event.key in ("shift+up", "shift+down"):
            event.prevent_default(); event.stop()
            direction = -1 if event.key == "shift+up" else 1
            feed.viewport_page_navigate(direction)
            return
        elif event.key == "down":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(1)
            return
        elif event.key == "up":
            event.prevent_default(); event.stop()
            feed.arrow_navigate(-1)
            return
        elif event.key == "pagedown":
            event.prevent_default(); event.stop()
            feed.step_card(1)
            return
        elif event.key == "pageup":
            event.prevent_default(); event.stop()
            feed.step_card(-1)
            return
        elif event.key in ("alt+n", "meta+n"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(1)
            return
        elif event.key in ("alt+p", "meta+p"):
            event.prevent_default(); event.stop()
            feed.navigate_snippet(-1)
            return
        elif event.key == "home":
            event.prevent_default(); event.stop()
            feed.jump_to_home()
            return
        elif event.key == "end":
            event.prevent_default(); event.stop()
            feed.jump_to_end()
            return

        super()._on_key(event)

class NotesPanel(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(id="notes_panel", **kwargs)
        self._parent_expanded_states: dict[str, bool] = {}
        self.border_title = " Notes "

    def compose(self) -> ComposeResult:
        yield NotesEditorArea(id="notes_editor")

    def record_parent_expanded_state(self, chat_id: str, expanded: bool) -> None:
        self._parent_expanded_states[chat_id] = expanded

    def clear_session_expansion_states(self) -> None:
        self._parent_expanded_states.clear()

    async def update_notes_content(self, is_history: bool, notes_text: str, parent_lineage: list[dict], chat_id: str = "") -> None:
        self.border_title = " Global Notes " if is_history else " Notes "
        editor = self.query_one("#notes_editor", NotesEditorArea)

        editor._suppress_change_sync = True
        try:
            editor.load_text(notes_text)

            app = self.app
            if not is_history and chat_id and chat_id not in app._seen_chats_in_session:
                app._seen_chats_in_session.add(chat_id)
                editor.move_cursor(editor.document.end, select=False)
            else:
                old_loc = editor.cursor_location
                max_r = max(0, editor.document.line_count - 1)
                r = min(old_loc[0], max_r)
                c = min(old_loc[1], len(editor.document.get_line(r)))
                editor.move_cursor((r, c), select=False)
        finally:
            editor._suppress_change_sync = False

        existing_parents = list(self.query("#notes_parents_container"))
        if existing_parents:
            await existing_parents[0].remove()

        valid_parents = [item for item in parent_lineage if (item.get("notes") or "").strip()] if (not is_history and parent_lineage) else []

        if valid_parents:
            parents_container = Vertical(id="notes_parents_container")
            await self.mount(parents_container, before=editor)

            cards = []
            for item in valid_parents:
                cid = item["id"]
                is_exp = self._parent_expanded_states.get(cid, False)
                card = ParentNoteCard(
                    chat_id=cid,
                    title=item["title"],
                    notes_text=item["notes"],
                    depth=item["depth"],
                    is_expanded=is_exp,
                )
                cards.append(card)

            await parents_container.mount_all(cards)

