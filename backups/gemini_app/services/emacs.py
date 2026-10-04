"""Emacsclient IPC and window management."""

import json
import subprocess


def get_emacs_frames() -> list[dict]:
    """Queries Emacs for active frames and their open windows."""
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


def send_to_emacs_buffer(code_text: str, target_buf: str | None = None) -> bool:
    """Injects text into target buffer, or active window if None."""
    try:
        escaped_text = json.dumps(code_text)
        if target_buf:
            escaped_buf = json.dumps(target_buf)
            elisp = f"(gemini-insert-into-window {escaped_buf} {escaped_text})"
        else:
            elisp = f"(with-current-buffer (window-buffer (selected-window)) (insert {escaped_text}))"

        res = subprocess.run(
            ["emacsclient", "--eval", elisp],
            capture_output=True,
            timeout=1,
        )
        return res.returncode == 0
    except Exception:
        return False
