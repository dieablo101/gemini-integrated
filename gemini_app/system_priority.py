"""System-level scheduling and I/O priority management for Gemini console.

Ensures the console process maintains high CPU and I/O scheduling priority
ahead of concurrent CPU-heavy workloads (such as Godot engine, compilers, or 3D games),
preventing stutter or startup lag during in-place reboots and live streaming.
Uses Linux RealtimeKit (RTKit via DBus) or native nice/ioprio syscalls.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Optional


def _get_ioprio_syscall_num() -> int:
    """Returns the platform-specific syscall number for SYS_ioprio_set."""
    machine = platform.machine().lower()
    if "x86_64" in machine or "amd64" in machine:
        return 251
    elif "aarch64" in machine or "arm64" in machine:
        return 30
    elif "arm" in machine:
        return 314
    elif "i386" in machine or "i686" in machine:
        return 289
    return 251


def elevate_system_priority(
    target_nice: int = -10,
    pid: Optional[int] = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Elevates CPU nice scheduling and I/O priority for the specified process (default: current PID).

    Tries native os.setpriority first, then falls back to freedesktop RealtimeKit (RTKit)
    via DBus which grants high priority without requiring root or sudo.
    Also elevates I/O scheduling class to Best-Effort Level 0.
    """
    target_pid = pid if pid is not None else os.getpid()
    res: dict[str, Any] = {
        "pid": target_pid,
        "target_nice": target_nice,
        "initial_nice": 0,
        "current_nice": 0,
        "nice_elevated": False,
        "nice_method": "none",
        "ioprio_class": "unknown",
        "ioprio_level": -1,
        "ioprio_method": "none",
        "status": "standard",
    }

    if platform.system().lower() != "linux":
        res["status"] = "unsupported_platform"
        return res

    # 1. Inspect initial nice level
    try:
        initial_nice = os.getpriority(os.PRIO_PROCESS, target_pid)
        res["initial_nice"] = initial_nice
        res["current_nice"] = initial_nice
    except Exception as e:
        res["initial_error"] = str(e)
        return res

    # If already at or better than target nice, mark as elevated
    if initial_nice <= target_nice:
        res["nice_elevated"] = True
        res["nice_method"] = "inherited"

    # 2. Try direct os.setpriority
    if not res["nice_elevated"]:
        try:
            os.setpriority(os.PRIO_PROCESS, target_pid, target_nice)
            res["nice_elevated"] = True
            res["nice_method"] = "os.setpriority"
        except (PermissionError, OSError):
            pass

    # 3. If direct os.setpriority failed, use freedesktop RealtimeKit (RTKit)
    if not res["nice_elevated"]:
        for cand_nice in [target_nice, -5, -2]:
            try:
                cmd = [
                    "busctl", "call",
                    "org.freedesktop.RealtimeKit1",
                    "/org/freedesktop/RealtimeKit1",
                    "org.freedesktop.RealtimeKit1",
                    "MakeThreadHighPriorityWithPID",
                    "tti", str(target_pid), str(target_pid),
                    "--", str(cand_nice),
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if proc.returncode == 0:
                    res["nice_elevated"] = True
                    res["nice_method"] = "rtkit_dbus"
                    break
            except Exception:
                pass

    # Update current nice
    try:
        res["current_nice"] = os.getpriority(os.PRIO_PROCESS, target_pid)
        if res["current_nice"] < initial_nice:
            res["nice_elevated"] = True
    except Exception:
        pass

    # 4. Elevate I/O priority to Best-Effort (Class 2), Priority 0 (highest best effort)
    # IOPRIO_WHO_PROCESS = 1, IOPRIO_CLASS_BE = 2 -> (2 << 13) | 0 = 16384
    ioprio_val = (2 << 13) | 0
    ioprio_success = False

    try:
        libc = None
        try:
            libc = ctypes.CDLL(None)
        except Exception:
            libc = ctypes.CDLL("libc.so.6")

        if libc and hasattr(libc, "syscall"):
            sys_num = _get_ioprio_syscall_num()
            # int ioprio_set(int which, int who, int ioprio)
            # who = 0 means current process if target_pid == current PID, else target_pid
            who_val = 0 if target_pid == os.getpid() else target_pid
            ret = libc.syscall(sys_num, 1, who_val, ioprio_val)
            if ret == 0:
                ioprio_success = True
                res["ioprio_method"] = "libc_syscall"
                res["ioprio_class"] = "best-effort"
                res["ioprio_level"] = 0
    except Exception:
        pass

    # Fallback to ionice CLI
    if not ioprio_success:
        try:
            proc = subprocess.run(
                ["ionice", "-c", "2", "-n", "0", "-p", str(target_pid)],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if proc.returncode == 0:
                ioprio_success = True
                res["ioprio_method"] = "ionice_cli"
                res["ioprio_class"] = "best-effort"
                res["ioprio_level"] = 0
        except Exception:
            pass

    res["status"] = "elevated" if res["nice_elevated"] else ("improved" if res["current_nice"] < 0 else "standard")
    return res


def get_system_priority(pid: Optional[int] = None) -> dict[str, Any]:
    """Inspects the current CPU nice level, scheduler priority, and I/O scheduling class."""
    target_pid = pid if pid is not None else os.getpid()
    info: dict[str, Any] = {
        "pid": target_pid,
        "nice": 0,
        "ioprio": "unknown",
        "is_high_priority": False,
    }

    try:
        current_nice = os.getpriority(os.PRIO_PROCESS, target_pid)
        info["nice"] = current_nice
        info["is_high_priority"] = (current_nice < 0)
    except Exception:
        pass

    try:
        proc = subprocess.run(
            ["ionice", "-p", str(target_pid)],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if proc.returncode == 0 and proc.stdout:
            info["ioprio"] = proc.stdout.strip()
    except Exception:
        pass

    return info


def format_priority_summary(pid: Optional[int] = None) -> str:
    """Formats a concise single-line summary of system scheduling priority."""
    p = get_system_priority(pid)
    nice_val = p.get("nice", 0)
    ioprio = p.get("ioprio", "unknown")
    high = p.get("is_high_priority", False)

    indicator = "⚡ High Priority" if high else "⚙ Normal Priority"
    return f"{indicator} (nice: {nice_val}, I/O: {ioprio}, PID: {p.get('pid')})"
