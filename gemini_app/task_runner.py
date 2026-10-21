"""Bilateral Task Runner & Status Reporting Service.

Enables background processes, build runners, and external jobs to report live progress
directly into the Gemini Console UI:
- Updates the active status area (#feed_status)
- Dispatches animated toast notifications
- Pulses navbar accent indicators
- Injects final completion or progress updates directly into the conversational Chat Feed
"""

import argparse
import json
import socket
import sys
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional

from gemini_app.config import ACTIVE_TASK_FILE, GEMINI_HOME, SOCKET_PATH

TASK_LOG_PATH = GEMINI_HOME / "task_runner.log"


def send_console_event(payload: Dict[str, Any], timeout: float = 2.0) -> bool:
    """Sends a JSON event packet to the active Gemini Textual socket server.

    Returns True if successfully received and acknowledged by the UI,
    or False if the console is offline/unreachable (logging to fallback file).
    """
    if not SOCKET_PATH.exists():
        _log_fallback(payload, "Socket does not exist")
        return False

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(SOCKET_PATH))
            msg_bytes = json.dumps(payload).encode("utf-8")
            client.sendall(msg_bytes)
            try:
                raw_resp = client.recv(4096)
                if raw_resp:
                    resp = json.loads(raw_resp.decode("utf-8"))
                    return resp.get("status") == "ok"
            except Exception:
                pass
            return True
    except Exception as e:
        _log_fallback(payload, str(e))
        return False


def _log_fallback(payload: Dict[str, Any], reason: str) -> None:
    """Appends un-sent console events to task_runner.log for auditing."""
    try:
        TASK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"reason": reason, "payload": payload}) + "\n")
    except Exception:
        pass


def update_status(
    text: str = "",
    toast: Optional[str] = None,
    title: str = "",
    severity: str = "information",
    pulse_nav: bool = False,
    color: Optional[str] = None,
    clear: bool = False,
    duration: float = 3.5,
) -> bool:
    """Updates the console's live status bar, with optional toast and navbar pulse."""
    if clear:
        try:
            if ACTIVE_TASK_FILE.exists():
                ACTIVE_TASK_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    elif text:
        try:
            ACTIVE_TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
            task_info = {
                "pid": os.getpid(),
                "text": text,
                "timestamp": time.time(),
            }
            ACTIVE_TASK_FILE.write_text(json.dumps(task_info), encoding="utf-8")
        except Exception:
            pass

    payload: Dict[str, Any] = {
        "action": "status",
        "text": text,
        "clear": clear,
    }
    if toast:
        payload["toast"] = toast
        payload["title"] = title
        payload["severity"] = severity
        payload["duration"] = duration
    if pulse_nav:
        payload["pulse_nav"] = True
        if color:
            payload["palette"] = color

    return send_console_event(payload)


def notify_chat(
    text: str,
    role: str = "gemini",
    toast: Optional[str] = None,
    title: str = "Task Complete",
    pulse_nav: bool = True,
) -> bool:
    """Posts a message card directly into the chat feed and updates chat history."""
    payload: Dict[str, Any] = {
        "action": "notify_chat",
        "text": text,
        "role": role,
        "pulse_nav": pulse_nav,
    }
    if toast:
        payload["toast"] = toast
        payload["title"] = title

    return send_console_event(payload)


def clear_status() -> bool:
    """Clears the live status bar in the console."""
    try:
        if ACTIVE_TASK_FILE.exists():
            ACTIVE_TASK_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return send_console_event({"action": "status", "clear": True})


def cli_main(argv: Optional[list] = None) -> int:
    """CLI entry point for task reporting from shell scripts and background runners."""
    parser = argparse.ArgumentParser(
        prog="gemini-status",
        description="Gemini Bilateral Status & Chat Notification Tool",
    )
    parser.add_argument("text", nargs="?", default="", help="Status text or notification message")
    parser.add_argument("--toast", "-t", help="Popup toast notification message")
    parser.add_argument("--title", default="", help="Title for toast notification")
    parser.add_argument(
        "--severity",
        choices=["information", "warning", "error"],
        default="information",
        help="Toast severity level",
    )
    parser.add_argument("--chat", "-c", help="Inject message directly into conversation feed")
    parser.add_argument("--pulse", "-p", action="store_true", help="Pulse top navbar indicator")
    parser.add_argument("--color", default="cyan", help="Color palette for navbar pulse")
    parser.add_argument("--clear", action="store_true", help="Clear status line")
    parser.add_argument("--duration", type=float, default=3.5, help="Toast timeout duration")

    args = parser.parse_args(argv)

    if args.clear:
        clear_status()
        return 0

    if args.chat:
        notify_chat(
            text=args.chat,
            toast=args.toast,
            title=args.title or "Task Complete",
            pulse_nav=args.pulse,
        )
        return 0

    if args.text or args.toast:
        update_status(
            text=args.text,
            toast=args.toast,
            title=args.title,
            severity=args.severity,
            pulse_nav=args.pulse,
            color=args.color,
            duration=args.duration,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(cli_main())
