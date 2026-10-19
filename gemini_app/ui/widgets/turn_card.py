"""TurnCard widget displaying individual conversational turns with fork selection checkboxes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Markdown

if TYPE_CHECKING:
    from gemini_app.ui.widgets.feed import FeedArea


class TurnCard(Vertical):
    """Visual card displaying a single chat message turn with role header and Markdown body."""

    can_focus = False

    def __init__(self, index: int, sender: str, text: str, turn_id: str, is_selected: bool = False, **kwargs) -> None:
        instance_id = f"card_{uuid4().hex[:8]}"
        super().__init__(classes="turn_card", id=instance_id, **kwargs)
        self.turn_index = index
        self.turn_id = turn_id
        self.sender = sender
        self.text_content = text
        self.is_selected = is_selected

    def compose(self) -> ComposeResult:
        with Horizontal(classes="turn_header"):
            yield Label(self._get_box_label(), classes="turn_box_label", markup=False)
        yield Markdown(f"{self.text_content}\n\n---", classes="turn_body")

    def _get_box_label(self) -> str:
        feed = None
        if self.is_mounted and hasattr(self.app, "query_one"):
            try:
                feed = self.app.query_one("#feed")
            except Exception:
                pass

        fork_active = getattr(feed, "fork_ui_active", False) if feed else False

        app = getattr(self, "app", None)
        has_note = False
        if app and hasattr(app, "relational_notes") and self.turn_id:
            has_note = bool((app.relational_notes.get(self.turn_id) or "").strip())
        note_badge = " [📝 Note]" if has_note else ""

        if fork_active:
            box = "[X]" if self.is_selected else "[ ]"
            return f"{box} {self.sender}{note_badge}"
        else:
            return f"{self.sender}{note_badge}"

    def update_display(self) -> None:
        try:
            lbl = self.query_one(".turn_box_label", Label)
            lbl.update(self._get_box_label())
        except Exception:
            pass

    def update_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self.update_display()

    def toggle(self) -> None:
        feed = self.app.query_one("#feed")
        new_val = not self.is_selected
        if new_val:
            feed._fork_selected_indices.add(self.turn_index)
        else:
            feed._fork_selected_indices.discard(self.turn_index)
        self.update_selected(new_val)
        self.refresh()

    @on(events.Click)
    def on_card_click(self, event: events.Click) -> None:
        feed = self.app.query_one("#feed")
        if hasattr(feed, "is_locked") and feed.is_locked():
            event.stop()
            return
        if getattr(feed, "fork_ui_active", False):
            curr = event.widget
            while curr and curr is not self:
                if "turn_header" in curr.classes or "turn_box_label" in curr.classes:
                    event.stop()
                    feed.highlight_card(self.turn_index, scroll=False)
                    self.toggle()
                    return
                curr = curr.parent
