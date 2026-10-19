"""Graphical animated boot screen for Gemini Integrated Bilateral Console."""

from __future__ import annotations

import time
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Static

from gemini_app.config import DEFAULT_PALETTE, MOBILE_BREAKPOINT, THEMES
from gemini_app.ui.modals.base import ResponsiveModalScreen


class BootScreen(ResponsiveModalScreen[bool]):
    """Graphical animated boot screen shown for 2 seconds upon console startup."""

    DEFAULT_CSS = """
    BootScreen {
        align: center middle;
        background: #000000;
        layers: base;
    }
    #boot_box {
        width: 68;
        height: auto;
        max-height: 22;
        border: double red;
        background: #080808;
        padding: 1 2;
        align: center middle;
        content-align: center middle;
        text-align: center;
    }
    BootScreen.-mobile #boot_box {
        width: 90%;
        max-width: 50;
        padding: 1 1;
    }
    #boot_emblem {
        width: 100%;
        text-align: center;
        content-align: center middle;
        margin-bottom: 1;
    }
    #boot_title_widget {
        width: 100%;
        text-align: center;
        content-align: center middle;
        text-style: bold;
        margin-bottom: 1;
    }
    #boot_status_line {
        width: 100%;
        text-align: center;
        content-align: center middle;
        margin-bottom: 1;
    }
    #boot_progress_line {
        width: 100%;
        text-align: center;
        content-align: center middle;
        margin-bottom: 1;
    }
    #boot_footer_row {
        width: 100%;
        height: 1;
        align: center middle;
        content-align: center middle;
        text-align: center;
        margin-top: 1;
    }
    #boot_footer_row Static {
        width: auto;
        height: 1;
        background: transparent;
    }
    #boot_footer_sep {
        margin: 0 1;
    }
    """

    SCANNER_FRAMES = [
        "╸━╾─────◈──────╼━╺",
        "╸━╾────◈◈─────╼━╺",
        "╸━╾───◈◈◈────╼━╺",
        "╸━╾──◈◈◈◈───╼━╺",
        "╸━╾─◈◈◈◈◈──╼━╺",
        "╸━╾◈◈◈◈◈◈─╼━╺",
        "╸━╾─◈◈◈◈◈──╼━╺",
        "╸━╾──◈◈◈◈───╼━╺",
        "╸━╾───◈◈◈────╼━╺",
        "╸━╾────◈◈─────╼━╺",
    ]

    ORB_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, duration_seconds: float = 2.0) -> None:
        super().__init__()
        self.duration_seconds: float = max(0.5, duration_seconds)
        self._start_time: float = 0.0
        self._frame_idx: int = 0
        self._anim_timer: Timer | None = None
        self._dismiss_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="boot_box"):
            yield Static("", id="boot_emblem")
            yield Static("", id="boot_title_widget")
            yield Static("", id="boot_status_line")
            yield Static("", id="boot_progress_line")
            with Horizontal(id="boot_footer_row"):
                yield Static("[bold red]^q:[/] [white]quit[/]", id="boot_footer_quit")
                yield Static("[red]|[/]", id="boot_footer_sep")
                yield Static("[bold red]^c + c:[/] [white]commands[/]", id="boot_footer_commands")

    @property
    def current_theme_palette(self) -> dict[str, str]:
        theme_name = getattr(self.app, "active_palette_name", DEFAULT_PALETTE)
        return THEMES.get(theme_name, THEMES[DEFAULT_PALETTE])

    def on_mount(self) -> None:
        super().on_mount()
        self._start_time = time.monotonic()
        self._frame_idx = 0
        self._update_display()
        self._anim_timer = self.set_interval(0.06, self._tick_animation)
        self._dismiss_timer = self.set_timer(self.duration_seconds, self._dismiss_boot)

    def on_resize(self, event: events.Resize) -> None:
        super().on_resize(event)
        self._update_display()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("ctrl+q", "q"):
            self._dismiss_boot()
            if hasattr(self.app, "action_quit"):
                self.app.action_quit()
            return
        # Any other key allows early skip if user presses keyboard
        self._dismiss_boot()

    def on_click(self, event: events.Click) -> None:
        # Clicking allows early skip
        self._dismiss_boot()

    def _dismiss_boot(self) -> None:
        if self._anim_timer:
            self._anim_timer.stop()
            self._anim_timer = None
        if self._dismiss_timer:
            self._dismiss_timer.stop()
            self._dismiss_timer = None
        try:
            self.dismiss(True)
        except Exception:
            pass

    def _tick_animation(self) -> None:
        self._frame_idx += 1
        self._update_display()

    def _update_display(self) -> None:
        try:
            cfg = self.current_theme_palette
            acc = cfg["accent"]
            acc_bright = cfg["accent_bright"]
            acc_dim = cfg["accent_dim"]

            now = time.monotonic()
            elapsed = max(0.0, now - self._start_time)
            pct = min(100, int((elapsed / self.duration_seconds) * 100))

            is_mobile = self.has_class("-mobile") or (
                self.size.width <= MOBILE_BREAKPOINT if self.size and self.size.width else (
                    self.app.size.width <= MOBILE_BREAKPOINT if self.app and self.app.size else False
                )
            )

            # 1. Scanning Wave / Emblem
            wave = self.SCANNER_FRAMES[self._frame_idx % len(self.SCANNER_FRAMES)]
            orb = self.ORB_FRAMES[self._frame_idx % len(self.ORB_FRAMES)]
            emblem_text = f"[{acc}]{wave}[/]"
            self.query_one("#boot_emblem", Static).update(emblem_text)

            # 2. Main Title (Desktop vs Mobile break)
            if is_mobile:
                # Centered on mobile:
                # gemini
                # integrated
                title_markup = (
                    f"[{acc}]╭──────────────────────────────╮[/]\n"
                    f"[{acc}]│[/]            [bold {acc_bright}]gemini[/]            [{acc}]│[/]\n"
                    f"[{acc}]│[/]          [bold {acc_bright}]integrated[/]          [{acc}]│[/]\n"
                    f"[{acc}]╰──────────────────────────────╯[/]"
                )
            else:
                # Centered on desktop:
                # gemini-integrated
                title_markup = (
                    f"[{acc}]╭──────────────────────────────────────────────╮[/]\n"
                    f"[{acc}]│[/]          [bold {acc_bright}]gemini-integrated[/]          [{acc}]│[/]\n"
                    f"[{acc}]╰──────────────────────────────────────────────╯[/]"
                )
            self.query_one("#boot_title_widget", Static).update(title_markup)

            # 3. Status Phase Line
            if pct < 25:
                status_desc = "Initializing bilateral neural stream..."
            elif pct < 50:
                status_desc = "Calibrating cognitive anchors & memory..."
            elif pct < 80:
                status_desc = "Syncing tri-modal notes & visual graph..."
            else:
                status_desc = "Console environment ready. Launching..."

            status_markup = f"[bold {acc}]{orb}[/] [{acc_dim}]{status_desc}[/]"
            self.query_one("#boot_status_line", Static).update(status_markup)

            # 4. Animated Progress Bar
            bar_width = 18 if is_mobile else 26
            filled = int(bar_width * (pct / 100))
            unfilled = max(0, bar_width - filled)
            bar_chars = f"[{acc}]" + ("█" * filled) + f"[/][#262626]" + ("░" * unfilled) + "[/]"
            progress_markup = f"⟨ {bar_chars} ⟩ [bold {acc_bright}]{pct:>3}%[/]"
            self.query_one("#boot_progress_line", Static).update(progress_markup)

            # 5. Footer row styling
            self.query_one("#boot_footer_quit", Static).update(f"[bold {acc}]^q:[/] [white]quit[/]")
            self.query_one("#boot_footer_sep", Static).update(f"[{acc}]|[/]")
            self.query_one("#boot_footer_commands", Static).update(f"[bold {acc}]^c + c:[/] [white]commands[/]")
        except Exception:
            pass
