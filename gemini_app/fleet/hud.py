"""Live Telemetry and AI Cognitive Monitor HUD.

A zero-dependency, low-power terminal dashboard designed to run smoothly on
mobile satellites (iPad iSH, Android Termux in horizontal/landscape phone screens)
as well as desktop consoles.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import select
import shutil
import sys
import termios
import time
import tty
from typing import Any, Callable, Dict, List, Optional


# ANSI Color and Formatting Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Palette
CYAN = "\033[38;2;56;189;248m"
BLUE = "\033[38;2;59;130;246m"
GREEN = "\033[38;2;34;197;94m"
YELLOW = "\033[38;2;234;179;8m"
PURPLE = "\033[38;2;168;85;247m"
RED = "\033[38;2;239;68;68m"
GRAY = "\033[38;2;148;163;184m"
DARK_GRAY = "\033[38;2;71;85;105m"
WHITE = "\033[38;2;248;250;252m"
BG_BLUE = "\033[48;2;30;58;138m"
BG_DARK = "\033[48;2;15;23;42m"


def strip_ansi(text: str) -> str:
    """Strips ANSI escape codes from string for exact visible character measurement."""
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]", "", text)


def clip_str(text: str, max_len: int) -> str:
    """Clips text to max_len, appending '...' if truncated."""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def clip_ansi(text: str, max_visible_len: int) -> str:
    """Clips text to max_visible_len while preserving ANSI formatting and closing with RESET."""
    if max_visible_len <= 0:
        return ""
    raw = strip_ansi(text)
    if len(raw) <= max_visible_len:
        return text

    target = max(1, max_visible_len - 3)
    out: List[str] = []
    vis = 0
    in_esc = False
    esc_buf: List[str] = []

    for ch in text:
        if ch == "\033":
            in_esc = True
            esc_buf.append(ch)
        elif in_esc:
            esc_buf.append(ch)
            if ch.isalpha():
                in_esc = False
                out.append("".join(esc_buf))
                esc_buf = []
        else:
            if vis < target:
                out.append(ch)
                vis += 1
            else:
                break

    out.append("...")
    out.append(RESET)
    return "".join(out)


def render_meter_bar(pct: float, width: int = 10) -> str:
    """Renders a compact ANSI percentage bar."""
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    empty = width - filled
    bar_filled = "█" * filled
    bar_empty = "░" * empty
    color = GREEN if pct < 70 else (YELLOW if pct < 90 else RED)
    return f"{color}[{bar_filled}{DARK_GRAY}{bar_empty}{color}]{RESET} {pct:.0f}%"


class SatelliteHUD:
    """Terminal HUD rendering engine optimized for landscape mobile screens."""

    def __init__(
        self,
        node_id: str,
        mothership_addr: str,
        on_upgrade_request: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.node_id = node_id
        self.mothership_addr = mothership_addr
        self.on_upgrade_request = on_upgrade_request

        self.is_connected = False
        self.last_ping_ms: Optional[float] = None
        self.mothership_data: Dict[str, Any] = {}
        self.local_vitals: Dict[str, Any] = {}
        self.recent_events: List[str] = []
        self.active_status_toast: Optional[str] = None
        self.toast_expires: float = 0.0

        self._running = False
        self._orig_termios = None

    def update_telemetry(self, data: Dict[str, Any]) -> None:
        """Updates internal mothership telemetry cache."""
        self.mothership_data = data
        self.is_connected = True

    def set_connection_status(self, connected: bool, ping_ms: Optional[float] = None) -> None:
        """Updates connection state and latency."""
        self.is_connected = connected
        if ping_ms is not None:
            self.last_ping_ms = ping_ms

    def log_event(self, text: str) -> None:
        """Appends an event to the recent event history."""
        timestamp = time.strftime("%H:%M:%S")
        self.recent_events.append(f"[{timestamp}] {text}")
        if len(self.recent_events) > 20:
            self.recent_events.pop(0)

    def show_toast(self, message: str, duration: float = 3.0) -> None:
        """Shows a temporary status toast across the HUD footer."""
        self.active_status_toast = message
        self.toast_expires = time.time() + duration

    def _format_box_line(self, left: str, content: str, width: int) -> str:
        """Formats a single content line enclosed in vertical box lines, guaranteeing no overflow or wrapping."""
        inner_w = max(10, width - 4)  # 2 for '│ ', 2 for ' │'
        clipped = clip_ansi(content, inner_w)
        raw_len = len(strip_ansi(clipped))
        padding = max(0, inner_w - raw_len)
        return f"{BLUE}│{RESET} {clipped}{' ' * padding} {BLUE}│{RESET}\n"

    def render(self) -> str:
        """Constructs full dashboard frame fitted to current terminal size."""
        term_cols, term_lines = shutil.get_terminal_size((80, 24))
        w = min(120, max(38, term_cols))

        # Top border with title & connection pill
        if self.is_connected:
            ping_str = f" {self.last_ping_ms:.0f}ms" if self.last_ping_ms else ""
            status_pill = f"{GREEN}{BOLD}[● LIVE{ping_str}]{RESET}"
            raw_pill_len = len(f"[● LIVE{ping_str}]")
        else:
            status_pill = f"{RED}{BOLD}[● OFFLINE]{RESET}"
            raw_pill_len = len("[● OFFLINE]")

        title = f"{CYAN}{BOLD}🛰️ GEMINI HUD{RESET}"
        header_inner = f"─ {title} ─ {status_pill} "
        raw_header_len = len("─ 🛰️ GEMINI HUD ─ ") + raw_pill_len + 1

        rem_addr_w = max(0, w - raw_header_len - 6)
        addr_disp = clip_str(self.mothership_addr, rem_addr_w) if rem_addr_w >= 7 else ""
        addr_part = f" {DARK_GRAY}{addr_disp}{BLUE}" if addr_disp else ""
        used_len = raw_header_len + (len(addr_disp) + 1 if addr_disp else 0) + 4
        dash_fill = max(0, w - used_len)
        top_bar = f"{BLUE}┌{header_inner}{'─' * dash_fill}{addr_part} ─┐{RESET}\n"

        lines = [top_bar]

        # 1. System & Node Vitals
        host_name = self.mothership_data.get("host", "mothership")
        platform_info = self.mothership_data.get("platform", "Linux")
        vitals = self.mothership_data.get("vitals", {})
        git_info = self.mothership_data.get("git", {})
        cognitive = self.mothership_data.get("cognitive", {})

        cpu_pct = vitals.get("cpu_pct", 0.0)
        mem_used = vitals.get("mem_used_mb", 0.0)
        mem_tot = vitals.get("mem_total_mb", 0.0)

        git_branch = git_info.get("branch", "main")
        git_sha = git_info.get("commit", "unknown")
        clean_tag = f"{GREEN}clean{RESET}" if git_info.get("is_clean", True) else f"{YELLOW}dirty{RESET}"

        line1 = (
            f"{BOLD}Host:{RESET} {WHITE}{host_name}{RESET} ({GRAY}{platform_info}{RESET})  "
            f"{BOLD}Node:{RESET} {CYAN}{self.node_id}{RESET}"
        )
        lines.append(self._format_box_line("│", line1, w))

        meter = render_meter_bar(cpu_pct, width=6 if w < 65 else 8)
        mem_str = f"{mem_used / 1024:.1f}G/{mem_tot / 1024:.1f}G" if mem_tot > 0 else "N/A"
        load_avg = vitals.get("load_avg", [0.0, 0.0, 0.0])
        ld_str = f"{load_avg[0]:.2f}" if load_avg else "?"
        line2 = (
            f"{BOLD}CPU:{RESET} {meter} ({DARK_GRAY}ld:{ld_str}{RESET})  "
            f"{BOLD}RAM:{RESET} {WHITE}{mem_str}{RESET}  "
            f"{BOLD}Git:{RESET} {BLUE}{git_branch}@{git_sha}{RESET} [{clean_tag}]"
        )
        lines.append(self._format_box_line("│", line2, w))

        # Divider
        div_mind = f"{BLUE}├─ {PURPLE}{BOLD}🧠 AI COGNITIVE STREAM{RESET} {BLUE}{'─' * max(0, w - 26)}┤{RESET}\n"
        lines.append(div_mind)

        # 2. Cognitive State (Cleaning duplicated prefixes and state duplication)
        raw_state = str(cognitive.get("state_desc") or "Standing By").strip()
        raw_task = str(cognitive.get("task") or "Awaiting active task").strip()
        thought = str(cognitive.get("thought") or "Connected and monitoring bilateral stream.").strip()
        tool = str(cognitive.get("tool") or "none").strip()
        topic_str = str(cognitive.get("topic") or "fleet & satellite nodes").strip()

        # Strip redundant "Task: " / "State: " prefixes
        clean_task = raw_task
        while clean_task.lower().startswith("task:"):
            clean_task = clean_task[5:].strip()
        while clean_task.startswith("•"):
            clean_task = clean_task[1:].strip()

        clean_state = raw_state
        while clean_state.lower().startswith("state:"):
            clean_state = clean_state[6:].strip()
        while clean_state.startswith("•"):
            clean_state = clean_state[1:].strip()

        # If clean_state is identical to clean_task, show a distinct informative state
        if clean_state.lower() == clean_task.lower():
            clean_state = "Active Processing" if tool not in ("none", "idle", "") else "Standing By"

        topic_clipped = clip_str(topic_str, 20 if w < 70 else 26)
        rem_state_w = max(10, w - len(topic_clipped) - 18)
        c_line1 = f"{BOLD}Topic:{RESET} {PURPLE}{topic_clipped}{RESET}  {BOLD}State:{RESET} {WHITE}{clip_str(clean_state, rem_state_w)}{RESET}"
        c_line2 = f"{BOLD}Task:{RESET}  {YELLOW}{clean_task}{RESET}"
        c_line3 = f"{BOLD}Think:{RESET} {GRAY}\"{thought}\"{RESET}"

        # Dynamic tool execution badge & turn counter
        turn_num = cognitive.get("turn_number", 1)
        turn_badge = f"{DARK_GRAY}(Turn #{turn_num}){RESET}"
        if tool in ("none", "idle", ""):
            tool_pill = f"{DARK_GRAY}[idle]{RESET}"
        elif "[done]" in tool:
            tool_pill = f"{BLUE}[{tool}]{RESET}"
        else:
            tool_pill = f"{GREEN}{BOLD}[⚡ {tool}]{RESET}"
        c_line4 = f"{BOLD}Tool:{RESET}  {tool_pill}  {turn_badge}"

        lines.append(self._format_box_line("│", c_line1, w))
        lines.append(self._format_box_line("│", c_line2, w))
        lines.append(self._format_box_line("│", c_line3, w))
        lines.append(self._format_box_line("│", c_line4, w))

        # Divider
        div_act = f"{BLUE}├─ {YELLOW}{BOLD}📋 ACTIVITY & RECENT COMMITS{RESET} {BLUE}{'─' * max(0, w - 32)}┤{RESET}\n"
        lines.append(div_act)

        # 3. Recent Commits / Activity
        recent_commits = git_info.get("recent_commits", [])
        if recent_commits:
            for c in recent_commits[:2]:
                sha = c.get("sha", "")
                msg = c.get("message", "")
                lines.append(self._format_box_line("│", f"{BLUE}• {sha}{RESET} {GRAY}{msg}{RESET}", w))
        elif self.recent_events:
            for ev in self.recent_events[-2:]:
                lines.append(self._format_box_line("│", f"{GRAY}{ev}{RESET}", w))
        else:
            lines.append(self._format_box_line("│", f"{DARK_GRAY}No recent activity recorded.{RESET}", w))

        # Bottom Bar & Footer
        now_str = time.strftime("%H:%M:%S")
        if self.active_status_toast and time.time() < self.toast_expires:
            toast_text = f"{BG_BLUE}{WHITE}{BOLD} {self.active_status_toast} {RESET}"
            bot_inner = f"─ {toast_text} "
            raw_bot_len = len(f"─  {self.active_status_toast}  ")
        else:
            bot_hint = "[q:quit u:upg]" if w < 55 else "[q:quit u:upgrade r:redraw]"
            bot_inner = f"─ {DARK_GRAY}{bot_hint}{RESET} "
            raw_bot_len = len(f"─ {bot_hint} ")

        bot_dash = max(0, w - 2 - raw_bot_len - len(now_str) - 3)
        bottom_bar = f"{BLUE}└{bot_inner}{'─' * bot_dash} {DARK_GRAY}{now_str}{BLUE} ─┘{RESET}\n"
        lines.append(bottom_bar)

        return "".join(lines)

    def start_raw_terminal(self) -> None:
        """Sets terminal to raw mode with hidden cursor and alternate buffer."""
        try:
            if sys.stdin.isatty():
                self._orig_termios = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                try:
                    os.set_blocking(sys.stdin.fileno(), False)
                except Exception:
                    pass
            # Alt buffer, clear screen, home cursor, hide cursor
            sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25l")
            sys.stdout.flush()
        except Exception:
            pass

    def restore_terminal(self) -> None:
        """Restores normal terminal settings."""
        try:
            sys.stdout.write("\033[?25h\033[?1049l")  # Show cursor + exit alt buffer
            sys.stdout.flush()
            if sys.stdin.isatty():
                try:
                    os.set_blocking(sys.stdin.fileno(), True)
                except Exception:
                    pass
                if self._orig_termios:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._orig_termios)
        except Exception:
            pass

    def check_keyboard_input(self) -> Optional[str]:
        """Polls for single keypress non-blockingly without ever hanging the event loop."""
        if not sys.stdin.isatty():
            return None
        try:
            data = os.read(sys.stdin.fileno(), 32)
            if data:
                return data.decode("utf-8", errors="ignore")[:1]
        except (BlockingIOError, InterruptedError, OSError):
            return None
        except Exception:
            pass
        return None

    def render_loop_tick(self) -> Optional[str]:
        """Renders one frame and checks for keypress, clearing to bottom to prevent ghost lines."""
        frame = self.render()
        # Home cursor, clear to end of screen, and write frame cleanly
        sys.stdout.write(f"\033[H\033[J{frame}")
        sys.stdout.flush()
        return self.check_keyboard_input()
