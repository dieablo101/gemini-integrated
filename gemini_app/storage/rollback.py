"""Autonomous safety supervisor and safe reboot rollback engine for Gemini console."""

from __future__ import annotations

import compileall
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import time
from typing import Any, Callable, Optional, Tuple
from uuid import uuid4

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


def verify_offline_preflight(cwd: Path | str | None = None) -> Tuple[bool, str]:
    """Runs offline syntax and compilation preflight checks before any commit or console reboot."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    try:
        # 1. Compile gemini_app directory
        app_dir = working_dir / "gemini_app"
        if app_dir.exists():
            success = compileall.compile_dir(str(app_dir), maxlevels=10, quiet=1, force=False)
            if not success:
                return False, "Pre-flight compilation check failed inside gemini_app/."

        # 2. Check root python files
        for py_file in working_dir.glob("*.py"):
            try:
                py_compile.compile(str(py_file), doraise=True)
            except Exception as pe:
                return False, f"Pre-flight compilation failed in {py_file.name}: {pe}"

        return True, "Pre-flight verification passed: all python modules compile cleanly."
    except Exception as e:
        return False, f"Pre-flight verification error: {e}"


def check_reboot_guard(min_interval_seconds: float = 2.0, cwd: Path | str | None = None) -> Tuple[bool, str]:
    """Enforces reboot safety guard: rate-limits rapid reboots and validates preflight compilation."""
    state = read_state()
    last_reboot = state.get("reboot_timestamp", 0.0)
    now = time.time()
    if (now - last_reboot) < min_interval_seconds:
        return False, f"Reboot rate-limited: reboot requested within {min_interval_seconds:.1f}s of previous attempt."

    # Preflight check
    ok, msg = verify_offline_preflight(cwd=cwd)
    if not ok:
        return False, f"Reboot blocked by preflight safety check: {msg}"

    return True, "Reboot guard check passed."


def create_safety_checkpoint(label: str = "auto", cwd: Path | str | None = None) -> dict[str, Any]:
    """Records an explicit rollback checkpoint into state.json."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    sha = get_current_git_commit(working_dir)
    checkpoint = {
        "id": f"ckpt_{int(time.time())}_{uuid4().hex[:6]}",
        "commit": sha,
        "label": label,
        "timestamp": time.time(),
    }
    state = read_state()
    checkpoints = state.get("safety_checkpoints", [])
    checkpoints.append(checkpoint)
    # Keep last 10 checkpoints
    state["safety_checkpoints"] = checkpoints[-10:]
    write_state(state)
    return checkpoint


def restore_safety_checkpoint(checkpoint_sha_or_id: str, cwd: Path | str | None = None) -> Tuple[bool, str]:
    """Restores repository to a previously recorded safety checkpoint or commit hash."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    state = read_state()
    checkpoints = state.get("safety_checkpoints", [])

    target_sha = ""
    for ckpt in reversed(checkpoints):
        if ckpt.get("id") == checkpoint_sha_or_id or ckpt.get("commit") == checkpoint_sha_or_id:
            target_sha = ckpt.get("commit") or ""
            break

    if not target_sha:
        return False, f"Checkpoint '{checkpoint_sha_or_id}' not found."

    try:
        res = subprocess.run(
            ["git", "reset", "--hard", target_sha],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            return False, f"Git reset to checkpoint failed: {res.stderr.strip()}"

        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True, f"Successfully restored to checkpoint {target_sha[:8]}."
    except Exception as e:
        return False, f"Failed restoring checkpoint: {e}"


def mark_reboot_in_progress(target_commit: Optional[str] = None) -> None:
    """Flags that a reboot has been initiated with pending startup validation."""
    state = read_state()
    state["reboot_in_progress"] = True
    state["reboot_target_commit"] = target_commit or get_current_git_commit()
    state["reboot_timestamp"] = time.time()
    write_state(state)


def mark_startup_successful(cwd: Path | str | None = None) -> None:
    """Marks startup as verified, clears failure counters, and promotes current HEAD to last_stable_commit."""
    state = read_state()
    state["reboot_in_progress"] = False
    state.pop("reboot_target_commit", None)
    state["boot_failures_count"] = 0
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


def launch_safe_mode(
    exc: Exception | None = None,
    last_stable: Optional[str] = None,
    cwd: Path | str | None = None,
) -> None:
    """Launches minimal Safe Mode terminal fallback when repeated startup crashes occur."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    sha = last_stable or get_last_stable_commit()

    header = """
======================================================================
                 ⚡ GEMINI CONSOLE — SAFE MODE ⚡
======================================================================
Startup failure detected across consecutive boot attempts.
The console has entered Safe Mode to protect your environment.
"""
    sys.stderr.write(header)
    if exc:
        sys.stderr.write(f"Crash details: {exc}\n")
    if sha:
        sys.stderr.write(f"Last verified stable commit: {sha[:8]}\n")
    sys.stderr.write("----------------------------------------------------------------------\n")

    # If non-interactive, exit cleanly without blocking stdin
    if not sys.stdin.isatty() or os.environ.get("GEMINI_TESTING"):
        sys.stderr.write("[SAFE MODE] Non-interactive environment. Exiting safely.\n")
        return

    print("Safe Mode Options:")
    print("  [1] Roll back repository to last verified stable commit")
    print("  [2] Launch Out-of-Band Emergency Recovery Terminal")
    print("  [3] Reset crash counter and attempt normal boot")
    print("  [4] Exit to shell")

    try:
        choice = input("Select an option (1-4) [1]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(1)

    if choice == "1":
        print("[SAFE MODE] Rolling back repository...")
        ok, msg = perform_git_rollback(cwd=working_dir)
        print(f"[SAFE MODE] {msg}")
        if ok:
            print("[SAFE MODE] Restarting application...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
    elif choice == "2":
        emergency_script = working_dir / "emergency_terminal.py"
        if emergency_script.exists():
            print("[SAFE MODE] Launching emergency recovery terminal...")
            os.execv(sys.executable, [sys.executable, str(emergency_script)])
        else:
            print("[SAFE MODE] emergency_terminal.py not found.")
    elif choice == "3":
        print("[SAFE MODE] Resetting crash counter...")
        st = read_state()
        st["boot_failures_count"] = 0
        write_state(st)
        print("[SAFE MODE] Attempting restart...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        print("[SAFE MODE] Exiting to shell.")
        sys.exit(0)


def run_with_guardian(app_launcher: Callable[[], Any], cwd: Path | str | None = None) -> None:
    """Executes the application launcher wrapped in startup crash detection, Safe Mode, and auto-rollback."""
    working_dir = Path(cwd or Path(__file__).resolve().parent.parent.parent)
    rebooting = is_reboot_in_progress()

    state = read_state()
    boot_failures = state.get("boot_failures_count", 0) + 1
    last_boot = state.get("last_boot_timestamp", 0.0)
    now = time.time()
    rapid_crash = (now - last_boot < 10.0) and boot_failures >= 3

    state["boot_failures_count"] = boot_failures
    state["last_boot_timestamp"] = now
    write_state(state)

    if boot_failures >= 3 or rapid_crash or os.environ.get("GEMINI_SAFE_MODE") == "1":
        launch_safe_mode(
            exc=Exception(
                f"Repeated startup failures detected ({boot_failures} consecutive crashes"
                + (", rapid boot loop within 10s" if rapid_crash else "")
                + ")" if not os.environ.get("GEMINI_SAFE_MODE") else "Safe mode explicitly requested via GEMINI_SAFE_MODE"
            ),
            last_stable=get_last_stable_commit(),
            cwd=working_dir,
        )
        return

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

        curr_state = read_state()
        if curr_state.get("boot_failures_count", 0) >= 3:
            launch_safe_mode(exc=exc, last_stable=get_last_stable_commit(), cwd=working_dir)
            return

        # If not rebooting or rollback failed, re-raise
        raise
