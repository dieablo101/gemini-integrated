"""Graphical animated boot screen for Gemini Integrated Bilateral Console."""

from __future__ import annotations

import math
import time
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Static

from gemini_app.config import DEFAULT_PALETTE, MOBILE_BREAKPOINT, THEMES
from gemini_app.ui.modals.base import ResponsiveModalScreen


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Convert hex string (e.g. '#ff0000' or '#f00') to RGB tuple."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors by factor t (0.0 to 1.0)."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


# Compact 3-row block glyphs for animated typography
BLOCK_GLYPHS: dict[str, list[str]] = {
    "G": ["█▀▀▀", "█ ▀█", "▀▀▀▀"],
    "E": ["██▀", "██ ", "▀▀▀"],
    "M": ["█▀█▀█", "█ ▀ █", "▀   ▀"],
    "I": ["▀█▀", " █ ", "▀▀▀"],
    "N": ["█▀▀█", "█  █", "▀  ▀"],
    "-": ["  ", "▄▄", "  "],
    "T": ["▀█▀", " █ ", " ▀ "],
    "R": ["█▀▀█", "█▀▀▄", "▀  ▀"],
    "A": ["▄▀▀▄", "█▀▀█", "▀  ▀"],
    "D": ["█▀▀▄", "█  █", "▀▀▀ "],
    " ": ["  ", "  ", "  "],
}


def render_block_text_with_shadow(
    word: str,
    frame_idx: int,
    acc: str,
    acc_bright: str,
    acc_dim: str,
    shadow_char: str = "░",
) -> list[str]:
    """Render a block text banner with 45-degree drop shadow and animated luminance wave."""
    rows = ["", "", ""]
    for i, ch in enumerate(word.upper()):
        g = BLOCK_GLYPHS.get(ch, ["   ", "   ", "   "])
        for r in range(3):
            rows[r] += g[r]
            if i < len(word) - 1:
                rows[r] += " "

    h = 3
    w = len(rows[0])
    shadow_base = lerp_color(acc_dim, "#0a0a0a", 0.65)

    output_lines: list[str] = []
    for r in range(h + 1):
        line = ""
        last_color: str | None = None
        for c in range(w + 1):
            is_fg = r < h and c < w and rows[r][c] != " "
            is_sh = (
                not is_fg
                and r >= 1
                and c >= 1
                and (r - 1) < h
                and (c - 1) < w
                and rows[r - 1][c - 1] != " "
            )

            if is_fg:
                ch = rows[r][c]
                # Traveling wave luminance shader
                phase = (c * 0.18) - (frame_idx * 0.28)
                luminance = (math.sin(phase) + 1.0) / 2.0
                if luminance < 0.5:
                    col = lerp_color(acc_dim, acc, luminance * 2.0)
                else:
                    col = lerp_color(acc, acc_bright, (luminance - 0.5) * 2.0)
            elif is_sh:
                ch = shadow_char
                # Subtle secondary harmonic for shadow glow
                sh_phase = (c * 0.18) - (frame_idx * 0.28)
                sh_lum = (math.sin(sh_phase) + 1.0) / 2.0
                col = lerp_color(shadow_base, acc_dim, sh_lum * 0.35)
            else:
                ch = " "
                col = None

            if col != last_color:
                if last_color is not None:
                    line += "[/]"
                if col is not None:
                    line += f"[{col}]"
                last_color = col
            line += ch
        if last_color is not None:
            line += "[/]"
        output_lines.append(line)
    return output_lines


class BootScreen(ResponsiveModalScreen[bool]):
    """Graphical animated boot screen shown for 2 seconds upon console startup."""

    DEFAULT_CSS = """
    BootScreen {
        align: center middle;
        background: #000000;
        layers: base;
    }
    #boot_box {
        width: 82;
        max-width: 98%;
        height: auto;
        max-height: 25;
        border: double red;
        background: #080808;
        padding: 1 1;
        align: center middle;
        content-align: center middle;
        text-align: center;
    }
    BootScreen.-mobile #boot_box {
        width: 96%;
        max-width: 50;
        max-height: 28;
        padding: 0 1;
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
        self._painted_frames: int = 0
        self._anim_timer: Timer | None = None
        self._dismiss_timer: Timer | None = None
        self._is_dismissed: bool = False

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
        self._painted_frames = 0
        self._update_display()
        self._anim_timer = self.set_interval(0.06, self._tick_animation)
        self._dismiss_timer = self.set_timer(self.duration_seconds + 0.5, self._dismiss_boot)

    def on_resize(self, event: events.Resize) -> None:
        super().on_resize(event)
        self._update_display()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("ctrl+q", "q"):
            self._dismiss_boot()
            if hasattr(self.app, "action_quit"):
                self.app.action_quit()
            return

        # Guard against buffered keystrokes immediately upon boot/reboot:
        # Require minimum 0.6s grace period and only intentional skip keys
        now = time.monotonic()
        if self._start_time <= 0 or (now - self._start_time) < 0.6:
            return

        if event.key in ("escape", "space", "enter"):
            self._dismiss_boot()

    def on_click(self, event: events.Click) -> None:
        # Guard against terminal focus-clicks or buffered mouse events upon boot:
        now = time.monotonic()
        if self._start_time <= 0 or (now - self._start_time) < 0.6:
            return
        self._dismiss_boot()

    def _dismiss_boot(self) -> None:
        if self._is_dismissed:
            return
        self._is_dismissed = True
        if self._anim_timer:
            try:
                self._anim_timer.stop()
            except Exception:
                pass
            self._anim_timer = None
        if self._dismiss_timer:
            try:
                self._dismiss_timer.stop()
            except Exception:
                pass
            self._dismiss_timer = None
        try:
            if getattr(self, "app", None) and hasattr(self.app, "screen_stack") and self in self.app.screen_stack:
                if self.app.screen is self:
                    self.dismiss(True)
                else:
                    try:
                        self.app.screen_stack.remove(self)
                        if self._result_callbacks:
                            cb = self._result_callbacks[-1]
                            cb(True)
                    except Exception:
                        self.dismiss(True)
            else:
                self.dismiss(True)
        except Exception:
            pass

    def _tick_animation(self) -> None:
        if self._is_dismissed:
            return
        now = time.monotonic()
        elapsed = max(0.0, now - self._start_time) if self._start_time > 0 else 0.0
        self._frame_idx += 1
        self._painted_frames += 1

        if self._start_time > 0 and elapsed >= self.duration_seconds and self._painted_frames >= 8:
            self._dismiss_boot()
            return
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

            # 2. Main Title (Desktop single-line vs Mobile 2-tier block stack)
            if is_mobile:
                gemini_lines = render_block_text_with_shadow(
                    "GEMINI",
                    self._frame_idx,
                    acc,
                    acc_bright,
                    acc_dim,
                )
                integrated_lines = render_block_text_with_shadow(
                    "INTEGRATED",
                    self._frame_idx,
                    acc,
                    acc_bright,
                    acc_dim,
                )
                title_markup = (
                    "\n".join(gemini_lines)
                    + "\n"
                    + "\n".join(integrated_lines)
                    + f"\n[{acc_dim}]◈ gemini ◈[/]\n[{acc_dim}]◈ integrated ◈[/]"
                )
            else:
                desktop_lines = render_block_text_with_shadow(
                    "GEMINI-INTEGRATED",
                    self._frame_idx,
                    acc,
                    acc_bright,
                    acc_dim,
                )
                title_markup = (
                    "\n".join(desktop_lines)
                    + f"\n[{acc_dim}]◈ gemini-integrated bilateral console ◈[/]"
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
