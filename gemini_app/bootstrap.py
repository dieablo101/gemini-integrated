"""Autonomous pre-flight bootstrapping: Linux distro dependency resolution, .venv & pip dependencies, and API key management."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from gemini_app.config import (
    DEFAULT_COPYRIGHT_HOLDER,
    GEMINI_HOME,
    PROJECTS_DIR,
    STATE_FILE,
)

CONFIG_FILE: Path = GEMINI_HOME / "config.json"


def get_stored_api_key() -> Optional[str]:
    """Retrieves GEMINI_API_KEY from environment, config.json, or state.json."""
    # 1. Environment variable
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    # 2. Config JSON (~/.gemini/config.json)
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            k = cfg.get("GEMINI_API_KEY") or cfg.get("gemini_api_key")
            if k and str(k).strip():
                return str(k).strip()
        except Exception:
            pass

    # 3. State JSON (~/.gemini/state.json)
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            k = st.get("gemini_api_key") or st.get("GEMINI_API_KEY")
            if k and str(k).strip():
                return str(k).strip()
        except Exception:
            pass

    return None


def persist_api_key(api_key: str) -> None:
    """Stores GEMINI_API_KEY across config.json, state.json, and user shell startup files."""
    clean_key = api_key.strip()
    if not clean_key:
        return

    # Set in running process environment
    os.environ["GEMINI_API_KEY"] = clean_key

    # 1. Save to ~/.gemini/config.json
    try:
        cfg: dict = {}
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        cfg["GEMINI_API_KEY"] = clean_key
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass

    # 2. Save to ~/.gemini/state.json
    try:
        st: dict = {}
        if STATE_FILE.exists():
            try:
                st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        st["gemini_api_key"] = clean_key
        if "user_realname" not in st:
            st["user_realname"] = DEFAULT_COPYRIGHT_HOLDER
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass

    # 3. Append to ~/.bashrc and ~/.zshrc if not already present
    export_line = f'export GEMINI_API_KEY="{clean_key}"\n'
    home = Path.home()
    for rc_name in (".bashrc", ".zshrc", ".profile"):
        rc_path = home / rc_name
        if rc_path.exists():
            try:
                content = rc_path.read_text(encoding="utf-8", errors="ignore")
                if "export GEMINI_API_KEY=" not in content:
                    with open(rc_path, "a", encoding="utf-8") as f:
                        f.write(f"\n# Added by Gemini Integrated Console\n{export_line}")
            except Exception:
                pass


def prompt_for_api_key_cli() -> Optional[str]:
    """Prompts the user interactively on CLI for the Gemini API key during first boot."""
    sys.stdout.write("\n")
    sys.stdout.write("=" * 64 + "\n")
    sys.stdout.write("  GEMINI INTEGRATED BILATERAL CONSOLE - FIRST-TIME SETUP\n")
    sys.stdout.write("=" * 64 + "\n")
    sys.stdout.write("A Google Gemini API Key is required to communicate with the model.\n")
    sys.stdout.write("Get a free key here: https://aistudio.google.com/app/apikey\n\n")

    try:
        key = input("Enter your GEMINI_API_KEY: ").strip()
        if key:
            persist_api_key(key)
            sys.stdout.write("✓ Key saved to environment, config, and shell profiles.\n\n")
            return key
    except (EOFError, KeyboardInterrupt):
        sys.stdout.write("\nSetup aborted.\n")
    return None


def detect_linux_distro() -> Dict[str, str]:
    """Inspects Linux release metadata to identify distro ID, family, and package manager."""
    info = {
        "system": platform.system().lower(),
        "id": "unknown",
        "family": "unknown",
        "pkg_manager": "unknown",
    }

    if info["system"] != "linux":
        return info

    os_release = Path("/etc/os-release")
    if not os_release.exists():
        os_release = Path("/usr/lib/os-release")

    parsed_release: dict[str, str] = {}
    if os_release.exists():
        try:
            for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    parsed_release[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass

    distro_id = parsed_release.get("ID", "").lower()
    id_like = parsed_release.get("ID_LIKE", "").lower().split()

    info["id"] = distro_id
    all_ids = [distro_id] + id_like

    if any(d in all_ids for d in ("ubuntu", "debian", "linuxmint", "pop", "kali", "raspbian", "elementary")):
        info["family"] = "debian"
        info["pkg_manager"] = "apt-get"
    elif any(d in all_ids for d in ("fedora", "rhel", "centos", "rocky", "almalinux")):
        info["family"] = "fedora"
        info["pkg_manager"] = "dnf" if shutil.which("dnf") else "yum"
    elif any(d in all_ids for d in ("arch", "manjaro", "endeavouros", "artix")):
        info["family"] = "arch"
        info["pkg_manager"] = "pacman"
    elif any(d in all_ids for d in ("opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap")):
        info["family"] = "suse"
        info["pkg_manager"] = "zypper"
    elif "alpine" in all_ids:
        info["family"] = "alpine"
        info["pkg_manager"] = "apk"
    elif "void" in all_ids:
        info["family"] = "void"
        info["pkg_manager"] = "xbps-install"

    return info


def check_and_install_distro_dependencies() -> Dict[str, Any]:
    """Autonomously checks and installs required system dependencies (git, python3-venv, etc.) based on distro check."""
    distro = detect_linux_distro()
    pkg_mgr = distro.get("pkg_manager")

    packages_by_mgr = {
        "apt-get": ["git", "python3-venv", "python3-pip", "xclip"],
        "dnf": ["git", "python3-virtualenv", "python3-pip", "xclip"],
        "yum": ["git", "python3-virtualenv", "python3-pip", "xclip"],
        "pacman": ["git", "python", "python-pip", "python-virtualenv", "xclip"],
        "zypper": ["git", "python3", "python3-pip", "python3-virtualenv", "xclip"],
        "apk": ["git", "python3", "py3-pip", "py3-virtualenv", "xclip"],
    }

    results = {
        "distro": distro,
        "git_found": shutil.which("git") is not None,
        "installed": [],
        "errors": [],
    }

    # If git is missing or we are bootstrapping system packages
    if not results["git_found"] and pkg_mgr in packages_by_mgr:
        pkgs = packages_by_mgr[pkg_mgr]
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        sudo_cmd = [] if is_root else (["sudo"] if shutil.which("sudo") else [])

        cmd: list[str] = []
        if pkg_mgr == "apt-get":
            update_cmd = sudo_cmd + ["apt-get", "update", "-qq"]
            try:
                subprocess.run(update_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            cmd = sudo_cmd + ["apt-get", "install", "-y", "-qq"] + pkgs
        elif pkg_mgr in ("dnf", "yum"):
            cmd = sudo_cmd + [pkg_mgr, "install", "-y", "-q"] + pkgs
        elif pkg_mgr == "pacman":
            cmd = sudo_cmd + ["pacman", "-Sy", "--noconfirm"] + pkgs
        elif pkg_mgr == "zypper":
            cmd = sudo_cmd + ["zypper", "--non-interactive", "install", "-y"] + pkgs
        elif pkg_mgr == "apk":
            cmd = sudo_cmd + ["apk", "add", "--no-cache"] + pkgs

        if cmd:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if proc.returncode == 0:
                    results["installed"].extend(pkgs)
                    results["git_found"] = shutil.which("git") is not None
                else:
                    results["errors"].append(proc.stderr.strip())
            except Exception as e:
                results["errors"].append(str(e))

    return results


def is_running_in_venv() -> bool:
    """Checks whether the current process is running inside a Python virtual environment."""
    return (
        sys.prefix != sys.base_prefix
        or "VIRTUAL_ENV" in os.environ
        or hasattr(sys, "real_prefix")
    )


def check_python_dependencies() -> List[str]:
    """Returns list of missing critical Python package imports."""
    required = ["textual", "google.genai", "rich", "pyperclip"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def ensure_virtualenv_and_dependencies(workspace_dir: Optional[Path] = None) -> str:
    """Ensures a valid .venv exists with all pip dependencies installed.

    If not currently running in a venv, creates or locates .venv and returns its python binary path.
    """
    REQUIRED_PIP_PACKAGES = [
        "textual>=0.50.0",
        "google-genai>=1.0.0",
        "rich>=13.0.0",
        "pyperclip>=1.8.0",
        "setuptools>=61.0",
        "wheel",
        "build",
    ]

    # If running in an active venv and dependencies are present, all is good
    if is_running_in_venv():
        missing = check_python_dependencies()
        if not missing:
            return sys.executable
        # Install missing dependencies into current venv
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + missing, check=False)
        return sys.executable

    # Locate or create .venv
    base_dir = (workspace_dir or Path.cwd()).resolve()
    target_venv = base_dir / ".venv"

    # If base directory is not writable (e.g. read-only mount), fall back to ~/.gemini/venv
    if not target_venv.exists():
        try:
            target_venv.mkdir(parents=True, exist_ok=True)
            target_venv.rmdir()
        except OSError:
            target_venv = GEMINI_HOME / "venv"

    venv_python = target_venv / "bin" / "python3"

    # Create venv if python executable does not exist
    if not venv_python.exists():
        try:
            import venv
            venv.create(str(target_venv), with_pip=True, clear=False)
        except Exception:
            subprocess.run([sys.executable, "-m", "venv", str(target_venv)], check=True)

    # Ensure pip dependencies are installed in the venv
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "-q", "pip"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q"] + REQUIRED_PIP_PACKAGES,
            check=True,
        )
    except Exception as e:
        sys.stderr.write(f"Warning: Error installing dependencies into venv: {e}\n")

    return str(venv_python)


def run_preflight_bootstrap(workspace_dir: Optional[Path] = None, interactive_api_prompt: bool = True) -> bool:
    """Orchestrates preflight checks:

    1. Ensures Projects directory exists.
    2. Runs autonomous OS/distro check and system dependency validation.
    3. Verifies or bootstraps .venv and pip packages.
    4. Ensures GEMINI_API_KEY is configured in env/state.
    """
    # 1. Ensure Projects directory exists in user home
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Check and install Linux distro dependencies (git, etc.)
    check_and_install_distro_dependencies()

    # 3. Check / setup GEMINI_API_KEY
    key = get_stored_api_key()
    if not key and interactive_api_prompt and sys.stdin.isatty():
        key = prompt_for_api_key_cli()

    if key:
        os.environ["GEMINI_API_KEY"] = key

    # 4. Ensure venv and python packages
    if not is_running_in_venv():
        venv_py = ensure_virtualenv_and_dependencies(workspace_dir)
        # If we just bootstrapped an external venv and we're in the runner script, re-exec into venv
        if venv_py != sys.executable and os.path.exists(venv_py):
            os.execv(venv_py, [venv_py] + sys.argv)

    return True
