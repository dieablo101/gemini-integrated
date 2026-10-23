"""TurnCard widget displaying individual conversational turns and cognitive memory interludes."""

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
    """Visual card displaying a single chat message turn or cognitive interlude with role/intent badge and Markdown body."""

    can_focus = False

    def __init__(
        self,
        index: int,
        sender: str,
        text: str,
        turn_id: str,
        is_selected: bool = False,
        badge: str = "",
        card_type: str = "turn",
        theme_shade: str = "",
        **kwargs
    ) -> None:
        instance_id = f"card_{uuid4().hex[:8]}"
        classes = "turn_card"
        if card_type == "cognitive_interlude":
            classes += " turn_card_cognitive"
            if theme_shade == "accent_bright":
                classes += " card-cognitive-bright"
            elif theme_shade == "accent_dim":
                classes += " card-cognitive-dim"
            else:
                classes += " card-cognitive-accent"
        elif card_type == "fold_marker":
            classes += " turn_card_fold"

        super().__init__(classes=classes, id=instance_id, **kwargs)
        self.turn_index = index
        self.turn_id = turn_id
        self.sender = sender
        self.text_content = text
        self.is_selected = is_selected
        self.badge = badge
        self.card_type = card_type
        self.theme_shade = theme_shade

    def compose(self) -> ComposeResult:
        with Horizontal(classes="turn_header"):
            yield Label(self._get_box_label(), classes="turn_box_label", markup=False)
        if self.card_type == "fold_marker":
            yield Markdown(f"{self.text_content}", classes="turn_body")
        else:
            yield Markdown(f"{self.text_content}\n\n---", classes="turn_body")

    def _get_box_label(self) -> str:
        app = getattr(self, "app", None)
        has_note = False
        if app and hasattr(app, "relational_notes") and self.turn_id:
            has_note = bool((app.relational_notes.get(self.turn_id) or "").strip())
        note_badge = " [📝 Note]" if has_note else ""

        display = self.badge if self.badge else self.sender
        return f"{display}{note_badge}"

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
        """Deprecated fork toggle kept for test compatibility."""
        self.is_selected = not self.is_selected
        self.update_display()

    @on(events.Click)
    def on_card_click(self, event: events.Click) -> None:
        feed = self.app.query_one("#feed")
        if hasattr(feed, "is_locked") and feed.is_locked():
            event.stop()
            return
