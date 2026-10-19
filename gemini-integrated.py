#!/usr/bin/env python3
"""Runner script for the modular Gemini Bilateral Terminal Console.

Autonomously bootstraps virtual environment, pip dependencies,
system dependencies, and API key on first launch.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def ensure_environment() -> None:
    """Ensures a virtual environment exists with required packages and re-execs inside it if needed."""
    # Check if already running in a virtualenv with textual installed
    in_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
    if in_venv:
        try:
            import textual
            import google.genai
            import rich
            import pyperclip
            return  # Environment is fully operational
        except ImportError:
            pass

    script_dir = Path(__file__).resolve().parent
    venv_dir = script_dir / ".venv"
    if not venv_dir.exists():
        try:
            venv_dir.mkdir(parents=True, exist_ok=True)
            venv_dir.rmdir()
        except OSError:
            venv_dir = Path.home() / ".gemini" / "venv"

    venv_python = venv_dir / "bin" / "python3"

    if not venv_python.exists():
        sys.stdout.write("⚡ First-time launch: Initializing virtual environment (.venv)...\n")
        try:
            import venv
            venv.create(str(venv_dir), with_pip=True, clear=False)
        except Exception:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    # Check dependencies in venv
    req_check = subprocess.run(
        [str(venv_python), "-c", "import textual, google.genai, rich, pyperclip"],
        capture_output=True,
    )
    if req_check.returncode != 0:
        sys.stdout.write("⚡ Installing required pip packages into .venv...\n")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "-q", "pip", "setuptools", "wheel"],
            check=False,
        )
        pkg_list = ["textual>=0.50.0", "google-genai>=1.0.0", "rich>=13.0.0", "pyperclip>=1.8.0"]
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q"] + pkg_list,
            check=True,
        )
        sys.stdout.write("✓ Virtual environment & dependencies ready.\n")

    # If we are not currently running under venv_python, re-exec into venv
    if Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])


if __name__ == "__main__":
    ensure_environment()
    from gemini_app.main import main
    main()
