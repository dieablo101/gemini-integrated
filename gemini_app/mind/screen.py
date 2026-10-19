"""Full-screen interactive Cognitive Mind Map view with steering input bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Markdown

from gemini_app.config import MOBILE_BREAKPOINT

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp


class MindMapScreen(Screen):
    """Interactive screen displaying Gemini's technical direction, inferred user intent, and ASCII topology."""

    BINDINGS = [
        Binding("escape", "back_to_chat", "Back to Chat"),
        Binding("ctrl+g", "back_to_chat", "Back to Chat"),
        Binding("q", "back_to_chat", "Back to Chat"),
    ]

    DEFAULT_CSS = """
    MindMapScreen {
        layout: vertical;
        background: #000000;
        layers: base toasts overlay;
    }
    #mind_split {
        height: 1fr;
        width: 100%;
        layout: horizontal;
        background: #000000;
    }
    MindMapScreen.-mobile #mind_split {
        layout: vertical;
    }
    #mind_states_column {
        width: 60%;
        height: 100%;
        background: #000000;
        layout: vertical;
    }
    MindMapScreen.-mobile #mind_states_column {
        width: 100%;
        height: 50%;
        border-right: none !important;
        border-bottom: solid red;
    }
    #gemini_mind_card {
        height: 50%;
        width: 100%;
        padding: 1;
        overflow-y: auto;
        background: #000000;
    }
    #user_mind_card {
        height: 50%;
        width: 100%;
        padding: 1;
        overflow-y: auto;
        background: #000000;
    }
    #mind_tree_column {
        width: 40%;
        height: 100%;
        padding: 1;
        overflow-y: auto;
        background: #000000;
    }
    MindMapScreen.-mobile #mind_tree_column {
        width: 100%;
        height: 50%;
    }
    .mind_header {
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #mind_input_bar {
        height: auto;
        min-height: 3;
        width: 100%;
        padding: 0 1 1 1;
        background: #000000;
    }
    #mind_input {
        width: 100%;
        background: #000000;
        color: #ffffff;
    }
    """

    def _update_screen_classes(self, width: int | None = None) -> None:
        w = width if width is not None else (self.size.width or (self.app.size.width if self.app else 100))
        self.set_class(w <= MOBILE_BREAKPOINT, "-mobile")

    def on_mount(self) -> None:
        if hasattr(self.app, "active_palette_name"):
            self.add_class(f"theme-{self.app.active_palette_name}")
        self._update_screen_classes()
        self.refresh_display()
        self.query_one("#mind_input", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        self._update_screen_classes(event.size.width)

    def refresh_display(self) -> None:
        app: ChatApp = self.app  # type: ignore
        try:
            gemini_md = self.query_one("#gemini_mind_text", Markdown)
            user_md = self.query_one("#user_mind_text", Markdown)
            tree_md = self.query_one("#mind_tree_text", Markdown)

            gemini_md.update(getattr(app, "current_gemini_state", "") or "*No conclusive direction recorded yet.*")
            user_md.update(getattr(app, "current_user_state", "") or "*Awaiting initial conversational alignment.*")

            tree_content = getattr(app, "current_tree_content", "")
            tree_body = f"```text\n{tree_content}\n```" if tree_content else "*Tree not initialized.*"
            tree_md.update(tree_body)

            gemini_md.refresh(layout=True)
            user_md.refresh(layout=True)
            tree_md.refresh(layout=True)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        with Horizontal(id="mind_split"):
            with Vertical(id="mind_states_column"):
                with Vertical(id="gemini_mind_card"):
                    yield Label("── GEMINI MIND STATE (Conclusive Direction) ──", classes="mind_header")
                    yield Markdown(id="gemini_mind_text")
                with Vertical(id="user_mind_card"):
                    yield Label("── USER MIND STATE (Inferred Intent) ──", classes="mind_header")
                    yield Markdown(id="user_mind_text")
            with VerticalScroll(id="mind_tree_column"):
                yield Label("── WORKSPACE & CHAT TOPOLOGY ──", classes="mind_header")
                yield Markdown(id="mind_tree_text")

        with Vertical(id="mind_input_bar"):
            yield Input(
                placeholder="Steer Mind State: e.g. Focus purely on XML engine, scaffold parser...",
                id="mind_input",
            )

    @on(Input.Submitted, "#mind_input")
    def on_steer_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            return
        self.query_one("#mind_input", Input).value = ""
        if hasattr(self.app, "steer_mind_state"):
            self.app.steer_mind_state(raw)
        self.notify("Cognitive steering sent to Gemini...", timeout=2.5)

    def action_back_to_chat(self) -> None:
        self.app.pop_screen()
