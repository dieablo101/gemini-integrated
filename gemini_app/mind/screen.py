"""Full-screen interactive Cognitive Mind Map view and live reactive animation watcher."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Label, Markdown, Static

from gemini_app.config import DEFAULT_PALETTE, MOBILE_BREAKPOINT, SPINNER_FRAMES, THEMES
from gemini_app.introspection import ANIMATION_FRAMES

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp


def format_fleet_nodes_markdown() -> str:
    """Formats live connected nodes and registered fleet nodes into rich Markdown."""
    try:
        import socket
        from gemini_app.fleet.nodes import get_fleet_snapshot
        from gemini_app.fleet.protocol import DEFAULT_PORT, get_local_lan_ip
        snapshot = get_fleet_snapshot()
        active_cnt = snapshot.get("active_count", 0)
        total_cnt = snapshot.get("total_registered", 0)
        nodes = snapshot.get("nodes", [])

        local_ip = get_local_lan_ip()

        # Probe if Mothership daemon is genuinely listening on local TCP port
        is_listening = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.05)
                is_listening = (s.connect_ex(("127.0.0.1", DEFAULT_PORT)) == 0)
        except Exception:
            is_listening = False

        if is_listening:
            daemon_status = f"{active_cnt} Active" if active_cnt > 0 else "Listening"
        else:
            daemon_status = "Offline"

        lines = [
            f"**Mothership Fleet:** `{local_ip}:{DEFAULT_PORT}` ({daemon_status})",
            f"**Satellites:** `{active_cnt}` active / `{total_cnt}` registered",
            "",
        ]

        # Filter out internal/control clients
        valid_nodes = [
            n for n in nodes
            if n.get("node_id") not in ("console", "console-client", "local", "mothership")
        ]

        if not valid_nodes:
            lines.append("*No satellite nodes registered or connected yet.*")
            lines.append(f"Run on node: `python3 gemini-integrated.py node --mothership {local_ip}`")
            return "\n".join(lines)

        for n in valid_nodes:
            nid = n.get("node_id", "satellite")
            host = n.get("host", "127.0.0.1")
            status = n.get("status", "offline")
            user = n.get("ssh_user", "root")
            port = n.get("ssh_port", 22)
            autostart = n.get("autostart", "auto")
            telem = n.get("telemetry", {})
            live_info = n.get("live_info", {})

            # Prefer LAN IP if host is IPv6 and telemetry records LAN route
            route_ip = telem.get("route", {}).get("local_ip")
            display_host = route_ip if (route_ip and (":" in host or host.startswith("127."))) else host

            is_termux = bool(telem.get("is_termux") or "termux" in nid)
            is_ish = bool(telem.get("is_ish") or "ish" in nid)
            if is_termux:
                if port == 22:
                    port = 8022
                if user == "root":
                    user = "termux"

            addr_str = f"[{display_host}]:{port}" if ":" in display_host else f"{display_host}:{port}"

            if status == "online":
                if live_info.get("address"):
                    live_addr = live_info["address"]
                    if ":" in live_addr and not live_addr.startswith("["):
                        parts = live_addr.rsplit(":", 1)
                        if ":" in parts[0]:
                            live_addr = f"[{parts[0]}]:{parts[1]}"
                    addr_str = live_addr
                lines.append(f"🟢 **`{nid}`** (`{addr_str}`) [● LIVE]")
            else:
                last_seen_ago = n.get("last_seen_seconds_ago", 999)
                if last_seen_ago < 60:
                    time_str = "just now"
                elif last_seen_ago < 3600:
                    time_str = f"{int(last_seen_ago // 60)}m ago"
                else:
                    time_str = f"{last_seen_ago / 3600:.1f}h ago"
                lines.append(f"🔴 **`{nid}`** (`{addr_str}`) [● OFFLINE - {time_str}]")

            # System vitals
            sys_name = telem.get("system", "")
            mach = telem.get("machine", "")
            plat = telem.get("platform", "")
            if is_ish and not plat:
                plat = "iSH Alpine"
            elif is_termux and not plat:
                plat = "Termux Android"

            cpu = telem.get("cpu_pct", 0.0)
            mem_t = telem.get("mem_total_mb", 0.0)
            mem_a = telem.get("mem_avail_mb", 0.0)
            mem_u = telem.get("mem_used_mb", 0.0)
            if not mem_u and mem_t and mem_a:
                mem_u = max(0.0, mem_t - mem_a)

            vitals_parts = []
            plat_str = f"{sys_name} {mach}".strip()
            if plat and plat != plat_str:
                plat_str = f"{plat_str} ({plat})"
            if plat_str:
                vitals_parts.append(plat_str)
            if cpu:
                vitals_parts.append(f"CPU: {cpu:.1f}%")
            if mem_t > 0:
                pct_val = (mem_u / mem_t) * 100
                vitals_parts.append(f"RAM: {mem_u / 1024:.1f}G/{mem_t / 1024:.1f}G ({pct_val:.0f}%)")

            bat = telem.get("battery", {})
            if bat and bat.get("percentage") is not None:
                icon = "⚡" if bat.get("charging") else "🔋"
                vitals_parts.append(f"{icon} {bat['percentage']}%")

            if telem.get("has_ipad_mount"):
                vitals_parts.append(f"iOS Files: {telem.get('ipad_files_count', 0)}")

            webapplet = telem.get("webapplet", {})
            if webapplet and webapplet.get("running"):
                w_port = webapplet.get("port", 8888)
                w_status = "active" if webapplet.get("wingman_active") else "standby"
                vitals_parts.append(f"Wingman :{w_port} ({w_status})")

            if vitals_parts:
                lines.append(f"  • **Sys:** {' | '.join(vitals_parts)}")

            from pathlib import Path
            k_name = Path(n.get("ssh_key", "")).name if n.get("ssh_key") else "id_cluster"

            auto_label = autostart
            if is_termux:
                auto_label = "termux-boot"
            elif is_ish:
                auto_label = "openrc"

            ssh_addr = f"[{display_host}]:{port}" if ":" in display_host else f"{display_host}:{port}"
            lines.append(f"  • **Rescue:** `{user}@{ssh_addr}` *(key: {k_name})* | **Autostart:** `{auto_label}`")
            lines.append("")

        return "\n".join(lines).strip()
    except Exception as exc:
        return f"*Fleet status: {exc}*"


class MindMapScreen(Screen):
    """Interactive screen displaying Gemini's direction, user intent, topology, and fleet nodes."""

    BINDINGS = [
        Binding("escape", "back_to_chat", "Back to Chat"),
        Binding("ctrl+g", "back_to_chat", "Back to Chat"),
        Binding("q", "back_to_chat", "Back to Chat"),
    ]

    DEFAULT_CSS = """
    MindMapScreen {
        layout: vertical;
        background: #000000;
        layers: base overlay toasts;
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
        width: 55%;
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
        width: 45%;
        height: 100%;
        background: #000000;
        layout: vertical;
    }
    MindMapScreen.-mobile #mind_tree_column {
        width: 100%;
        height: 50%;
    }
    #mind_topology_card {
        height: 50%;
        width: 100%;
        padding: 1;
        overflow-y: auto;
        background: #000000;
    }
    #mind_nodes_card {
        height: 50%;
        width: 100%;
        padding: 1;
        overflow-y: auto;
        background: #000000;
    }
    .mind_header {
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._live_watch_timer: Timer | None = None
        self._anim_frame_idx: int = 0
        self._last_state_signature: str = ""
        self._last_nodes_signature: str = ""

    def _update_screen_classes(self, width: int | None = None) -> None:
        w = width if width is not None else (self.size.width or (self.app.size.width if self.app else 100))
        self.set_class(w <= MOBILE_BREAKPOINT, "-mobile")

    def on_mount(self) -> None:
        if hasattr(self.app, "active_palette_name"):
            self.add_class(f"theme-{self.app.active_palette_name}")
        self._update_screen_classes()
        self.refresh_display()
        self._live_watch_timer = self.set_interval(0.6, self._on_live_watch_tick)

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
            nodes_md = self.query_one("#mind_nodes_text", Markdown)

            g_state = getattr(app, "current_gemini_state", "") or "*No conclusive direction recorded yet.*"
            u_state = getattr(app, "current_user_state", "") or "*Awaiting initial conversational alignment.*"
            t_content = getattr(app, "current_tree_content", "")
            tree_body = f"```text\n{t_content}\n```" if t_content else "*Tree not initialized.*"

            nodes_body = format_fleet_nodes_markdown()

            gemini_md.update(g_state)
            user_md.update(u_state)
            tree_md.update(tree_body)
            nodes_md.update(nodes_body)

            self._last_state_signature = f"{g_state}::{u_state}::{t_content}"
            self._last_nodes_signature = nodes_body

            gemini_md.refresh(layout=True)
            user_md.refresh(layout=True)
            tree_md.refresh(layout=True)
            nodes_md.refresh(layout=True)
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

        # 2. Check and refresh fleet nodes display every 3 ticks (~1.8s)
        if self._anim_frame_idx % 3 == 0:
            try:
                nodes_md = self.query_one("#mind_nodes_text", Markdown)
                new_nodes_body = format_fleet_nodes_markdown()
                if new_nodes_body != self._last_nodes_signature:
                    self._last_nodes_signature = new_nodes_body
                    nodes_md.update(new_nodes_body)
            except Exception:
                pass

        # 3. Render reactive animation & cognitive flow on pulse bar
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
            with Vertical(id="mind_tree_column"):
                with Vertical(id="mind_topology_card"):
                    yield Label("── WORKSPACE & TELEMETRY TOPOLOGY ──", classes="mind_header")
                    yield Markdown(id="mind_tree_text")
                with Vertical(id="mind_nodes_card"):
                    yield Label("── NETWORK / NODES ──", classes="mind_header")
                    yield Markdown(id="mind_nodes_text")

    def action_back_to_chat(self) -> None:
        self.app.pop_screen()
