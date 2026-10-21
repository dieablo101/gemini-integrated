"""Autonomous Linux distribution detection and system dependency management.

Detects the active Linux distribution and autonomously verifies and installs
required dependencies (git, curl, python packages, clipboard tools) using the
native distribution package manager.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

# Binary to package mappings by package manager / distro family
DISTRO_PACKAGE_MAPS: dict[str, dict[str, str]] = {
    "apt-get": {
        "git": "git",
        "curl": "curl",
        "python3": "python3",
        "pip": "python3-pip",
        "venv": "python3-venv",
        "xclip": "xclip",
        "wl-copy": "wl-clipboard",
        "tar": "tar",
    },
    "dnf": {
        "git": "git",
        "curl": "curl",
        "python3": "python3",
        "pip": "python3-pip",
        "xclip": "xclip",
        "wl-copy": "wl-clipboard",
        "tar": "tar",
    },
    "pacman": {
        "git": "git",
        "curl": "curl",
        "python3": "python",
        "pip": "python-pip",
        "xclip": "xclip",
        "wl-copy": "wl-clipboard",
        "tar": "tar",
    },
    "apk": {
        "git": "git",
        "curl": "curl",
        "python3": "python3",
        "pip": "py3-pip",
        "tar": "tar",
    },
    "zypper": {
        "git": "git",
        "curl": "curl",
        "python3": "python3",
        "pip": "python3-pip",
        "xclip": "xclip",
        "wl-copy": "wl-clipboard",
        "tar": "tar",
    },
    "xbps-install": {
        "git": "git",
        "curl": "curl",
        "python3": "python3",
        "pip": "python3-pip",
        "xclip": "xclip",
        "tar": "tar",
    },
}


def parse_os_release() -> dict[str, str]:
    """Parses /etc/os-release or /usr/lib/os-release into a key-value dictionary."""
    os_info: dict[str, str] = {}
    for candidate in [Path("/etc/os-release"), Path("/usr/lib/os-release")]:
        if candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os_info[k.strip()] = v.strip().strip('"').strip("'")
                if os_info:
                    break
            except Exception:
                continue
    return os_info


def detect_os() -> dict[str, str]:
    """Detects Linux distribution information and native package manager."""
    info = parse_os_release()
    distro_id = info.get("ID", "").lower()
    distro_like = info.get("ID_LIKE", "").lower()
    name = info.get("NAME", "Linux")
    version = info.get("VERSION_ID", "")

    # Determine package manager based on distro ID and ID_LIKE
    pkg_mgr = ""
    install_prefix: list[str] = []

    if distro_id in ("debian", "ubuntu", "linuxmint", "pop", "kali", "raspbian") or "debian" in distro_like or "ubuntu" in distro_like:
        pkg_mgr = "apt-get"
        install_prefix = ["apt-get", "install", "-y"]
    elif distro_id in ("fedora", "rhel", "centos", "rocky", "almalinux") or "fedora" in distro_like or "rhel" in distro_like:
        pkg_mgr = "dnf" if shutil.which("dnf") else "yum"
        install_prefix = [pkg_mgr, "install", "-y"]
    elif distro_id in ("arch", "manjaro", "endeavouros", "artix") or "arch" in distro_like:
        pkg_mgr = "pacman"
        install_prefix = ["pacman", "-Sy", "--noconfirm"]
    elif distro_id == "alpine":
        pkg_mgr = "apk"
        install_prefix = ["apk", "add"]
    elif "suse" in distro_id or "suse" in distro_like:
        pkg_mgr = "zypper"
        install_prefix = ["zypper", "install", "-y"]
    elif distro_id == "void":
        pkg_mgr = "xbps-install"
        install_prefix = ["xbps-install", "-Sy"]
    else:
        # Fallback binary detection
        for pm, cmd in [
            ("apt-get", ["apt-get", "install", "-y"]),
            ("dnf", ["dnf", "install", "-y"]),
            ("pacman", ["pacman", "-Sy", "--noconfirm"]),
            ("zypper", ["zypper", "install", "-y"]),
            ("apk", ["apk", "add"]),
        ]:
            if shutil.which(pm):
                pkg_mgr = pm
                install_prefix = cmd
                break

    return {
        "distro_id": distro_id or "unknown",
        "distro_like": distro_like,
        "name": name,
        "version": version,
        "package_manager": pkg_mgr,
        "install_command": " ".join(install_prefix),
    }


def check_command_installed(command: str) -> bool:
    """Returns True if the specified executable command is available in PATH."""
    return shutil.which(command) is not None


def check_dependencies(commands: list[str] | None = None) -> dict[str, bool]:
    """Checks the availability of the given list of command-line tools."""
    cmds = commands or ["git", "curl", "python3", "xclip"]
    return {cmd: check_command_installed(cmd) for cmd in cmds}


def get_missing_binaries(binaries: list[str]) -> list[str]:
    """Returns a list of binaries from the given list that are not found in PATH."""
    return [b for b in binaries if not check_command_installed(b)]


def install_system_dependencies(packages: list[str] | None = None) -> dict[str, Any]:
    """Autonomously installs system dependencies using the native package manager."""
    os_info = detect_os()
    pkg_mgr = os_info["package_manager"]

    if not pkg_mgr:
        return {
            "status": "error",
            "message": f"Unsupported or undetectable package manager for OS: {os_info['name']}",
            "os_info": os_info,
        }

    # Resolve package names
    target_pkgs = packages or ["git", "curl"]
    mapping = DISTRO_PACKAGE_MAPS.get(pkg_mgr, {})
    resolved_packages: list[str] = [mapping.get(p, p) for p in target_pkgs]

    # Build execution command
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    cmd: list[str] = []

    if not is_root and shutil.which("sudo"):
        cmd.extend(["sudo", "-n"])

    if pkg_mgr == "apt-get":
        # Prepend non-interactive environment if apt
        update_cmd = (["sudo", "-n"] if not is_root and shutil.which("sudo") else []) + ["apt-get", "update", "-y"]
        try:
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            subprocess.run(
                update_cmd,
                check=False,
                capture_output=True,
                env=env,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
        cmd.extend(["apt-get", "install", "-y", *resolved_packages])
    elif pkg_mgr in ("dnf", "yum"):
        cmd.extend([pkg_mgr, "install", "-y", *resolved_packages])
    elif pkg_mgr == "pacman":
        cmd.extend(["pacman", "-Sy", "--noconfirm", *resolved_packages])
    elif pkg_mgr == "apk":
        cmd.extend(["apk", "add", *resolved_packages])
    elif pkg_mgr == "zypper":
        cmd.extend(["zypper", "install", "-y", *resolved_packages])
    elif pkg_mgr == "xbps-install":
        cmd.extend(["xbps-install", "-Sy", *resolved_packages])
    else:
        return {
            "status": "error",
            "message": f"Cannot execute installation for unrecognized package manager: {pkg_mgr}",
        }

    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "success",
            "installed_packages": resolved_packages,
            "os": os_info["name"],
            "package_manager": pkg_mgr,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Installation command failed (exit code {e.returncode})",
            "command": " ".join(cmd),
            "stdout": e.stdout,
            "stderr": e.stderr,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to execute package installer: {e}",
            "command": " ".join(cmd),
        }


def ensure_system_dependencies(required: list[str] | None = None) -> dict[str, Any]:
    """Checks required binaries and autonomously installs missing ones based on OS check."""
    req = required or ["git"]
    missing = get_missing_binaries(req)

    os_info = detect_os()
    if not missing:
        return {
            "status": "success",
            "all_installed": True,
            "checked": req,
            "missing": [],
            "os_info": os_info,
            "message": "All required dependencies are installed.",
        }

    # Missing dependencies found: autonomously install
    install_result = install_system_dependencies(packages=missing)
    # Re-verify
    still_missing = get_missing_binaries(req)
    install_result["all_installed"] = len(still_missing) == 0
    install_result["still_missing"] = still_missing
    return install_result
