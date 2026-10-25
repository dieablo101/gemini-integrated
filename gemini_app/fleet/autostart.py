"""Autonomous Boot-Persistence & Autostart Provisioner for Satellite Nodes.

Ensures that whenever a satellite node is deployed on a machine, it starts
automatically on system boot, runs continuously in the background, and pings
the Mothership without manual intervention.

Supports systemd (user/system), OpenRC (Alpine Linux), iSH (iOS Alpine),
macOS launchd, and cron (@reboot).
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


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

ISH_AUTOSTART_BLOCK_START = "# === Gemini Bilateral Satellite Node Autostart ==="
ISH_AUTOSTART_BLOCK_END = "# === End Gemini Satellite ==="

TERMUX_AUTOSTART_BLOCK_START = "# === Gemini Bilateral Satellite Node Autostart (Termux) ==="
TERMUX_AUTOSTART_BLOCK_END = "# === End Gemini Satellite (Termux) ==="

TERMUX_BOOT_TEMPLATE = """#!/data/data/com.termux/files/usr/bin/sh
# Gemini Bilateral Satellite Node Boot Autostart (Termux:Boot)
sleep 4
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
fi
cd {work_dir} || exit 1
if [ -f "{work_dir}/.venv/bin/python" ]; then
    PY_BIN="{work_dir}/.venv/bin/python"
elif [ -f "{work_dir}/venv/bin/python" ]; then
    PY_BIN="{work_dir}/venv/bin/python"
elif [ -f "$HOME/.venv/bin/python" ]; then
    PY_BIN="$HOME/.venv/bin/python"
else
    PY_BIN="{python_bin}"
fi
nohup $PY_BIN {script_path} node --mothership {mothership} --interval {interval} > {work_dir}/satellite.log 2>&1 &
"""

TERMUX_HOOK_TEMPLATE = """{start_marker}
# Launch Gemini background node only if not already running
if ! pgrep -f 'gemini-integrated.py' >/dev/null 2>&1; then
    if command -v termux-wake-lock >/dev/null 2>&1; then
        termux-wake-lock
    fi
    cd {work_dir} 2>/dev/null || true
    if [ -f "{work_dir}/.venv/bin/python" ]; then
        PY_BIN="{work_dir}/.venv/bin/python"
    elif [ -f "{work_dir}/venv/bin/python" ]; then
        PY_BIN="{work_dir}/venv/bin/python"
    elif [ -f "$HOME/.venv/bin/python" ]; then
        PY_BIN="$HOME/.venv/bin/python"
    else
        PY_BIN="{python_bin}"
    fi
    nohup $PY_BIN {script_path} node --mothership {mothership} --interval {interval} > {work_dir}/satellite.log 2>&1 &
fi
{end_marker}
"""

ISH_HOOK_TEMPLATE = """{start_marker}
# Do not run in non-interactive sessions (e.g. scp, sftp, non-interactive ssh)
case "$-" in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

# Launch Gemini background node only if not already running
if ! pgrep -f 'gemini-integrated.py' >/dev/null 2>&1; then
    cd {work_dir} 2>/dev/null || cd /root/gemini-integrated 2>/dev/null || true
    if [ -f .venv/bin/python ]; then
        PY_BIN=".venv/bin/python"
    elif [ -f venv/bin/python ]; then
        PY_BIN="venv/bin/python"
    else
        PY_BIN="{python_bin}"
    fi
    nohup $PY_BIN {script_path} node --interval {interval} > /var/log/gemini-satellite.log 2>&1 &
fi
{end_marker}
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
    # 1. Check for Android Termux
    if "com.termux" in os.environ.get("PREFIX", "") or Path("/data/data/com.termux").exists() or "TERMUX_VERSION" in os.environ:
        return "termux"

    # 2. Check for macOS launchd
    if sys.platform == "darwin":
        return "launchd"

    # 2. Check for iSH (iOS Alpine user-mode Linux emulator)
    if os.path.exists("/proc/ish") or os.path.exists("/dev/location"):
        return "ish"
    if hasattr(os, "uname"):
        try:
            u = os.uname()
            if "ish" in u.release.lower() or "ish" in u.version.lower():
                return "ish"
        except Exception:
            pass

    # 3. Check for OpenRC (standard Alpine / Gentoo)
    if os.path.exists("/sbin/openrc-run") or os.path.exists("/etc/init.d"):
        return "openrc"

    # 4. Check for systemd
    if shutil.which("systemctl"):
        try:
            res = subprocess.run(["systemctl", "--version"], capture_output=True, timeout=2)
            if res.returncode == 0:
                return "systemd"
        except Exception:
            pass

    # 5. Fallback to cron
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


def update_autostart_mothership(new_mothership: str, port: Optional[int] = None) -> bool:
    """Updates the target mothership host across all known autostart configurations on this machine."""
    new_mothership = new_mothership.strip()
    if not new_mothership:
        return False

    updated_any = False

    # 1. Systemd services (system if root, user otherwise)
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    systemd_paths = []
    if is_root:
        systemd_paths.append(Path("/etc/systemd/system/gemini-satellite.service"))
    systemd_paths.append(Path.home() / ".config" / "systemd" / "user" / "gemini-satellite.service")
    for p in systemd_paths:
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8")
                new_content = re.sub(r"(--mothership\s+)\S+", rf"\g<1>{new_mothership}", content)
                if new_content != content:
                    p.write_text(new_content, encoding="utf-8")
                    updated_any = True
                    cmd_prefix = ["systemctl"] if "/etc/systemd/system" in str(p) else ["systemctl", "--user"]
                    try:
                        subprocess.run(cmd_prefix + ["daemon-reload"], capture_output=True, timeout=3)
                    except Exception:
                        pass
            except Exception:
                pass

    # 2. iSH, Termux, and shell profile files
    profile_candidates = [
        Path("/etc/profile.d/gemini-satellite.sh"),
        Path("/etc/local.d/gemini-satellite.start"),
        Path.home() / ".termux" / "boot" / "gemini-satellite.sh",
        Path("/root/.profile"),
        Path("/root/.ashrc"),
        Path.home() / ".profile",
        Path.home() / ".ashrc",
        Path.home() / ".bashrc",
    ]
    for p in profile_candidates:
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8")
                if "--mothership" in content:
                    new_content = re.sub(r"(--mothership\s+)\S+", rf"\g<1>{new_mothership}", content)
                    if new_content != content:
                        p.write_text(new_content, encoding="utf-8")
                        updated_any = True
            except Exception:
                pass

    # 3. macOS LaunchAgent plist
    plist = Path.home() / "Library" / "LaunchAgents" / "com.gemini.satellite.plist"
    if plist.exists():
        try:
            content = plist.read_text(encoding="utf-8")
            pattern = r"(<string>--mothership</string>\s*<string>)[^<]+(</string>)"
            new_content = re.sub(pattern, rf"\g<1>{new_mothership}\g<2>", content)
            if new_content != content:
                plist.write_text(new_content, encoding="utf-8")
                updated_any = True
        except Exception:
            pass

    # 4. Crontab
    if shutil.which("crontab"):
        try:
            proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if proc.returncode == 0 and "gemini-integrated" in proc.stdout and "--mothership" in proc.stdout:
                new_cron = re.sub(r"(--mothership\s+)\S+", rf"\g<1>{new_mothership}", proc.stdout)
                if new_cron != proc.stdout:
                    subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
                    updated_any = True
        except Exception:
            pass

    return updated_any


def install_autostart(
    mothership: Optional[str] = None,
    interval: float = 10.0,
    force_init: Optional[str] = None,
) -> Dict[str, Any]:
    """Installs boot-persistent satellite daemon on the current machine."""
    from gemini_app.fleet.satellite import get_saved_mothership, save_mothership
    if mothership:
        mothership = mothership.strip()
        save_mothership(mothership)
    else:
        mothership = get_saved_mothership()

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
            subprocess.run(cmd_prefix + ["daemon-reload"], check=True, capture_output=True, timeout=5)
            subprocess.run(cmd_prefix + ["enable", "gemini-satellite.service"], check=True, capture_output=True, timeout=5)
            subprocess.run(cmd_prefix + ["restart", "gemini-satellite.service"], check=True, capture_output=True, timeout=5)
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

    elif init_type == "termux":
        installed_targets = []
        # 1. Termux:Boot autostart (~/.termux/boot/gemini-satellite.sh)
        termux_boot_dir = Path.home() / ".termux" / "boot"
        try:
            termux_boot_dir.mkdir(parents=True, exist_ok=True)
            boot_script = termux_boot_dir / "gemini-satellite.sh"
            boot_content = TERMUX_BOOT_TEMPLATE.format(
                python_bin=python_bin,
                script_path=script_path,
                mothership=mothership,
                interval=str(interval),
                work_dir=work_dir,
            )
            boot_script.write_text(boot_content, encoding="utf-8")
            boot_script.chmod(0o755)
            installed_targets.append(str(boot_script))
        except Exception:
            pass

        # 2. Shell profile hook (~/.bashrc, ~/.profile)
        hook_code = TERMUX_HOOK_TEMPLATE.format(
            start_marker=TERMUX_AUTOSTART_BLOCK_START,
            end_marker=TERMUX_AUTOSTART_BLOCK_END,
            python_bin=python_bin,
            script_path=script_path,
            mothership=mothership,
            interval=str(interval),
            work_dir=work_dir,
        )
        for p in [Path.home() / ".bashrc", Path.home() / ".profile"]:
            try:
                existing = p.read_text(encoding="utf-8") if p.exists() else ""
                if TERMUX_AUTOSTART_BLOCK_START not in existing:
                    new_content = existing.rstrip() + f"\n\n{hook_code}\n"
                    p.write_text(new_content, encoding="utf-8")
                    p.chmod(0o755)
                    installed_targets.append(str(p))
                else:
                    installed_targets.append(f"{p} (already present)")
            except Exception:
                pass

        # 3. Acquire Termux wake lock to prevent CPU Doze suspension
        if shutil.which("termux-wake-lock"):
            try:
                subprocess.run(["termux-wake-lock"], capture_output=True, timeout=2)
            except Exception:
                pass

        # 4. Launch background node immediately if not running
        try:
            launch_cmd = (
                f"cd {work_dir} && "
                f"nohup {python_bin} {script_path} node --mothership {mothership} --interval {interval} > {work_dir}/satellite.log 2>&1 &"
            )
            subprocess.Popen(
                ["/bin/sh", "-c", launch_cmd],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        return {
            "status": "ok",
            "init": "termux",
            "installed_targets": installed_targets,
            "message": f"Termux autostart installed (Termux:Boot & shell hooks). Wake-lock active.",
        }

    elif init_type == "ish":
        # iSH (iOS Alpine Linux emulator)
        hook_code = ISH_HOOK_TEMPLATE.format(
            start_marker=ISH_AUTOSTART_BLOCK_START,
            end_marker=ISH_AUTOSTART_BLOCK_END,
            python_bin=python_bin,
            script_path=script_path,
            mothership=mothership,
            interval=str(interval),
            work_dir=work_dir,
        )

        installed_targets: List[str] = []

        # 1. System profile.d hook
        profile_d = Path("/etc/profile.d")
        if profile_d.exists() and profile_d.is_dir():
            sh_hook = profile_d / "gemini-satellite.sh"
            try:
                sh_hook.write_text(f"#!/bin/sh\n{hook_code}\n", encoding="utf-8")
                sh_hook.chmod(0o755)
                installed_targets.append(str(sh_hook))
            except Exception:
                pass

        # 2. Append to shell profile files for interactive/login shells
        profile_candidates = [
            Path("/root/.profile"),
            Path("/root/.ashrc"),
            Path.home() / ".profile",
            Path.home() / ".ashrc",
            Path.home() / ".bashrc",
        ]
        seen_paths = set()
        for p in profile_candidates:
            resolved = str(p.resolve()) if p.exists() else str(p)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                existing = p.read_text(encoding="utf-8") if p.exists() else ""
                if ISH_AUTOSTART_BLOCK_START not in existing:
                    new_content = existing.rstrip() + f"\n\n{hook_code}\n"
                    p.write_text(new_content, encoding="utf-8")
                    p.chmod(0o755)
                    installed_targets.append(str(p))
                else:
                    installed_targets.append(f"{p} (already present)")
            except Exception:
                pass

        # 3. Also populate /etc/local.d if possible
        try:
            local_d = Path("/etc/local.d")
            local_d.mkdir(parents=True, exist_ok=True)
            local_script = local_d / "gemini-satellite.start"
            local_script.write_text(f"#!/bin/sh\n{hook_code}\n", encoding="utf-8")
            local_script.chmod(0o755)
            installed_targets.append(str(local_script))
        except Exception:
            pass

        # 4. Launch immediately in background if not already running
        try:
            launch_cmd = (
                f"cd {work_dir} && "
                f"nohup {python_bin} {script_path} node --mothership {mothership} --interval {interval} > /var/log/gemini-satellite.log 2>&1 &"
            )
            subprocess.Popen(
                ["/bin/sh", "-c", launch_cmd],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        return {
            "status": "ok",
            "init": "ish",
            "installed_targets": installed_targets,
            "message": f"iSH autostart installed across {len(installed_targets)} profile hooks. Node launched in background.",
        }

    elif init_type == "openrc":
        # Standard OpenRC / Alpine / Gentoo
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

            # Try to start it now
            subprocess.Popen(["/bin/sh", str(start_script)], start_new_session=True)
            return {
                "status": "ok",
                "init": "openrc",
                "service_file": str(start_script),
                "message": f"Boot script installed at {start_script} (OpenRC local.d). Will run on system boot.",
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

    elif init_type == "termux":
        cleaned = []
        boot_script = Path.home() / ".termux" / "boot" / "gemini-satellite.sh"
        if boot_script.exists():
            try:
                boot_script.unlink()
                cleaned.append(str(boot_script))
            except Exception:
                pass

        for p in [Path.home() / ".bashrc", Path.home() / ".profile"]:
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8")
                    if TERMUX_AUTOSTART_BLOCK_START in text:
                        import re
                        pattern = re.escape(TERMUX_AUTOSTART_BLOCK_START) + r".*?" + re.escape(TERMUX_AUTOSTART_BLOCK_END)
                        stripped = re.sub(pattern, "", text, flags=re.DOTALL).strip() + "\n"
                        p.write_text(stripped, encoding="utf-8")
                        cleaned.append(str(p))
                except Exception:
                    pass

        if shutil.which("termux-wake-unlock"):
            try:
                subprocess.run(["termux-wake-unlock"], capture_output=True, timeout=2)
            except Exception:
                pass

        return {"status": "ok", "message": f"Termux autostart cleaned from {len(cleaned)} targets. Wake lock released."}

    elif init_type == "ish":
        cleaned = []
        p_hook = Path("/etc/profile.d/gemini-satellite.sh")
        if p_hook.exists():
            try:
                p_hook.unlink()
                cleaned.append(str(p_hook))
            except Exception:
                pass

        profile_candidates = [
            Path("/root/.profile"),
            Path("/root/.ashrc"),
            Path.home() / ".profile",
            Path.home() / ".ashrc",
            Path.home() / ".bashrc",
        ]
        for p in profile_candidates:
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8")
                    if ISH_AUTOSTART_BLOCK_START in text:
                        # Strip block between start and end
                        import re
                        pattern = re.escape(ISH_AUTOSTART_BLOCK_START) + r".*?" + re.escape(ISH_AUTOSTART_BLOCK_END)
                        stripped = re.sub(pattern, "", text, flags=re.DOTALL).strip() + "\n"
                        p.write_text(stripped, encoding="utf-8")
                        cleaned.append(str(p))
                except Exception:
                    pass

        local_script = Path("/etc/local.d/gemini-satellite.start")
        if local_script.exists():
            try:
                local_script.unlink()
                cleaned.append(str(local_script))
            except Exception:
                pass

        return {"status": "ok", "message": f"iSH autostart cleaned from {len(cleaned)} targets."}

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

    elif init == "termux":
        boot_script = Path.home() / ".termux" / "boot" / "gemini-satellite.sh"
        has_bashrc = False
        p_bash = Path.home() / ".bashrc"
        if p_bash.exists():
            try:
                has_bashrc = TERMUX_AUTOSTART_BLOCK_START in p_bash.read_text(encoding="utf-8")
            except Exception:
                pass
        status_info["installed"] = boot_script.exists() or has_bashrc

        try:
            ps_res = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
            if ps_res.returncode != 0:
                ps_res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            status_info["running"] = (
                "gemini-integrated.py node" in ps_res.stdout
                or "gemini-integrated.py satellite" in ps_res.stdout
                or "gemini-integrated.py hud" in ps_res.stdout
            )
        except Exception:
            pass

    elif init == "ish":
        has_prof_d = Path("/etc/profile.d/gemini-satellite.sh").exists()
        has_root_prof = False
        p_root = Path("/root/.profile")
        if p_root.exists():
            try:
                has_root_prof = ISH_AUTOSTART_BLOCK_START in p_root.read_text(encoding="utf-8")
            except Exception:
                pass
        status_info["installed"] = has_prof_d or has_root_prof

        try:
            ps_res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            status_info["running"] = (
                "gemini-integrated.py node" in ps_res.stdout
                or "gemini-integrated.py satellite" in ps_res.stdout
                or "gemini-integrated.py hud" in ps_res.stdout
            )
        except Exception:
            pass

    elif init == "openrc":
        p = Path("/etc/local.d/gemini-satellite.start")
        status_info["installed"] = p.exists()
        try:
            ps_res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            status_info["running"] = (
                "gemini-integrated.py node" in ps_res.stdout
                or "gemini-integrated.py satellite" in ps_res.stdout
                or "gemini-integrated.py hud" in ps_res.stdout
            )
        except Exception:
            pass

    return status_info
