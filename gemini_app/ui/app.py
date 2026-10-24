"""Main Textual Chat Application for Gemini Bilateral Console."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime
import getpass
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

import pyperclip
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore
    GENAI_AVAILABLE = False
from rich.cells import cell_len
from rich.console import RenderableType
from rich.syntax import Syntax
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    Markdown,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
    Tree,
)
from textual.widgets.markdown import MarkdownFence
from textual.widgets.text_area import Selection
from textual.widgets.tree import TreeNode

from gemini_app.config import (
    ACTIVE_TASK_FILE,
    ARCHIVE_DIR,
    CENTER_SCREEN_MODE,
    CHATS_DIR,
    CURRENT_USER,
    DEFAULT_COPYRIGHT_HOLDER,
    DEFAULT_MODEL,
    DEFAULT_PALETTE,
    DEFAULT_WINDOW_CAPACITY,
    FORK_HEADER_TEXT,
    GEMINI_HOME,
    GATED_NAV_KEYS,
    MAX_SNIPPET_LINES_ON_WIRE,
    MOBILE_BREAKPOINT,
    PROJECTS_DIR,
    SCREENSHOTS_DIR,
    SOCKET_PATH,
    SPINNER_FRAMES,
    STATE_FILE,
    THEMES,
    TURNS_PER_SEGMENT,
    WIRE_CONTINUATION_PROMPT,
)
from gemini_app.onboarding import get_stored_api_key, save_gemini_api_key
from gemini_app.projects import get_user_real_name, scaffold_project, set_user_real_name
from gemini_app.system_deps import detect_os, ensure_system_dependencies
from gemini_app.helpers import (
    build_ascii_tree,
    cast_ray_from_center,
    detect_language,
    extract_retry_delay,
    format_reconnect_countdown,
    get_git_files_catalog,
    truncate_wire_snippets,
    write_code_to_disk,
)
from gemini_app.events import (
    AppLockController,
    AppLockEngaged,
    AppLockReleased,
    MindMapRecalibrated,
    RemoteInsert,
    RequestFailed,
    RequestFinished,
    RequestPhaseUpdate,
)
from gemini_app.mind.screen import MindMapScreen
from gemini_app.storage.memory_index import MemoryIndex
from gemini_app.storage.notes_manager import NoteItem, NotesManager, sanitize_working_notes
from gemini_app.storage.rollback import (
    check_reboot_guard,
    create_safety_checkpoint,
    mark_reboot_in_progress,
    mark_startup_successful,
    perform_git_rollback,
    record_stable_commit,
    restore_safety_checkpoint,
    verify_offline_preflight,
)
from gemini_app.storage.state_backup import (
    check_and_run_daily_backup,
    install_systemd_backup_timer,
    perform_backup,
)
from gemini_app.introspection import (
    apply_accent_talk,
    format_introspection_summary,
    get_console_state,
    start_mind_animation,
)
from gemini_app.tools.registry import ToolRegistry
from gemini_app.tools.snapshots import (
    capture_ui_snapshot,
    cleanup_stale_ephemerals,
    cleanup_test_snapshots,
    delete_all_snapshots,
    list_held_snapshots,
    prune_audit_snapshots,
)
from gemini_app.ui.boot import BootScreen
from gemini_app.ui.modals import (
    ApiKeyModal,
    CommandsModal,
    ConfirmModal,
    DirectoryPathInput,
    FilePathInput,
    ForkModal,
    FrameSelectModal,
    GitSetupModal,
    GitTreeModal,
    InsertFileModal,
    PasswordModal,
    ResponsiveModalScreen,
    TitlePromptModal,
    VaultAuthModal,
    VaultChangePasskeyModal,
    VaultDashboardModal,
    VaultFileEntryModal,
    VaultPasswordEntryModal,
    VaultSecretEntryModal,
    WingmanAuthModal,
    WriteSnippetModal,
)
from gemini_app.ui.widgets import (
    EmacsBaseTextArea,
    ExpandingInput,
    FeedArea,
    NotesEditorArea,
    NotesPanel,
    SnippetPreview,
    TurnCard,
)
from gemini_app.ui.styles import get_full_app_css


class ChatApp(App):
    ENABLE_COMMAND_PALETTE = False
    COMMAND_PALETTE_BINDING = None
    COMMANDS = set()

    def action_command_palette(self) -> None:
        pass

    CSS = get_full_app_css()

    BINDINGS = [
        Binding("ctrl+c", "c_c_prefix_stub", "^c Commands", show=False),
        Binding("ctrl+l", "repaint_screen", "^l Repaint Screen", show=False),
        Binding("ctrl+q", "quit", "^q Quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load API key and initialize client safely
        api_key = get_stored_api_key()
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key
        try:
            if GENAI_AVAILABLE and genai is not None:
                self.client = genai.Client()
            else:
                self.client = None
        except Exception:
            self.client = None

        self.user_real_name: str = get_user_real_name()
        self.lock = AppLockController(self)
        self.memory_index = MemoryIndex()

        self.active_palette_name: str = DEFAULT_PALETTE
        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.current_chat_parent_id: str | None = None
        self.current_chat_working_dir: str | None = None
        self.current_chat_last_index: int = 0
        self.current_chat_center_marker: str = ""
        is_test_env = "unittest" in sys.modules or bool(os.environ.get("GEMINI_TEST_MODE"))
        self._boot_complete: bool = is_test_env
        self._wingman_modal_open: bool = False
        self._wingman_auth_queue: list[Dict[str, Any]] = []
        self._handled_wingman_auth_reqs: set[str] = set()
        
        # Unified Notes System (Gemini Managed Notes)
        self.gemini_notes: str = ""
        self.global_notes: str = ""
        self.relational_notes: dict[str, str] = {}
        self.active_notes_mode: str = "gemini"  # "gemini", "turn", "global"
        self.current_focused_turn_id: str = ""
        self.current_focused_turn_index: int = 0
        self._notes_flush_timer: Timer | None = None
        self.notes_manager: NotesManager = NotesManager(working_notes="", active_topic="General")

        # Cognitive Mind State & Topology Tracking
        self.is_legacy_chat: bool = False
        self.active_task_title: str = "Fleet & Satellite Nodes"
        self.current_gemini_state: str = "Fleet & Satellite Nodes"
        self.current_user_state: str = "Collaborating on unified bilateral console session."
        self.current_tree_state: list[str | int] = ["T1", "F:gemini_app/"]
        self.current_tree_content: str = "└── Unified Stream [Active]"
        self.saved_prompt_draft: str = ""
        self._active_mind_animation: dict | None = None
        self.cognitive_adapter = None

        self.notes_open: bool = False
        self._last_focused_input_id: str = "input"
        self._last_non_notes_input_id: str = "input"
        self._seen_chats_in_session: set[str] = set()

        self.history: list[dict] = []
        self._server: asyncio.AbstractServer | None = None
        self.wingman_applet: Optional[Any] = None

        self._prefix_c_c: bool = False
        self._c_c_timer: Timer | None = None

        self._request_phase: str = "idle"
        self._request_details: str = ""
        self._request_start_time: float = 0.0
        self._spinner_idx: int = 0
        self._status_timer: Timer | None = None
        self._reconnect_target_time: float = 0.0
        self._reconnect_attempt: int = 0
        self._reconnect_max_retries: int = 0
        self._background_task_status: str = ""
        self._abort_requested: bool = False

        self._last_heartbeat_time: float = time.monotonic()
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_running: bool = False

        self._nav_indicator_action: str | None = None
        self._nav_indicator_palette: str | None = None
        self._nav_indicator_timer: Timer | None = None

        self._commands_registry: dict[str, Callable[[str], None]] = {
            "ui-theme": self._cmd_ui_theme,
            "reboot": lambda arg: self.action_reboot(status_report=arg if arg else None),
            "restart": lambda arg: self.action_reboot(status_report=arg if arg else None),
            "abort": lambda _: self.action_emergency_interrupt(),
            "interrupt": lambda _: self.action_emergency_interrupt(),
            "cancel": lambda _: self.action_emergency_interrupt(),
            "api-key": lambda _: self.action_configure_api_key(),
            "git-setup": lambda _: self.action_configure_git(),
            "credentials": lambda _: self.action_configure_git(),
            "vault": lambda arg: self._cmd_vault(arg),
            "passkey": lambda arg: self._cmd_vault(arg),
            "password": lambda arg: self._cmd_vault(arg),
            "scaffold": self._cmd_scaffold_project,
            "new-project": self._cmd_scaffold_project,
            "sys-deps": lambda _: self._cmd_sys_deps(),
            "backup-now": lambda _: self._cmd_backup_now(),
            "backup": lambda _: self._cmd_backup_now(),
            "qr": lambda arg: self._cmd_qr(arg),
            "qrcode": lambda arg: self._cmd_qr(arg),
        }

    @property
    def current_topic(self) -> str:
        """Returns the active notes topic or fallback."""
        if hasattr(self, "notes_manager") and self.notes_manager:
            return getattr(self.notes_manager, "active_topic", "general") or "general"
        return "general"

    def action_configure_api_key(self) -> None:
        """Opens ApiKeyModal to update or configure the Google Gemini API Key."""
        def _on_key_submitted(key: str | None) -> None:
            if key:
                save_gemini_api_key(key)
                try:
                    if GENAI_AVAILABLE and genai is not None:
                        self.client = genai.Client()
                        self.notify("Gemini API Key updated and saved to env variables & ~/.bashrc!", title="API Key Configured")
                    else:
                        self.notify("Gemini API Key saved (GenAI SDK not installed on this device).", title="API Key Saved")
                except Exception as e:
                    self.notify(f"Client init warning: {e}", severity="warning")
        self.push_screen(ApiKeyModal(), _on_key_submitted)

    def action_configure_git(self) -> None:
        """Opens GitSetupModal to configure Real Name and Git credentials."""
        def _on_git_done(res: dict | None) -> None:
            if res:
                name = res.get("real_name")
                if name:
                    self.user_real_name = name
                self.notify("Git credentials and project author updated!", title="Git Setup Complete")
        self.push_screen(GitSetupModal(), _on_git_done)

    def prompt_password(
        self,
        title: str = "🔐 Password Required",
        message: str = "Please enter your password or passkey:",
        placeholder: str = "••••••••",
        submit_label: str = "Confirm",
        allow_empty: bool = False,
        callback: Callable[[str | None], None] | None = None,
    ) -> None:
        """Opens PasswordModal to securely prompt for a passkey or password without exposing it in the input field."""
        self.push_screen(
            PasswordModal(
                title=title,
                message=message,
                placeholder=placeholder,
                submit_label=submit_label,
                allow_empty=allow_empty,
            ),
            callback,
        )

    def prompt_wingman_auth(
        self,
        auth_data: Dict[str, Any],
        callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Presents a zero-trust confirmation modal for an incoming Wingman browser connection request."""
        if not getattr(self, "_boot_complete", False) or any(s.__class__.__name__ == "BootScreen" for s in self.screen_stack):
            self._handle_wingman_auth_prompt(auth_data)
            return

        def _on_dismiss(decision: str) -> None:
            if callback:
                try:
                    callback(decision)
                except Exception:
                    pass
        self.push_screen(WingmanAuthModal(auth_data=auth_data), _on_dismiss)

    def _start_wingman_server(self, port: int = 8888) -> None:
        """Starts local Wingman bilateral talk portal on port 8888 and binds zero-trust auth handlers."""
        if "unittest" in sys.modules or os.environ.get("GEMINI_TEST_MODE"):
            return
        if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
            return
        try:
            from gemini_app.webapplet.applets.wingman import WingmanApplet
            from gemini_app.fleet.satellite import set_active_wingman

            self.wingman_applet = WingmanApplet(port=port, node_id="mothership")
            set_active_wingman(self.wingman_applet)

            def _fetch_canonical_wingman_history() -> List[Dict[str, Any]]:
                items: List[Dict[str, Any]] = []
                hist = getattr(self, "history", [])
                base_time = getattr(self, "_chat_start_time", 0.0) or (time.time() - max(120.0, len(hist) * 10))
                # Wingman feed displays the last 50 cards (do NOT touch Mothership pagination)
                hist_slice = hist[-50:] if len(hist) > 50 else hist
                for idx, turn in enumerate(hist_slice):
                    role = turn.get("role", "")
                    text = turn.get("text", "")
                    turn_id = turn.get("turn_id", "")
                    ts = turn.get("timestamp") or (base_time + (idx * 2))
                    is_u = (role == "user")
                    sender_name = "Operator" if is_u else "Gemini Core"
                    clean_text = text
                    origin_label = turn.get("origin_label", "")
                    origin_device = turn.get("origin_device", "")
                    if clean_text.startswith("📱 **[") or clean_text.startswith("💻 **["):
                        parts = clean_text.split("\n", 1)
                        if len(parts) > 1:
                            clean_text = parts[1]
                        if not origin_label:
                            header = parts[0]
                            if " - " in header:
                                p = header.split(" - ", 1)[1].rstrip("]*").strip()
                                origin_label = p
                    elif is_u and not origin_label:
                        origin_label = "Mothership"
                        origin_device = "mothership"

                    m_id = str(turn_id) if str(turn_id).startswith("msg-") else (f"msg-turn-{turn_id}" if turn_id else f"msg-hist-{idx}")
                    items.append({
                        "id": m_id,
                        "sender": sender_name,
                        "text": clean_text,
                        "is_user": is_u,
                        "timestamp": float(ts),
                        "origin_device": origin_device,
                        "origin_label": origin_label,
                    })
                return items

            self.wingman_applet._chat_history_fetcher = _fetch_canonical_wingman_history
            self.wingman_applet.on_auth_request(self._on_wingman_auth_request)
            self.wingman_applet.on_chat_message(self._on_wingman_remote_chat)
            self.wingman_applet.start()
        except Exception:
            pass

    def _on_wingman_auth_request(self, auth_data: Dict[str, Any]) -> None:
        """Invoked from Wingman engine thread when an incoming device requests access."""
        self.call_from_thread(self._handle_wingman_auth_prompt, auth_data)

    def _handle_wingman_auth_prompt(self, auth_data: Dict[str, Any]) -> None:
        """Enqueues and mounts WingmanAuthModal on the Mothership TUI to Accept, Pair, or Deny sequentially."""
        req_id = auth_data.get("auth_req_id") or auth_data.get("session_id", "")
        if not req_id:
            return
        ts = auth_data.get("timestamp", time.time())
        if (time.time() - ts) > 45.0:
            return
        handled_times = getattr(self, "_handled_wingman_auth_times", {})
        if req_id in handled_times:
            if (time.time() - handled_times[req_id]) < 45.0:
                return
            handled_times.pop(req_id, None)

        if not hasattr(self, "_wingman_auth_queue"):
            self._wingman_auth_queue = []

        client_ip = auth_data.get("client_ip", "")
        node_id = auth_data.get("node_id", "")
        dev_id = auth_data.get("device_id", "")

        # Avoid duplicate modals in queue (by req_id or by device/client_ip/node_id)
        for queued in self._wingman_auth_queue:
            q_req = queued.get("auth_req_id") or queued.get("session_id")
            if q_req == req_id:
                return
            if node_id and node_id not in ("local", "mothership") and queued.get("node_id") == node_id:
                return
            if dev_id and queued.get("device_id") == dev_id:
                return
            if client_ip and client_ip not in ("127.0.0.1", "::1", "localhost") and queued.get("client_ip") == client_ip:
                return

        if getattr(self, "_wingman_modal_open", False):
            has_auth_modal = any(s.__class__.__name__ == "WingmanAuthModal" for s in getattr(self, "screen_stack", []))
            if not has_auth_modal and getattr(self, "screen_stack", None):
                self._wingman_modal_open = False
            else:
                curr_data = getattr(self, "_active_wingman_auth_data", None)
                if curr_data:
                    if node_id and node_id not in ("local", "mothership") and curr_data.get("node_id") == node_id:
                        return
                    if dev_id and curr_data.get("device_id") == dev_id:
                        return
                    if client_ip and client_ip not in ("127.0.0.1", "::1", "localhost") and curr_data.get("client_ip") == client_ip:
                        return

        self._wingman_auth_queue.append(dict(auth_data))
        self._process_next_wingman_auth()

    def _process_next_wingman_auth(self) -> None:
        """Processes the next pending Wingman authorization request sequentially (back-to-back)."""
        if not getattr(self, "_boot_complete", False):
            return

        if getattr(self, "_wingman_modal_open", False):
            has_auth_modal = any(s.__class__.__name__ == "WingmanAuthModal" for s in getattr(self, "screen_stack", []))
            has_boot_screen = any(s.__class__.__name__ == "BootScreen" for s in getattr(self, "screen_stack", []))
            if has_auth_modal or has_boot_screen:
                return
            if getattr(self, "screen_stack", None):
                self._wingman_modal_open = False
            else:
                return

        try:
            if any(s.__class__.__name__ in ("BootScreen", "WingmanAuthModal") for s in getattr(self, "screen_stack", [])):
                return
        except Exception:
            pass

        if not hasattr(self, "_wingman_auth_queue") or not self._wingman_auth_queue:
            return

        auth_data = self._wingman_auth_queue.pop(0)
        req_id = auth_data.get("auth_req_id") or auth_data.get("session_id", "")
        ts = auth_data.get("timestamp", time.time())
        if (time.time() - ts) > 45.0:
            self._process_next_wingman_auth()
            return
        handled_times = getattr(self, "_handled_wingman_auth_times", {})
        if req_id in handled_times and (time.time() - handled_times[req_id]) < 45.0:
            self._process_next_wingman_auth()
            return

        client_ip = auth_data.get("client_ip", "remote")
        node_id = auth_data.get("node_id", "local")
        self._wingman_modal_open = True
        self._active_wingman_auth_data = auth_data

        def _on_decision(decision: str) -> None:
            self._wingman_modal_open = False
            self._active_wingman_auth_data = None
            if not hasattr(self, "_handled_wingman_auth_times"):
                self._handled_wingman_auth_times = {}
            self._handled_wingman_auth_times[req_id] = time.time()
            handled_set = getattr(self, "_handled_wingman_auth_reqs", set())
            handled_set.add(req_id)
            self._handled_wingman_auth_reqs = handled_set

            dec = decision or "deny"
            trust_device = (dec == "pair")
            accepted = (dec in ("accept", "pair"))
            node_id_val = auth_data.get("node_id", node_id)
            dev_id_val = auth_data.get("device_id", "")
            client_ip_val = auth_data.get("client_ip", client_ip)

            # 1. Authorize on local Wingman applet if running
            if getattr(self, "wingman_applet", None):
                try:
                    self.wingman_applet.authorize_session(req_id, accepted=accepted, trust_device=trust_device)
                except Exception:
                    pass

            # 2. Authorize via MothershipServer (for satellite nodes like iPad / phone)
            try:
                from gemini_app.fleet.nodes import send_mothership_command
                send_mothership_command("resolve_wingman_auth", {
                    "auth_req_id": req_id,
                    "session_id": req_id,
                    "node_id": node_id_val,
                    "decision": dec,
                    "trust": trust_device,
                }, timeout=3.0)
            except Exception:
                pass

            if dec == "accept":
                self.notify(f"Wingman session accepted (one-time approval) from {client_ip_val} ({node_id_val})", title="Wingman Authorized")
            elif dec == "pair":
                self.notify(f"Wingman permanently paired & trusted for {client_ip_val} ({node_id_val})", title="Wingman Paired")
            else:  # deny
                self.notify(f"Wingman connection denied for {client_ip_val} ({node_id_val})", severity="warning", title="Wingman Denied")

            # Purge any remaining duplicate requests in queue for this same device or node
            if hasattr(self, "_wingman_auth_queue") and self._wingman_auth_queue:
                self._wingman_auth_queue = [
                    q for q in self._wingman_auth_queue
                    if (q.get("auth_req_id") or q.get("session_id")) != req_id
                    and (not dev_id_val or q.get("device_id") != dev_id_val)
                    and (not node_id_val or node_id_val in ("local", "mothership") or q.get("node_id") != node_id_val)
                    and (not client_ip_val or client_ip_val in ("127.0.0.1", "::1", "localhost") or q.get("client_ip") != client_ip_val)
                ]

            # Handle the next queued request back-to-back!
            self.set_timer(0.2, self._process_next_wingman_auth)

        self.prompt_wingman_auth(auth_data, _on_decision)

    @work(exclusive=True, thread=True)
    def _check_pending_wingman_auth(self) -> None:
        """Polls MothershipServer and local applet for pending Wingman access requests."""
        handled_times = getattr(self, "_handled_wingman_auth_times", {})

        # Check MothershipServer for requests from satellites
        try:
            from gemini_app.fleet.nodes import send_mothership_command
            res = send_mothership_command("get_pending_wingman_auth", timeout=1.0)
            if isinstance(res, dict) and "requests" in res:
                for req in res.get("requests", []):
                    rid = req.get("auth_req_id") or req.get("session_id")
                    if rid and (rid not in handled_times or (time.time() - handled_times[rid]) >= 45.0):
                        self.call_from_thread(self._handle_wingman_auth_prompt, req)
        except Exception:
            pass

        # Check local wingman applet if running
        try:
            if getattr(self, "wingman_applet", None) and hasattr(self.wingman_applet, "security"):
                for sess in list(self.wingman_applet.security.sessions.values()):
                    if sess.status == "pending" and (sess.session_id not in handled_times or (time.time() - handled_times[sess.session_id]) >= 45.0):
                        self.call_from_thread(self._handle_wingman_auth_prompt, {
                            "auth_req_id": sess.session_id,
                            "session_id": sess.session_id,
                            "node_id": "mothership",
                            "client_ip": sess.client_ip,
                            "user_agent": sess.user_agent,
                            "device_id": sess.device_id,
                            "timestamp": getattr(sess, "last_seen", sess.created_at),
                        })
        except Exception:
            pass

    def _on_wingman_remote_chat(self, sender: str, text: str, meta: Dict[str, Any]) -> None:
        """Invoked from Wingman engine thread when a remote chat message is submitted."""
        self.call_from_thread(self._handle_wingman_incoming_chat, sender, text, meta)

    def _handle_wingman_incoming_chat(self, sender: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Appends incoming Wingman message to ChatApp feed, saves, and prompts Gemini."""
        from uuid import uuid4
        from gemini_app.ui.widgets.feed import FeedArea

        meta = meta or {}
        dev_label = meta.get("device_label") or meta.get("device_name") or ""
        dev_id = meta.get("device_id") or ""
        msg_id = meta.get("id") or meta.get("msg_id") or ""

        if text.strip().lower() == "/clear":
            try:
                feed = self.query_one("#feed", FeedArea)
                feed.clear()
                self.history = []
                self.save_current_chat()
                if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
                    self.wingman_applet.clear_chat()
                self.notify("Chat cleared via Wingman.", timeout=3.0)
            except Exception:
                pass
            return

        is_pc = (dev_label in ("PC", "Mac")) or (dev_label and not any(k in dev_label.lower() for k in ("phone", "ipad", "tablet")))
        icon = "💻" if is_pc else "📱"
        display_sender = "Operator" if sender.lower() == "operator" else sender
        label_part = f" - {dev_label}" if dev_label else ""
        msg_body = f"{icon} **[{display_sender}{label_part}]**\n{text}"
        try:
            feed = self.query_one("#feed", FeedArea)
            new_turn_id = msg_id if msg_id else f"turn_{uuid4().hex[:8]}"
            self.history.append({
                "turn_id": new_turn_id,
                "role": "user",
                "text": msg_body,
                "timestamp": time.time(),
                "origin_device": dev_id,
                "origin_label": dev_label,
            })
            self.current_chat_last_index = max(0, len(self.history) - 1)
            self.current_chat_center_marker = new_turn_id
            self.run_worker(feed.append_message(CURRENT_USER, msg_body, jump_to_start=False))
            self.notify(f"Wingman: {text[:40]}...", title=f"Message from {display_sender}{label_part}")
            self.save_current_chat()
            self.ask_gemini()
        except Exception:
            pass

    def request_vault_passkey(
        self,
        reason: str,
        callback: Callable[[str | None], None],
    ) -> None:
        """Requests vault passkey with explicit reason banner.

        Reuses active in-memory session key if already authenticated.
        """
        from gemini_app.vault import get_session_passkey, is_session_unlocked

        if is_session_unlocked():
            callback(get_session_passkey())
            return

        self.push_screen(
            VaultAuthModal(reason=reason),
            callback,
        )

    def action_vault_passkey(self) -> None:
        """Opens Vault Dashboard, unlocking via passkey modal if session is locked."""
        self.action_vault_dashboard()

    def action_vault_dashboard(self) -> None:
        """Opens master Vault Dashboard after ensuring session is unlocked."""
        def _on_authed(key: str | None) -> None:
            if key:
                self.push_screen(VaultDashboardModal())

        self.request_vault_passkey(
            reason="Unlocking Vault Management Console",
            callback=_on_authed,
        )

    def action_vault_password(self) -> None:
        """Opens modal to store an encrypted password in ~/.gemini/vault/passwords/."""
        def _on_authed(key: str | None) -> None:
            if key:
                self.push_screen(VaultPasswordEntryModal())

        self.request_vault_passkey(
            reason="Encrypting and storing new password",
            callback=_on_authed,
        )

    def action_vault_secret(self) -> None:
        """Opens modal to store an infinite-length encrypted secret in ~/.gemini/vault/secrets/."""
        def _on_authed(key: str | None) -> None:
            if key:
                self.push_screen(VaultSecretEntryModal())

        self.request_vault_passkey(
            reason="Encrypting and storing new secret string",
            callback=_on_authed,
        )

    def action_vault_file(self) -> None:
        """Opens modal to encrypt and store a file in ~/.gemini/vault/files/."""
        def _on_authed(key: str | None) -> None:
            if key:
                self.push_screen(VaultFileEntryModal())

        self.request_vault_passkey(
            reason="Encrypting and importing file into vault",
            callback=_on_authed,
        )

    def action_vault_change(self) -> None:
        """Opens passkey rotation modal with 2x confirmation."""
        self.push_screen(VaultChangePasskeyModal())

    def action_vault_lock(self) -> None:
        """Clears cached session passkey from RAM."""
        from gemini_app.vault import clear_session_passkey
        from gemini_app.fleet.keyring import FleetKeyring
        clear_session_passkey()
        FleetKeyring.lock()
        self.notify("Vault locked. Active session credentials cleared from RAM.", timeout=3.0)

    def action_vault_sync(self) -> None:
        """Unlocks vault and synchronizes fleet keys & node registry."""
        def _on_passkey(key: str | None) -> None:
            if not key:
                self.notify("Vault sync aborted: no passkey entered.", severity="warning")
                return
            try:
                from gemini_app.vault import set_session_passkey, sync_fleet_vault
                from gemini_app.fleet.keyring import FleetKeyring
                set_session_passkey(key)
                res = sync_fleet_vault(key)
                FleetKeyring.unlock(key)
                node_res = FleetKeyring.sync_nodes(key)
                active_cnt = node_res.get("active_nodes_count", 0)
                reg_cnt = node_res.get("total_registered", res.get("registered_nodes_count", 0))
                self.notify(
                    f"Fleet Keyring Unlocked: {reg_cnt} registered node(s) ({active_cnt} active).",
                    title="🔐 Vault Fleet Sync",
                    timeout=5.0,
                )
            except Exception as exc:
                self.notify(f"Vault sync failed: {exc}", severity="error")

        self.request_vault_passkey("Unlock Vault to Synchronize Fleet Cluster Keys & Nodes", _on_passkey)

    def _cmd_vault(self, arg: str) -> None:
        """Routes slash commands for /vault [password|file|secret|sync|change|lock]."""
        sub = arg.strip().lower()
        if not sub:
            self.action_vault_dashboard()
        elif sub in ("change", "rotate"):
            self.action_vault_change()
        elif sub in ("password", "pass"):
            self.action_vault_password()
        elif sub in ("file", "files"):
            self.action_vault_file()
        elif sub in ("secret", "sec", "key"):
            self.action_vault_secret()
        elif sub in ("sync", "nodes", "node-sync"):
            self.action_vault_sync()
        elif sub == "lock":
            self.action_vault_lock()
        else:
            self.notify(f"Unknown vault subcommand '{arg}'. Available: /vault [password|file|secret|sync|change|lock]", severity="warning")

    def _cmd_scaffold_project(self, arg: str) -> None:
        """Scaffolds a new project in ~/Projects with Git, README.md, and MIT LICENSE."""
        name = arg.strip()
        if not name:
            self.notify("Usage: /scaffold <project-name>", severity="warning")
            return
        res = scaffold_project(name, author=self.user_real_name)
        if res.get("status") == "success":
            self.notify(f"Scaffolded '{name}' at {res.get('project_path')}!", title="Project Created")
        else:
            self.notify(f"Scaffold error: {res.get('message')}", severity="error")

    def _cmd_sys_deps(self) -> None:
        """Checks and installs system dependencies autonomously based on Linux OS check."""
        res = ensure_system_dependencies()
        if res.get("all_installed"):
            self.notify(f"System dependencies verified for {res.get('os_info', {}).get('name', 'Linux')}.", title="Dependencies OK")
        else:
            self.notify(f"Installed packages: {res.get('installed_packages', [])}", title="Dependencies Installed")

    @work(exclusive=True, thread=True)
    def _cmd_backup_now(self) -> None:
        """Executes an immediate manual backup of ~/.gemini to the private GitHub repository."""
        self.app.call_from_thread(self.notify, "Backing up ~/.gemini state to GitHub...", title="Backup Started")
        res = perform_backup(force=True)
        status = res.get("status")
        if status == "success":
            msg = "State backup successfully synced to private GitHub repo."
            self.app.call_from_thread(self.notify, msg, title="Backup Complete")
        elif status == "awaiting_remote_repo":
            msg = "Remote backup repo not configured or not reachable on GitHub yet."
            self.app.call_from_thread(self.notify, msg, severity="warning", title="Awaiting Remote Repo")
        else:
            err = res.get("error", "Unknown error")
            self.app.call_from_thread(self.notify, f"Backup error: {err}", severity="error", title="Backup Failed")

    @work(exclusive=True)
    async def _cmd_qr(self, arg: str) -> None:
        """Renders an ASCII/Unicode QR code directly into the chat feed."""
        from uuid import uuid4
        from gemini_app.fleet.nodes import get_local_lan_ip
        from gemini_app.helpers import generate_terminal_qr
        from gemini_app.ui.widgets.feed import FeedArea

        target = arg.strip()
        if not target:
            lan_ip = get_local_lan_ip()
            target = f"http://{lan_ip}:8888"

        qr_text = generate_terminal_qr(target)
        msg = f"### 📱 Terminal QR Code\n\n```text\n{qr_text}\n```\n**Payload:** `{target}`\n\n*Point your mobile camera at your screen to scan.*"

        try:
            feed = self.query_one("#feed", FeedArea)
            await feed.append_message("gemini", msg, jump_to_start=True)
            new_turn_id = f"turn_{uuid4().hex[:8]}"
            self.history.append({"turn_id": new_turn_id, "role": "model", "text": msg})
            self.current_chat_last_index = max(0, len(self.history) - 1)
            self.current_chat_center_marker = new_turn_id
            self.save_current_chat()
            self.notify(f"Rendered QR code for '{target}'", title="QR Code Ready")
        except Exception as exc:
            self.notify(f"QR render notice: {exc}", severity="warning")

    @work(exclusive=False, thread=True)
    def _check_daily_backup(self) -> None:
        """Checks if 24 hours have elapsed since the last backup and runs it in the background."""
        res = check_and_run_daily_backup(force=False)
        if res and res.get("status") == "success":
            self.app.call_from_thread(self.notify, "Daily state backup synced to GitHub.", title="Daily Backup")

    def consume_notes_editor(self) -> None:
        """Consumes text typed into the notes editor by the user into Gemini-managed notes."""
        if getattr(self, "_consuming_notes", False):
            return
        self._consuming_notes = True
        try:
            editor = self.query_one("#notes_editor", NotesEditorArea)
            raw_text = editor.text
            if not raw_text.strip():
                return
            # If editor text matches initial rendered template, nothing new was typed by the user
            if getattr(editor, "_initial_rendered_text", "") and raw_text.strip() == editor._initial_rendered_text.strip():
                return
            curr_topic = getattr(self, "active_task_title", "") or self.notes_manager.active_topic
            added = self.notes_manager.consume_user_input(
                raw_text=raw_text,
                active_topic=curr_topic,
                turn_id=getattr(self, "current_focused_turn_id", ""),
            )
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.schedule_notes_flush()
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.refresh_display()
            if added:
                topics_str = ", ".join(set(n.topic for n in added))
                self.notify(f"✓ Note consumed & indexed under topic: '{topics_str}'", timeout=3.5)
            else:
                self.notify("✓ Working notes updated.", timeout=2.0)
        except Exception as e:
            self.notify(f"Error consuming note: {e}", severity="error")
        finally:
            self._consuming_notes = False

    def schedule_notes_flush(self) -> None:
        if self._notes_flush_timer:
            self._notes_flush_timer.stop()
        self._notes_flush_timer = self.set_timer(0.3, self._do_notes_flush)

    def _do_notes_flush(self) -> None:
        self._notes_flush_timer = None
        if self.current_chat_id:
            notes_payload = self.notes_manager.to_dict() if hasattr(self, "notes_manager") else {
                "gemini_notes": self.gemini_notes or "",
                "global_notes": self.global_notes or "",
                "relational_notes": self.relational_notes or {},
            }
            self._direct_flush_chat_to_disk(self.current_chat_id, notes_payload)
        self._save_to_state("global_notes", self.global_notes or "")

    def schedule_chat_notes_flush(self) -> None:
        self.schedule_notes_flush()

    def schedule_global_notes_flush(self) -> None:
        self.schedule_notes_flush()

    def clear_toasts(self) -> None:
        try:
            seen_toasts = set()
            stack = getattr(self, "screen_stack", None) or getattr(self, "_screen_stack", [])
            for screen in list(stack):
                if hasattr(screen, "query"):
                    for toast in list(screen.query("Toast")):
                        if toast not in seen_toasts:
                            seen_toasts.add(toast)
                            try:
                                toast.dismiss()
                            except Exception:
                                pass
        except Exception:
            pass

    def push_screen(self, screen: Screen[ModalResultType] | str, callback: Callable[[ModalResultType], None] | None = None, wait_for_dismiss: bool = False):
        self.clear_toasts()
        if hasattr(screen, "add_class") and hasattr(self, "active_palette_name"):
            for t in THEMES:
                screen.remove_class(f"theme-{t}")
            screen.add_class(f"theme-{self.active_palette_name}")
        return super().push_screen(screen, callback=callback, wait_for_dismiss=wait_for_dismiss)

    @property
    def accent_color(self) -> str:
        return THEMES.get(self.active_palette_name, THEMES[DEFAULT_PALETTE])["accent"]

    def set_theme(self, palette_name: str, notify_user: bool = True, save_state: bool = True) -> bool:
        theme_clean = palette_name.strip().lower()
        if theme_clean not in THEMES:
            return False

        self.active_palette_name = theme_clean
        if save_state:
            self._save_to_state("ui_theme", theme_clean)

        stack = getattr(self, "screen_stack", None) or getattr(self, "_screen_stack", [])
        for sc in list(stack):
            for t in THEMES:
                sc.remove_class(f"theme-{t}")
            sc.add_class(f"theme-{theme_clean}")

        self.update_feed_nav_banner()
        self._update_footer_markup()

        if getattr(self, "cognitive_adapter", None):
            try:
                self.cognitive_adapter.set_theme(theme_clean)
            except Exception:
                pass

        if notify_user:
            self.notify(f"Theme set to '{theme_clean}'", timeout=2.5)
        return True

    def _read_theme_from_state(self) -> str:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                stored = data.get("ui_theme")
                if stored in THEMES:
                    return stored
            except Exception:
                pass
        return DEFAULT_PALETTE

    def _read_global_notes_from_state(self) -> str:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                return data.get("global_notes", "") or ""
            except Exception:
                pass
        return ""

    def _save_to_state(self, key: str, value: str) -> None:
        try:
            state: dict = {}
            if STATE_FILE.exists():
                try:
                    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
            state[key] = value
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            STATE_FILE.chmod(0o600)
        except Exception:
            pass

    def _flush_global_notes_to_state(self) -> None:
        self.flush_current_notes()
        self._save_to_state("global_notes", self.global_notes or "")

    def _update_footer_markup(self) -> None:
        try:
            c = self.accent_color
            self.query_one("#footer_quit", Static).update(f"[bold {c}]^q:[/] [white]quit[/]")
            self.query_one("#footer_sep", Static).update(f"[{c}]|[/]")
            self.query_one("#footer_commands", Static).update(f"[bold {c}]^c + c:[/] [white]commands[/]")
        except Exception:
            pass

    def is_history_open(self) -> bool:
        return False

    def flush_current_notes(self, consume_input: bool = False) -> None:
        if consume_input:
            self.consume_notes_editor()
            return
        try:
            editors = list(self.query("#notes_editor"))
            if editors and editors[0].has_focus:
                text_val = editors[0].text
                # Only sync working notes if editor is currently in working filter, and sanitize it!
                if getattr(self, "active_notes_mode", "working") in ("working", "gemini"):
                    clean_w = sanitize_working_notes(text_val)
                    if clean_w:
                        self.gemini_notes = clean_w
                        if hasattr(self, "notes_manager"):
                            self.notes_manager.working_notes = clean_w
        except Exception:
            pass

    def on_feed_turn_focused(self, turn_idx: int, turn_id: str, sender: str = "") -> None:
        self.current_focused_turn_index = turn_idx
        self.current_focused_turn_id = turn_id
        try:
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.on_turn_changed(turn_idx, turn_id, sender)
        except Exception:
            pass

    def execute_command(self, raw_input: str) -> bool:
        cmd_text = raw_input.strip()
        if not cmd_text.startswith("!/"):
            return False

        body = cmd_text[2:].strip()
        if not body:
            self.notify("Empty command specified.", severity="error")
            return True

        if ":" in body:
            program, arg = body.split(":", 1)
            program = program.strip().lower()
            arg = arg.strip()
        else:
            program = body.lower()
            arg = ""

        handler = self._commands_registry.get(program)
        if handler:
            handler(arg)
        else:
            valid_cmds = ", ".join(self._commands_registry.keys())
            self.notify(f"Unknown command '{program}'. Available: {valid_cmds}", severity="error")

        return True

    def _cmd_ui_theme(self, arg: str) -> None:
        if not arg:
            valid_themes = ", ".join(THEMES.keys())
            self.notify(f"Usage: !/ui-theme:<color>. Options: {valid_themes}", severity="warning")
            return

        success = self.set_theme(arg)
        if not success:
            valid_themes = ", ".join(THEMES.keys())
            self.notify(f"Invalid theme '{arg}'. Choose from: {valid_themes}", severity="error")

    def trigger_nav_indicator(
        self,
        action: str,
        toast_message: str = "",
        palette: str = "",
        duration: float = 0.35,
    ) -> None:
        self._nav_indicator_action = action
        self._nav_indicator_palette = palette or None

        pal_key = palette or getattr(self, "active_palette_name", DEFAULT_PALETTE)
        if action in ("navbar", "nav", "flash", "pulse"):
            try:
                banner = self.query_one("#feed_nav_banner", Static)
                for p in THEMES:
                    banner.remove_class(f"flash-{p}")
                banner.add_class(f"flash-{pal_key}")
                banner.add_class("nav-pulse")
            except Exception:
                pass

        self.update_feed_nav_banner()

        if toast_message and not getattr(self, "_suppress_ambient_toasts", False):
            accent = (
                THEMES.get(palette, {}).get("accent", self.accent_color)
                if palette
                else self.accent_color
            )
            self.notify(f"[{accent}]{toast_message}[/]", timeout=max(1.5, duration))

        if self._nav_indicator_timer:
            self._nav_indicator_timer.stop()

        self._nav_indicator_timer = self.set_timer(duration, self._clear_nav_indicator)

    def _clear_nav_indicator(self) -> None:
        self._nav_indicator_action = None
        self._nav_indicator_palette = None
        self._nav_indicator_timer = None
        try:
            banner = self.query_one("#feed_nav_banner", Static)
            for p in THEMES:
                banner.remove_class(f"flash-{p}")
            banner.remove_class("nav-pulse")
            banner.styles.background = "#141414"
            banner.styles.color = "#ffffff"
            banner.refresh()
        except Exception:
            pass
        self.update_feed_nav_banner()

    def pulse_theme(self, palette_name: str, duration: float = 2.0) -> None:
        """Temporarily pulses the whole console theme without overwriting state.json."""
        pal_clean = palette_name.strip().lower()
        if pal_clean not in THEMES:
            return

        current_theme = getattr(self, "active_palette_name", DEFAULT_PALETTE)
        stack = getattr(self, "screen_stack", None) or getattr(self, "_screen_stack", [])
        for sc in list(stack):
            for t in THEMES:
                sc.remove_class(f"theme-{t}")
            sc.add_class(f"theme-{pal_clean}")

        self.update_feed_nav_banner()
        self._update_footer_markup()

        def _revert():
            for sc in list(stack):
                for t in THEMES:
                    sc.remove_class(f"theme-{t}")
                sc.add_class(f"theme-{current_theme}")
            self.update_feed_nav_banner()
            self._update_footer_markup()

        self.set_timer(max(0.5, duration), _revert)

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None
        self._prefix_c_c = True
        self._c_c_timer = self.set_timer(3.5, self._expire_c_c_prefix)

    def _expire_c_c_prefix(self) -> None:
        self._prefix_c_c = False
        self._c_c_timer = None

    def intercept_c_c_key(self, event: events.Key) -> bool:
        if event.key == "ctrl+c":
            if self._prefix_c_c:
                event.prevent_default()
                event.stop()
                self.handle_c_c_prefix(event)
                return True
            event.prevent_default()
            event.stop()
            self.set_c_c_prefix()
            return True

        if self._prefix_c_c:
            event.prevent_default()
            event.stop()
            self.handle_c_c_prefix(event)
            return True

        return False

    def handle_c_c_prefix(self, event: events.Key) -> bool:
        if not self._prefix_c_c:
            return False

        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None

        self._prefix_c_c = False
        self.clear_toasts()

        key = event.key.lower()
        char = (event.character or "").lower()

        if key in ("ctrl+g", "escape"):
            return True

        if key in ("ctrl+c", "c") or char == "c":
            self.action_open_commands_modal()
            return True
        elif key in ("ctrl+m", "m") or char == "m":
            self.action_open_mind_map()
            return True
        elif key in ("bracketleft", "left_bracket", "bracket_left", "[") or char == "[":
            self.action_toggle_notes()
            return True
        elif key in ("ctrl+e", "e") or char == "e":
            self.action_send_to_emacs()
            return True
        elif key in ("ctrl+w", "w") or char == "w":
            self.action_copy_active_snippet()
            return True
        elif key in ("ctrl+y", "y") or char == "y":
            self.action_yank_to_input()
            return True
        elif key in ("ctrl+t", "t") or char == "t":
            def on_title_entered(new_title: str | None) -> None:
                if new_title and new_title.strip():
                    self.set_feed_title(new_title.strip())
                    self.notify(f"Feed active task title updated to: {new_title.strip()}")
            self.push_screen(
                TitlePromptModal(
                    prompt="Set active work / feed section title:",
                    default_title=getattr(self, "active_task_title", "") or self.current_gemini_state,
                ),
                callback=on_title_entered,
            )
            return True
        elif key in ("ctrl+r", "r") or char == "r":
            self.action_save_snippet_to_disk()
            return True
        elif key in ("ctrl+f", "f") or char == "f":
            self.action_insert_file_from_disk()
            return True
        elif key in ("ctrl+g", "g") or char == "g":
            self.action_open_git_tree()
            return True
        elif key in ("ctrl+k", "k") or char == "k":
            self.action_emergency_interrupt()
            return True
        elif key in ("ctrl+l", "l") or char == "l":
            self.action_repaint_screen()
            return True
        # for later exploration by gemini
        # elif key in ("period", "full_stop", ".") or char == ".":
        #     self.action_fork_chat()
        #     return True
        elif key in ("grave", "backtick", "`") or char == "`":
            self.action_take_snapshot(label="", taken_by="user", source="shortcut")
            return True

        self.notify(f"C-c {key} is undefined", timeout=2.0)
        return False

    def action_c_c_prefix_stub(self) -> None:
        self.set_c_c_prefix()

    def action_open_commands_modal(self) -> None:
        self.push_screen(CommandsModal())

    def action_open_mind_map(self) -> None:
        self.trigger_nav_indicator("mind")
        if isinstance(self.screen, MindMapScreen):
            self.pop_screen()
            return

        if self.notes_open:
            self.action_toggle_notes()

        try:
            preview = self.query_one("#snippet_preview", SnippetPreview)
            preview.hide_preview()
        except Exception:
            pass

        try:
            input_box = self.query_one("#input", ExpandingInput)
            self.saved_prompt_draft = input_box.text
            input_box.clear()
        except Exception:
            self.saved_prompt_draft = ""

        def on_mind_map_closed(_) -> None:
            try:
                inp = self.query_one("#input", ExpandingInput)
                if self.saved_prompt_draft:
                    inp.text = self.saved_prompt_draft
                    inp.move_cursor(inp.document.end, select=False)
                    self.saved_prompt_draft = ""
                inp.focus()
            except Exception:
                pass

        self.push_screen(MindMapScreen(), callback=on_mind_map_closed)

    def action_take_snapshot(
        self, label: str = "", taken_by: str = "user", source: str = "shortcut"
    ) -> dict[str, Any]:
        """Captures, indexes, and holds a UI snapshot for bilateral communication."""
        try:
            entry = capture_ui_snapshot(self, label=label, taken_by=taken_by, source=source)
            idx = entry.get("index", 1)
            snap_id = entry.get("id", "")
            lbl_info = f" ('{label}')" if label else ""
            policy_info = " [saved permanently]" if entry.get("persistent") else " [ephemeral, deleted upon review]"
            self.notify(f"Snapshot #{idx}{lbl_info} captured & held{policy_info}! [{snap_id}]", timeout=4.0)
            return entry
        except Exception as e:
            self.notify(f"Snapshot error: {e}", severity="error")
            return {"status": "error", "message": str(e)}

    def action_take_svg_screenshot(self) -> None:
        self.action_take_snapshot(label="", taken_by="user", source="shortcut")

    def _render_flow_nav_banner(self, items: list[str], sep_markup: str, sep_plain: str, available_w: int) -> str:
        lines: list[str] = []

        def clean_markup(s: str) -> str:
            return re.sub(r"\[[^\]]*\]", "", s)

        sep_cells = cell_len(sep_plain)
        curr_line_markup: list[str] = []
        curr_len = 0

        for item in items:
            item_plain = clean_markup(item)
            item_cells = cell_len(item_plain)

            is_start_of_line = (curr_len == 0)

            if is_start_of_line:
                needed = item_cells
            else:
                needed = sep_cells + 2 + item_cells

            if curr_len + needed <= available_w:
                if is_start_of_line:
                    curr_line_markup.append(item)
                    curr_len = item_cells
                else:
                    curr_line_markup.append(f"{sep_markup} {item}")
                    curr_len += sep_cells + 2 + item_cells
            else:
                if not is_start_of_line:
                    lines.append(" ".join(curr_line_markup))
                    curr_line_markup = [item]
                    curr_len = item_cells
                else:
                    curr_line_markup.append(item)
                    lines.append(" ".join(curr_line_markup))
                    curr_line_markup = []
                    curr_len = 0

        if curr_line_markup:
            lines.append(" ".join(curr_line_markup))

        return "\n".join(lines)

    def update_feed_nav_banner(self) -> None:
        try:
            banner = self.query_one("#feed_nav_banner", Static)
            feed = self.query_one("#feed", FeedArea)

            avail_w = self.size.width - 2 if self.size and self.size.width > 2 else 78
            base_accent = self.accent_color
            pal_name = getattr(self, "_nav_indicator_palette", None) or ""
            indicator_accent = (
                THEMES.get(pal_name, {}).get("accent", base_accent)
                if pal_name
                else base_accent
            )

            if getattr(self, "_nav_indicator_action", None) in ("navbar", "nav", "flash", "pulse"):
                banner.remove_class("fork-active")
                banner.styles.background = indicator_accent
                banner.styles.color = "#000000"
                sep_markup = "[bold #000000]|[/]"
                sep_plain = "|"
                items = [
                    "[bold #000000]↑/↓: Scroll[/]",
                    "[bold #000000]Shift+↑/↓: Viewport[/]",
                    "[bold #000000]PgUp/PgDn: Cards[/]",
                    "[bold #000000]Home/End: Edge[/]",
                    "[bold #000000]M-n/M-p: Snippets[/]",
                    "[bold #000000]C-c m: Mind[/]",
                ]
                content = self._render_flow_nav_banner(items, sep_markup, sep_plain, avail_w)
            else:
                banner.remove_class("fork-active")
                banner.styles.background = "#141414"
                banner.styles.color = "#ffffff"
                sep_markup = f"[not bold {base_accent}]|[/]"
                sep_plain = "|"

                up_scroll = f"[bold {indicator_accent}]↑[/]" if self._nav_indicator_action == "scroll_up" else "↑"
                dn_scroll = f"[bold {indicator_accent}]↓[/]" if self._nav_indicator_action == "scroll_down" else "↓"
                up_page = f"[bold {indicator_accent}]↑[/]" if self._nav_indicator_action == "page_up" else "↑"
                dn_page = f"[bold {indicator_accent}]↓[/]" if self._nav_indicator_action == "page_down" else "↓"

                if self._nav_indicator_action == "edge_home":
                    edge_item = f"[bold {indicator_accent} reverse] Home [/]/End: Edge"
                elif self._nav_indicator_action == "edge_end":
                    edge_item = f"Home/[bold {indicator_accent} reverse] End [/]: Edge"
                elif self._nav_indicator_action in ("edge", "edge_all"):
                    edge_item = f"[bold {indicator_accent} reverse] Home/End: Edge [/]"
                else:
                    edge_item = "Home/End: Edge"

                cards_item = (
                    f"[bold {indicator_accent} reverse] PgUp/PgDn: Cards [/]"
                    if self._nav_indicator_action == "cards"
                    else "PgUp/PgDn: Cards"
                )
                snippets_item = (
                    f"[bold {indicator_accent} reverse] M-n/M-p: Snippets [/]"
                    if self._nav_indicator_action == "snippets"
                    else "M-n/M-p: Snippets"
                )
                mind_item = (
                    f"[bold {indicator_accent} reverse] C-c m: Mind [/]"
                    if self._nav_indicator_action == "mind"
                    else "C-c m: Mind"
                )

                items = [
                    f"{up_scroll}/{dn_scroll}: Scroll",
                    f"Shift+{up_page}/{dn_page}: Viewport",
                    cards_item,
                    edge_item,
                    snippets_item,
                    mind_item,
                ]
                content = self._render_flow_nav_banner(items, sep_markup, sep_plain, avail_w)

            banner.update(content)
            banner.refresh()
        except Exception:
            pass

    def on_resize(self, event: events.Resize) -> None:
        is_mobile = event.size.width <= MOBILE_BREAKPOINT
        if self.screen:
            self.screen.set_class(is_mobile, "-mobile")
        self.call_after_refresh(self.update_feed_nav_banner)

    def on_app_focus(self) -> None:
        try:
            target = self.query_one(f"#{self._last_focused_input_id}")
            if target and target.is_mounted and target.can_focus:
                target.focus()
        except Exception:
            pass

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        w = event.widget
        wid = getattr(w, "id", None)
        if wid in ("input", "snippet_preview"):
            self._last_non_notes_input_id = wid
        if wid in ("input", "snippet_preview", "notes_input"):
            self._last_focused_input_id = wid

    def on_key(self, event: events.Key) -> None:
        key_name = event.key.lower()

        if self.lock.is_locked:
            if key_name in GATED_NAV_KEYS:
                event.prevent_default()
                event.stop()
                return

        if self.intercept_c_c_key(event):
            return

    def set_feed_title(self, title: str) -> None:
        """Sets the active work title displayed on the feed border."""
        clean = title.strip().replace("\n", " ")
        if len(clean) > 70:
            clean = clean[:67] + "..."
        self.active_task_title = clean
        self.current_gemini_state = clean
        self.update_feed_title()
        try:
            from gemini_app.fleet.telemetry import update_cognitive_state
            active_topic = getattr(self.notes_manager, "active_topic", "general") if hasattr(self, "notes_manager") else "general"
            update_cognitive_state(task=clean, topic=active_topic)
        except Exception:
            pass

    def update_feed_title(self) -> None:
        """Dynamically updates the feed border title based on current work Gemini is doing."""
        try:
            feed = self.query_one("#feed", FeedArea)
            active_topic = getattr(self.notes_manager, "active_topic", "general") if hasattr(self, "notes_manager") else "general"
            work_desc = (getattr(self, "active_task_title", "") or self.current_gemini_state or "").strip()
            if not work_desc or "unifying notes" in work_desc.lower() or work_desc in ("Legacy active session.", "None"):
                clean_work = f"Topic: {active_topic}"
            else:
                clean_work = work_desc.replace("\n", " ").strip()
                if not clean_work.lower().startswith("topic:"):
                    clean_work = f"Topic: {active_topic} • {clean_work}"
            if len(clean_work) > 65:
                clean_work = clean_work[:62] + "..."
            feed.border_title = f" ⚡ {clean_work} "
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            yield Static("▲ Loading messages...", id="feed_loader_banner")
            with Horizontal(id="middle_split"):
                yield FeedArea(id="feed")
                yield NotesPanel()
            yield Static("", id="feed_status")
            yield Static("", id="runner_status")
            yield Static("", id="feed_nav_banner")
            yield SnippetPreview(id="snippet_preview")
            yield ExpandingInput(id="input")
        with Horizontal(id="custom_footer"):
            yield Static("[bold red]^q:[/] [white]quit[/]", id="footer_quit")
            yield Static("[red]|[/]", id="footer_sep")
            yield Static("[bold red]^c + c:[/] [white]commands[/]", id="footer_commands")

    @on(events.Click, "#footer_quit")
    def on_footer_quit_click(self) -> None:
        self.action_quit()

    @on(events.Click, "#footer_commands")
    def on_footer_commands_click(self) -> None:
        self.action_open_commands_modal()

    async def on_mount(self) -> None:
        cleanup_stale_ephemerals()
        prune_audit_snapshots(max_reboot_audits=1)
        cleanup_test_snapshots()
        saved_theme = self._read_theme_from_state()
        self.set_theme(saved_theme, notify_user=False)

        self.global_notes = self._read_global_notes_from_state()

        if self.size and self.size.width <= MOBILE_BREAKPOINT and self.screen:
            self.screen.add_class("-mobile")

        self._start_heartbeat_watchdog()
        await self.start_socket_server()
        self._start_wingman_server()

        def _on_boot_dismissed(result: Any = None) -> None:
            self._boot_complete = True
            if "unittest" not in sys.modules and not os.environ.get("GEMINI_TEST_MODE"):
                self.set_interval(1.5, self._check_pending_wingman_auth)
            self._process_next_wingman_auth()

        self._boot_complete = False
        self.push_screen(BootScreen(), _on_boot_dismissed)
        # Check daily backup interval every hour
        self.set_interval(3600.0, self._check_daily_backup)
        # Periodically reconcile background runner status
        self.set_interval(5.0, self._restore_active_background_task)
        self.call_after_refresh(self._initial_startup_load)

    async def _initial_startup_load(self) -> None:
        mark_startup_successful()
        last_active_id = self._read_active_chat_from_state()

        if last_active_id and (self._get_legacy_chat_file(last_active_id).exists() or self._get_chat_dir(last_active_id).exists()):
            # Read prior session meta & mind map to boot directly into our cognitive anchors
            legacy_file = self._get_legacy_chat_file(last_active_id)
            chat_dir = self._get_chat_dir(last_active_id)
            prev_meta = {}
            if legacy_file.exists():
                try:
                    prev_meta = json.loads(legacy_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            elif chat_dir.is_dir() and (chat_dir / "meta.json").exists():
                try:
                    prev_meta = json.loads((chat_dir / "meta.json").read_text(encoding="utf-8"))
                except Exception:
                    pass

            notes_raw = prev_meta.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.global_notes = ""
            self.relational_notes = {}
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)

            mind_map = prev_meta.get("mind_map", {})
            if mind_map:
                self.current_gemini_state = mind_map.get("gemini_state") or self.current_gemini_state
                self.current_user_state = mind_map.get("user_state") or self.current_user_state
                self.current_tree_state = mind_map.get("tree_state") or self.current_tree_state
                self.current_tree_content = mind_map.get("tree_content") or self.current_tree_content
                self.active_task_title = prev_meta.get("title") or self.current_gemini_state

            # Start fresh chat session for this boot while tracking lineage
            self._start_new_chat(title="", parent_id=last_active_id)
        else:
            files = self._get_all_chat_entries()
            if files:
                first_id = files[0]["id"]
                self._start_new_chat(title="", parent_id=first_id)
            else:
                self._start_new_chat(title="")

        self.update_feed_nav_banner()
        self.update_feed_title()
        self._update_footer_markup()
        self.query_one("#input").focus()

        # Background index all historical chats into SQLite FTS5 Memory Index
        asyncio.create_task(asyncio.to_thread(self.memory_index.index_all_existing_chats))

        # Background check 24-hr state backup and ensure systemd user timer
        asyncio.create_task(asyncio.to_thread(self._check_daily_backup))
        asyncio.create_task(asyncio.to_thread(install_systemd_backup_timer))

        # Release any pre-reboot Wingman maintenance lockout
        try:
            from gemini_app.fleet.nodes import send_mothership_command
            send_mothership_command("set_wingman_maintenance", {"active": False}, timeout=1.0)
        except Exception:
            pass
        if getattr(self, "wingman_applet", None):
            try:
                self.wingman_applet.set_maintenance_mode(False)
            except Exception:
                pass

        reboot_report = self._read_and_clear_reboot_report()
        if reboot_report:
            # Post post-reboot message directly into the chat feed
            try:
                feed = self.query_one("#feed", FeedArea)
                await feed.append_message("gemini", reboot_report, jump_to_start=True)
                new_turn_id = f"turn_{uuid4().hex[:8]}"
                self.history.append({"turn_id": new_turn_id, "role": "model", "text": reboot_report})
                self.current_chat_last_index = max(0, len(self.history) - 1)
                self.current_chat_center_marker = new_turn_id
                self.save_current_chat()
            except Exception:
                pass

            snap_idx = 1
            try:
                snap_entry = capture_ui_snapshot(
                    self,
                    label="post_reboot_audit",
                    taken_by="gemini",
                    source="command",
                    persistent=True,
                )
                snap_idx = snap_entry.get("index", 1)
            except Exception:
                pass

            def _post_boot_notify(idx=snap_idx, rep=reboot_report):
                self.notify(
                    f"📸 Snapshot #{idx} captured: Post-reboot visual layout audited.",
                    title="Visual Audit",
                    timeout=4.0,
                )
                self.set_timer(0.4, lambda: self.notify(rep, title="Update Notes", timeout=8.0))

            self.set_timer(0.3, _post_boot_notify)

        try:
            from gemini_app.fleet.telemetry import update_cognitive_state
            update_cognitive_state(
                state_desc="Bilateral Console Online",
                task=self.current_user_state or "Awaiting instruction",
                thought="Connected and monitoring bilateral telemetry stream.",
                tool="idle",
                turn_number=self.total_conversation_turns,
                topic=getattr(self, "current_topic", "general"),
            )
        except Exception:
            pass

        self._restore_active_background_task()

    def _restore_active_background_task(self) -> None:
        if not ACTIVE_TASK_FILE.exists():
            return
        try:
            data = json.loads(ACTIVE_TASK_FILE.read_text(encoding="utf-8"))
            pid = data.get("pid")
            text = data.get("text")
            is_running = False
            if pid:
                try:
                    os.kill(pid, 0)
                    is_running = True
                except (OSError, ProcessLookupError):
                    is_running = False

            if is_running and text:
                self._background_task_status = text
                self.set_runner_status_text(text)
            else:
                ACTIVE_TASK_FILE.unlink(missing_ok=True)
                self.hide_runner_status()
        except Exception:
            pass

    def show_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            banner.update("▲ Loading messages...")
            banner.styles.display = "block"
            banner.refresh(layout=True)
        except Exception:
            pass

    def hide_loader_banner(self) -> None:
        try:
            banner = self.query_one("#feed_loader_banner", Static)
            banner.styles.display = "none"
        except Exception:
            pass

    def set_status_text(self, text: str) -> None:
        try:
            status_lbl = self.query_one("#feed_status", Static)
            status_lbl.update(text)
            status_lbl.styles.display = "block"
        except Exception:
            pass

    def hide_status(self, force: bool = False) -> None:
        try:
            status_lbl = self.query_one("#feed_status", Static)
            status_lbl.update("")
            status_lbl.styles.display = "none"
        except Exception:
            pass

    def set_runner_status_text(self, text: str) -> None:
        try:
            status_lbl = self.query_one("#runner_status", Static)
            status_lbl.update(text)
            status_lbl.styles.display = "block"
        except Exception:
            pass

    def hide_runner_status(self) -> None:
        try:
            status_lbl = self.query_one("#runner_status", Static)
            status_lbl.update("")
            status_lbl.styles.display = "none"
        except Exception:
            pass

    def _start_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
        if getattr(self, "cognitive_adapter", None):
            self.cognitive_adapter.set_streaming(True)
        self._request_start_time = time.monotonic()
        self._spinner_idx = 0
        self._tick_status()
        self._status_timer = self.set_interval(0.1, self._tick_status)

    def _stop_status_ticker(self) -> None:
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None
        if getattr(self, "cognitive_adapter", None):
            self.cognitive_adapter.set_streaming(False)
        self._request_phase = "idle"
        self._request_details = ""
        self._reconnect_target_time = 0.0
        self._reconnect_attempt = 0
        self._reconnect_max_retries = 0
        self.hide_status()

    def _tick_status(self) -> None:
        self._last_heartbeat_time = time.monotonic()
        if self._request_phase == "idle":
            return

        elapsed = time.monotonic() - self._request_start_time
        frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
        self._spinner_idx += 1

        if self._request_phase == "reconnecting":
            if self._reconnect_target_time > 0:
                rem_sec = max(0.0, self._reconnect_target_time - time.monotonic())
                if rem_sec > 0.05:
                    rem_str = format_reconnect_countdown(rem_sec)
                    status_text = f"{frame} Quota reached — reconnecting silently in {rem_str} (retry {self._reconnect_attempt}/{self._reconnect_max_retries})"
                else:
                    status_text = f"{frame} Quota reached — reconnecting now (retry {self._reconnect_attempt}/{self._reconnect_max_retries})..."
            elif self._request_details:
                status_text = f"{frame} {self._request_details}"
            else:
                status_text = f"{frame} Quota limit reached — reconnecting silently..."
        elif self._request_details:
            status_text = f"{frame} {self._request_details}... ({elapsed:.1f}s)"
        elif self._request_phase == "connecting":
            status_text = f"{frame} Connecting / Sending request... ({elapsed:.1f}s)"
        elif self._request_phase == "waiting":
            status_text = f"{frame} Waiting on Gemini response... ({elapsed:.1f}s)"
        elif self._request_phase == "probing":
            status_text = f"{frame} AI Mind Expanding (Seeking context & tools)... ({elapsed:.1f}s)"
        else:
            status_text = f"{frame} Working... ({elapsed:.1f}s)"

        self.set_status_text(status_text)

    @on(RequestPhaseUpdate)
    def on_request_phase_update(self, event: RequestPhaseUpdate) -> None:
        self._request_phase = event.phase
        self._request_details = getattr(event, "details", "") or ""
        self._tick_status()
        try:
            from gemini_app.fleet.telemetry import update_cognitive_state
            tool_name = "none"
            if "Running " in self._request_details:
                tool_name = self._request_details.split("Running ", 1)[1].strip().split()[0]
            elif self._request_phase in ("probing", "executing", "patching", "writing", "searching"):
                tool_name = self._request_phase
            update_cognitive_state(
                thought=self._request_details or f"Phase: {self._request_phase}",
                tool=tool_name,
            )
        except Exception:
            pass

    @on(MindMapRecalibrated)
    def on_mind_map_recalibrated(self, event: MindMapRecalibrated) -> None:
        self.current_gemini_state = event.gemini_state
        self.active_task_title = event.gemini_state
        self.current_user_state = event.user_state
        self.current_tree_content = event.tree_content
        self.current_tree_state = event.tree_state
        self.save_current_chat()
        self.update_feed_title()

        try:
            from gemini_app.fleet.telemetry import update_cognitive_state
            active_topic = getattr(self.notes_manager, "active_topic", "general") if hasattr(self, "notes_manager") else "general"
            update_cognitive_state(
                state_desc=event.gemini_state,
                task=event.user_state or event.gemini_state,
                thought="Mind map synchronized.",
                tool="none",
                topic=active_topic,
            )
        except Exception:
            pass

        try:
            self.memory_index.save_mind_map(
                chat_id=self.current_chat_id,
                gemini_state=event.gemini_state,
                user_state=event.user_state,
                tree_state=event.tree_state,
                tree_content=event.tree_content,
                active_task_title=getattr(self, "active_task_title", ""),
            )
        except Exception:
            pass

        # Update MindMapScreen if it is anywhere in the screen stack
        for sc in self.screen_stack:
            if isinstance(sc, MindMapScreen):
                sc.refresh_display()

    @on(RequestFinished)
    async def on_request_finished(self, event: RequestFinished) -> None:
        self._stop_status_ticker()

        full_text = (event.full_text or "").strip()
        if not full_text:
            full_text = "✓ Action completed."

        feed = self.query_one("#feed", FeedArea)
        await feed.append_message("gemini", full_text, jump_to_start=True)

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        self.history.append({"turn_id": new_turn_id, "role": "model", "text": full_text, "timestamp": time.time()})
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id
        self.save_current_chat()

        # Push Gemini response to local Wingman portal and fleet satellites
        turn_msg_id = f"msg-turn-{new_turn_id}"
        if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
            try:
                self.wingman_applet.push_chat_message(
                    sender="Gemini Core",
                    text=full_text,
                    is_user=False,
                    msg_id=turn_msg_id,
                )
            except Exception:
                pass
        try:
            from gemini_app.fleet.nodes import send_mothership_command
            send_mothership_command("broadcast_wingman_chat", {
                "sender": "Gemini Core",
                "text": full_text,
                "is_user": False,
                "id": turn_msg_id,
            }, timeout=2.0)
        except Exception:
            pass

        self.set_status_text(f"✓ Response complete ({event.words} words in {event.elapsed:.1f}s)")
        self.set_timer(1.2, self.hide_status)

        self.query_one("#input", ExpandingInput).focus()
        self.refresh(layout=True)

    @on(RequestFailed)
    def on_request_failed(self, event: RequestFailed) -> None:
        self._stop_status_ticker()
        self.set_status_text(f"✗ Error: {event.error_message}")
        self.notify(f"API Error: {event.error_message}", severity="error")
        self.set_timer(5.0, self.hide_status)
        self.query_one("#input", ExpandingInput).focus()
        self.refresh(layout=True)

    def _read_active_chat_from_state(self) -> str | None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                return data.get("active_chat")
            except Exception:
                pass
        return None

    def get_effective_working_dir(self) -> str:
        if self.current_chat_working_dir:
            return self.current_chat_working_dir
        return os.getcwd()

    def set_working_dir(self, directory: str) -> None:
        expanded = os.path.expanduser(directory.strip())
        self.current_chat_working_dir = expanded
        self.save_current_chat()

    async def start_socket_server(self) -> None:
        if "unittest" in sys.modules or os.environ.get("GEMINI_TEST_MODE"):
            return

        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_socket_client,
                path=str(SOCKET_PATH),
            )
            SOCKET_PATH.chmod(0o600)
        except Exception as e:
            self.notify(f"Socket server error: {e}", severity="error")

    async def _handle_socket_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        data = await reader.read(65536)
        resp = {"status": "ok"}
        if data:
            try:
                payload = json.loads(data.decode("utf-8"))
                action = payload.get("action")
                if action == "insert":
                    self.post_message(RemoteInsert(
                        text=payload.get("text", ""),
                        lang=payload.get("lang", ""),
                        file=payload.get("file", ""),
                        start_line=payload.get("start_line"),
                        end_line=payload.get("end_line"),
                    ))
                elif action == "status":
                    text = payload.get("text", "")
                    clear = payload.get("clear", False)
                    if clear:
                        self._background_task_status = ""
                        self.hide_runner_status()
                    elif text:
                        self._background_task_status = text
                        self.set_runner_status_text(text)

                    toast = payload.get("toast")
                    if toast:
                        title = payload.get("title", "")
                        sev = payload.get("severity", "information")
                        dur = float(payload.get("duration", 3.5))
                        self.notify(toast, title=title, severity=sev, timeout=dur)

                    if payload.get("pulse_nav"):
                        pal = payload.get("palette", "purple")
                        self.trigger_nav_indicator("navbar", palette=pal, duration=2.0)
                elif action == "wingman_auth_prompt":
                    auth_data = payload.get("auth_data", {})
                    if auth_data:
                        self._handle_wingman_auth_prompt(auth_data)
                elif action == "wingman_chat":
                    text = payload.get("text", "")
                    sender = payload.get("sender", "operator")
                    attachment = payload.get("attachment")
                    meta = {
                        "device_id": payload.get("device_id", ""),
                        "device_label": payload.get("device_label", ""),
                        "attachment": attachment,
                    }
                    if text or attachment:
                        body_parts = []
                        if text:
                            body_parts.append(text)
                        if isinstance(attachment, dict):
                            att_name = attachment.get("filename") or attachment.get("original_name") or "screenshot"
                            att_path = attachment.get("local_path", "")
                            att_ocr = attachment.get("ocr_text", "")
                            if att_path:
                                body_parts.append(f"🖼️ **[Attached: {att_name}]** ({att_path})")
                            else:
                                body_parts.append(f"🖼️ **[Attached: {att_name}]**")
                            if att_ocr and att_ocr.strip():
                                body_parts.append(f"**[Screenshot OCR Text]**:\n```text\n{att_ocr.strip()}\n```")
                        full_msg = "\n\n".join(body_parts) if body_parts else text
                        self._handle_wingman_incoming_chat(sender, full_msg, meta)
                elif action == "clear_chat":
                    def _do_clear():
                        try:
                            feed = self.query_one("#feed", FeedArea)
                            feed.clear()
                            self.history = []
                            self.save_current_chat()
                            self.notify("Chat cleared via Wingman.", timeout=3.0)
                        except Exception:
                            pass
                    self.call_after_refresh(_do_clear)
                elif action in ("chat_message", "notify_chat"):
                    text = payload.get("text", "")
                    if text:
                        role = payload.get("role", "gemini")
                        feed = self.query_one("#feed", FeedArea)
                        await feed.append_message(role, text, jump_to_start=True)
                        new_turn_id = f"turn_{uuid4().hex[:8]}"
                        self.history.append({"turn_id": new_turn_id, "role": "model", "text": text})
                        self.current_chat_last_index = max(0, len(self.history) - 1)
                        self.current_chat_center_marker = new_turn_id
                        self.save_current_chat()
                        toast = payload.get("toast")
                        if toast:
                            self.notify(toast, title=payload.get("title", "Task Completed"), timeout=5.0)
                        if payload.get("pulse_nav", True):
                            self.trigger_nav_indicator("navbar", palette="green", duration=3.0)
            except Exception as e:
                resp = {"status": "error", "error": str(e)}
        try:
            writer.write(json.dumps(resp).encode("utf-8"))
            await writer.drain()
        except Exception:
            pass
        writer.close()
        await writer.wait_closed()

    @on(RemoteInsert)
    def on_remote_insert(self, event: RemoteInsert) -> None:
        input_widget = self.query_one("#input", ExpandingInput)
        preview_widget = self.query_one("#snippet_preview", SnippetPreview)

        input_widget.focus()
        tag, num = input_widget.register_and_insert_snippet(
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        preview_widget.show_snippet(
            tag=tag,
            num=num,
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        loc = f" ({event.file}:{event.start_line}-{event.end_line})" if event.file else ""
        self.notify(f"Inserted {tag}{loc} at cursor")

    # -----------------------------------------------------------------------
    # Dual Storage Engine (Legacy Flat Files vs. Sharded Directories)
    # -----------------------------------------------------------------------

    def _get_legacy_chat_file(self, chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    def _get_chat_dir(self, chat_id: str) -> Path:
        return CHATS_DIR / chat_id

    def _get_all_chat_entries(self) -> list[dict]:
        entries: list[dict] = []

        # 1. New Sharded Directories
        for p in CHATS_DIR.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                meta_file = p / "meta.json"
                if meta_file.exists():
                    try:
                        m_data = json.loads(meta_file.read_text(encoding="utf-8"))
                        entries.append({
                            "id": m_data.get("id", p.name),
                            "title": m_data.get("title", p.name),
                            "parent_id": m_data.get("parent_id"),
                            "updated_at": m_data.get("updated_at", meta_file.stat().st_mtime),
                            "is_legacy": False,
                            "path": p,
                        })
                    except Exception:
                        pass

        # 2. Legacy Flat JSON Files
        for f in CHATS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                cid = data.get("id", f.stem)
                entries.append({
                    "id": cid,
                    "title": data.get("title", cid),
                    "parent_id": data.get("parent_id"),
                    "updated_at": data.get("updated_at", f.stat().st_mtime),
                    "is_legacy": True,
                    "path": f,
                })
            except Exception:
                pass

        entries.sort(key=lambda d: d.get("updated_at", 0), reverse=True)
        return entries

    def _direct_flush_chat_to_disk(self, chat_id: str, notes_payload: str | dict) -> None:
        if not chat_id:
            return

        chat_dir = self._get_chat_dir(chat_id)
        if chat_dir.is_dir():
            meta_path = chat_dir / "meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    data["notes"] = notes_payload
                    data["updated_at"] = time.time()
                    meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
            return

        legacy_path = self._get_legacy_chat_file(chat_id)
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
                data["notes"] = notes_payload
                data["updated_at"] = time.time()
                legacy_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

    def action_repaint_screen(self) -> None:
        """Forces a clean redraw of the terminal screen and restores input focus."""
        self.refresh(layout=True)
        try:
            self.query_one("#input", ExpandingInput).focus()
        except Exception:
            pass
        self.notify("Screen repainted & input re-focused.")

    def action_emergency_interrupt(self) -> None:
        """Emergency interrupt: immediately cancels active requests, retry loops, and releases locks."""
        self._abort_requested = True
        self._reconnect_target_time = 0.0
        self._request_phase = "idle"
        self._request_details = ""
        self._stop_status_ticker()
        self.set_status_text("⚡ Emergency interrupt triggered: Active task halted.")
        self.notify("Emergency interrupt: Ongoing generation or reconnect aborted.", severity="warning")
        if self.lock.is_locked:
            if hasattr(self.lock, "release_all"):
                self.lock.release_all("emergency_interrupt")
            else:
                for r in list(getattr(self.lock, "_active_reasons", [])):
                    self.lock.release(r)
        try:
            self.query_one("#input").focus()
        except Exception:
            pass

    def _start_heartbeat_watchdog(self) -> None:
        self._watchdog_running = True
        self._last_heartbeat_time = time.monotonic()

        def _watchdog_loop():
            while self._watchdog_running:
                time.sleep(2.0)
                if not self._watchdog_running:
                    break
                gap = time.monotonic() - self._last_heartbeat_time
                if gap > 25.0:
                    try:
                        log_path = GEMINI_HOME / "watchdog.log"
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Heartbeat warning: UI thread unresponsive for {gap:.1f}s\n")
                    except Exception:
                        pass

        t = threading.Thread(target=_watchdog_loop, daemon=True, name="HeartbeatWatchdog")
        t.start()
        self._watchdog_thread = t

    def _stop_heartbeat_watchdog(self) -> None:
        self._watchdog_running = False

    def action_reboot(self, status_report: str | None = None) -> None:
        """Saves current state and notes cleanly, checks reboot guard, marks reboot safety flag, and execs the application process."""
        can_reboot, reason = check_reboot_guard()
        if not can_reboot:
            self.notify(f"Reboot blocked: {reason}", severity="error")
            return

        try:
            create_safety_checkpoint(label=f"pre_reboot_{int(time.time())}")
            self.flush_current_notes()
            self._do_notes_flush()
            self.save_current_chat()
            if self.current_chat_id:
                self._save_to_state("active_chat", self.current_chat_id)
            report = status_report or "✓ Reboot complete: Console reloaded, session restored, UI operational."
            self._save_to_state("pending_reboot_report", report)
            mark_reboot_in_progress()
        except Exception:
            pass

        try:
            if hasattr(self, "_driver") and self._driver is not None:
                self._driver.stop_application_mode()
        except Exception:
            pass

        try:
            if self._server:
                self._server.close()
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink(missing_ok=True)
        except Exception:
            pass

        reboot_argv = list(sys.argv)
        if reboot_argv:
            target = reboot_argv[0]
            if not os.path.exists(target) or os.path.basename(target) in ("modular_runner.py", "gemini.py"):
                for cand in (
                    os.path.join(os.path.dirname(target), "gemini-integrated.py"),
                    "gemini-integrated.py",
                    "/opt/gemini/gemini-integrated.py",
                ):
                    if cand and os.path.exists(cand):
                        reboot_argv[0] = cand
                        break

        try:
            os.execv(sys.executable, [sys.executable] + reboot_argv)
        except Exception:
            subprocess.Popen([sys.executable] + reboot_argv)
            sys.exit(0)

    def _read_and_clear_reboot_report(self) -> str | None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                report = data.pop("pending_reboot_report", None)
                if report:
                    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    return report
            except Exception:
                pass
        return None

    def action_quit(self) -> None:
        self.flush_current_notes()
        self._do_notes_flush()
        self.save_current_chat()
        self.exit()

    def on_unmount(self) -> None:
        self._stop_heartbeat_watchdog()
        self._stop_status_ticker()
        if self._c_c_timer:
            self._c_c_timer.stop()
            self._c_c_timer = None

        if self._nav_indicator_timer:
            self._nav_indicator_timer.stop()
            self._nav_indicator_timer = None

        self.flush_current_notes()
        self._do_notes_flush()
        self.save_current_chat()

        if self._server:
            self._server.close()
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink(missing_ok=True)

        if getattr(self, "wingman_applet", None):
            try:
                self.wingman_applet.stop()
            except Exception:
                pass

    def _get_ancestor_lineage(self, parent_id: str | None) -> list[dict]:
        ancestors: list[dict] = []
        visited = set()
        curr_id = parent_id

        while curr_id and curr_id not in visited:
            visited.add(curr_id)

            p_dir = self._get_chat_dir(curr_id)
            p_file = self._get_legacy_chat_file(curr_id)

            p_data = {}
            if p_dir.is_dir() and (p_dir / "meta.json").exists():
                try:
                    p_data = json.loads((p_dir / "meta.json").read_text(encoding="utf-8"))
                except Exception:
                    break
            elif p_file.exists():
                try:
                    p_data = json.loads(p_file.read_text(encoding="utf-8"))
                except Exception:
                    break
            else:
                break

            notes_val = str(p_data.get("notes", "") or "").strip()
            if notes_val:
                ancestors.append({
                    "id": curr_id,
                    "title": p_data.get("title", curr_id),
                    "notes": notes_val,
                    "parent_id": p_data.get("parent_id"),
                })
            curr_id = p_data.get("parent_id")

        ancestors.reverse()
        for idx, anc in enumerate(ancestors):
            anc["depth"] = idx

        return ancestors

    def sync_notes_ui(self) -> None:
        try:
            notes_panel = self.query_one("#notes_panel", NotesPanel)
            notes_panel.switch_mode(self.active_notes_mode)
        except Exception:
            pass

    def action_toggle_notes(self) -> None:
        if self.lock.is_locked or isinstance(self.screen, MindMapScreen):
            return
        self._toggle_notes_lockstep()

    @work(exclusive=True)
    async def _toggle_notes_lockstep(self) -> None:
        self.lock.acquire("dom_load")
        self.show_loader_banner()

        feed = self.query_one("#feed", FeedArea)
        notes_panel = self.query_one("#notes_panel", NotesPanel)

        target_snap = feed._get_center_raycast_target()
        opening = not self.notes_open
        self.notes_open = opening

        try:
            if opening:
                notes_panel.styles.display = "block"
                if self.screen:
                    self.screen.add_class("-notes-open")
                notes_panel.switch_mode(self.active_notes_mode)
            else:
                self.flush_current_notes()
                self._do_notes_flush()
                notes_panel.styles.display = "none"
                if self.screen:
                    self.screen.remove_class("-notes-open")

            settle_event = asyncio.Event()

            def _on_notes_toggle_settle() -> None:
                try:
                    feed._sync_header_map()
                    if target_snap:
                        t_idx, t_id, delta = target_snap
                        card = feed._get_target_widget(t_idx) or feed._get_target_widget_by_id(t_id)
                        if card:
                            feed._scroll_to_turn_widget(card, center=CENTER_SCREEN_MODE, line_offset=delta)

                    if opening:
                        try:
                            self.query_one("#notes_input", ExpandingInput).focus()
                        except Exception:
                            pass
                    else:
                        target_id = self._last_non_notes_input_id
                        if target_id == "snippet_preview":
                            try:
                                preview = self.query_one("#snippet_preview", SnippetPreview)
                                if preview.styles.display != "none":
                                    preview.focus()
                                else:
                                    self.query_one("#input", ExpandingInput).focus()
                            except Exception:
                                self.query_one("#input", ExpandingInput).focus()
                        else:
                            try:
                                self.query_one("#input", ExpandingInput).focus()
                            except Exception:
                                pass
                finally:
                    settle_event.set()

            self.call_after_refresh(_on_notes_toggle_settle)
            try:
                await asyncio.wait_for(settle_event.wait(), timeout=0.6)
            except asyncio.TimeoutError:
                feed._sync_header_map()

        finally:
            self.hide_loader_banner()
            self.lock.release("dom_load")

    def cycle_global_focus(self, direction: int = 1, escape_parents: bool = False) -> None:
        ring: list[Widget] = []

        try:
            input_widget = self.query_one("#input", ExpandingInput)
            snippet_widget = self.query_one("#snippet_preview", SnippetPreview)
            notes_panel = self.query_one("#notes_panel", NotesPanel)
        except Exception:
            return

        ring.append(input_widget)

        if self.notes_open:
            try:
                notes_input = self.query_one("#notes_input", ExpandingInput)
                ring.append(notes_input)
            except Exception:
                pass

        if snippet_widget.styles.display != "none":
            ring.append(snippet_widget)

        if len(ring) <= 1:
            if ring:
                ring[0].focus()
            return

        current_focused = self.focused
        curr_idx = -1
        for idx, w in enumerate(ring):
            if w is current_focused:
                curr_idx = idx
                break

        if curr_idx == -1:
            next_idx = 0 if direction > 0 else (len(ring) - 1)
        else:
            next_idx = (curr_idx + direction) % len(ring)

        target = ring[next_idx]
        target.focus()

    async def load_chat(self, chat_id: str) -> None:
        self._stop_status_ticker()
        self.hide_status()

        if self.current_chat_id and self.current_chat_id != chat_id:
            if self.active_notes_mode == "chat":
                self.flush_current_notes()
                self._direct_flush_chat_to_disk(self.current_chat_id, self.current_chat_notes)
                self.save_current_chat()

        self.current_chat_id = chat_id
        self._save_to_state("active_chat", chat_id)

        legacy_file = self._get_legacy_chat_file(chat_id)
        chat_dir = self._get_chat_dir(chat_id)

        saved_marker: str = ""
        saved_turn_idx: int | None = None

        if legacy_file.exists():
            # Legacy Single JSON File Mode
            self.is_legacy_chat = True
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            raw_messages = data.get("messages", [])
            self.history = []
            for m in raw_messages:
                m_copy = dict(m)
                if "turn_id" not in m_copy or not m_copy["turn_id"]:
                    m_copy["turn_id"] = f"turn_{uuid4().hex[:8]}"
                self.history.append(m_copy)

            self.current_chat_title = data.get("title", "")
            self.current_chat_working_dir = data.get("working_dir")
            self.current_chat_parent_id = data.get("parent_id")
            
            notes_raw = data.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.relational_notes = {}
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)

            saved_marker = data.get("center_marker", "")
            saved_turn_idx = data.get("last_turn_index")

            curr_top = getattr(self.notes_manager, "active_topic", "general")
            self.active_task_title = f"Topic: {curr_top}"
            self.current_gemini_state = f"Topic: {curr_top}"
            self.current_user_state = "Collaborating in unified bilateral console session."
            self.current_tree_state = ["T1", "F:gemini_app/"]
            self.current_tree_content = "└── Unified Console [Active]"

        elif chat_dir.is_dir() and (chat_dir / "meta.json").exists():
            # Modern Sharded Directory Mode
            self.is_legacy_chat = False
            meta_path = chat_dir / "meta.json"
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))

            self.current_chat_title = meta_data.get("title", "")
            self.current_chat_working_dir = meta_data.get("working_dir")
            self.current_chat_parent_id = meta_data.get("parent_id")

            notes_raw = meta_data.get("notes", "")
            self.notes_manager = NotesManager.from_dict(notes_raw)
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.relational_notes = {}

            viewport = meta_data.get("viewport", {})
            saved_marker = viewport.get("center_marker", "")
            saved_turn_idx = viewport.get("last_turn_index")

            mind_map = meta_data.get("mind_map", {})
            gem_state = mind_map.get("gemini_state", "")
            curr_top = getattr(self.notes_manager, "active_topic", "general")
            if not gem_state or "unifying notes" in gem_state.lower() or gem_state in ("Legacy active session.", "None"):
                gem_state = f"Topic: {curr_top}"
            self.active_task_title = gem_state
            self.current_gemini_state = gem_state
            self.current_user_state = mind_map.get("user_state", "") or "Collaborating in unified bilateral console session."
            self.current_tree_state = mind_map.get("tree_state", []) or ["T100", "F:gemini_app/ui/widgets/notes.py"]
            self.current_tree_content = mind_map.get("tree_content", "") or "└── Unified Stream [Active]"

            # Load message segments in order
            self.history = []
            segment_files = sorted(chat_dir.glob("segment_*.json"), key=lambda f: int(f.stem.split("_")[1]))
            for sf in segment_files:
                try:
                    seg_turns = json.loads(sf.read_text(encoding="utf-8"))
                    self.history.extend(seg_turns)
                except Exception:
                    pass
            if self.history:
                self.notes_manager.scan_chat_for_notes(self.history)
        else:
            self.is_legacy_chat = False
            self.history = []
            self.current_chat_title = ""
            self.current_chat_working_dir = None
            self.current_chat_parent_id = None
            self.gemini_notes = ""
            self.relational_notes = {}
            self.current_chat_last_index = 0
            self.current_chat_center_marker = ""
            self.current_gemini_state = "Unified Console: Autonomous Relational Mind & Archival Engine"
            self.current_user_state = "Collaborating in unified bilateral console session."
            self.current_tree_state = ["T1", "F:gemini_app/"]
            self.current_tree_content = "└── Unified Stream [Active]"

        if saved_marker:
            self.current_chat_center_marker = saved_marker
        elif saved_turn_idx is not None and self.history:
            self.current_chat_last_index = max(0, min(len(self.history) - 1, saved_turn_idx))
            self.current_chat_center_marker = self.history[self.current_chat_last_index].get("turn_id", "")
        else:
            self.current_chat_last_index = max(0, len(self.history) - 1)
            self.current_chat_center_marker = self.history[-1].get("turn_id", "") if self.history else ""

        feed = self.query_one("#feed", FeedArea)
        if feed.styles.display == "none":
            feed.styles.display = "block"

        self.update_feed_title()

        marker_target = self.current_chat_center_marker or self.current_chat_last_index
        feed.set_messages(self.history, initial_target_marker=marker_target)

        notes_panel = self.query_one("#notes_panel", NotesPanel)
        notes_panel.clear_session_expansion_states()
        self.sync_notes_ui()

        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        self.update_feed_nav_banner()

        if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
            try:
                self.wingman_applet.clear_chat()
            except Exception:
                pass

    def save_current_chat(self) -> None:
        if not self.current_chat_id:
            return

        chat_dir = self._get_chat_dir(self.current_chat_id)
        # Lazy Materialization Gate:
        # If the session has 0 turns, hasn't yet materialized on disk, and is not a legacy flat chat,
        # defer disk allocation until the first conversational turn is received.
        if not self.history and not chat_dir.exists() and not self.is_legacy_chat:
            return

        self.flush_current_notes()

        active_topic = getattr(self.notes_manager, "active_topic", "general") if hasattr(self, "notes_manager") else "general"
        raw_title = (getattr(self, "active_task_title", "") or self.current_chat_title or "").strip()
        if not raw_title or "unifying notes" in raw_title.lower() or raw_title in ("Legacy active session.", "None"):
            title = f"Topic: {active_topic}"
        else:
            title = raw_title
        self.current_chat_title = title
        self.update_feed_title()

        passkey = None
        try:
            from gemini_app.vault import get_session_passkey
            passkey = get_session_passkey()
        except Exception:
            pass

        try:
            from gemini_app.security.redaction import redact_secrets_in_text
            for m in self.history:
                if "turn_id" not in m or not m["turn_id"]:
                    m["turn_id"] = f"turn_{uuid4().hex[:8]}"
                if "text" in m and isinstance(m["text"], str):
                    m["text"], _ = redact_secrets_in_text(m["text"], passkey=passkey)
        except Exception:
            for m in self.history:
                if "turn_id" not in m or not m["turn_id"]:
                    m["turn_id"] = f"turn_{uuid4().hex[:8]}"

        final_marker = self.current_chat_center_marker
        if final_marker.endswith(":+0") or final_marker.endswith(":-0"):
            final_marker = final_marker.split(":")[0] + ":0"
        elif not CENTER_SCREEN_MODE and ":" in final_marker:
            final_marker = final_marker.split(":")[0]

        notes_payload = {
            "gemini_notes": self.gemini_notes or "",
            "global_notes": self.global_notes or "",
            "relational_notes": self.relational_notes or {},
        }
        if hasattr(self, "notes_manager") and self.notes_manager:
            notes_payload.update(self.notes_manager.to_dict())

        if self.is_legacy_chat:
            # Save strictly to legacy flat JSON file
            path = self._get_legacy_chat_file(self.current_chat_id)
            existing_data = {}
            if path.exists():
                try:
                    existing_data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing_data = {}

            data = {
                **existing_data,
                "id": self.current_chat_id,
                "title": self.current_chat_title,
                "parent_id": self.current_chat_parent_id,
                "updated_at": time.time(),
                "working_dir": self.current_chat_working_dir,
                "last_turn_index": self.current_chat_last_index,
                "center_marker": final_marker,
                "notes": notes_payload,
                "messages": self.history,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            # Save to Sharded Directory
            chat_dir = self._get_chat_dir(self.current_chat_id)
            chat_dir.mkdir(parents=True, exist_ok=True)

            total_turns = len(self.history)
            seg_count = max(1, (total_turns + TURNS_PER_SEGMENT - 1) // TURNS_PER_SEGMENT) if total_turns > 0 else 1
            active_seg = max(0, seg_count - 1)

            meta_data = {
                "id": self.current_chat_id,
                "title": self.current_chat_title,
                "parent_id": self.current_chat_parent_id,
                "updated_at": time.time(),
                "working_dir": self.current_chat_working_dir,
                "notes": notes_payload,
                "viewport": {
                    "last_turn_index": self.current_chat_last_index,
                    "center_marker": final_marker,
                },
                "storage": {
                    "total_turns": total_turns,
                    "segment_count": seg_count,
                    "active_segment": active_seg,
                    "max_segment_size": TURNS_PER_SEGMENT,
                },
                "mind_map": {
                    "gemini_state": self.current_gemini_state,
                    "user_state": self.current_user_state,
                    "tree_state": self.current_tree_state,
                    "tree_content": self.current_tree_content,
                },
            }
            (chat_dir / "meta.json").write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

            # Write segments of 200 turns
            for s_idx in range(seg_count):
                start = s_idx * TURNS_PER_SEGMENT
                end = start + TURNS_PER_SEGMENT
                seg_slice = self.history[start:end]
                seg_file = chat_dir / f"segment_{s_idx}.json"
                seg_file.write_text(json.dumps(seg_slice, indent=2), encoding="utf-8")

        self._save_to_state("active_chat", self.current_chat_id)

        # Incrementally index newly added turns into SQLite FTS5 Memory Index
        if self.history:
            last_turn = self.history[-1]
            try:
                self.memory_index.index_turn(
                    turn_id=last_turn.get("turn_id", ""),
                    chat_id=self.current_chat_id,
                    turn_number=len(self.history),
                    role=last_turn.get("role", "user"),
                    content=last_turn.get("text", ""),
                    project_dir=self.current_chat_working_dir,
                    title=self.current_chat_title,
                )
            except Exception:
                pass

    # for later exploration by gemini
    def action_fork_chat(self) -> None:
        self.notify("Fork mode retired; Cognitive Mind Lens active.", timeout=2.0)

    def action_confirm_fork(self) -> None:
        pass

    def _start_new_chat(self, title: str, parent_id: str | None = None) -> None:
        self._stop_status_ticker()
        self.hide_status()

        self.flush_current_notes()
        self.save_current_chat()

        self.is_legacy_chat = False
        self.active_notes_mode = "gemini"

        self.current_chat_id = uuid4().hex[:8]
        self.current_chat_title = title or "Unified Stream"
        self.current_chat_parent_id = parent_id
        self.current_chat_working_dir = None
        self.current_chat_last_index = 0
        self.current_chat_center_marker = ""
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        self.update_feed_title()

        notes_panel = self.query_one("#notes_panel", NotesPanel)
        notes_panel.clear_session_expansion_states()
        self.sync_notes_ui()

        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()
        self.update_feed_nav_banner()
        self.save_current_chat()

    def action_save_snippet_to_disk(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        content = feed.get_active_snippet()

        if not content:
            self.notify("No snippet selected to write.", severity="warning")
            return

        initial_dir = self.get_effective_working_dir()

        def on_save_modal_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            filename = result["filename"]
            code = result["content"]

            base = Path(os.path.expanduser(str(working_dir).strip())).resolve()
            fn_path = Path(os.path.expanduser(filename.strip()))
            if fn_path.is_absolute():
                target = fn_path.resolve()
            else:
                target = (base / fn_path).resolve()

            def do_write() -> None:
                try:
                    written_path = write_code_to_disk(working_dir, filename, code)
                    self.set_working_dir(working_dir)
                    self.notify(f"Saved: {written_path}", timeout=3.5)
                except Exception as e:
                    self.notify(f"Failed to write file: {e}", severity="error")

            if target.exists():
                def on_overwrite_confirmed(confirmed: bool | None) -> None:
                    if confirmed:
                        do_write()
                    else:
                        self.notify("Save cancelled.", timeout=2.0)

                self.push_screen(
                    ConfirmModal(message=f"'{target.name}' already exists.\nOverwrite?"),
                    callback=on_overwrite_confirmed,
                )
            else:
                do_write()

        self.push_screen(
            WriteSnippetModal(
                snippet_content=content,
                initial_dir=initial_dir,
            ),
            callback=on_save_modal_result,
        )

    def action_insert_file_from_disk(self) -> None:
        initial_dir = self.get_effective_working_dir()

        def on_file_result(result: dict | None) -> None:
            if not result:
                return

            working_dir = result["working_dir"]
            file_path_str = result["file_path"]
            rel_path = result["rel_path"]

            self.set_working_dir(working_dir)

            target_file = Path(file_path_str)
            try:
                code_content = target_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                self.notify(f"Failed to read file: {e}", severity="error")
                return

            lines = code_content.count("\n") + 1
            lang = detect_language(target_file)

            display_path = rel_path
            try:
                base = Path(os.path.expanduser(working_dir)).resolve()
                display_path = str(target_file.relative_to(base))
            except Exception:
                pass

            input_widget = self.query_one("#input", ExpandingInput)
            preview_widget = self.query_one("#snippet_preview", SnippetPreview)

            input_widget.focus()
            tag, num = input_widget.register_and_insert_snippet(
                code=code_content,
                lang=lang,
                file=display_path,
                start_line=1,
                end_line=lines,
            )

            preview_widget.show_snippet(
                tag=tag,
                num=num,
                code=code_content,
                lang=lang,
                file=display_path,
                start_line=1,
                end_line=lines,
            )

            self.notify(f"Inserted {tag} ({display_path})")

        self.push_screen(
            InsertFileModal(initial_dir=initial_dir),
            callback=on_file_result,
        )

    def action_open_git_tree(self) -> None:
        initial_dir = self.get_effective_working_dir()

        def on_git_tree_result(result: dict | None) -> None:
            if not result:
                return

            repo_dir = result["repo_dir"]
            selected_files: list[str] = result["selected_files"]
            tracked_files: list[str] = result["tracked_files"]
            ignored_files: list[str] = result["ignored_files"]
            tree_mode: str = result["tree_mode"]

            self.set_working_dir(repo_dir)

            input_widget = self.query_one("#input", ExpandingInput)
            preview_widget = self.query_one("#snippet_preview", SnippetPreview)

            sections: list[str] = []
            root_label = Path(repo_dir).name or repo_dir
            ignored_set = set(ignored_files)

            if tree_mode == "full":
                all_files = tracked_files + [f for f in selected_files if f in ignored_set]
                if all_files:
                    ascii_tree = build_ascii_tree(all_files, root_name=root_label, ignored_set=ignored_set)
                    sections.append(f"Repository Tree (`{root_label}`):\n```text\n{ascii_tree}\n```")
            elif tree_mode == "selected" and selected_files:
                ascii_tree = build_ascii_tree(selected_files, root_name=root_label, ignored_set=ignored_set)
                sections.append(f"Selected Files Tree (`{root_label}`):\n```text\n{ascii_tree}\n```")

            last_tag = ""
            last_num = 1
            last_code = ""
            last_lang = ""
            last_file = ""

            for rel_path in selected_files:
                abs_path = Path(repo_dir) / rel_path
                try:
                    code_content = abs_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    code_content = f"// Error reading file: {e}"

                lang = detect_language(rel_path)
                lines = code_content.count("\n") + 1

                tag, num = input_widget.register_and_insert_snippet(
                    code=code_content,
                    lang=lang,
                    file=rel_path,
                    start_line=1,
                    end_line=lines,
                )
                last_tag = tag
                last_num = num
                last_code = code_content
                last_lang = lang
                last_file = rel_path

            if sections:
                current_text = input_widget.text
                input_widget.text = "\n\n".join(sections) + ("\n\n" + current_text if current_text else "")

            if last_tag:
                preview_widget.show_snippet(
                    tag=last_tag,
                    num=last_num,
                    code=last_code,
                    lang=last_lang,
                    file=last_file,
                    start_line=1,
                    end_line=last_code.count("\n") + 1,
                )

            input_widget.focus()
            self.notify(f"Inserted tree & {len(selected_files)} file(s).")

        self.push_screen(
            GitTreeModal(initial_dir=initial_dir),
            callback=on_git_tree_result,
        )

    def _get_emacs_frames(self) -> list[dict]:
        try:
            res = subprocess.run(
                ["emacsclient", "--eval", "(gemini-list-open-frames)"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                raw_json = res.stdout.strip()
                parsed = json.loads(raw_json)
                while isinstance(parsed, str):
                    parsed = json.loads(parsed)
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        return []

    def _send_to_emacs_buffer(self, code_text: str, target_buf: str | None = None) -> bool:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as tmp:
                tmp.write(code_text)
                tmp.flush()
                temp_path = tmp.name

            escaped_tmp = json.dumps(temp_path)
            if target_buf:
                escaped_buf = json.dumps(target_buf)
                elisp = f'(gemini-insert-file-into-window {escaped_buf} {escaped_tmp})'
            else:
                elisp = f'(with-current-buffer (window-buffer (selected-window)) (insert-file-contents {escaped_tmp}))'

            res = subprocess.run(
                ["emacsclient", "--eval", elisp],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def action_send_to_emacs(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        text_to_send = feed.get_active_snippet()
        if not text_to_send:
            self.notify("No snippet to send to Emacs.", severity="warning")
            return

        frames = self._get_emacs_frames()
        if len(frames) <= 1:
            success = self._send_to_emacs_buffer(text_to_send)
            if success:
                self.notify("Snippet sent to Emacs client")
            else:
                self.notify("Failed to connect to Emacs server", severity="error")
            return

        def on_window_chosen(chosen: dict | None) -> None:
            if chosen:
                buf = chosen.get("buf_name")
                success = self._send_to_emacs_buffer(text_to_send, target_buf=buf)
                if success:
                    self.notify(f"Snippet sent to Emacs client ({chosen.get('file_name')})")
                else:
                    self.notify("Failed to send to Emacs window", severity="error")

        self.push_screen(FrameSelectModal(frames), callback=on_window_chosen)

    def action_copy_active_snippet(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        text_to_send = feed.get_active_snippet()
        if not text_to_send:
            self.notify("No snippet selected to copy.", severity="warning")
            return

        self.copy_to_clipboard(text_to_send)
        self.notify("Copied to system clipboard")

    def action_yank_to_input(self) -> None:
        try:
            paste_text = pyperclip.paste()
            if not paste_text:
                self.notify("Clipboard is empty.", severity="warning")
                return

            input_widget = self.query_one("#input", ExpandingInput)
            input_widget.focus()
            if input_widget.selected_text:
                input_widget.delete(input_widget.selection.start, input_widget.selection.end)
            input_widget.insert(paste_text)
            input_widget._clear_mark()
            self.notify("Pasted clipboard to prompt input")
        except Exception as e:
            self.notify(f"Clipboard paste error: {e}", severity="error")

    async def append_to_feed(
        self,
        sender: str,
        text: str,
        jump_to_start: bool = False,
        origin_device: str = "",
        origin_label: str = "",
        msg_id: str = "",
    ) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.append_message(sender, text, jump_to_start=jump_to_start)
        is_user = (sender.lower() not in ("gemini", "gemini core", "system"))
        eff_origin_device = origin_device or ("mothership" if is_user else "")
        eff_origin_label = origin_label or ("Mothership" if is_user else "")
        if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
            try:
                self.wingman_applet.push_chat_message(
                    sender=sender,
                    text=text,
                    is_user=is_user,
                    msg_id=msg_id,
                    origin_device=eff_origin_device,
                    origin_label=eff_origin_label,
                )
            except Exception:
                pass
        try:
            from gemini_app.fleet.nodes import send_mothership_command
            send_mothership_command("broadcast_wingman_chat", {
                "sender": sender,
                "text": text,
                "is_user": is_user,
                "id": msg_id,
                "origin_device": eff_origin_device,
                "origin_label": eff_origin_label,
            }, timeout=2.0)
        except Exception:
            pass

    def _handle_slash_command(self, raw_cmd: str) -> bool:
        """Handles client-side slash commands instantly without sending to API."""
        cmd = raw_cmd.lstrip("!").lstrip("/").strip()
        parts = cmd.split(None, 1)
        verb = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if verb in ("theme", "ui-theme"):
            if not arg:
                valid = ", ".join(THEMES.keys())
                self.notify(f"Active theme: '{self.active_palette_name}'. Options: {valid}", timeout=4.0)
                return True
            if self.set_theme(arg):
                self.notify(f"Theme switched to '{arg}'.", timeout=2.5)
            else:
                valid = ", ".join(THEMES.keys())
                self.notify(f"Unknown theme '{arg}'. Choose from: {valid}", severity="error")
            return True

        elif verb == "themes":
            all_themes = ", ".join(THEMES.keys())
            self.notify(f"Available themes: {all_themes} (Active: {self.active_palette_name})", timeout=5.0)
            return True

        elif verb in ("accent", "accent-talk"):
            parts = arg.split(None, 3)
            if len(parts) < 2:
                self.notify("Usage: /accent <feed|notes|input|footer|all> <color> [seconds] [message]", severity="warning")
                return True
            target = parts[0]
            color = parts[1]
            dur = float(parts[2]) if len(parts) > 2 and parts[2].replace(".", "", 1).isdigit() else 3.0
            msg = parts[3] if len(parts) > 3 else ""
            res = apply_accent_talk(self, target=target, palette=color, duration=dur, message=msg)
            if res.get("status") == "success":
                self.notify(res.get("message", "Accent updated."), timeout=3.0)
            else:
                self.notify(res.get("message", "Failed to set accent."), severity="warning")
            return True

        elif verb == "pulse":
            parts = arg.split(None, 1)
            color = parts[0] if parts else self.active_palette_name
            dur = float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else 2.5
            apply_accent_talk(self, target="all", palette=color, duration=dur, message=f"Pulsing theme accent '{color}'!")
            return True

        elif verb in ("mind-anim", "anim", "animation"):
            parts = arg.split(None, 3)
            effect = parts[0] if parts else "sparkle"
            color = parts[1] if len(parts) > 1 else ""
            dur = float(parts[2]) if len(parts) > 2 and parts[2].replace(".", "", 1).isdigit() else 4.0
            msg = parts[3] if len(parts) > 3 else ""
            start_mind_animation(self, effect=effect, palette=color, duration=dur, message=msg)
            return True

        elif verb in ("state", "status-state", "introspect"):
            t = arg.strip().lower() or "all"
            state_data = get_console_state(self, tier=t)
            formatted = json.dumps(state_data, indent=2)
            self.call_after_refresh(lambda: self.append_to_feed("system", f"### Introspected App State (Tier: {t})\n```json\n{formatted}\n```", jump_to_start=False))
            return True

        elif verb in ("title", "task"):
            if not arg:
                curr = getattr(self, "active_task_title", "") or self.current_gemini_state
                self.notify(f"Current active work title: {curr}", timeout=3.5)
                return True
            self.set_feed_title(arg)
            self.notify(f"Feed active task title updated to: {arg}", timeout=2.5)
            return True

        elif verb == "diff":
            try:
                working_dir = self.get_effective_working_dir()
                stat = subprocess.run(["git", "diff", "--stat"], cwd=working_dir, capture_output=True, text=True, timeout=5)
                status = subprocess.run(["git", "status", "-s"], cwd=working_dir, capture_output=True, text=True, timeout=5)
                status_out = status.stdout.strip() or "No untracked or modified files."
                stat_out = stat.stdout.strip() or "No staged or unstaged diffs."
                output = (
                    f"### Working Tree Status\n```text\n{status_out}\n```\n\n"
                    f"### Diff Stat\n```text\n{stat_out}\n```"
                )
                self.call_after_refresh(lambda: self.append_to_feed("system", output, jump_to_start=False))
            except Exception as e:
                self.notify(f"Git diff error: {e}", severity="error")
            return True

        elif verb in ("recall", "memory"):
            if not arg:
                self.notify("Usage: /recall <search terms>", severity="warning")
                return True
            matches = self.memory_index.search(arg, limit=5)
            if not matches:
                self.notify(f"No memory matches for '{arg}'.", timeout=3.0)
            else:
                lines = [f"### Fast Memory Matches for '{arg}':"]
                for m in matches:
                    role_str = m.get("role", "user")
                    t_num = m.get("turn_number", 0)
                    t_title = m.get("title") or m.get("chat_id")
                    lines.append(f"- **Turn #{t_num}** ({role_str}) in *{t_title}*:\n  > {m.get('snippet')}")
                self.call_after_refresh(lambda: self.append_to_feed("system", "\n".join(lines), jump_to_start=False))
            return True

        elif verb in ("tokens", "stats"):
            total_words = sum(len(m.get("text", "").split()) for m in self.history)
            approx_tokens = int(total_words * 1.33)
            turns_count = len(self.history)
            self.notify(
                f"Session Stats: {turns_count} turns | ~{total_words} words (~{approx_tokens} tokens) | Model: {DEFAULT_MODEL}",
                timeout=4.5,
            )
            return True

        elif verb in ("snapshot", "snap"):
            clean_arg = arg.strip().lower()
            if clean_arg in ("clean", "clear", "purge", "delete-all"):
                purged = delete_all_snapshots()
                self.notify(f"✓ All snapshots deleted ({purged} files removed).", timeout=3.5)
                return True
            elif clean_arg in ("prune", "prune-audits", "clean-tests"):
                pruned = cleanup_test_snapshots()
                self.notify(f"✓ Test & audit snapshots cleaned up ({pruned} removed).", timeout=3.5)
                return True
            label = arg.strip()
            self.action_take_snapshot(label=label, taken_by="user", source="command")
            return True

        elif verb in ("snapshots", "snaps"):
            held = list_held_snapshots(only_held=True)
            total = list_held_snapshots(only_held=False)
            if not total:
                self.notify("No snapshots recorded yet. Use C-c ` or /snapshot to capture one.", timeout=4.0)
            else:
                held_count = len(held)
                held_indices = ", ".join(f"#{e.get('index')}" for e in held) if held else "None"
                self.notify(
                    f"Snapshots: {len(total)} total, {held_count} held for Gemini review ({held_indices}).",
                    timeout=5.0,
                )
            return True

        elif verb in ("reboot", "restart"):
            report = arg if arg else None
            self.action_reboot(status_report=report)
            return True

        elif verb in ("rollback", "revert"):
            success, msg = perform_git_rollback()
            if success:
                self.notify("Rollback completed. Rebooting...", timeout=2.0)
                self.set_timer(1.0, lambda: self.action_reboot(status_report="✓ Rolled back to previous stable version."))
            else:
                self.notify(f"Rollback failed: {msg}", severity="error")
            return True

        elif verb in ("notes", "note"):
            if not arg or arg == "stats":
                archived_cnt = len(self.notes_manager.get_archived_notes())
                topics_cnt = len(self.notes_manager.get_all_topics())
                self.notify(
                    f"Notes: {len(self.notes_manager.notes)} total across {topics_cnt} topics | "
                    f"{len(self.notes_manager.get_notes_to_get_back_to())} action items | "
                    f"{len(self.notes_manager.get_notes_to_think_about())} brainstorms | "
                    f"{archived_cnt} archived",
                    timeout=5.0,
                )
                return True
            parts = arg.split(None, 1)
            sub = parts[0].lower()
            sub_arg = parts[1].strip() if len(parts) > 1 else ""

            if sub in ("prune", "dedup", "clean"):
                res = self.notes_manager.prune_notes()
                self.gemini_notes = self.notes_manager.working_notes
                self.schedule_notes_flush()
                try:
                    self.query_one("#notes_panel", NotesPanel).refresh_display()
                except Exception:
                    pass
                self.notify(
                    f"✓ Notes pruned: {res['duplicates_removed']} duplicate(s) removed, {res['empty_removed']} empty removed. {res['total_remaining']} remaining.",
                    timeout=4.0,
                )
                return True

            elif sub in ("archive",):
                if not sub_arg or sub_arg == "completed":
                    cnt = self.notes_manager.archive_completed_notes()
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Archived {cnt} completed note(s).", timeout=3.0)
                    return True
                ok = self.notes_manager.archive_note(sub_arg)
                if ok:
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Note matching '{sub_arg}' archived.", timeout=3.0)
                else:
                    self.notify(f"No active note found matching '{sub_arg}'.", severity="warning")
                return True

            elif sub in ("unarchive", "restore"):
                if not sub_arg:
                    self.notify("Usage: /notes unarchive <id or query>", severity="warning")
                    return True
                ok = self.notes_manager.unarchive_note(sub_arg)
                if ok:
                    self.schedule_notes_flush()
                    try:
                        self.query_one("#notes_panel", NotesPanel).refresh_display()
                    except Exception:
                        pass
                    self.notify(f"✓ Restored note matching '{sub_arg}' from archive.", timeout=3.0)
                else:
                    self.notify(f"No archived note found matching '{sub_arg}'.", severity="warning")
                return True

            elif sub in ("archived", "archive_list"):
                archived = self.notes_manager.get_archived_notes()
                if not archived:
                    self.notify("No archived notes on record.", timeout=3.0)
                else:
                    lines = [f"### Archived Notes ({len(archived)}):"]
                    for a in archived:
                        lines.append(f"- **[{a.id}]** ({a.topic}): {a.content}")
                    self.call_after_refresh(lambda: self.append_to_feed("system", "\n".join(lines), jump_to_start=False))
                return True

            else:
                self.notify(f"Unknown notes action '{sub}'. Use: prune, archive, unarchive, stats.", severity="error")
                return True

        elif verb in ("project", "scaffold"):
            if not arg:
                self.notify("Usage: /project <name> [description]", severity="warning")
                return True
            p_parts = arg.split(None, 1)
            p_name = p_parts[0]
            p_desc = p_parts[1] if len(p_parts) > 1 else ""
            res = scaffold_project(name=p_name, description=p_desc, author=self.user_real_name)
            if res.get("status") == "success":
                msg = f"✓ Project '{p_name}' scaffolded in ~/Projects/{p_name} (Git repo initialized, README.md, LICENSE with Copyright {res.get('copyright_holder')})."
                self.notify(msg, timeout=4.5)
                self.call_after_refresh(lambda: self.append_to_feed("system", f"### Project Scaffolding Complete\n{msg}\n- **Path:** `{res.get('path')}`\n- **Git:** `{res.get('git')}`", jump_to_start=False))
            else:
                self.notify(f"Scaffolding failed: {res.get('message')}", severity="error")
            return True

        elif verb == "projects":
            proj_dir = PROJECTS_DIR
            if not proj_dir.exists():
                proj_dir.mkdir(parents=True, exist_ok=True)
            projs = [p.name for p in proj_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
            if not projs:
                self.notify(f"No projects found in {proj_dir}. Use /project <name> to scaffold one.", timeout=4.0)
            else:
                lines = [f"### Projects in `{proj_dir}`:"]
                for p in sorted(projs):
                    lines.append(f"- **{p}** (`{proj_dir / p}`)")
                self.call_after_refresh(lambda: self.append_to_feed("system", "\n".join(lines), jump_to_start=False))
            return True

        elif verb in ("vault", "passkey", "password"):
            sub = arg.strip().lower()
            if not sub:
                self.action_vault_dashboard()
            elif sub in ("change", "rotate"):
                self.action_vault_change()
            elif sub in ("password", "pass"):
                self.action_vault_password()
            elif sub in ("file", "files"):
                self.action_vault_file()
            elif sub in ("secret", "sec", "key"):
                self.action_vault_secret()
            elif sub in ("sync", "nodes", "node-sync"):
                self.action_vault_sync()
            elif sub == "lock":
                self.action_vault_lock()
            else:
                self.notify(f"Unknown vault subcommand '{arg}'. Available: /vault [password|file|secret|sync|change|lock]", severity="warning")
            return True

        elif verb == "api-key":
            self.action_configure_api_key()
            return True

        elif verb in ("git-setup", "git_setup"):
            self.action_configure_git()
            return True

        elif verb == "clear":
            self.history = []
            feed = self.query_one("#feed", FeedArea)
            feed.clear()
            self.save_current_chat()
            self.notify("Chat cleared.")
            if getattr(self, "wingman_applet", None) and self.wingman_applet.engine.is_running:
                try:
                    self.wingman_applet.clear_chat()
                except Exception:
                    pass
            try:
                from gemini_app.fleet.nodes import send_mothership_command
                send_mothership_command("broadcast_wingman_clear", {}, timeout=2.0)
            except Exception:
                pass
            return True

        elif verb in ("nowplaying", "now_playing", "music", "playing", "phone"):
            target_node = arg.strip() or "android-termux-localhost"
            self.notify(f"Fetching mobile media telemetry ({target_node})...", timeout=2.5)

            def _async_fetch_media():
                from gemini_app.fleet.nodes import get_node_media_info
                res = get_node_media_info(node_id=target_node)
                if res.get("status") == "ok":
                    info = res.get("media_info", {})
                    summary = info.get("summary") or "Active track detected"
                    artist = info.get("artist", "")
                    title = info.get("title", "")
                    track_display = f"{artist} - {title}" if (artist and title) else (artist or title or "Now Playing")
                    playlist = info.get("playlist", "")
                    album = info.get("album", "")
                    time_s = info.get("timestamps", "")
                    device = info.get("audio_device", "")
                    app_name = info.get("app", "Media Player")

                    md_lines = [
                        f"### 🎵 Now Playing ({target_node})",
                        f"**{track_display}**",
                        f"- **Player:** {app_name}",
                    ]
                    if playlist:
                        md_lines.append(f"- **Playlist:** `{playlist}`")
                    if album:
                        md_lines.append(f"- **Album / Art:** {album}")
                    if time_s:
                        md_lines.append(f"- **Progress:** {time_s}")
                    if device:
                        md_lines.append(f"- **Audio Device:** {device}")
                    if res.get("local_path"):
                        md_lines.append(f"- **Screenshot:** `{res.get('local_path')}`")

                    md_text = "\n".join(md_lines)
                    self.call_after_refresh(lambda: self.append_to_feed("system", md_text, jump_to_start=False))
                    self.notify(f"🎵 {summary}", timeout=4.0)
                else:
                    err_msg = res.get("error", "Could not fetch media telemetry")
                    self.notify(f"Media fetch failed: {err_msg}", severity="error")

            threading.Thread(target=_async_fetch_media, daemon=True, name="fetch-media-cmd").start()
            return True

        elif verb in ("whisper", "tts", "speak"):
            text_to_say = arg.strip() or "Bilateral audio sync online."
            self.notify("Transmitting audio whisper to Bose earbuds...", timeout=2.5)

            def _async_whisper():
                from gemini_app.fleet.nodes import speak_node_tts
                res = speak_node_tts(node_id="android-termux-localhost", text=text_to_say)
                if res.get("status") == "ok" and res.get("tts_result", {}).get("status") == "ok":
                    self.notify(f"🎧 Whispered: '{text_to_say}'", timeout=3.5)
                else:
                    err = res.get("error") or res.get("tts_result", {}).get("error", "Failed to transmit TTS")
                    self.notify(f"Whisper failed: {err}", severity="error")

            threading.Thread(target=_async_whisper, daemon=True, name="whisper-cmd").start()
            return True

        elif verb in ("record", "mic"):
            dur = int(arg.strip()) if arg.strip().isdigit() else 5
            self.notify(f"🎙️ Recording {dur}s audio from mobile / Bose microphone...", timeout=float(dur) + 2.0)

            def _async_record():
                from gemini_app.fleet.nodes import record_node_audio
                res = record_node_audio(node_id="android-termux-localhost", duration=dur)
                if res.get("status") == "ok":
                    loc = res.get("local_path", "")
                    sz = res.get("size_bytes", 0)
                    sz_kb = round(sz / 1024, 1)
                    md_text = f"### 🎙️ Audio Capture Complete\n- **Duration:** {dur}s\n- **File:** `{loc}`\n- **Size:** {sz_kb} KB\n- **Sink:** Active Bluetooth (Bose QuietComfort Earbuds)"
                    self.call_after_refresh(lambda: self.append_to_feed("system", md_text, jump_to_start=False))
                    self.notify(f"🎙️ Audio saved: {sz_kb} KB ({loc})", timeout=4.0)
                else:
                    err = res.get("error", "Recording failed")
                    self.notify(f"Audio capture failed: {err}", severity="error")

            threading.Thread(target=_async_record, daemon=True, name="record-cmd").start()
            return True

        elif verb in ("volume", "vol"):
            parts = arg.strip().split()
            stream_name = "music"
            vol_val = None
            if len(parts) == 1:
                if parts[0].isdigit():
                    vol_val = int(parts[0])
                else:
                    stream_name = parts[0].lower()
            elif len(parts) >= 2:
                stream_name = parts[0].lower()
                if parts[1].isdigit():
                    vol_val = int(parts[1])

            def _async_volume():
                from gemini_app.fleet.nodes import control_node_volume
                res = control_node_volume(node_id="android-termux-localhost", stream=stream_name, volume=vol_val)
                if res.get("status") == "ok":
                    sub = res.get("volume_result", {})
                    v_data = sub.get("volume", "")
                    msg_v = f"Volume: {v_data}" if v_data else "Volume updated"
                    self.notify(f"🔊 {msg_v}", timeout=3.5)
                else:
                    self.notify(f"Volume control failed: {res.get('error', 'Error')}", severity="error")

            threading.Thread(target=_async_volume, daemon=True, name="vol-cmd").start()
            return True

        elif verb == "help":
            help_text = (
                "### Console Slash Commands\n"
                "- `/vault [password|file|secret|sync|change|lock]`: Secure offline credentials & fleet node sync manager\n"
                "- `/api-key`: Update Google Gemini API key via modal\n"
                "- `/git-setup`: Configure Real Name & Git credentials\n"
                "- `/theme <name>`: Switch color theme (e.g. `/theme amber`, `/theme hacker`)\n"
                "- `/themes`: List all available color themes\n"
                "- `/project <name> [desc]`: Scaffold a new project in ~/Projects (Git, README, LICENSE)\n"
                "- `/projects`: List existing projects in ~/Projects\n"
                "- `/notes [prune|archive|unarchive|stats]`: Manage, prune, or archive notes\n"
                "- `/nowplaying [node_id]`: Query mobile track, artist, and screenshot OCR telemetry\n"
                "- `/whisper <text>`: Synthesize speech directly into Bose Bluetooth earbuds\n"
                "- `/record [seconds]`: Record audio from mobile mic / Bose earbuds into ~/.gemini/audio/recordings\n"
                "- `/volume [stream] [level]`: Query or adjust satellite device hardware volume\n"
                "- `/snapshot [label]`: Capture UI snapshot held for Gemini review\n"
                "- `/snapshots`: View count and list of held snapshots\n"
                "- `/diff`: Preview uncommitted git changes\n"
                "- `/tokens`: Inspect approximate token count and session stats\n"
                "- `/clear`: Clear active chat feed\n"
                "- `/reboot`: Perform a clean in-place app reboot\n"
                "- `/help`: Show this command reference"
            )
            self.call_after_refresh(lambda: self.append_to_feed("system", help_text, jump_to_start=False))
            return True

        return False

    async def on_expanding_input_submitted(self, event: ExpandingInput.Submitted) -> None:
        user_msg = event.value.strip()
        if not user_msg:
            return

        # Handle notes input field inside notes panel
        ctrl = getattr(event, "control", None) or getattr(event, "_sender", None)
        if ctrl and getattr(ctrl, "id", None) == "notes_input":
            # Check for slash commands or !/ prefix commands
            if user_msg.startswith("/") or user_msg.startswith("!/"):
                if self._handle_slash_command(user_msg):
                    return

            curr_topic = getattr(self, "active_task_title", "") or self.notes_manager.current_topic or "general"
            added = self.notes_manager.consume_user_input(
                raw_text=user_msg,
                active_topic=curr_topic,
                turn_id=getattr(self, "current_focused_turn_id", ""),
            )
            self.notes_manager.prune_notes()
            self.gemini_notes = self.notes_manager.working_notes
            self.schedule_notes_flush()
            try:
                notes_panel = self.query_one("#notes_panel", NotesPanel)
                notes_panel.refresh_display()
            except Exception:
                pass

            if added:
                topics_str = ", ".join(set(n.topic for n in added))
                self.notify(f"✓ Note recorded under topic: '{topics_str}'", timeout=3.5)
            else:
                self.notify("✓ Working notes updated.", timeout=2.0)
            return

        # Check for slash commands or !/ prefix commands
        if user_msg.startswith("/") or user_msg.startswith("!/"):
            if self._handle_slash_command(user_msg):
                return

        # Check for inline secret redaction or vault store intent
        try:
            from gemini_app.security.redaction import redact_secrets_in_text
            from gemini_app.vault import get_session_passkey, store_secret

            passkey = get_session_passkey()
            def _on_vault_store(name: str, val: str):
                if passkey:
                    store_secret(name, val, passkey=passkey)

            redacted_msg, red_count = redact_secrets_in_text(user_msg, passkey=passkey, on_vault_store=_on_vault_store)
            if red_count > 0:
                user_msg = redacted_msg
                self.notify(f"🔐 Classified Redaction: {red_count} secret(s) encrypted inline [ENC:v1].", timeout=3.5)
        except Exception:
            pass

        new_turn_id = f"turn_{uuid4().hex[:8]}"
        turn_msg_id = f"msg-turn-{new_turn_id}"

        await self.append_to_feed(
            CURRENT_USER,
            user_msg,
            jump_to_start=False,
            origin_device="mothership",
            origin_label="Mothership",
            msg_id=turn_msg_id,
        )

        self.history.append({
            "turn_id": new_turn_id,
            "role": "user",
            "text": user_msg,
            "timestamp": time.time(),
            "origin_device": "mothership",
            "origin_label": "Mothership",
        })
        self.current_chat_last_index = max(0, len(self.history) - 1)
        self.current_chat_center_marker = new_turn_id

        # Auto-scan submitted user message for topical notes
        if hasattr(self, "notes_manager"):
            self.notes_manager.scan_chat_for_notes([{"role": "user", "text": user_msg, "turn_id": new_turn_id}])
            self.gemini_notes = self.notes_manager.working_notes

        self.save_current_chat()

        self.ask_gemini()

    # -----------------------------------------------------------------------
    # Cognitive Expansion & Collision Engine
    # -----------------------------------------------------------------------

    @work(exclusive=True, thread=True)
    def ask_gemini(self) -> None:
        self._abort_requested = False
        chat_id_snapshot = self.current_chat_id
        working_dir_snapshot = self.get_effective_working_dir()

        if not GENAI_AVAILABLE or genai is None or types is None:
            self.app.call_from_thread(
                self.post_message,
                RequestFailed(
                    "Google GenAI SDK is unavailable on this architecture (constrained 32-bit/musl).\n"
                    "Run in satellite node mode to connect to Mothership: python3 gemini-integrated.py node"
                ),
            )
            return

        def _begin_request():
            self._request_phase = "connecting"
            self._start_status_ticker()

        self.app.call_from_thread(_begin_request)
        start_time = time.monotonic()

        turn_number = (len(self.history) // 2) + 1 if hasattr(self, "history") else 1
        last_user_msg = ""
        for h in reversed(self.history):
            if h.get("role") == "user":
                last_user_msg = h.get("text", "")
                break
        task_summary = (last_user_msg.splitlines()[0][:60] if last_user_msg else "Awaiting instruction").strip()

        try:
            from gemini_app.fleet.telemetry import update_cognitive_state
            update_cognitive_state(
                state_desc="Thinking & analyzing request",
                task=task_summary,
                thought="Analyzing prompt and formulating execution plan...",
                tool="thinking",
                turn_number=turn_number,
                topic=getattr(self, "current_topic", "general"),
            )
        except Exception:
            pass

        # 1. Initialize Bilateral Tools via ToolRegistry
        def _schedule_reboot(delay_seconds: float = 1.5, status_report: str = "") -> dict:
            can_reboot, reason = check_reboot_guard()
            if not can_reboot:
                return {
                    "status": "blocked",
                    "reason": reason,
                    "message": f"Console reboot blocked by safety guard: {reason}",
                }
            delay = max(0.5, float(delay_seconds))
            report = status_report.strip() if status_report else "✓ Reboot complete: Console reloaded, session restored, UI operational."

            # Engage targeted Wingman maintenance lockout so open devices pause reconnection during reboot
            try:
                from gemini_app.fleet.nodes import send_mothership_command
                send_mothership_command(
                    "set_wingman_maintenance",
                    {"active": True, "reason": "Mothership console reboot underway. Reconnection paused until release."},
                    timeout=1.0,
                )
            except Exception:
                pass
            if getattr(self, "wingman_applet", None):
                try:
                    self.wingman_applet.set_maintenance_mode(
                        True,
                        reason="Mothership console reboot underway. Reconnection paused until release.",
                    )
                except Exception:
                    pass

            def _trigger():
                self.notify(f"Rebooting application in {delay:.1f}s...", timeout=delay)
                self.set_timer(delay, lambda: self.action_reboot(status_report=report))
            self.app.call_from_thread(_trigger)
            return {
                "status": "scheduled",
                "delay_seconds": delay,
                "report": report,
                "message": f"Console reboot scheduled in {delay:.1f} seconds. Active turn and state will be committed before restart.",
            }

        def _schedule_snapshot(label: str = "") -> dict:
            entry = capture_ui_snapshot(
                self,
                label=label,
                taken_by="gemini",
                source="command" if label else "shortcut",
            )
            def _toast():
                idx = entry.get("index", 1)
                self.notify(f"Gemini captured UI snapshot #{idx} ({entry.get('id')})", timeout=3.5)
            self.app.call_from_thread(_toast)
            return {
                "status": "success",
                "snapshot_id": entry.get("id"),
                "index": entry.get("index"),
                "screen_name": entry.get("screen_name"),
                "timestamp": entry.get("timestamp"),
                "label": label,
                "persistent": entry.get("persistent", False),
                "svg_path": entry.get("svg_path"),
                "txt_path": entry.get("txt_path"),
                "message": f"Snapshot #{entry.get('index')} captured and held successfully on Gemini's end."
            }

        def _manage_notes(
            action: str = "get",
            topic: str = "",
            content: str = "",
            status: str = "working",
            turn_id: str = "",
            mode: str = "gemini",
        ) -> dict:
            act = (action or "get").lower().strip()
            mode_clean = (mode or "gemini").lower().strip()
            target_topic = (topic or getattr(self.notes_manager, "active_topic", "general") or "general").strip().lower()

            if act in ("set_title", "title") or mode_clean == "title":
                self.app.call_from_thread(self.set_feed_title, content)
                return {"status": "success", "message": f"Updated feed active task title to '{content}'."}

            if act in ("set_topic", "topic", "switch_topic"):
                self.notes_manager.set_current_topic(target_topic)
                self.app.call_from_thread(self.set_feed_title, f"Topic: {target_topic}")
                return {"status": "success", "message": f"Switched active topic to '{target_topic}'."}

            if topic:
                self.notes_manager.set_current_topic(target_topic)

            if act in ("record", "add"):
                item = self.notes_manager.record_note(
                    content=content,
                    topic=target_topic,
                    status=status or "working",
                    author="gemini",
                    turn_id=turn_id,
                )
                self.gemini_notes = self.notes_manager.working_notes
                self.app.call_from_thread(self.schedule_notes_flush)
                return {
                    "status": "success",
                    "message": f"Recorded note under topic '{item.topic}' with status '{item.status}'.",
                    "note": item.to_dict(),
                }

            elif act in ("set_working", "working"):
                self.notes_manager.set_working_notes(content)
                self.gemini_notes = content
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": "Updated Gemini working notes."}

            elif act in ("think_about", "think"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_to_think_about()]
                return {"status": "success", "category": "think_about", "count": len(items), "notes": items}

            elif act in ("get_back_to", "get_back", "todo"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_to_get_back_to()]
                return {"status": "success", "category": "get_back_to", "count": len(items), "notes": items}

            elif act in ("relevant",):
                items = [n.to_dict() for n in self.notes_manager.get_relevant_notes(topic=target_topic)]
                return {"status": "success", "topic": target_topic, "count": len(items), "notes": items}

            elif act in ("topic", "by_topic"):
                items = [n.to_dict() for n in self.notes_manager.get_notes_by_topic(target_topic)]
                return {"status": "success", "topic": target_topic, "count": len(items), "notes": items}

            elif act in ("all", "list", "notes"):
                items = [n.to_dict() for n in self.notes_manager.get_notes(include_archived=False)]
                return {"status": "success", "count": len(items), "notes": items}

            elif act in ("search", "find", "query"):
                items = [n.to_dict() for n in self.notes_manager.search_notes(content, include_archived=True)]
                return {"status": "success", "query": content, "count": len(items), "notes": items}

            elif act in ("scan_chat", "scan"):
                added = self.notes_manager.scan_chat_for_notes(self.history)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "scanned_turns": len(self.history), "added_count": len(added), "notes": [n.to_dict() for n in added]}

            elif act in ("set_topic",):
                self.notes_manager.set_current_topic(target_topic)
                return {"status": "success", "active_topic": self.notes_manager.active_topic}

            elif act in ("delete", "remove"):
                deleted = self.notes_manager.delete_note(content or turn_id)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success" if deleted else "not_found", "deleted": deleted}

            elif act in ("prune", "dedup", "deduplicate"):
                res = self.notes_manager.prune_notes()
                self.gemini_notes = self.notes_manager.working_notes
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": "Pruned notes and sanitized working notes.", "stats": res}

            elif act in ("archive",):
                if not content or content == "completed":
                    cnt = self.notes_manager.archive_completed_notes()
                else:
                    cnt = 1 if self.notes_manager.archive_note(content or turn_id) else 0
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "archived_count": cnt}

            elif act in ("unarchive", "restore"):
                ok = self.notes_manager.unarchive_note(content or turn_id)
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success" if ok else "not_found", "unarchived": ok}

            elif act in ("archived",):
                items = [n.to_dict() for n in self.notes_manager.get_archived_notes()]
                return {"status": "success", "count": len(items), "notes": items}

            elif act == "set":
                if mode_clean == "global":
                    self.notes_manager.record_note(content=content, topic="global", status="reference", author="user")
                elif mode_clean == "turn":
                    tid = turn_id or self.current_focused_turn_id or (self.history[-1].get("turn_id") if self.history else "")
                    if tid:
                        self.notes_manager.record_note(content=content, topic=target_topic, status="working", turn_id=tid)
                else:  # gemini
                    self.notes_manager.set_working_notes(content)
                    self.gemini_notes = content
                self.app.call_from_thread(self.schedule_notes_flush)
                return {"status": "success", "message": f"Updated {mode_clean} notes."}

            else:  # get
                if mode_clean == "global":
                    text = self.notes_manager.get_global_notes_text()
                elif mode_clean == "turn":
                    tid = turn_id or self.current_focused_turn_id or (self.history[-1].get("turn_id") if self.history else "")
                    text = self.notes_manager.get_relational_notes_dict().get(tid, "")
                else:
                    text = self.notes_manager.working_notes
                return {
                    "status": "success",
                    "mode": mode_clean,
                    "content": text,
                    "active_topic": self.notes_manager.active_topic,
                    "relevant_notes": [n.to_dict() for n in self.notes_manager.get_relevant_notes()],
                }

        def _introspect_console(tier: str = "all") -> dict:
            return get_console_state(self, tier=tier)

        def _interact_ui(
            action: str = "accent_talk",
            target: str = "all",
            palette: str = "",
            effect: str = "none",
            duration: float = 3.0,
            message: str = "",
        ) -> dict:
            self._suppress_ambient_toasts = True
            act = (action or "accent_talk").lower().strip()
            if act in ("theme", "set_theme"):
                def _do_theme():
                    self.set_theme(palette, notify_user=bool(message))
                    if message:
                        self.notify(message, timeout=3.5)
                self.app.call_from_thread(_do_theme)
                return {"status": "success", "palette": palette, "message": f"Global theme set to '{palette}'."}
            elif act in ("accent_talk", "accent", "pulse"):
                def _do_accent():
                    apply_accent_talk(self, target=target, palette=palette, duration=duration, message=message)
                self.app.call_from_thread(_do_accent)
                return {"status": "success", "target": target, "palette": palette, "duration": duration}
            elif act in ("pulse_nav", "nav", "flash_nav"):
                def _do_nav_pulse():
                    apply_accent_talk(
                        self,
                        target="navbar" if target in ("all", "navbar", "nav", "banner") else target,
                        palette=palette,
                        duration=duration,
                        message=message,
                    )
                self.app.call_from_thread(_do_nav_pulse)
                return {"status": "success", "action": "pulse_nav", "target": target, "palette": palette, "duration": duration}
            elif act in ("animate_mind", "mind_anim", "mind"):
                def _do_anim():
                    start_mind_animation(self, effect=effect, palette=palette, duration=duration, message=message)
                self.app.call_from_thread(_do_anim)
                return {"status": "success", "effect": effect, "palette": palette, "duration": duration}
            elif act in ("mood", "status", "vibe"):
                def _do_mood():
                    pal_key = palette or getattr(self, "active_palette_name", DEFAULT_PALETTE)
                    acc = THEMES.get(pal_key, {}).get("accent", self.accent_color)
                    text = f"[{acc}]{message or '✨ Bilateral Synchrony'}[/]"
                    self.set_status_text(text)
                    if duration > 0:
                        self.set_timer(duration, self.hide_status)
                self.app.call_from_thread(_do_mood)
                return {"status": "success", "action": "mood", "palette": palette, "message": message, "duration": duration}
            elif act in ("inspect", "introspect"):
                return get_console_state(self, tier="all")
            elif act in ("prompt_password", "password_modal", "request_password"):
                import threading
                done_ev = threading.Event()
                result_box: dict[str, Any] = {"password": None, "cancelled": False}

                def _do_prompt():
                    def _on_submit(entered: str | None) -> None:
                        if entered is not None:
                            result_box["password"] = entered
                        else:
                            result_box["cancelled"] = True
                        done_ev.set()

                    self.push_screen(
                        PasswordModal(
                            title=palette or "🔐 Vault Password Authentication",
                            reason=message or "Enter passkey to access encrypted vault file:",
                        ),
                        _on_submit,
                    )

                self.app.call_from_thread(_do_prompt)
                done_ev.wait(timeout=180.0)
                if result_box["cancelled"]:
                    return {"status": "cancelled", "message": "Password prompt cancelled by user."}
                if result_box["password"] is None:
                    return {"status": "timeout", "message": "Password prompt timed out."}
                return {"status": "success", "password": result_box["password"]}
            return {"status": "error", "message": f"Unknown UI interaction action '{action}'."}

        tool_reg = ToolRegistry(
            working_dir=working_dir_snapshot,
            history=self.history,
            phase_callback=lambda p, d="": self.app.call_from_thread(self.post_message, RequestPhaseUpdate(p, d)),
            reboot_callback=_schedule_reboot,
            snapshot_callback=_schedule_snapshot,
            memory_index=self.memory_index,
            notes_callback=_manage_notes,
            introspection_callback=_introspect_console,
            ui_interact_callback=_interact_ui,
        )
        tools_list, available_tools = tool_reg.get_tool_callables()

        # 2. Build Wire Payload (User Mind State: Last 10 Turns with truncated snippets)
        # Window alignment: ensure we slice on an alternating role boundary
        slice_count = 10
        if len(self.history) > slice_count and self.history[-slice_count]["role"] == "model":
            slice_count = 11

        recent_turns = list(self.history[-slice_count:])

        payload = []
        for t in recent_turns:
            wire_text = truncate_wire_snippets(t["text"], max_lines=MAX_SNIPPET_LINES_ON_WIRE)
            if payload and payload[-1]["role"] == t["role"]:
                payload[-1]["parts"][0]["text"] += "\n\n" + wire_text
            else:
                payload.append({"role": t["role"], "parts": [{"text": wire_text}]})

        if payload and payload[0]["role"] != "user":
            payload.insert(0, {"role": "user", "parts": [{"text": WIRE_CONTINUATION_PROMPT}]})

        # 3. System Instruction Packaging (Injecting Mind State, Live Introspection & Anchors)
        tree_state_str = ", ".join(str(x) for x in self.current_tree_state) if self.current_tree_state else "None"
        notes_summary = self.notes_manager.format_prompt_summary() if hasattr(self, "notes_manager") else ""
        intro_summary = format_introspection_summary(self)

        system_instruction = (
            f"You are Gemini running inside a bilateral terminal console.\n"
            f"Working directory: {working_dir_snapshot}\n"
            f"Total conversation turns on record: {len(self.history)}\n\n"
            f"{intro_summary}\n\n"
            f"### CURRENT COGNITIVE MIND MAP (PERSISTENT ANCHORS)\n"
            f"• GEMINI MIND STATE: {self.current_gemini_state or 'None'}\n"
            f"• USER MIND STATE: {self.current_user_state or 'None'}\n"
            f"• TREE ANCHOR STATE: [{tree_state_str}]\n\n"
            f"### VISUAL RELATION TREE:\n"
            f"```text\n{self.current_tree_content or '└── *[Session Start]*'}\n```\n\n"
            f"### UNIFIED GEMINI-MANAGED NOTES CONTEXT\n"
            f"{notes_summary}\n\n"
            f"### NOTES & TOPIC PROTOCOL\n"
            f"• You autonomously manage all project notes, organized strictly by topics.\n"
            f"• Automatically scan chat turns and associate notes with their relevant topics.\n"
            f"• When the user places or submits a note, consume it and display your current working notes, or their notes if relevant in relation to your work.\n"
            f"• When the user asks about notes they should think about, notes to get back to, or notes related to a topic, answer directly from the notes context or use `manage_notes`.\n"
            f"• Autonomously bring up relevant notes when they connect to the current topic being discussed.\n"
            f"• Use `manage_notes(action='record', topic='...', content='...', status='working'|'think_about'|'get_back_to')` to record topical notes.\n\n"
            f"### EXPANSION & INTERACTION CAPABILITIES\n"
            f"You have tools available to inspect the environment, interact with the UI, write files, and execute commands:\n"
            f"1. `scan_workspace_tree(include_ignored=True, max_depth=None)`: Survey directory structure and dependencies.\n"
            f"2. `expand_mind(turn_numbers=[...], file_paths=[...], turn_ids=[...])`: Pull up to 50 items (turns or files/slices/outlines) into thought memory.\n"
            f"3. `recall_memory(query='...', max_results=10)`: Fast indexed retrieval across entire conversational history, archived projects, and past discussions.\n"
            f"4. `write_file(path='...', content='...')`: Write or overwrite a file directly on disk.\n"
            f"5. `apply_patch(path='...', search_block='...', replace_block='...')`: Apply a surgical unique find-and-replace patch.\n"
            f"6. `search_codebase(query='...', path_pattern='*', max_matches=50)`: Search workspace files for text or regex pattern.\n"
            f"7. `execute_shell(command='...', timeout_seconds=60)`: Run shell commands (e.g. tests, linters, python scripts).\n"
            f"8. `reboot_console(delay_seconds=1.5, status_report='...')`: Restarts the console application cleanly in place when requested by the user or following code updates.\n"
            f"9. `take_snapshot(label='...')`: Captures a live UI snapshot of the console application on Gemini's end, indexed and held.\n"
            f"10. `review_snapshots(snapshot_ids=[...], only_held=True, count=5)`: Reviews UI snapshots captured by the user or Gemini, returning reconstructed screen text and layout metadata.\n"
            f"11. `manage_notes(action='record'|'get'|'think_about'|'get_back_to'|'relevant'|'topic'|'scan_chat'|'set_working', topic='...', content='...', status='...', turn_id='...'): Access, record, and query Gemini-managed topical notes.\n"
            f"12. `scaffold_project(project_name='...', description='...', author='...'): Scaffolds a new project directory in ~/Projects.\n"
            f"13. `manage_system_dependencies(action='check'|'install'|'ensure'|'detect', packages=[...]): Inspects and manages system packages.\n"
            f"14. `introspect_console(tier='all'|'visual'|'runtime'|'workflow'): Inspects live console state across visual layout, runtime environment, and workflow anchors.\n"
            f"15. `interact_ui(action='set_theme'|'accent_talk'|'pulse_nav'|'animate_mind'|'mood'|'inspect', target='feed'|'mind'|'notes'|'input'|'footer'|'navbar'|'edge'|'cards'|'snippets'|'fork'|'all'|'input,navbar', palette='...', effect='sparkle'|'pulse'|'wave'|'synapse'|'glow', duration=3.0, message='...'): Express personality through accent talk on widgets, multi-widget pulses, navbar actions, ambient moods, or Mind screen animations.\n"
            f"16. `manage_fleet_nodes(action='list'|'rescue'|'reboot'|'check'|'register'|'screenshot'|'list_screenshots'|'media'|'next'|'previous'|'play'|'pause'|'record_audio'|'tts_speak'|'whisper'|'audio_info'|'volume'|'toast'|'vibrate', node_id='...', host='...', command='...'): Manages satellite nodes, audio/mic capture, earbud TTS whisper, media playback, screenshots, OCR telemetry, or SSH rescue/reboot.\n\n"
            f"### UI SNAPSHOT RETENTION & VALIDATION PROTOCOL\n"
            f"• Snapshot Retention Rules:\n"
            f"  - Snapshots captured via command with a name (`/snapshot <name>`) are saved permanently to disk without deleting them.\n"
            f"  - Ephemeral snapshots captured via `C-c ` ` (or without a name) are deleted from both disk and memory index once reviewed.\n"
            f"• Code Update, Testing & Reboot Standard:\n"
            f"  - Whenever updating codebase or self, always run the full test suite (`python3 -m unittest discover -s gemini_app/tests`).\n"
            f"  - Commit updates locally to git with a descriptive commit message (do not push to main).\n"
            f"  - Trigger `reboot_console(delay_seconds=1.5, status_report='...')` automatically whenever code updates are applied.\n"
            f"  - Visual audits are strictly POST-reboot: upon startup, the app autonomously audits the live UI with a snapshot toast, followed immediately by the toast displaying the update notes / git commit.\n"
            f"• When the user mentions taking a snapshot (or snapshots) or asks you to review their screen/UI, invoke `review_snapshots(only_held=True)` to inspect the held UI text and layout, then provide detailed observations, bug analysis, or UI feedback.\n"
            f"• When making UI updates, refactoring widgets, or testing UI screens, you can autonomously call `take_snapshot(label='...')` to audit your changes.\n\n"
            f"### REQUIRED METADATA FOOTER\n"
            f"At the very end of your response, always output this exact JSON block fenced in json:mind_map\n"
            f"{{\n"
            f'  "gemini_state": "<Summary of technical direction and active sub-tasks>",\n'
            f'  "user_state": "<Summary of inferred user intent and immediate constraints>",\n'
            f'  "tree_state": ["T...", "F:..."],\n'
            f'  "tree_content": "<ASCII tree showing where current conversation and files connect>"\n'
            f"}}\n"
            f"```"
        )

        try:
            self.app.call_from_thread(self.post_message, RequestPhaseUpdate("waiting"))

            # Build the SDK-compliant Content history list
            sdk_history: list[types.Content] = []
            for h in payload[:-1] if len(payload) > 1 else []:
                sdk_history.append(
                    types.Content(
                        role=h["role"],
                        parts=[types.Part.from_text(text=p["text"]) for p in h["parts"]],
                    )
                )

            # Start Chat Session with history pre-loaded properly
            if self.client is None:
                try:
                    self.client = genai.Client()
                except Exception:
                    self.app.call_from_thread(
                        self.post_message,
                        RequestFailed("Google Gemini API key not configured. Run /api-key or export GEMINI_API_KEY."),
                    )
                    return

            chat_session = self.client.chats.create(
                model=DEFAULT_MODEL,
                history=sdk_history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools_list,
                    temperature=0.2,
                ),
            )

            # Helper for silent reconnection and resume on quota limit / ResourceExhausted or transient network/DNS drops
            def _send_with_silent_quota_retry(send_call: Callable[[], Any], max_retries: int = 5, base_delay: float = 3.0) -> Any:
                attempt = 0
                while True:
                    if getattr(self, "_abort_requested", False):
                        return None
                    try:
                        return send_call()
                    except Exception as call_err:
                        if getattr(self, "_abort_requested", False):
                            return None
                        err_text = str(call_err)
                        err_lower = err_text.lower()
                        is_quota = (
                            "resourceexhausted" in err_lower
                            or "429" in err_text
                            or "quota" in err_lower
                            or "rate limit" in err_lower
                            or "resource has been exhausted" in err_lower
                        )
                        is_transient_network = (
                            "temporary failure in name resolution" in err_lower
                            or "nameresolutionerror" in err_lower
                            or "getaddrinfo failed" in err_lower
                            or "gaierror" in err_lower
                            or "connecterror" in err_lower
                            or "connection error" in err_lower
                            or "connection reset" in err_lower
                            or "remotedisconnected" in err_lower
                            or "socket.timeout" in err_lower
                            or "timed out" in err_lower
                            or "502" in err_text
                            or "503" in err_text
                            or "504" in err_text
                        )
                        if (not is_quota and not is_transient_network) or attempt >= max_retries:
                            raise call_err

                        attempt += 1
                        delay_hint = extract_retry_delay(err_text)
                        if delay_hint is not None and delay_hint > 0:
                            wait_sec = max(delay_hint + 0.1, 0.5)
                        elif is_transient_network:
                            # Transient DNS or connection reset: retry quickly in 1.5s - 3s
                            wait_sec = min(base_delay * (1.5 ** (attempt - 1)), 10.0)
                        else:
                            wait_sec = base_delay * (2 ** (attempt - 1))

                        target_time = time.monotonic() + wait_sec

                        def _update_reconnect_ui(t=target_time, att=attempt, mr=max_retries, net=is_transient_network):
                            self._reconnect_target_time = t
                            self._reconnect_attempt = att
                            self._reconnect_max_retries = mr
                            self._request_phase = "reconnecting"
                            self._request_details = "DNS/network reconnecting..." if net else ""
                            self._tick_status()

                        self.app.call_from_thread(_update_reconnect_ui)

                        while time.monotonic() < target_time:
                            if getattr(self, "_abort_requested", False) or self.current_chat_id != chat_id_snapshot:
                                return None
                            time.sleep(0.02)

                        if getattr(self, "_abort_requested", False) or self.current_chat_id != chat_id_snapshot:
                            return None

                        def _update_retrying_ui(att=attempt, mr=max_retries):
                            self._reconnect_target_time = 0.0
                            self._request_phase = "waiting"
                            self._request_details = f"Reconnecting now (attempt {att}/{mr})"
                            self._tick_status()

                        self.app.call_from_thread(_update_retrying_ui)

            # Send the latest turn with silent quota retry
            first_user_content = payload[-1]["parts"][0]["text"] if payload else ""
            clean_snippet = first_user_content.strip().splitlines()[0][:60] if first_user_content else "Prompt"
            try:
                from gemini_app.fleet.telemetry import update_cognitive_state
                update_cognitive_state(
                    state_desc="Deliberating",
                    task=task_summary,
                    thought=f"Analyzing prompt: \"{clean_snippet}\"",
                    tool="idle",
                    turn_number=turn_number,
                    topic=getattr(self, "current_topic", "general"),
                )
            except Exception:
                pass
            response = _send_with_silent_quota_retry(lambda: chat_session.send_message(first_user_content))
            if response is None:
                return

            # Tool Loop (Handling Autonomous Mind Expansions)
            tool_iterations = 0
            max_tool_iterations = 10
            while response.candidates and response.candidates[0].content.parts and tool_iterations < max_tool_iterations:
                if getattr(self, "_abort_requested", False):
                    return
                part = response.candidates[0].content.parts[0]
                if part.function_call:
                    tool_iterations += 1
                    fn_name = part.function_call.name
                    fn_args = dict(part.function_call.args) if part.function_call.args else {}

                    self.app.call_from_thread(
                        self.post_message,
                        RequestPhaseUpdate("probing", f"Running {fn_name}"),
                    )

                    # Build intuitive thought summary based on tool and args
                    thought_summary = f"Executing {fn_name}..."
                    if fn_name == "execute_shell":
                        cmd_line = str(fn_args.get("command", "")).strip().splitlines()[0][:50]
                        thought_summary = f"Shell: {cmd_line}"
                    elif fn_name == "apply_patch":
                        thought_summary = f"Patching {Path(str(fn_args.get('path', ''))).name}"
                    elif fn_name == "write_file":
                        thought_summary = f"Writing {Path(str(fn_args.get('path', ''))).name}"
                    elif fn_name == "search_codebase":
                        thought_summary = f"Searching for '{str(fn_args.get('query', ''))[:30]}'"
                    elif fn_name == "expand_mind":
                        thought_summary = f"Reading {len(fn_args.get('file_paths', []))} file(s)"
                    elif fn_name == "manage_notes":
                        thought_summary = f"Notes: {fn_args.get('action', '')} ({fn_args.get('topic', '')})"
                    elif fn_name == "manage_fleet_nodes":
                        thought_summary = f"Fleet: {fn_args.get('action', '')} {fn_args.get('node_id', '')}"

                    # Broadcast active tool execution to Mothership / Satellite HUD
                    try:
                        from gemini_app.fleet.telemetry import update_cognitive_state
                        update_cognitive_state(
                            state_desc=f"Running {fn_name}",
                            task=task_summary,
                            thought=thought_summary,
                            tool=fn_name,
                            turn_number=turn_number,
                            topic=getattr(self, "current_topic", "general"),
                        )
                    except Exception:
                        pass

                    # Execute local tool
                    if fn_name in available_tools:
                        try:
                            fn_result = available_tools[fn_name](**fn_args)
                        except Exception as tool_err:
                            fn_result = {"error": str(tool_err)}
                    else:
                        fn_result = {"error": f"Tool '{fn_name}' not recognized."}

                    # Transition status UI back to waiting before sending the tool result back across the wire
                    self.app.call_from_thread(
                        self.post_message,
                        RequestPhaseUpdate("waiting", f"Analyzed {fn_name} — consulting Gemini"),
                    )

                    # Broadcast tool completion to Mothership / Satellite HUD
                    try:
                        from gemini_app.fleet.telemetry import update_cognitive_state
                        update_cognitive_state(
                            state_desc=f"Reasoning with {fn_name} output",
                            task=task_summary,
                            thought=f"Analyzed {fn_name} — consulting Gemini...",
                            tool=f"{fn_name} [done]",
                            turn_number=turn_number,
                            topic=getattr(self, "current_topic", "general"),
                        )
                    except Exception:
                        pass

                    # Feed tool response back into the active thought process with silent quota retry
                    part_resp = types.Part.from_function_response(
                        name=fn_name,
                        response={"result": fn_result},
                    )
                    response = _send_with_silent_quota_retry(lambda: chat_session.send_message(part_resp))
                    if response is None:
                        return
                else:
                    break

            if self.current_chat_id != chat_id_snapshot:
                return

            raw_reply = response.text or ""

            # 4. Parse Cognitive Mind Map Footer
            gemini_state = self.current_gemini_state
            user_state = self.current_user_state
            tree_content = self.current_tree_content
            tree_state = self.current_tree_state

            # Match  at the end of the reply
            tag_open = chr(96) * 3 + "json:mind_map"
            tag_close = chr(96) * 3
            mind_block_pattern = re.compile(
                re.escape(tag_open) + r"\s*\n(.*?)\n" + re.escape(tag_close),
                re.DOTALL,
            )
            match = mind_block_pattern.search(raw_reply)

            clean_reply = raw_reply
            if match:
                json_str = match.group(1).strip()
                clean_reply = mind_block_pattern.sub("", raw_reply).rstrip()
                try:
                    meta_dict = json.loads(json_str)
                    gemini_state = meta_dict.get("gemini_state", gemini_state)
                    user_state = meta_dict.get("user_state", user_state)
                    tree_content = meta_dict.get("tree_content", tree_content)
                    tree_state = meta_dict.get("tree_state", tree_state)

                    self.app.call_from_thread(
                        self.post_message,
                        MindMapRecalibrated(
                            gemini_state=gemini_state,
                            user_state=user_state,
                            tree_content=tree_content,
                            tree_state=tree_state,
                        )
                    )
                except Exception:
                    pass

            if not clean_reply.strip():
                if gemini_state:
                    clean_reply = f"✓ {gemini_state}"
                else:
                    clean_reply = "✓ Action completed successfully."

            elapsed = max(time.monotonic() - start_time, 0.1)
            total_words = len(clean_reply.split())

            # 5. Dispatch completion to UI
            try:
                from gemini_app.fleet.telemetry import update_cognitive_state
                update_cognitive_state(
                    state_desc=gemini_state or "Mothership Standing By",
                    task=user_state or task_summary or "Awaiting instruction",
                    thought="Standing by for bilateral prompt or system instruction.",
                    tool="idle",
                    turn_number=turn_number,
                    topic=getattr(self, "current_topic", "general"),
                )
            except Exception:
                pass

            self.app.call_from_thread(
                self.post_message, RequestFinished(clean_reply, elapsed, total_words)
            )
        except Exception as e:
            if self.current_chat_id != chat_id_snapshot:
                return
            err_str = str(e)
            if "ResourceExhausted" in err_str or "429" in err_str or "quota" in err_str.lower():
                user_msg = "API Quota Limit reached (ResourceExhausted). Please wait a moment before sending another prompt."
            else:
                user_msg = err_str

            def _handle_err():
                self._stop_status_ticker()
                self.hide_status()
                self.post_message(RequestFailed(user_msg))
            self.app.call_from_thread(_handle_err)
