"""Command execution tool for running shell commands safely inside the working directory."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any


def execute_shell(working_dir: str | Path, command: str, timeout_seconds: int = 60) -> dict[str, Any]:
    """Executes a shell command inside the working directory and returns stdout, stderr, and exit_code."""
    try:
        working_path = Path(os.path.expanduser(str(working_dir).strip())).resolve()
        env = os.environ.copy()
        venv_bin = Path("/opt/gemini/.venv/bin")
        if venv_bin.exists():
            env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = str(venv_bin.parent)

        # Enforce non-interactive environment to isolate child processes from the controlling terminal
        # and prevent sudo/apt/git from prompting on /dev/tty, corrupting row 0, or intercepting keystrokes.
        env["DEBIAN_FRONTEND"] = "noninteractive"
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["SUDO_PROMPT"] = ""
        env["PYTHONUNBUFFERED"] = "1"

        res = subprocess.run(
            command,
            shell=True,
            cwd=str(working_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Command timed out after {timeout_seconds}s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
