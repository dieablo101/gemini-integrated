"""Full-screen interactive Cognitive Mind Map view with steering input bar and live reactive animation watcher."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Input, Label, Markdown, Static

from gemini_app.config import DEFAULT_PALETTE, MOBILE_BREAKPOINT, SPINNER_FRAMES, THEMES
from gemini_app.introspection import ANIMATION_FRAMES

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
    #mind_pulse_bar {
        width: 100%;
        height: 1;
        background: #141414;
        color: #ffffff;
        text-align: center;
        text-style: bold;
        padding: 0 1;
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._live_watch_timer: Timer | None = None
        self._anim_frame_idx: int = 0
        self._last_state_signature: str = ""

    def _update_screen_classes(self, width: int | None = None) -> None:
        w = width if width is not None else (self.size.width or (self.app.size.width if self.app else 100))
        self.set_class(w <= MOBILE_BREAKPOINT, "-mobile")

    def on_mount(self) -> None:
        if hasattr(self.app, "active_palette_name"):
            self.add_class(f"theme-{self.app.active_palette_name}")
        self._update_screen_classes()
        self.refresh_display()
        self._live_watch_timer = self.set_interval(0.6, self._on_live_watch_tick)
        self.query_one("#mind_input", Input).focus()

    def on_unmount(self) -> None:
        if self._live_watch_timer:
            self._live_watch_timer.stop()
            self._live_watch_timer = None

    def on_resize(self, event: events.Resize) -> None:
        self._update_screen_classes(event.size.width)

    def refresh_display(self) -> None:
        app: ChatApp = self.app  # type: ignore
        try:
            gemini_md = self.query_one("#gemini_mind_text", Markdown)
            user_md = self.query_one("#user_mind_text", Markdown)
            tree_md = self.query_one("#mind_tree_text", Markdown)

            g_state = getattr(app, "current_gemini_state", "") or "*No conclusive direction recorded yet.*"
            u_state = getattr(app, "current_user_state", "") or "*Awaiting initial conversational alignment.*"
            t_content = getattr(app, "current_tree_content", "")
            tree_body = f"```text\n{t_content}\n```" if t_content else "*Tree not initialized.*"

            gemini_md.update(g_state)
            user_md.update(u_state)
            tree_md.update(tree_body)

            self._last_state_signature = f"{g_state}::{u_state}::{t_content}"

            gemini_md.refresh(layout=True)
            user_md.refresh(layout=True)
            tree_md.refresh(layout=True)
        except Exception:
            pass

    def _on_live_watch_tick(self) -> None:
        """Reactive watcher running while the user is actively viewing the Mind screen."""
        app: ChatApp = self.app  # type: ignore
        if not app:
            return

        # 1. Check for real-time state changes while user is watching
        g_state = getattr(app, "current_gemini_state", "") or "*No conclusive direction recorded yet.*"
        u_state = getattr(app, "current_user_state", "") or "*Awaiting initial conversational alignment.*"
        t_content = getattr(app, "current_tree_content", "")
        current_sig = f"{g_state}::{u_state}::{t_content}"

        if current_sig != self._last_state_signature:
            self.refresh_display()

        # 2. Render reactive animation & cognitive flow on pulse bar
        try:
            pulse_bar = self.query_one("#mind_pulse_bar", Static)
            now = time.monotonic()
            anim = getattr(app, "_active_mind_animation", None)

            if anim and isinstance(anim, dict) and now < anim.get("end_time", 0):
                eff = anim.get("effect", "sparkle")
                pal = anim.get("palette", getattr(app, "active_palette_name", DEFAULT_PALETTE))
                acc = THEMES.get(pal, THEMES[DEFAULT_PALETTE])["accent"]
                frames = ANIMATION_FRAMES.get(eff, ANIMATION_FRAMES["sparkle"])
                frame = frames[self._anim_frame_idx % len(frames)]
                rem = max(0.0, anim.get("end_time", 0) - now)
                msg = anim.get("message", "Cognitive Wave Active")
                pulse_bar.update(f"[{acc}]{frame} {msg} ({rem:.1f}s) {frame}[/]")
            elif getattr(app, "_request_phase", "idle") != "idle":
                phase = getattr(app, "_request_phase", "working")
                details = getattr(app, "_request_details", "")
                acc = getattr(app, "accent_color", "#ff3333")
                frame = SPINNER_FRAMES[self._anim_frame_idx % len(SPINNER_FRAMES)]
                desc = details or phase.title()
                pulse_bar.update(f"[{acc}]{frame} ✨ Cognitive Activity: {desc} ✨ {frame}[/]")
            else:
                acc = getattr(app, "accent_color", "#ff3333")
                pal = getattr(app, "active_palette_name", DEFAULT_PALETTE)
                pulse_bar.update(f"[{acc}]✦ Mind State Synchronized | Theme: {pal} ✦[/]")
        except Exception:
            pass

        self._anim_frame_idx += 1

    def compose(self) -> ComposeResult:
        yield Static("✦ Mind Map Synchronized", id="mind_pulse_bar")
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
