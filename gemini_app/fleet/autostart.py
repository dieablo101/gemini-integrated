"""Autonomous Boot-Persistence & Autostart Provisioner for Satellite Nodes.

Ensures that whenever a satellite node is deployed on a machine, it starts
automatically on system boot, runs continuously in the background, and pings
the Mothership without manual intervention.

Supports systemd (user/system), OpenRC (Alpine/iSH), macOS launchd, and cron (@reboot).
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional


SYSTEMD_SERVICE_TEMPLATE = """[Unit]
Description=Gemini Bilateral Satellite Node Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python_bin} {script_path} node --mothership {mothership} --interval {interval}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
WorkingDirectory={work_dir}

[Install]
WantedBy=default.target
"""

OPENRC_LOCAL_TEMPLATE = """#!/bin/sh
# Gemini Bilateral Satellite Node Autostart
# Automatically launched by OpenRC / local.d on boot
cd {work_dir} || exit 1
nohup {python_bin} {script_path} node --mothership {mothership} --interval {interval} > /var/log/gemini-satellite.log 2>&1 &
"""

LAUNCHD_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gemini.satellite</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>{script_path}</string>
        <string>node</string>
        <string>--mothership</string>
        <string>{mothership}</string>
        <string>--interval</string>
        <string>{interval}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{work_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{work_dir}/satellite.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{work_dir}/satellite.stderr.log</string>
</dict>
</plist>
"""


def detect_init_system() -> str:
    """Detects the primary init/daemon system available on this host."""
    # 1. Check for macOS launchd
    if sys.platform == "darwin":
        return "launchd"

    # 2. Check for OpenRC or iSH/Alpine
    if os.path.exists("/etc/local.d") or os.path.exists("/sbin/openrc-run") or os.path.exists("/proc/ish"):
        return "openrc"

    # 3. Check for systemd
    if shutil.which("systemctl"):
        try:
            res = subprocess.run(["systemctl", "--version"], capture_output=True, timeout=2)
            if res.returncode == 0:
                return "systemd"
        except Exception:
            pass

    # 4. Fallback to cron
    if shutil.which("crontab"):
        return "cron"

    return "unknown"


def get_gemini_runner_path() -> Path:
    """Locates the gemini-integrated.py runner path."""
    curr = Path(__file__).resolve().parent.parent.parent / "gemini-integrated.py"
    if curr.exists():
        return curr
    for cand in [Path("/opt/gemini/gemini-integrated.py"), Path.cwd() / "gemini-integrated.py"]:
        if cand.exists():
            return cand
    return Path(sys.argv[0]).resolve()


def install_autostart(
    mothership: str = "192.168.1.90",
    interval: float = 10.0,
    force_init: Optional[str] = None,
) -> Dict[str, Any]:
    """Installs boot-persistent satellite daemon on the current machine."""
    init_type = force_init or detect_init_system()
    python_bin = sys.executable
    script_path = str(get_gemini_runner_path())
    work_dir = str(Path(script_path).parent)

    if init_type == "systemd":
        # Check if running as root or user
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        if is_root:
            service_path = Path("/etc/systemd/system/gemini-satellite.service")
            cmd_prefix = ["systemctl"]
        else:
            user_dir = Path.home() / ".config" / "systemd" / "user"
            user_dir.mkdir(parents=True, exist_ok=True)
            service_path = user_dir / "gemini-satellite.service"
            cmd_prefix = ["systemctl", "--user"]

        content = SYSTEMD_SERVICE_TEMPLATE.format(
            python_bin=python_bin,
            script_path=script_path,
            mothership=mothership,
            interval=str(interval),
            work_dir=work_dir,
        )
        service_path.write_text(content, encoding="utf-8")

        try:
            subprocess.run(cmd_prefix + ["daemon-reload"], check=True, timeout=5)
            subprocess.run(cmd_prefix + ["enable", "gemini-satellite.service"], check=True, timeout=5)
            subprocess.run(cmd_prefix + ["restart", "gemini-satellite.service"], check=True, timeout=5)
            return {
                "status": "ok",
                "init": "systemd",
                "service_file": str(service_path),
                "message": f"systemd service enabled and started. Will autostart on every boot.",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "init": "systemd",
                "service_file": str(service_path),
                "message": f"Wrote {service_path}, but systemctl failed: {exc}",
            }

    elif init_type == "openrc":
        # OpenRC / Alpine / iSH
        local_d = Path("/etc/local.d")
        if not local_d.exists():
            try:
                local_d.mkdir(parents=True, exist_ok=True)
            except Exception:
                local_d = Path.home() / ".gemini"

        start_script = local_d / "gemini-satellite.start"
        content = OPENRC_LOCAL_TEMPLATE.format(
            python_bin=python_bin,
            script_path=script_path,
            mothership=mothership,
            interval=str(interval),
            work_dir=work_dir,
        )
        try:
            start_script.write_text(content, encoding="utf-8")
            start_script.chmod(0o755)

            # In iSH or mobile containers without active OpenRC daemon, also hook /etc/profile.d/
            profile_d = Path("/etc/profile.d")
            if profile_d.exists() and profile_d.is_dir():
                prof_hook = profile_d / "gemini-satellite.sh"
                hook_code = (
                    f"#!/bin/sh\n"
                    f"# Gemini satellite autostart hook\n"
                    f"pgrep -f 'gemini-integrated.*(node|hud)' >/dev/null || "
                    f"nohup {python_bin} {script_path} node --mothership {mothership} --interval {interval} >/dev/null 2>&1 &\n"
                )
                try:
                    prof_hook.write_text(hook_code, encoding="utf-8")
                    prof_hook.chmod(0o755)
                except Exception:
                    pass

            # Try to start it now
            subprocess.Popen(["/bin/sh", str(start_script)], start_new_session=True)
            return {
                "status": "ok",
                "init": "openrc",
                "service_file": str(start_script),
                "message": f"Boot script installed at {start_script} (OpenRC local.d & profile.d). Will run on system boot.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "init": "openrc",
                "error": f"Failed to write {start_script}: {exc}",
            }

    elif init_type == "launchd":
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / "com.gemini.satellite.plist"

        content = LAUNCHD_PLIST_TEMPLATE.format(
            python_bin=python_bin,
            script_path=script_path,
            mothership=mothership,
            interval=str(interval),
            work_dir=work_dir,
        )
        plist_path.write_text(content, encoding="utf-8")
        try:
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, timeout=3)
            subprocess.run(["launchctl", "load", str(plist_path)], check=True, timeout=5)
            return {
                "status": "ok",
                "init": "launchd",
                "service_file": str(plist_path),
                "message": f"macOS LaunchAgent loaded at {plist_path}. Starts automatically on login/boot.",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "init": "launchd",
                "service_file": str(plist_path),
                "message": f"Wrote {plist_path}, but launchctl failed: {exc}",
            }

    else:
        # Fallback to crontab @reboot
        cron_line = f"@reboot cd {work_dir} && nohup {python_bin} {script_path} node --mothership {mothership} --interval {interval} > /dev/null 2>&1 &"
        try:
            curr_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            if "gemini-integrated" not in curr_cron:
                new_cron = curr_cron.rstrip() + f"\n{cron_line}\n"
                proc = subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
                if proc.returncode == 0:
                    return {
                        "status": "ok",
                        "init": "cron",
                        "message": "Installed @reboot crontab entry for node persistence.",
                    }
            return {
                "status": "ok",
                "init": "cron",
                "message": "Node autostart crontab entry is already active.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "init": "cron",
                "error": f"Failed to install crontab autostart: {exc}",
            }


def remove_autostart() -> Dict[str, Any]:
    """Removes satellite autostart configuration."""
    init_type = detect_init_system()

    if init_type == "systemd":
        cmd_prefix = ["systemctl"] if (hasattr(os, "geteuid") and os.geteuid() == 0) else ["systemctl", "--user"]
        try:
            subprocess.run(cmd_prefix + ["stop", "gemini-satellite.service"], capture_output=True)
            subprocess.run(cmd_prefix + ["disable", "gemini-satellite.service"], capture_output=True)
        except Exception:
            pass
        return {"status": "ok", "message": "systemd satellite service disabled."}

    elif init_type == "openrc":
        start_script = Path("/etc/local.d/gemini-satellite.start")
        if start_script.exists():
            start_script.unlink()
        return {"status": "ok", "message": "OpenRC local.d start script removed."}

    elif init_type == "launchd":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.gemini.satellite.plist"
        if plist.exists():
            try:
                subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
            except Exception:
                pass
            plist.unlink()
        return {"status": "ok", "message": "LaunchAgent removed."}

    return {"status": "ok", "message": "Autostart cleanup finished."}


def check_autostart_status() -> Dict[str, Any]:
    """Inspects if satellite autostart is installed and active on this device."""
    init = detect_init_system()
    status_info: Dict[str, Any] = {"init_system": init, "installed": False, "running": False}

    if init == "systemd":
        cmd_prefix = ["systemctl"] if (hasattr(os, "geteuid") and os.geteuid() == 0) else ["systemctl", "--user"]
        try:
            res = subprocess.run(cmd_prefix + ["is-enabled", "gemini-satellite.service"], capture_output=True, text=True)
            status_info["installed"] = "enabled" in res.stdout
            active_res = subprocess.run(cmd_prefix + ["is-active", "gemini-satellite.service"], capture_output=True, text=True)
            status_info["running"] = "active" in active_res.stdout
        except Exception:
            pass

    elif init == "openrc":
        p = Path("/etc/local.d/gemini-satellite.start")
        status_info["installed"] = p.exists()
        try:
            ps_res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            status_info["running"] = "gemini-integrated.py node" in ps_res.stdout or "gemini-integrated.py hud" in ps_res.stdout
        except Exception:
            pass

    return status_info
