"""Autonomous safety supervisor and safe reboot rollback engine for Gemini console."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Optional, Tuple

from gemini_app.config import GEMINI_HOME, STATE_FILE


def get_current_git_commit(cwd: Path | str | None = None) -> Optional[str]:
    """Returns the current HEAD git commit hash, or None if git is unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or Path(__file__).resolve().parent.parent.parent),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def read_state() -> dict[str, Any]:
    """Reads ~/.gemini/state.json safely."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_state(data: dict[str, Any]) -> None:
    """Writes ~/.gemini/state.json atomically."""
    try:
        STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass


def record_stable_commit(commit_sha: Optional[str] = None, cwd: Path | str | None = None) -> Optional[str]:
    """Records a known working commit hash into state.json."""
    sha = commit_sha or get_current_git_commit(cwd)
    if sha:
        state = read_state()
        state["last_stable_commit"] = sha
        write_state(state)
    return sha


def get_last_stable_commit() -> Optional[str]:
    """Retrieves the last known stable commit hash from state.json."""
    state = read_state()
    return state.get("last_stable_commit")


def mark_reboot_in_progress(target_commit: Optional[str] = None) -> None:
    """Flags that a reboot has been initiated with pending startup validation."""
    state = read_state()
    state["reboot_in_progress"] = True
    state["reboot_target_commit"] = target_commit or get_current_git_commit()
    state["reboot_timestamp"] = time.time()
    write_state(state)


def mark_startup_successful(cwd: Path | str | None = None) -> None:
    """Marks startup as verified and promotes current HEAD to last_stable_commit."""
    state = read_state()
    state["reboot_in_progress"] = False
    state.pop("reboot_target_commit", None)
    curr = get_current_git_commit(cwd)
    if curr:
        state["last_stable_commit"] = curr
    write_state(state)


def is_reboot_in_progress() -> bool:
    """Returns True if a reboot is currently undergoing startup validation."""
    state = read_state()
    return bool(state.get("reboot_in_progress"))


def perform_git_rollback(cwd: Path | str | None = None) -> Tuple[bool, str]:
    """Rolls back the repository working tree to the last known stable commit."""
    target_sha = get_last_stable_commit()
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)

    if not target_sha:
        return False, "No previous stable commit recorded in state.json to roll back to."

    try:
        # 1. Hard reset to stable commit
        reset_res = subprocess.run(
            ["git", "reset", "--hard", target_sha],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if reset_res.returncode != 0:
            return False, f"Git reset failed: {reset_res.stderr.strip()}"

        # 2. Clean untracked artifacts created during failed edit
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )

        state = read_state()
        state["reboot_in_progress"] = False
        state["pending_reboot_report"] = (
            f"⚠️ Startup Failure Detected! Automatically rolled back to last stable commit ({target_sha[:8]})."
        )
        write_state(state)

        return True, f"Successfully rolled back working tree to {target_sha[:8]}."
    except Exception as e:
        return False, f"Rollback error: {e}"


def run_with_guardian(app_launcher: Callable[[], Any], cwd: Path | str | None = None) -> None:
    """Executes the application launcher wrapped in startup crash detection and auto-rollback."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    rebooting = is_reboot_in_progress()

    try:
        # Execute application
        app_launcher()
    except Exception as exc:
        if rebooting:
            sys.stderr.write(f"\n[GUARDIAN] Startup exception detected during reboot: {exc}\n")
            sys.stderr.write("[GUARDIAN] Initiating automatic git rollback to last stable commit...\n")
            success, msg = perform_git_rollback(cwd=working_dir)
            sys.stderr.write(f"[GUARDIAN] Rollback result: {msg}\n")
            if success:
                # Re-exec Python with the rolled-back clean code
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception:
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(1)
        # If not rebooting or rollback failed, re-raise
        raise
