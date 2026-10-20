#!/usr/bin/env python3
"""Runner script for the modular Gemini Bilateral Terminal Console.

Autonomously bootstraps virtual environment, pip dependencies,
system dependencies, and API key on first launch.
Handles subcommands (satellite/node, mothership, probe) cleanly
without requiring heavy UI or API dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import sys


def is_constrained_platform() -> bool:
    """Detects whether running on a constrained, emulated, or 32-bit platform."""
    if sys.maxsize <= 2**32:
        return True
    if os.path.exists("/proc/ish"):
        return True
    try:
        u = platform.uname()
        if "ish" in u.release.lower() or "ish" in u.version.lower():
            return True
    except Exception:
        pass
    if Path("/mnt/ipad").exists():
        return True
    if platform.machine().lower() in ("i386", "i686", "armv7l", "armv6l", "armhf", "aarch32"):
        return True
    return False


def ensure_environment() -> None:
    """Ensures a virtual environment exists with required packages and re-execs inside it if needed."""
    constrained = is_constrained_platform()

    # Check if already running in a virtualenv with required packages
    in_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
    if in_venv:
        try:
            import textual
            import rich
            import pyperclip
            if not constrained:
                import google.genai
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
    check_code = (
        "import textual, rich, pyperclip"
        if constrained
        else "import textual, google.genai, rich, pyperclip"
    )
    req_check = subprocess.run(
        [str(venv_python), "-c", check_code],
        capture_output=True,
    )
    if req_check.returncode != 0:
        if constrained:
            sys.stdout.write("⚡ Constrained architecture detected. Installing pure-wheel UI packages...\n")
            pkg_list = ["textual>=0.50.0", "rich>=13.0.0", "pyperclip>=1.8.0"]
        else:
            sys.stdout.write("⚡ Installing required pip packages into .venv...\n")
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--upgrade", "-q", "pip", "setuptools", "wheel"],
                check=False,
            )
            pkg_list = ["textual>=0.50.0", "google-genai>=1.0.0", "rich>=13.0.0", "pyperclip>=1.8.0"]

        try:
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-q"] + pkg_list,
                check=True,
            )
            sys.stdout.write("✓ Virtual environment & dependencies ready.\n")
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(f"Warning: pip install failed ({exc}). Continuing with available packages.\n")

    # If we are not currently running under venv_python, re-exec into venv
    if Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])


def print_help() -> None:
    """Displays command-line help for gemini-integrated."""
    help_text = """Gemini Integrated Bilateral Terminal Console

Usage:
  python3 gemini-integrated.py [options]
  python3 gemini-integrated.py node [options]
  python3 gemini-integrated.py mothership [options]

Subcommands:
  node, satellite         Run as lightweight distributed satellite node
  mothership              Run fleet mothership command-and-control server

Node Options:
  --mothership HOST       Mothership IP/host (default: 192.168.1.90)
  --port PORT             Mothership TCP port (default: 7331)
  --interval SECONDS      Heartbeat telemetry interval in seconds (default: 15.0)
  --once                  Send single registration/telemetry probe and exit
  --node-id ID            Override satellite node identifier

General Options:
  -h, --help              Show this help message and exit
  -v, --version           Show version information and exit
  --satellite             Shorthand for running in satellite node mode
  --ui                    Force local terminal UI even on constrained platforms
"""
    print(help_text.strip())


if __name__ == "__main__":
    # 1. First parse high-level flags and subcommands before touching venv or packages
    argv_set = set(sys.argv[1:])

    if "-h" in argv_set or "--help" in argv_set:
        print_help()
        sys.exit(0)

    if "-v" in argv_set or "--version" in argv_set:
        from gemini_app import __version__
        print(f"gemini-integrated v{__version__}")
        sys.exit(0)

    # 2. Check for node/satellite mode anywhere in CLI arguments
    satellite_tokens = {"--node", "-n", "--satellite", "node", "satellite"}
    matched_sat = [tok for tok in sys.argv[1:] if tok in satellite_tokens]
    if matched_sat:
        for tok in matched_sat:
            sys.argv.remove(tok)
        from gemini_app.fleet.satellite import main as satellite_main
        sys.exit(satellite_main())

    # 3. Check for mothership server mode
    mothership_tokens = {"--mothership-server", "--fleet-server", "mothership"}
    matched_mother = [tok for tok in sys.argv[1:] if tok in mothership_tokens]
    if matched_mother:
        for tok in matched_mother:
            sys.argv.remove(tok)
        from gemini_app.fleet.mothership import main as mothership_main
        sys.exit(mothership_main())

    # 4. If on a constrained platform without google-genai, auto-route gracefully
    if is_constrained_platform():
        try:
            import google.genai
        except ImportError:
            # Check if user specified --ui explicitly
            if "--ui" not in sys.argv:
                sys.stdout.write(
                    "⚡ Constrained mobile platform detected (iPad iSH / 32-bit musl).\n"
                    "   Local Google GenAI SDK requires Rust wheels not supported on this device.\n"
                    "   Auto-launching Satellite Node to connect with Mothership...\n"
                    "   (Pass --ui to force local terminal UI)\n\n"
                )
                from gemini_app.fleet.satellite import main as satellite_main
                sys.exit(satellite_main())

    ensure_environment()
    from gemini_app.main import main
    main()
