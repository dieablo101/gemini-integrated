"""Lightweight zero-dependency Satellite Node client.

Runs on mobile nodes (iPad iSH, Android Termux) and remote compute nodes
using only the Python standard library.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Optional, Tuple

from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage, get_local_lan_ip
from gemini_app.fleet.security import (
    compute_auth_signature,
    get_or_create_fleet_key,
    verify_command_signature,
)

try:
    from gemini_app.helpers import calculate_reconnect_backoff, format_reconnect_countdown
except ImportError:
    def format_reconnect_countdown(remaining_seconds: float) -> str:
        rem = max(0.0, float(remaining_seconds))
        return f"{rem:.1f}s" if rem < 60.0 else f"{int(rem // 60)}m {rem % 60:.1f}s"

    def calculate_reconnect_backoff(
        attempt: int,
        base_delay: float = 1.5,
        factor: float = 1.5,
        max_delay: float = 15.0,
        jitter: float = 0.1,
    ) -> float:
        import random
        raw = min(base_delay * (factor ** max(0, attempt - 1)), max_delay)
        if jitter > 0:
            raw += random.uniform(-raw * jitter, raw * jitter)
        return max(0.5, round(raw, 2))


def is_ish_platform() -> bool:
    """Detects iOS iSH Alpine emulation environment to apply crash-prevention safeguards."""
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
    return False


def is_termux_platform() -> bool:
    """Detects Android Termux environment."""
    if "com.termux" in os.environ.get("PREFIX", ""):
        return True
    if Path("/data/data/com.termux").exists():
        return True
    if "TERMUX_VERSION" in os.environ:
        return True
    return False


def acquire_termux_wake_lock() -> bool:
    """Acquires Android wake lock via termux-wake-lock to prevent CPU Doze sleep."""
    if not is_termux_platform():
        return False
    if shutil.which("termux-wake-lock"):
        try:
            subprocess.run(["termux-wake-lock"], capture_output=True, timeout=2)
            return True
        except Exception:
            pass
    return False


def release_termux_wake_lock() -> None:
    """Releases Android wake lock via termux-wake-unlock."""
    if not is_termux_platform():
        return
    if shutil.which("termux-wake-unlock"):
        try:
            subprocess.run(["termux-wake-unlock"], capture_output=True, timeout=2)
        except Exception:
            pass


# Ensure wake lock is released on process exit if acquired
atexit.register(release_termux_wake_lock)


def ensure_termux_mobile_environment(mothership_host: Optional[str] = None) -> None:
    """Configures mobile background persistence, wake-lock, and autostart on Android Termux."""
    if not is_termux_platform():
        return

    # 1. Acquire wake lock immediately so process is not frozen during Doze
    acquire_termux_wake_lock()

    # 2. Check termux-api tool availability
    if not shutil.which("termux-battery-status"):
        sys.stderr.write(
            "[satellite] Notice: 'termux-api' utilities not found.\n"
            "   Run 'pkg install -y termux-api' in Termux and install the Termux:API app\n"
            "   from F-Droid/GitHub for real-time mobile battery & thermal vitals.\n"
        )

    # 3. Check and auto-provision Termux:Boot autostart
    try:
        from gemini_app.fleet.autostart import check_autostart_status, install_autostart
        st = check_autostart_status()
        if not st.get("installed"):
            target = mothership_host or get_saved_mothership() or "192.168.1.90"
            res = install_autostart(mothership=target)
            if res.get("status") == "ok":
                sys.stdout.write(f"[satellite] Auto-provisioned Termux:Boot autostart service for Mothership ({target}).\n")
    except Exception:
        pass


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Finds the root repository directory containing .git, traversing upwards if needed."""
    curr = (start or Path.cwd()).resolve()
    for p in [curr] + list(curr.parents):
        if (p / ".git").is_dir():
            return p
    try:
        mod_root = Path(__file__).resolve().parents[2]
        if (mod_root / ".git").is_dir():
            return mod_root
    except Exception:
        pass
    return curr


def find_node_screenshots(limit: int = 10) -> List[Dict[str, Any]]:
    """Discovers screenshots across Android, iOS (iSH), and local node directories."""
    candidates: List[Path] = []
    if is_termux_platform():
        candidates = [
            Path.home() / "storage" / "dcim" / "Screenshots",
            Path.home() / "storage" / "pictures" / "Screenshots",
            Path.home() / "storage" / "shared" / "DCIM" / "Screenshots",
            Path.home() / "storage" / "shared" / "Pictures" / "Screenshots",
            Path("/sdcard/DCIM/Screenshots"),
            Path("/sdcard/Pictures/Screenshots"),
        ]
    elif is_ish_platform():
        candidates = [
            Path("/mnt/ipad"),
            Path.home() / ".gemini" / "screenshots",
        ]
    else:
        candidates = [
            Path.home() / ".gemini" / "screenshots",
            Path.home() / "Pictures" / "Screenshots",
            Path.home() / "Pictures",
            Path("/sdcard/DCIM/Screenshots"),
        ]
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    found_files: List[Dict[str, Any]] = []
    for cand in candidates:
        try:
            if not cand.exists() or not cand.is_dir():
                continue
            for item in cand.iterdir():
                if item.is_file() and item.suffix.lower() in valid_exts:
                    if item.name.startswith("wingman_camera_"):
                        continue
                    try:
                        st = item.stat()
                        found_files.append({
                            "path": str(item),
                            "filename": item.name,
                            "mtime": st.st_mtime,
                            "size_bytes": st.st_size,
                            "source_dir": str(cand),
                        })
                    except Exception:
                        pass
        except (PermissionError, OSError):
            continue

    found_files.sort(key=lambda x: x["mtime"], reverse=True)
    return found_files[:limit]


def get_effective_python(start: Optional[Path] = None) -> str:
    """Finds the best python binary, preferring local virtualenv if present."""
    base = find_repo_root(start)
    for venv_dir in (".venv", "venv"):
        for py_name in ("python", "python3"):
            cand = base / venv_dir / "bin" / py_name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    # Also check user home venv
    for venv_dir in (".venv", "venv"):
        for py_name in ("python", "python3"):
            cand = Path.home() / venv_dir / "bin" / py_name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    return sys.executable


def _exec_reboot() -> None:
    """Safely replaces the process image in place using the effective python binary."""
    py_bin = get_effective_python()
    root = find_repo_root()
    runner = root / "gemini-integrated.py"
    script = str(runner.resolve()) if runner.exists() else sys.argv[0]
    args = [py_bin, script]
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])
    os.execv(py_bin, args)


def _get_git_info_fast(repo_dir: Optional[Path] = None) -> tuple[str, str]:
    """Reads git branch and commit in pure Python without spawning subprocesses (safe for emulators)."""
    base = find_repo_root(repo_dir)
    git_dir = base / ".git"
    if not git_dir.is_dir():
        return "unknown", "unknown"
    try:
        head_file = git_dir / "HEAD"
        if not head_file.exists():
            return "unknown", "unknown"
        head_content = head_file.read_text(encoding="utf-8").strip()
        if head_content.startswith("ref:"):
            ref_path = head_content.split(":", 1)[1].strip()
            branch = ref_path.split("/")[-1]
            ref_file = git_dir / ref_path
            if ref_file.exists():
                commit = ref_file.read_text(encoding="utf-8").strip()[:7]
            else:
                packed = git_dir / "packed-refs"
                commit = "unknown"
                if packed.exists():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line and not line.startswith(("#", "^")) and ref_path in line:
                            commit = line.split()[0][:7]
                            break
            return commit, branch
        elif len(head_content) >= 7:
            return head_content[:7], "detached"
    except Exception:
        pass
    return "unknown", "unknown"


_last_ipad_check = 0.0
_cached_ipad_files = 0
_cached_has_mount = False
_active_wingman: Optional[Any] = None


def get_active_wingman() -> Optional[Any]:
    global _active_wingman
    return _active_wingman


def set_active_wingman(applet: Optional[Any]) -> None:
    global _active_wingman
    _active_wingman = applet


def check_ipad_mount() -> tuple[bool, int]:
    """Safely checks /mnt/ipad with caching to avoid iSH VFS/Cocoa file coordinator crashes."""
    global _last_ipad_check, _cached_ipad_files, _cached_has_mount
    now = time.time()
    if now - _last_ipad_check < 60.0:
        return _cached_has_mount, _cached_ipad_files
    _last_ipad_check = now
    try:
        ipad_mount = Path("/mnt/ipad")
        if ipad_mount.is_dir():
            _cached_has_mount = True
            count = 0
            # Limit iteration to at most 50 files using scandir to avoid memory explosion in iSH
            with os.scandir("/mnt/ipad") as it:
                for _ in it:
                    count += 1
                    if count >= 50:
                        break
            _cached_ipad_files = count
        else:
            _cached_has_mount = False
            _cached_ipad_files = 0
    except Exception:
        pass
    return _cached_has_mount, _cached_ipad_files


def ensure_ish_background_keepalive() -> None:
    """Safely checks environment on iOS iSH without spawning fragile kernel device threads."""
    # Note: Long-running threads that open /dev/location in Python cause Mach thread
    # panics and kernel faults in the iSH emulator. Shell hooks manage keepalives.
    pass


def get_memory_info_fast() -> tuple[Optional[int], Optional[int]]:
    """Reads MemTotal and MemAvailable in MB directly from /proc/meminfo in pure Python."""
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            total = None
            avail = None
            for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) // 1024
                elif line.startswith("MemFree:") and avail is None:
                    avail = int(line.split()[1]) // 1024
                if total is not None and avail is not None:
                    break
            return total, avail
    except Exception:
        pass
    return None, None


def get_battery_info() -> Dict[str, Any]:
    """Safely inspects battery and charging status across mobile platforms without crashing."""
    info: Dict[str, Any] = {"percentage": None, "charging": None, "temperature": None}
    # 1. Termux API check
    if is_termux_platform() and shutil.which("termux-battery-status"):
        try:
            res = subprocess.run(
                ["termux-battery-status"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                b_json = json.loads(res.stdout.strip())
                info["percentage"] = b_json.get("percentage")
                status = str(b_json.get("status", "")).upper()
                info["charging"] = (status == "CHARGING" or b_json.get("plugged") in ("PLUGGED_AC", "PLUGGED_USB", "PLUGGED_WIRELESS"))
                info["temperature"] = b_json.get("temperature")
                return info
        except Exception:
            pass

    # 2. Linux /sys/class/power_supply fallback
    try:
        ps_dir = Path("/sys/class/power_supply")
        if ps_dir.is_dir():
            for b_name in ("battery", "BAT0", "BAT1"):
                b_path = ps_dir / b_name
                if b_path.is_dir():
                    cap_f = b_path / "capacity"
                    stat_f = b_path / "status"
                    if cap_f.exists():
                        try:
                            info["percentage"] = int(cap_f.read_text().strip())
                        except Exception:
                            pass
                    if stat_f.exists():
                        try:
                            info["charging"] = stat_f.read_text().strip().lower() in ("charging", "full")
                        except Exception:
                            pass
                    return info
    except Exception:
        pass
    return info


def get_local_route_info() -> Dict[str, Any]:
    """Retrieves local interface IP and route classification (LAN vs Cellular/Roaming)."""
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to 8.8.8.8:80 (UDP probe doesn't transmit packets, queries routing kernel table)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    is_lan = is_lan_address(local_ip)
    return {
        "local_ip": local_ip,
        "is_lan": is_lan,
        "network_type": "LAN (Wi-Fi/Ethernet)" if is_lan else "Roaming / Cellular",
    }


_SATELLITE_START_TIME = time.time()


def get_system_uptime() -> float:
    """Reads system uptime in seconds from /proc/uptime with fallback to process start time."""
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return float(content.split()[0])
    except Exception:
        pass
    try:
        import psutil
        return max(0.0, time.time() - psutil.boot_time())
    except Exception:
        pass
    return max(0.0, time.time() - _SATELLITE_START_TIME)


def collect_telemetry() -> Dict[str, Any]:
    """Collects system capabilities and status using standard library only."""
    uname = platform.uname()
    try:
        disk_path = str(Path.home()) if Path.home().exists() else "/"
        total_b, used_b, free_b = shutil.disk_usage(disk_path)
    except Exception:
        total_b, used_b, free_b = shutil.disk_usage("/")

    # Check for iOS filesystem mount point with cached scandir guard
    has_ipad_mount, ipad_files_count = check_ipad_mount()

    # Read git status using pure Python to avoid fork/exec crashes in iSH emulator
    git_commit, git_branch = _get_git_info_fast()

    is_ish = is_ish_platform()
    is_termux = is_termux_platform()
    has_wake_lock = is_termux and bool(shutil.which("termux-wake-lock"))

    battery = get_battery_info()
    route_info = get_local_route_info()
    mem_total_mb, mem_avail_mb = get_memory_info_fast()

    wingman = get_active_wingman()
    pending_auth_list = []
    is_active_browser = False
    if wingman and hasattr(wingman, "is_browser_open"):
        is_active_browser = bool(wingman.is_browser_open())

    if wingman and hasattr(wingman, "security"):
        try:
            # Prune stale or abandoned sessions older than 45s
            if hasattr(wingman.security, "prune_stale_sessions"):
                wingman.security.prune_stale_sessions(max_pending_age=45.0)

            # Advertise pending auth requests if not in maintenance mode
            is_maint = getattr(wingman, "maintenance_mode", False)
            if not is_maint:
                now = time.time()
                node_lan_ip = route_info.get("local_ip") or get_local_lan_ip() or "127.0.0.1"
                for sess in list(wingman.security.sessions.values()):
                    if getattr(sess, "status", "") == "pending":
                        age = now - getattr(sess, "last_seen", sess.created_at)
                        if age < 45.0:
                            cip = getattr(sess, "client_ip", "")
                            if cip in ("127.0.0.1", "::1", "localhost", ""):
                                cip = node_lan_ip
                            pending_auth_list.append({
                                "auth_req_id": sess.session_id,
                                "session_id": sess.session_id,
                                "client_ip": cip,
                                "user_agent": getattr(sess, "user_agent", ""),
                                "device_id": getattr(sess, "device_id", ""),
                                "timestamp": getattr(sess, "last_seen", now),
                            })
                if pending_auth_list:
                    is_active_browser = True
        except Exception:
            pass

    webapplet_info = {
        "running": wingman.engine.is_running if (wingman and hasattr(wingman, "engine")) else False,
        "port": wingman.engine.port if (wingman and hasattr(wingman, "engine")) else 8888,
        "wingman_active": is_active_browser,
        "client_count": wingman.client_count if (wingman and hasattr(wingman, "client_count")) else 0,
        "pending_auth": pending_auth_list,
    }

    return {
        "hostname": socket.gethostname(),
        "system": uname.system,
        "release": uname.release,
        "machine": uname.machine,
        "python": platform.python_version(),
        "pid": os.getpid(),
        "uptime_seconds": round(get_system_uptime(), 1),
        "disk_free_gb": round(free_b / (1024 ** 3), 2),
        "disk_total_gb": round(total_b / (1024 ** 3), 2),
        "has_ipad_mount": has_ipad_mount,
        "ipad_files_count": ipad_files_count,
        "is_ish": is_ish,
        "is_termux": is_termux,
        "has_wake_lock": has_wake_lock,
        "battery": battery,
        "route": route_info,
        "mem_total_mb": mem_total_mb,
        "mem_avail_mb": mem_avail_mb,
        "git_commit": git_commit,
        "git_branch": git_branch,
        "webapplet": webapplet_info,
    }


def check_github_repo(remote_url: str = "https://github.com/dieablo101/gemini-integrated.git") -> Dict[str, Any]:
    """Checks whether the local node git branch is in sync with GitHub remote HEAD."""
    try:
        res = subprocess.run(
            ["git", "ls-remote", remote_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            remote_head = res.stdout.split()[0][:7]
            local_res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            local_head = local_res.stdout.strip() if local_res.returncode == 0 else "unknown"
            up_to_date = (local_head == remote_head)
            return {
                "ok": True,
                "remote_head": remote_head,
                "local_head": local_head,
                "up_to_date": up_to_date,
            }
        return {"ok": False, "error": res.stderr.strip() or "Empty output from ls-remote"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def execute_fleet_upgrade(
    target_ref: str = "origin/main",
    force: bool = False,
    repo_dir: Optional[Path] = None,
    target_commit: Optional[str] = None,
    bundle_b64: Optional[str] = None,
    bundle_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Executes atomic 3-stage safety gated upgrade on the local node repository.

    Stage 0: Direct in-memory bundle unpack from Mothership (fastest, zero internet/git dependency).
    Stage 1: Fetch target remote ref safely (git fetch with tarball fallback).
    Stage 2: Fast-forward checkout/merge into clean state.
    Stage 3: Pre-flight syntax and import verification.
             Rolls back atomically via git reset if pre-flight fails!
    """
    cwd = find_repo_root(repo_dir)

    # Get current commit using fast reader first (safe for emulators)
    fast_commit, _ = _get_git_info_fast(cwd)
    if fast_commit != "unknown":
        old_commit = fast_commit
    else:
        res_old = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        old_commit = res_old.stdout.strip() if res_old.returncode == 0 else "initial"

    branch_target = target_ref.split("/")[-1] if "/" in target_ref else target_ref
    is_ish = is_ish_platform()

    # Stage 0: Direct in-memory bundle unpack from Mothership (fastest, zero internet/git dependency)
    git_worked = False
    if bundle_b64 and not bundle_bytes:
        try:
            bundle_bytes = base64.b64decode(bundle_b64.encode("ascii"))
        except Exception as exc:
            return {
                "status": "error",
                "stage": "bundle_decode",
                "error": f"Base64 decode failed: {exc}",
            }

    if bundle_bytes:
        try:
            import io
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tar:
                for member in tar.getmembers():
                    clean_name = member.name.lstrip("./")
                    if not clean_name:
                        continue
                    dest_path = cwd / clean_name
                    if member.isdir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                    elif member.isreg():
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        with tar.extractfile(member) as src, open(dest_path, "wb") as dst:
                            dst.write(src.read())

            if target_commit and target_commit != "unknown" and len(target_commit.strip()) >= 7:
                try:
                    ref_f = cwd / ".git" / "refs" / "heads" / branch_target
                    ref_f.parent.mkdir(parents=True, exist_ok=True)
                    ref_f.write_text(f"{target_commit.strip()}\n", encoding="utf-8")
                except Exception:
                    pass
            git_worked = True
        except Exception as exc:
            return {
                "status": "error",
                "stage": "bundle_extract",
                "error": f"Bundle extraction failed: {exc}",
            }

    # Stage 1 & 2: Prefer native git fetch & reset first across all platforms (except iSH where git segfaults)
    if not git_worked and not is_ish:
        try:
            fetch_res = subprocess.run(
                ["git", "fetch", "origin", branch_target],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if fetch_res.returncode == 0:
                reset_target = f"origin/{branch_target}"
                merge_cmd = ["git", "reset", "--hard", reset_target] if force else ["git", "merge", "--ff-only", "FETCH_HEAD"]
                merge_res = subprocess.run(
                    merge_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if merge_res.returncode != 0:
                    # Force fallback to reset --hard to origin/branch_target
                    fallback_res = subprocess.run(
                        ["git", "reset", "--hard", f"origin/{branch_target}"],
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    git_worked = (fallback_res.returncode == 0)
                else:
                    git_worked = True
        except Exception:
            git_worked = False

    if not git_worked:
        # Fallback to Pure-Python tarball stream (zero subprocess, immune to emulator git crashes)
        try:
            import urllib.request
            import tarfile
            import io
            url = f"https://github.com/dieablo101/gemini-integrated/archive/refs/heads/{branch_target}.tar.gz"
            req = urllib.request.Request(url, headers={"User-Agent": "Gemini-Satellite-Updater/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                tar_bytes = resp.read()
            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
                for member in tar.getmembers():
                    parts = Path(member.name).parts
                    if len(parts) > 1:
                        rel_path = Path(*parts[1:])
                        dest_path = cwd / rel_path
                        if member.isdir():
                            dest_path.mkdir(parents=True, exist_ok=True)
                        elif member.isreg():
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            with tar.extractfile(member) as src, open(dest_path, "wb") as dst:
                                dst.write(src.read())

            # Synchronize git ref so version reader reflects new target commit
            if target_commit and target_commit != "unknown" and len(target_commit.strip()) >= 7:
                try:
                    ref_f = cwd / ".git" / "refs" / "heads" / branch_target
                    if ref_f.parent.exists():
                        ref_f.write_text(f"{target_commit.strip()}\n", encoding="utf-8")
                except Exception:
                    pass
        except Exception as exc:
            return {
                "status": "error",
                "stage": "fetch",
                "error": f"Tarball update failed: {exc}",
            }

    # Stage 3: Pre-Flight Syntax & Import Validation Gate
    effective_py = get_effective_python(cwd)
    if not is_ish:
        py_files = [str(p) for p in cwd.glob("gemini_app/**/*.py")]
        for top_py in ("gemini-integrated.py", "__main__.py"):
            if (cwd / top_py).exists():
                py_files.append(top_py)

        if py_files:
            compile_res = subprocess.run(
                [effective_py, "-m", "py_compile"] + py_files[:50],  # Sample compile
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if compile_res.returncode != 0:
                # Atomic rollback!
                subprocess.run(["git", "reset", "--hard", old_commit], cwd=cwd, capture_output=True)
                return {
                    "status": "error",
                    "stage": "syntax_validation",
                    "error": f"Pre-flight py_compile failed: {compile_res.stderr.strip()}",
                    "rolled_back": True,
                    "current_commit": old_commit,
                }

    # Test import check
    import_res = subprocess.run(
        [effective_py, "-c", "import gemini_app; from gemini_app.fleet.satellite import SatelliteNode; print('VERIFIED')"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if import_res.returncode != 0 or "VERIFIED" not in import_res.stdout:
        # Atomic rollback!
        if not is_ish:
            subprocess.run(["git", "reset", "--hard", old_commit], cwd=cwd, capture_output=True)
        return {
            "status": "error",
            "stage": "import_validation",
            "error": f"Pre-flight import check failed: {import_res.stderr.strip()}",
            "rolled_back": not is_ish,
            "current_commit": old_commit,
        }

    # Successful upgrade
    new_commit, _ = _get_git_info_fast(cwd)
    if is_ish:
        if target_commit and target_commit != "unknown":
            new_commit = target_commit[:7]
            if len(target_commit.strip()) == 40:
                try:
                    ref_f = cwd / ".git" / "refs" / "heads" / branch_target
                    if ref_f.parent.exists():
                        ref_f.write_text(f"{target_commit.strip()}\n", encoding="utf-8")
                except Exception:
                    pass
        elif new_commit == "unknown":
            new_commit = "updated"
    elif new_commit == "unknown" or new_commit == old_commit:
        res_new = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_new.returncode == 0 and res_new.stdout.strip():
            new_commit = res_new.stdout.strip()
        elif target_commit:
            new_commit = target_commit[:7]
        else:
            new_commit = "updated"

    upgraded = (old_commit != new_commit) or (bool(target_commit) and old_commit != target_commit[:7]) or force
    msg = f"Pre-flight verified. Upgraded {old_commit} -> {new_commit}" if upgraded else "Code already matches origin/main."
    return {
        "status": "ok",
        "stage": "completed",
        "old_commit": old_commit,
        "new_commit": new_commit,
        "upgraded": upgraded,
        "message": msg,
    }


CONFIG_FILE: Path = Path.home() / ".gemini" / "config.json"


def is_lan_address(addr: Optional[str]) -> bool:
    """Checks whether an address is a local LAN address (RFC 1918 / loopback / ULA)."""
    if not addr or not isinstance(addr, str):
        return False
    a = addr.strip().lower()
    if a in ("localhost", "127.0.0.1", "::1"):
        return True
    if a.startswith("192.168.") or a.startswith("10.") or a.startswith("169.254."):
        return True
    if a.startswith("172."):
        parts = a.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            second = int(parts[1])
            if 16 <= second <= 31:
                return True
    if a.startswith("fe80:") or a.startswith("fd") or a.startswith("fc"):
        return True
    return False


def get_config_path() -> Path:
    """Returns path to ~/.gemini/config.json."""
    return CONFIG_FILE


def get_saved_mothership_ipv6() -> Optional[str]:
    """Retrieves saved WAN IPv6 address from ~/.gemini/config.json or env."""
    cfg_file = get_config_path()
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            if cfg.get("mothership_wan_ipv6"):
                return str(cfg["mothership_wan_ipv6"]).strip()
        except Exception:
            pass
    env_v6 = os.getenv("GEMINI_MOTHERSHIP_IPV6")
    if env_v6:
        return env_v6.strip()
    return None


def get_saved_mothership_endpoints() -> Tuple[Optional[str], Optional[str], int]:
    """Retrieves saved LAN IP, WAN IP, and port from ~/.gemini/config.json."""
    cfg_file = get_config_path()
    lan_ip = None
    wan_ip = None
    port = DEFAULT_PORT

    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            lan_ip = cfg.get("mothership_lan")
            wan_ip = cfg.get("mothership_wan")
            host_saved = cfg.get("mothership_host") or cfg.get("mothership")
            if host_saved and not lan_ip and not wan_ip:
                if is_lan_address(host_saved):
                    lan_ip = host_saved
                else:
                    wan_ip = host_saved
            if cfg.get("mothership_port") is not None:
                port = int(cfg["mothership_port"])
        except Exception:
            pass

    env_host = os.getenv("GEMINI_MOTHERSHIP")
    if env_host:
        if is_lan_address(env_host):
            lan_ip = env_host.strip()
        else:
            wan_ip = env_host.strip()

    env_wan = os.getenv("GEMINI_MOTHERSHIP_WAN")
    if env_wan:
        wan_ip = env_wan.strip()

    return lan_ip, wan_ip, port


def save_mothership_dual_endpoints(
    lan_ip: Optional[str] = None,
    wan_ip: Optional[str] = None,
    port: Optional[int] = None,
    wan_ipv6: Optional[str] = None,
) -> bool:
    """Persists dynamic LAN, WAN, and IPv6 endpoints to ~/.gemini/config.json."""
    cfg_file = get_config_path()
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg: Dict[str, Any] = {}
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    if lan_ip:
        cfg["mothership_lan"] = lan_ip.strip()
        cfg["mothership_host"] = lan_ip.strip()
    if wan_ip:
        cfg["mothership_wan"] = wan_ip.strip()
    if wan_ipv6:
        cfg["mothership_wan_ipv6"] = wan_ipv6.strip()
    if port is not None:
        cfg["mothership_port"] = int(port)

    try:
        cfg_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        cfg_file.chmod(0o600)
    except Exception as exc:
        sys.stderr.write(f"[satellite] Warning: could not write config file {cfg_file}: {exc}\n")
        return False

    if lan_ip:
        try:
            from gemini_app.fleet.autostart import update_autostart_mothership
            update_autostart_mothership(lan_ip.strip(), port=port)
        except Exception:
            pass

    return True


def _is_pid_running(pid: int) -> bool:
    """Checks if a given PID is currently active."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_singleton_lock(mode: str = "node") -> bool:
    """Guarantees only one satellite node or HUD instance runs at a time.

    CRITICAL REDUNDANCY:
    1. If starting 'hud' (interactive foreground user session):
       - Cleanly signals any existing background daemon ('node') to exit and waits for it to release port 8888.
    2. If starting 'node' (headless background daemon):
       - Checks if an interactive 'hud' session is actively running.
       - If 'hud' is active, 'node' immediately yields and exits (never killing the user's HUD!).
    """
    pid_dir = Path(tempfile.gettempdir())
    pid_file = pid_dir / f"gemini-satellite-{mode}.pid"
    other_mode = "node" if mode == "hud" else "hud"
    other_pid_file = pid_dir / f"gemini-satellite-{other_mode}.pid"

    my_pid = os.getpid()

    # Redundancy 1: If starting HUD, terminate any background node daemon cleanly
    if mode == "hud" and other_pid_file.exists():
        try:
            old_pid = int(other_pid_file.read_text().strip())
            if old_pid != my_pid and _is_pid_running(old_pid):
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    for _ in range(20):
                        time.sleep(0.1)
                        if not _is_pid_running(old_pid):
                            break
                    if _is_pid_running(old_pid):
                        os.kill(old_pid, signal.SIGKILL)
                        time.sleep(0.1)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            other_pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        # Brief pause to let OS reclaim TCP ports
        time.sleep(0.2)

    # Redundancy 2: If starting background node daemon, yield if interactive HUD is active!
    if mode == "node" and other_pid_file.exists():
        try:
            old_pid = int(other_pid_file.read_text().strip())
            if old_pid != my_pid and _is_pid_running(old_pid):
                sys.stderr.write(
                    f"[satellite] Interactive HUD session is active (PID {old_pid}). "
                    f"Background daemon yielding to interactive user session.\n"
                )
                return False
        except Exception:
            pass

    # Redundancy 3: Check same-mode PID
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            if old_pid != my_pid and _is_pid_running(old_pid):
                if mode == "hud":
                    # Attempt graceful termination of stale HUD if active
                    try:
                        os.kill(old_pid, signal.SIGTERM)
                        for _ in range(5):
                            time.sleep(0.1)
                            if not _is_pid_running(old_pid):
                                break
                    except Exception:
                        pass
                    if _is_pid_running(old_pid):
                        sys.stderr.write(f"[satellite] Another HUD session is already active (PID {old_pid}). Exiting.\n")
                        return False
                else:
                    sys.stderr.write(f"[satellite] Gemini node is already running (PID {old_pid}). Exiting duplicate process.\n")
                    return False
        except Exception:
            pass

    try:
        pid_file.write_text(str(my_pid))
        import atexit
        def _cleanup():
            try:
                if pid_file.exists():
                    p = int(pid_file.read_text().strip())
                    if p == my_pid:
                        pid_file.unlink(missing_ok=True)
            except Exception:
                pass
        atexit.register(_cleanup)
        return True
    except Exception:
        return True


def get_saved_mothership(default: Optional[str] = None) -> str:
    """Retrieves the default mothership IP/host."""
    try:
        lan_ip, wan_ip, _ = get_saved_mothership_endpoints()
        return lan_ip or wan_ip or default or "192.168.1.90"
    except Exception:
        return default or "192.168.1.90"


def get_saved_mothership_port(default: int = DEFAULT_PORT) -> int:
    """Retrieves the default mothership TCP port."""
    try:
        _, _, port = get_saved_mothership_endpoints()
        return port or default
    except Exception:
        return default


def save_mothership(host: str, port: Optional[int] = None) -> bool:
    """Persists mothership host and optional port to ~/.gemini/config.json."""
    if is_lan_address(host):
        return save_mothership_dual_endpoints(lan_ip=host, port=port)
    else:
        return save_mothership_dual_endpoints(wan_ip=host, port=port)


def format_node_error(exc: Any, context: str = "") -> Dict[str, Any]:
    """Formats an exception into a compact error code and relational summary for HUD and Mothership reporting."""
    errno_val = getattr(exc, "errno", None)
    err_str = str(exc)
    err_lower = err_str.lower()

    if errno_val:
        code = f"ERR#{errno_val}"
    elif "timed out" in err_lower or isinstance(exc, (TimeoutError, socket.timeout)):
        code = "ERR#TIMEOUT"
    elif "auth" in err_lower or "reject" in err_lower or isinstance(exc, PermissionError):
        code = "ERR#AUTH"
    elif "upg" in err_lower or "git" in err_lower:
        code = "ERR#UPG"
    elif "signature" in err_lower:
        code = "ERR#SIG"
    else:
        name = type(exc).__name__.replace("Error", "")
        code = f"ERR#{name[:6].upper()}" if name else "ERR#UNKNOWN"

    if errno_val == 104 or "connection reset" in err_lower:
        rel = "ConnReset"
    elif errno_val == 111 or "connection refused" in err_lower:
        rel = "Refused"
    elif errno_val == 113 or "no route" in err_lower:
        rel = "NoRoute"
    elif errno_val == 32 or "broken pipe" in err_lower:
        rel = "BrokenPipe"
    elif errno_val == 110 or "timed out" in err_lower:
        rel = "TimedOut"
    elif "auth" in err_lower or isinstance(exc, PermissionError):
        rel = "AuthFail"
    elif "signature" in err_lower:
        rel = "SigFail"
    elif "not connected" in err_lower:
        rel = "NotConn"
    else:
        words = re.sub(r"[^a-zA-Z0-9 ]", "", err_str).split()
        rel = "".join(w.capitalize() for w in words[:2]) if words else "Err"

    rel_ctx = f"{rel}:{context}" if context else rel
    short_str = f"{code} ({rel_ctx})"

    return {
        "errno": errno_val,
        "code": code,
        "relationals": rel_ctx,
        "short_str": short_str,
        "details": err_str[:120],
        "timestamp": time.time(),
    }


class SatelliteNode:
    """Satellite client connecting to the Mothership."""

    def __init__(
        self,
        mothership_host: Optional[str] = None,
        mothership_port: Optional[int] = None,
        node_id: Optional[str] = None,
        heartbeat_interval: float = 15.0,
        auto_upgrade: bool = True,
    ) -> None:
        self._explicit_host = mothership_host.strip() if mothership_host else None
        saved_lan, saved_wan, saved_port = get_saved_mothership_endpoints()
        self.lan_host: Optional[str] = saved_lan or ("192.168.1.90" if self._explicit_host is None else (self._explicit_host if is_lan_address(self._explicit_host) else "192.168.1.90"))
        self.wan_host: Optional[str] = saved_wan or (self._explicit_host if (self._explicit_host and not is_lan_address(self._explicit_host)) else None)
        self.wan_ipv6: Optional[str] = get_saved_mothership_ipv6()

        self.mothership_port = mothership_port if mothership_port is not None else saved_port
        self.mothership_host = self._explicit_host or self.lan_host or self.wan_host or self.wan_ipv6 or "192.168.1.90"
        self.active_host: str = self.mothership_host
        self.active_route_type: str = "LAN" if is_lan_address(self.active_host) else "WAN"

        # Auto-configure mobile environment on Android Termux
        if is_termux_platform():
            ensure_termux_mobile_environment(mothership_host=self.lan_host or self.mothership_host)

        self.heartbeat_interval = heartbeat_interval
        self.auto_upgrade = auto_upgrade
        self._is_upgrading = False
        self._last_attempted_target: Optional[str] = None

        # Derive an intuitive default node id
        if not node_id:
            h = socket.gethostname().lower()
            m = platform.machine().lower()
            if is_ish_platform():
                node_id = f"ipad-ish-{h}"
            elif is_termux_platform():
                node_id = f"android-termux-{h}"
            else:
                node_id = f"node-{m}-{h}"
        self.node_id = node_id

        self.sock: Optional[socket.socket] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._screenshot_watcher_thread: Optional[threading.Thread] = None
        self._rendezvous_sock: Optional[socket.socket] = None
        self._rendezvous_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self.hud = None  # SatelliteHUD instance if running in HUD mode
        self._pending_ping_t0: Optional[float] = None
        self.pending_responses: Dict[str, Any] = {}
        self.response_events: Dict[str, threading.Event] = {}
        self._pending_errors: List[Dict[str, Any]] = []
        self.mothership_boot_id: Optional[str] = None
        self.wingman_maintenance: bool = False

        self.wingman_applet = None
        try:
            from gemini_app.webapplet.applets.wingman import WingmanApplet
            self.wingman_applet = WingmanApplet(port=8888, node_id=self.node_id)
            set_active_wingman(self.wingman_applet)
            self.wingman_applet.set_passkey_verifier(self.verify_passkey_with_mothership)
            self.wingman_applet.engine.on_client_state_change(self._on_wingman_state_change)
            self.wingman_applet.on_action(self._on_wingman_card_action)
            self.wingman_applet.on_chat_message(self._on_wingman_chat_message)
            self.wingman_applet._chat_history_fetcher = self.fetch_chat_history_from_mothership
            self.wingman_applet.security.on_pending_session(self._on_wingman_pending_session)
            try:
                self.wingman_applet.update_local_vitals(collect_telemetry())
            except Exception:
                pass
        except Exception:
            pass

    def verify_passkey_with_mothership(self, passkey: str, timeout: float = 6.0) -> bool:
        """Verifies passkey with Mothership over persistent TCP connection."""
        if not self._running or not self.sock:
            # Fallback to local vault if mothership is unreachable
            try:
                from gemini_app.fleet.wingman_auth import verify_homebase_passkey
                return verify_homebase_passkey(passkey)
            except Exception:
                return False
        req_id = f"vpass-{int(time.time() * 1000)}"
        ev = threading.Event()
        self.response_events[req_id] = ev
        try:
            msg = FleetMessage(
                msg_type=FleetMessage.TYPE_COMMAND,
                node_id=self.node_id,
                payload={"action": "verify_wingman_passkey", "params": {"passkey": passkey}},
                msg_id=req_id,
            )
            if not self.send_message(msg):
                return False
            if ev.wait(timeout):
                resp = self.pending_responses.pop(req_id, {})
                return bool(resp.get("valid", False))
        except Exception:
            pass
        finally:
            self.response_events.pop(req_id, None)
            self.pending_responses.pop(req_id, None)
        return False

    def _on_wingman_pending_session(self, session: Any) -> None:
        """Dispatches an authorization request event to the Mothership."""
        device_ip = getattr(session, "client_ip", "127.0.0.1")
        if device_ip in ("127.0.0.1", "::1", "localhost", ""):
            route = get_local_route_info()
            device_ip = route.get("local_ip") or get_local_lan_ip() or "127.0.0.1"

        if self.hud:
            self.hud.show_toast(f"Wingman access requested from {device_ip}...", duration=5.0)

        ev_entry = {
            "event": "wingman_access_request",
            "session_id": session.session_id,
            "auth_req_id": session.session_id,
            "node_id": self.node_id,
            "client_ip": device_ip,
            "user_agent": getattr(session, "user_agent", ""),
            "device_id": getattr(session, "device_id", ""),
            "timestamp": time.time(),
        }

        if not self._running or not self.sock or self.wingman_maintenance:
            if not hasattr(self, "_queued_auth_events"):
                self._queued_auth_events = []
            self._queued_auth_events.append(ev_entry)
            return

        try:
            ev = FleetMessage(
                msg_type=FleetMessage.TYPE_EVENT,
                node_id=self.node_id,
                payload=ev_entry,
            )
            self.send_message(ev)
        except Exception:
            pass

    def _on_wingman_chat_message(self, sender: str, text: str, body: Dict[str, Any]) -> None:
        """Transmits remote chat message from Wingman UI to Mothership."""
        if not self._running or not self.sock:
            return
        msg_id = body.get("id") or body.get("msg_id", "")
        attachment = body.get("attachment")
        try:
            payload = {
                "event": "wingman_chat_message",
                "node_id": self.node_id,
                "sender": sender,
                "text": text,
                "id": msg_id,
                "timestamp": time.time(),
            }
            if attachment:
                payload["attachment"] = attachment
            ev = FleetMessage(
                msg_type=FleetMessage.TYPE_EVENT,
                node_id=self.node_id,
                payload=payload,
            )
            self.send_message(ev)
        except Exception:
            pass

    def fetch_chat_history_from_mothership(self, timeout: float = 3.0) -> List[Dict[str, Any]]:
        """Queries Mothership for current fleet chat history."""
        if not self._running or not self.sock:
            return []
        req_id = f"chathist-{int(time.time() * 1000)}"
        ev = threading.Event()
        self.response_events[req_id] = ev
        try:
            msg = FleetMessage(
                msg_type=FleetMessage.TYPE_COMMAND,
                node_id=self.node_id,
                payload={"action": "get_wingman_chat_history"},
                msg_id=req_id,
            )
            if not self.send_message(msg):
                return []
            if ev.wait(timeout):
                resp = self.pending_responses.pop(req_id, {})
                return resp.get("history", [])
        except Exception:
            pass
        finally:
            self.response_events.pop(req_id, None)
            self.pending_responses.pop(req_id, None)
        return []

    def _on_wingman_card_action(self, card_id: str, action: str, body: Dict[str, Any]) -> None:
        """Transmits user button click or camera photo from Wingman UI back to Mothership."""
        if not self._running or not self.sock:
            return
        try:
            ev_type = "camera_photo_captured" if action == "photo_captured" else "wingman_action"
            ev = FleetMessage(
                msg_type=FleetMessage.TYPE_EVENT,
                node_id=self.node_id,
                payload={
                    "event": ev_type,
                    "card_id": card_id,
                    "action": action,
                    "body": body,
                    "filename": body.get("filename", "photo.jpg"),
                    "data_b64": body.get("data_b64", ""),
                    "timestamp": time.time(),
                },
            )
            self.send_message(ev)
        except Exception:
            pass

    def _on_wingman_state_change(self, is_active: bool, count: int) -> None:
        """Notifies Mothership immediately when user opens or closes Wingman on localhost."""
        if not is_active and self.wingman_applet and hasattr(self.wingman_applet, "security"):
            try:
                self.wingman_applet.security.prune_stale_sessions(max_pending_age=45.0, invalidate_unpaired=False)
            except Exception:
                pass

        if not self._running or not self.sock:
            return
        try:
            ev = FleetMessage(
                msg_type=FleetMessage.TYPE_EVENT,
                node_id=self.node_id,
                payload={
                    "event": "wingman_opened" if is_active else "wingman_closed",
                    "wingman_active": is_active,
                    "client_count": count,
                    "port": self.wingman_applet.engine.port if self.wingman_applet else 8888,
                },
            )
            self.send_message(ev)
            hb = FleetMessage(
                msg_type=FleetMessage.TYPE_HEARTBEAT,
                node_id=self.node_id,
                payload={"telemetry": collect_telemetry()},
            )
            self.send_message(hb)
        except Exception:
            pass

    def report_error(self, exc: Any, context: str = "") -> Dict[str, Any]:
        """Formats and reports a node error on HUD and transmits telemetry back to Mothership."""
        err_data = format_node_error(exc, context=context)
        if self.hud:
            self.hud.show_toast(err_data["short_str"], duration=5.0)
            self.hud.log_event(f"Error: {err_data['short_str']}")

        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_ERROR,
            node_id=self.node_id,
            payload={"error": err_data},
        )
        sent = False
        if self._running and self.sock:
            try:
                sent = self.send_message(msg)
            except Exception:
                sent = False
        if not sent:
            self._pending_errors.append(err_data)
            if len(self._pending_errors) > 10:
                self._pending_errors.pop(0)

        return err_data

    def _flush_pending_errors(self) -> None:
        """Sends queued errors and pending auth requests to Mothership once connection is established."""
        if not self._running or not self.sock:
            return
        while getattr(self, "_queued_auth_events", None):
            ev_data = self._queued_auth_events.pop(0)
            msg = FleetMessage(
                msg_type=FleetMessage.TYPE_EVENT,
                node_id=self.node_id,
                payload=ev_data,
            )
            self.send_message(msg)

        if self.wingman_applet and hasattr(self.wingman_applet, "security"):
            try:
                now_t = time.time()
                for s in list(self.wingman_applet.security.sessions.values()):
                    if getattr(s, "status", "") == "pending" and (now_t - getattr(s, "last_seen", s.created_at)) < 45.0:
                        self._on_wingman_pending_session(s)
            except Exception:
                pass

        if not self._pending_errors:
            return
        while self._pending_errors:
            err = self._pending_errors.pop(0)
            msg = FleetMessage(
                msg_type=FleetMessage.TYPE_ERROR,
                node_id=self.node_id,
                payload={"error": err},
            )
            self.send_message(msg)

    def request_mothership_bundle(self, timeout: float = 8.0) -> tuple[Optional[str], Optional[str]]:
        """Requests direct code bundle from Mothership over persistent TCP connection."""
        if not self.sock or not self._running:
            return None, None
        req_id = f"bundle-req-{int(time.time() * 1000)}"
        ev = threading.Event()
        self.response_events[req_id] = ev
        try:
            req_msg = FleetMessage(
                msg_type=FleetMessage.TYPE_COMMAND,
                node_id=self.node_id,
                payload={"action": "get_update_bundle"},
                msg_id=req_id,
            )
            self.send_message(req_msg)
            if ev.wait(timeout):
                resp = self.pending_responses.pop(req_id, {})
                if resp.get("status") == "ok":
                    return resp.get("bundle_b64"), resp.get("target_commit")
        except Exception:
            pass
        finally:
            self.response_events.pop(req_id, None)
            self.pending_responses.pop(req_id, None)
        return None, None

    def connect(self, timeout: float = 4.0) -> bool:
        """Establishes TCP connection to the Mothership with automatic LAN -> WAN failover."""
        # Candidates in priority order
        candidates = []
        seen_hosts = set()

        def add_candidate(h: Optional[str], route: str):
            if h and h.strip() and h.strip() not in seen_hosts:
                seen_hosts.add(h.strip())
                candidates.append((h.strip(), route))

        if self._explicit_host:
            explicit_route = "LAN" if is_lan_address(self._explicit_host) else "WAN"
            add_candidate(self._explicit_host, explicit_route)
            # Automatic WAN failover for roaming/cellular even when explicit LAN host was specified
            if explicit_route == "LAN":
                if self.wan_host:
                    add_candidate(self.wan_host, "WAN")
                if getattr(self, "wan_ipv6", None):
                    add_candidate(self.wan_ipv6, "WAN-IPv6")
            else:
                if self.lan_host:
                    add_candidate(self.lan_host, "LAN")
        else:
            if self.lan_host:
                add_candidate(self.lan_host, "LAN")
            if self.wan_host and self.wan_host != self.lan_host:
                add_candidate(self.wan_host, "WAN")
            if getattr(self, "wan_ipv6", None):
                add_candidate(self.wan_ipv6, "WAN-IPv6")
            if not candidates and self.mothership_host:
                add_candidate(self.mothership_host, "LAN" if is_lan_address(self.mothership_host) else "WAN")

        last_exc = None
        for host, route_type in candidates:
            try:
                # Fast timeout on LAN (1.8s) when WAN fallback exists so off-wifi nodes don't stall
                t_out = 1.8 if (route_type == "LAN" and len(candidates) > 1) else timeout
                s = socket.create_connection((host, self.mothership_port), timeout=t_out)
                # Mobile-hardened TCP Keepalive (detects carrier/Wi-Fi drops in ~20-30s instead of hanging 15+ minutes)
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    if hasattr(socket, "TCP_KEEPIDLE"):
                        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                    if hasattr(socket, "TCP_KEEPINTVL"):
                        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                    if hasattr(socket, "TCP_KEEPCNT"):
                        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                except Exception:
                    pass
                s.settimeout(None)  # Switch to blocking / select-ready for threads
                self.sock = s
                self.active_host = host
                self.active_route_type = route_type
                self.mothership_host = host
                if self.hud:
                    self.hud.mothership_addr = f"{host}:{self.mothership_port}"
                    self.hud.set_endpoints(self.lan_host, self.wan_host)
                    self.hud.set_connection_status(True, route_info=f"{route_type} ({host})")
                return True
            except Exception as exc:
                last_exc = exc
                if not self.hud:
                    sys.stderr.write(f"[satellite] Connection attempt via {route_type} ({host}:{self.mothership_port}) failed: {exc}\n")
                continue

        if self.hud:
            self.hud.set_connection_status(False)
            if last_exc:
                self.report_error(last_exc, context="connect")
        return False

    def send_message(self, msg: FleetMessage) -> bool:
        """Sends a framed FleetMessage over the socket."""
        if not self.sock:
            return False
        with self._write_lock:
            try:
                self.sock.sendall(msg.serialize())
                return True
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                self._running = False
                if self.hud:
                    self.hud.set_connection_status(False)
                    self.report_error(exc, context="send")
                else:
                    sys.stderr.write(f"[satellite] Connection lost: {exc}\n")
                return False
            except Exception as exc:
                if self.hud:
                    self.report_error(exc, context="send")
                else:
                    sys.stderr.write(f"[satellite] Send failed: {exc}\n")
                return False

    def handle_command(self, cmd_msg: FleetMessage) -> FleetMessage:
        """Dispatches an incoming command from the Mothership and prepares response."""
        action = cmd_msg.payload.get("action", "unknown")
        params = cmd_msg.payload.get("params", {})
        result_payload: Dict[str, Any] = {"status": "ok", "action": action}

        # Mutual Authentication Security Gate: verify signature from Mothership
        fleet_key = get_or_create_fleet_key()
        auth_sig = cmd_msg.payload.get("auth_sig")
        auth_ts = cmd_msg.payload.get("auth_ts")
        if auth_sig and auth_ts:
            if not verify_command_signature(fleet_key, action, self.node_id, auth_ts, auth_sig):
                sys.stderr.write(f"[satellite] REJECTED unauthorized command '{action}' from Mothership (invalid signature)\n")
                return FleetMessage(
                    msg_type=FleetMessage.TYPE_RESPONSE,
                    node_id=self.node_id,
                    payload={"status": "error", "error": "Unauthorized command: Mothership signature verification failed"},
                    msg_id=f"resp-{cmd_msg.msg_id}",
                )

        if action == "ping":
            result_payload["pong"] = time.time()
            result_payload["client_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

        elif action == "telemetry":
            result_payload["telemetry"] = collect_telemetry()

        elif action == "exec":
            cmd = params.get("command")
            if not cmd:
                result_payload["status"] = "error"
                result_payload["error"] = "No command provided"
            else:
                try:
                    proc = subprocess.run(
                        cmd,
                        shell=isinstance(cmd, str),
                        capture_output=True,
                        text=True,
                        timeout=params.get("timeout", 30),
                    )
                    result_payload["stdout"] = proc.stdout
                    result_payload["stderr"] = proc.stderr
                    result_payload["exit_code"] = proc.returncode
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)

        elif action == "git_check":
            remote = params.get("remote", "https://github.com/dieablo101/gemini-integrated.git")
            result_payload["git_check"] = check_github_repo(remote)

        elif action == "webapplet_push":
            if self.wingman_applet:
                title = params.get("title", "Gemini")
                content = params.get("content", "")
                actions = params.get("actions", [])
                accent = params.get("accent", True)
                cid = self.wingman_applet.push_card(title=title, content=content, actions=actions, accent=accent)
                result_payload["card_id"] = cid
            else:
                result_payload["status"] = "error"
                result_payload["error"] = "Wingman applet not initialized on node"

        elif action == "biometric_auth":
            reason = params.get("reason", "Authorize Action")
            t_out = float(params.get("timeout", 30.0))
            method = params.get("method", "auto")
            if is_termux_platform() and method in ("auto", "android_fingerprint", "fingerprint"):
                try:
                    from gemini_app.fleet.biometrics import authenticate_local_termux
                    result_payload.update(authenticate_local_termux(reason=reason, timeout=int(t_out)))
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            elif self.wingman_applet:
                bio_res = self.wingman_applet.request_biometric(reason=reason, method=method, timeout=t_out)
                result_payload.update(bio_res)
            else:
                result_payload["status"] = "error"
                result_payload["error"] = "No biometric provider active on node"

        elif action in ("wingman_auth_decision", "authorize_wingman"):
            sess_id = params.get("session_id") or params.get("auth_req_id", "")
            dev_id = params.get("device_id", "")
            decision = params.get("decision", "accept")
            accepted = params.get("accepted", True) if "accepted" in params else (decision in ("accept", "pair", "trust"))
            trust_device = params.get("trust_device", False) or params.get("trust", False) or (decision in ("pair", "trust"))
            if self.wingman_applet:
                res = self.wingman_applet.authorize_session(sess_id, accepted=accepted, trust_device=trust_device, device_id=dev_id)
                result_payload.update(res)
                if self.hud:
                    self.hud.show_toast(f"Wingman auth {decision.upper()}", duration=4.0)
            else:
                result_payload["status"] = "error"
                result_payload["error"] = "Wingman applet not active on node"

        elif action == "wingman_prompt_passkey":
            reason = params.get("reason", "Authorize Bilateral Homebase Message")
            prompt_id = params.get("prompt_id")
            if self.wingman_applet:
                p_id = self.wingman_applet.prompt_passkey(reason=reason, prompt_id=prompt_id)
                result_payload["prompt_id"] = p_id
                result_payload["status"] = "ok"
            else:
                result_payload["status"] = "error"
                result_payload["error"] = "Wingman applet not active on node"

        elif action == "fleet_upgrade":
            target_ref = params.get("target_ref", "origin/main")
            target_commit = params.get("target_commit")
            force = params.get("force", False)
            bundle_b64 = params.get("bundle_b64")
            if self.hud:
                self.hud.show_toast(f"Upgrading from Mothership ({target_commit[:7] if target_commit else target_ref})...", duration=5.0)
            upgrade_res = execute_fleet_upgrade(
                target_ref=target_ref,
                force=force,
                target_commit=target_commit,
                bundle_b64=bundle_b64,
            )
            result_payload.update(upgrade_res)

            # If upgrade succeeded and code was updated, trigger scheduled reboot
            if upgrade_res.get("status") == "ok" and upgrade_res.get("upgraded"):
                def _do_reboot():
                    time.sleep(1.0)
                    self._running = False
                    if self.sock:
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                    if self.hud:
                        try:
                            self.hud.restore_terminal()
                        except Exception:
                            pass
                    if os.environ.get("GEMINI_WATCHDOG") == "1":
                        sys.exit(42)
                    else:
                        _exec_reboot()

                threading.Thread(target=_do_reboot, daemon=True).start()

        elif action == "shutdown":
            result_payload["message"] = "Node shutting down cleanly"
            self._running = False

        elif action in ("list_screenshots", "find_screenshots"):
            limit = int(params.get("limit", 10))
            result_payload["screenshots"] = find_node_screenshots(limit=limit)

        elif action == "media_control":
            sub_act = params.get("media_action", "next").lower().strip()
            key_map = {
                "next": "next",
                "skip": "next",
                "previous": "previous",
                "prev": "previous",
                "back": "previous",
                "play": "play",
                "pause": "pause",
                "play_pause": "play-pause",
                "toggle": "play-pause",
                "stop": "stop",
            }
            target_key = key_map.get(sub_act, sub_act)
            success = False
            dispatched = []

            if is_termux_platform():
                # 1. Android MediaSession dispatch (zero root/adb required for media keys)
                try:
                    p1 = subprocess.run(
                        ["/system/bin/cmd", "media_session", "dispatch", target_key],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if p1.returncode == 0:
                        success = True
                        dispatched.append("media_session")
                except Exception:
                    pass

                # 2. Spotify Android broadcast intents
                spotify_action_map = {
                    "next": [
                        "com.spotify.mobile.android.ui.widget.NEXT",
                        "com.spotify.music.playbackcontrol.ACTION_NEXT",
                    ],
                    "previous": [
                        "com.spotify.mobile.android.ui.widget.PREVIOUS",
                        "com.spotify.music.playbackcontrol.ACTION_PREVIOUS",
                    ],
                    "play": ["com.spotify.mobile.android.ui.widget.PLAY"],
                    "pause": ["com.spotify.mobile.android.ui.widget.PAUSE"],
                    "play-pause": ["com.spotify.mobile.android.ui.widget.PLAY"],
                }
                for act_intent in spotify_action_map.get(target_key, []):
                    try:
                        p2 = subprocess.run(
                            ["am", "broadcast", "-a", act_intent, "-p", "com.spotify.music"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if p2.returncode == 0:
                            success = True
                            dispatched.append(act_intent)
                    except Exception:
                        pass

            elif shutil.which("playerctl"):
                try:
                    p_cmd = ["playerctl", target_key if target_key != "play-pause" else "play-pause"]
                    p3 = subprocess.run(p_cmd, capture_output=True, text=True, timeout=5)
                    if p3.returncode == 0:
                        success = True
                        dispatched.append("playerctl")
                except Exception:
                    pass

            result_payload["status"] = "ok" if (success or dispatched) else "error"
            result_payload["media_action"] = target_key
            result_payload["dispatched_methods"] = dispatched
            if not success and not dispatched:
                result_payload["error"] = f"Unable to dispatch media command '{target_key}' on this node platform."

        elif action in ("fetch_latest_screenshot", "get_screenshot", "fetch_screenshot"):
            import base64
            target_file = params.get("path") or params.get("filename")
            if target_file:
                target_p = Path(target_file)
            else:
                found = find_node_screenshots(limit=1)
                target_p = Path(found[0]["path"]) if found else None

            if not target_p or not target_p.exists() or not target_p.is_file():
                result_payload["status"] = "not_found"
                result_payload["error"] = "No screenshots found on node"
            else:
                try:
                    data = target_p.read_bytes()
                    st = target_p.stat()
                    result_payload["status"] = "ok"
                    result_payload["filename"] = target_p.name
                    result_payload["path"] = str(target_p)
                    result_payload["mtime"] = st.st_mtime
                    result_payload["size_bytes"] = len(data)
                    result_payload["data_b64"] = base64.b64encode(data).decode("ascii")
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = f"Failed to read screenshot: {exc}"

        elif action in ("record_audio", "audio_record", "mic_record"):
            import base64
            duration = int(params.get("duration", 5))
            duration = max(1, min(duration, 60))
            encoder = str(params.get("encoder", "opus")).lower().strip()
            if encoder not in ("opus", "aac", "amr_wb", "amr_nb", "mp4"):
                encoder = "opus"
            ext = "opus" if encoder == "opus" else ("m4a" if encoder in ("aac", "mp4") else encoder)

            if params.get("stop"):
                if is_termux_platform() and shutil.which("termux-microphone-record"):
                    subprocess.run(["termux-microphone-record", "-d"], capture_output=True, timeout=5)
                    result_payload["status"] = "ok"
                    result_payload["message"] = "Recording stopped"
                else:
                    result_payload["status"] = "error"
                    result_payload["error"] = "Not recording or termux-microphone-record unavailable"
            elif params.get("info"):
                if is_termux_platform() and shutil.which("termux-microphone-record"):
                    p = subprocess.run(["termux-microphone-record", "-i"], capture_output=True, text=True, timeout=5)
                    try:
                        result_payload["info"] = json.loads(p.stdout)
                        result_payload["status"] = "ok"
                    except Exception:
                        result_payload["status"] = "ok"
                        result_payload["raw"] = p.stdout.strip()
                else:
                    result_payload["status"] = "error"
                    result_payload["error"] = "termux-microphone-record unavailable"
            else:
                if is_termux_platform() and shutil.which("termux-microphone-record"):
                    tmp_dir = Path.home()
                    tmp_file = tmp_dir / f"audio_capture_{int(time.time())}.{ext}"
                    try:
                        rec_cmd = ["termux-microphone-record", "-l", str(duration), "-f", str(tmp_file), "-e", encoder]
                        p_start = subprocess.run(rec_cmd, capture_output=True, text=True, timeout=10)
                        if p_start.returncode != 0:
                            result_payload["status"] = "error"
                            result_payload["error"] = p_start.stderr or p_start.stdout or "Failed to start recording"
                        else:
                            t_start = time.time()
                            while (time.time() - t_start) < (duration + 6.0):
                                time.sleep(0.5)
                                chk = subprocess.run(["termux-microphone-record", "-i"], capture_output=True, text=True, timeout=4)
                                if '"isRecording": false' in chk.stdout:
                                    break
                            if tmp_file.exists() and tmp_file.stat().st_size > 0:
                                raw_bytes = tmp_file.read_bytes()
                                result_payload["status"] = "ok"
                                result_payload["filename"] = tmp_file.name
                                result_payload["encoder"] = encoder
                                result_payload["duration"] = duration
                                result_payload["size_bytes"] = len(raw_bytes)
                                result_payload["data_b64"] = base64.b64encode(raw_bytes).decode("ascii")
                                try:
                                    tmp_file.unlink()
                                except Exception:
                                    pass
                            else:
                                result_payload["status"] = "error"
                                result_payload["error"] = "Recorded audio file was empty or missing"
                    except Exception as exc:
                        result_payload["status"] = "error"
                        result_payload["error"] = f"Audio capture exception: {exc}"
                        if tmp_file.exists():
                            try:
                                tmp_file.unlink()
                            except Exception:
                                pass
                else:
                    result_payload["status"] = "unsupported"
                    result_payload["error"] = "Audio recording is currently only supported on Termux nodes with termux-api"

        elif action in ("tts_speak", "whisper", "say"):
            text = params.get("text") or params.get("message") or ""
            stream = str(params.get("stream") or "MUSIC").upper().strip()
            pitch = float(params.get("pitch", 1.0))
            rate = float(params.get("rate", 1.0))
            engine = params.get("engine", "")
            duck = bool(params.get("duck", True))

            if not text:
                result_payload["status"] = "error"
                result_payload["error"] = "Empty text for TTS"
            elif is_termux_platform() and shutil.which("termux-tts-speak"):
                original_music_vol = None
                ducked = False
                duck_vol = None

                # Query current music stream volume to support smooth audio ducking
                if duck and shutil.which("termux-volume"):
                    try:
                        vp = subprocess.run(["termux-volume"], capture_output=True, text=True, timeout=3)
                        if vp.returncode == 0:
                            vdata = json.loads(vp.stdout)
                            for item in vdata:
                                if str(item.get("stream", "")).lower() == "music":
                                    original_music_vol = int(item.get("volume", 15))
                                    break
                    except Exception:
                        pass

                if original_music_vol is not None and original_music_vol > 3:
                    custom_duck = params.get("duck_volume")
                    if custom_duck is not None:
                        duck_vol = int(custom_duck)
                    else:
                        # 0.55 ducking ratio balances music attenuation without squashing TTS vocal gain
                        duck_ratio = float(params.get("duck_ratio", 0.55))
                        duck_vol = min(original_music_vol, max(4, int(original_music_vol * duck_ratio)))
                    try:
                        subprocess.run(["termux-volume", "music", str(duck_vol)], capture_output=True, text=True, timeout=3)
                        ducked = True
                    except Exception:
                        pass

                cmd = ["termux-tts-speak", "-s", stream, "-p", str(pitch), "-r", str(rate)]
                if engine:
                    cmd.extend(["-e", engine])
                cmd.append(text)
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
                    if p.returncode == 0:
                        result_payload["status"] = "ok"
                        result_payload["text"] = text
                        result_payload["stream"] = stream
                        result_payload["ducked"] = ducked
                        if ducked:
                            result_payload["original_volume"] = original_music_vol
                            result_payload["duck_volume"] = duck_vol
                            # Hold ducking until utterance completes
                            words = len(text.split())
                            dur = max(1.8, (words / (2.6 * max(0.1, rate))) + 0.8)
                            time.sleep(dur)
                    else:
                        result_payload["status"] = "error"
                        result_payload["error"] = p.stderr or p.stdout or "TTS synthesis failed"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
                finally:
                    # Restore music volume cleanly after speech completes
                    if ducked and original_music_vol is not None:
                        try:
                            # Small rest to avoid abrupt volume pop
                            time.sleep(0.3)
                            subprocess.run(["termux-volume", "music", str(original_music_vol)], capture_output=True, text=True, timeout=3)
                        except Exception:
                            pass
            elif shutil.which("spd-say"):
                try:
                    p = subprocess.run(["spd-say", text], capture_output=True, text=True, timeout=10)
                    result_payload["status"] = "ok" if p.returncode == 0 else "error"
                    result_payload["engine"] = "spd-say"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            elif shutil.which("espeak"):
                try:
                    p = subprocess.run(["espeak", text], capture_output=True, text=True, timeout=10)
                    result_payload["status"] = "ok" if p.returncode == 0 else "error"
                    result_payload["engine"] = "espeak"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            else:
                result_payload["status"] = "unsupported"
                result_payload["error"] = "No TTS engine available on this node"

        elif action in ("audio_info", "get_audio_info"):
            if is_termux_platform() and shutil.which("termux-audio-info"):
                try:
                    p = subprocess.run(["termux-audio-info"], capture_output=True, text=True, timeout=5)
                    if p.returncode == 0:
                        result_payload["status"] = "ok"
                        try:
                            ainfo = json.loads(p.stdout)
                        except Exception:
                            ainfo = {"raw": p.stdout}
                        result_payload["audio_info"] = ainfo
                        result_payload["bluetooth_a2dp"] = bool(ainfo.get("BLUETOOTH_A2DP_IS_ON", False))
                        result_payload["wired_headset"] = bool(ainfo.get("WIREDHEADSET_IS_CONNECTED", False))
                        result_payload["headphones_connected"] = bool(
                            result_payload["bluetooth_a2dp"] or result_payload["wired_headset"]
                        )
                    else:
                        result_payload["status"] = "error"
                        result_payload["error"] = p.stderr or "termux-audio-info returned non-zero"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)

                if shutil.which("termux-volume"):
                    try:
                        vp = subprocess.run(["termux-volume"], capture_output=True, text=True, timeout=3)
                        if vp.returncode == 0:
                            vdata = json.loads(vp.stdout)
                            result_payload["volumes"] = vdata
                            for item in vdata:
                                if str(item.get("stream", "")).lower() == "music":
                                    result_payload["music_volume"] = item.get("volume")
                                    result_payload["max_music_volume"] = item.get("max_volume")
                                    break
                    except Exception:
                        pass
            else:
                result_payload["status"] = "unsupported"
                result_payload["error"] = "termux-audio-info is only supported on Termux nodes"

        elif action in ("volume_control", "volume", "set_volume"):
            stream = str(params.get("stream") or "music").lower().strip()
            target_vol = params.get("volume")
            if is_termux_platform() and shutil.which("termux-volume"):
                try:
                    if target_vol is not None:
                        cmd = ["termux-volume", stream, str(target_vol)]
                        p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    else:
                        p = subprocess.run(["termux-volume"], capture_output=True, text=True, timeout=5)
                    if p.returncode == 0:
                        result_payload["status"] = "ok"
                        try:
                            result_payload["volume"] = json.loads(p.stdout)
                        except Exception:
                            result_payload["volume"] = p.stdout.strip()
                    else:
                        result_payload["status"] = "error"
                        result_payload["error"] = p.stderr or "termux-volume returned non-zero"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            else:
                result_payload["status"] = "unsupported"
                result_payload["error"] = "termux-volume is only supported on Termux nodes"

        elif action == "toast":
            msg = params.get("message") or params.get("text") or "Bilateral notification"
            bg = str(params.get("background", "gray"))
            color = str(params.get("color", "white"))
            if is_termux_platform() and shutil.which("termux-toast"):
                cmd = ["termux-toast", "-b", bg, "-c", color, msg]
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    result_payload["status"] = "ok"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            else:
                result_payload["status"] = "unsupported"

        elif action == "vibrate":
            dur = int(params.get("duration_ms", 300))
            if is_termux_platform() and shutil.which("termux-vibrate"):
                cmd = ["termux-vibrate", "-d", str(dur)]
                if params.get("force"):
                    cmd.append("-f")
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    result_payload["status"] = "ok"
                except Exception as exc:
                    result_payload["status"] = "error"
                    result_payload["error"] = str(exc)
            else:
                result_payload["status"] = "unsupported"

        else:
            result_payload["status"] = "unsupported"
            result_payload["error"] = f"Unknown action: {action}"

        return FleetMessage(
            msg_type=FleetMessage.TYPE_RESPONSE,
            node_id=self.node_id,
            payload=result_payload,
            msg_id=f"resp-{cmd_msg.msg_id}",
        )

    def _trigger_auto_upgrade(self, target_commit: str, current_commit: str) -> None:
        """Asynchronously triggers node auto-upgrade and reboots whatever node mode was running."""
        now = time.time()
        if getattr(self, "_last_attempted_target", None) == target_commit and (now - getattr(self, "_last_attempt_time", 0.0)) < 120.0:
            return
        if self._is_upgrading:
            return
        self._last_attempted_target = target_commit
        self._last_attempt_time = now
        self._is_upgrading = True

        def _worker():
            try:
                msg = f"Mothership updated ({current_commit} -> {target_commit})! Auto-updating..."
                if self.hud:
                    self.hud.show_toast(msg, duration=5.0)
                else:
                    sys.stdout.write(f"[satellite] {msg}\n")

                bundle_b64, ms_c = self.request_mothership_bundle(timeout=8.0)
                target_c = ms_c or target_commit
                res = execute_fleet_upgrade(
                    target_ref="origin/main",
                    target_commit=target_c,
                    bundle_b64=bundle_b64,
                )
                if res.get("status") == "ok" and res.get("upgraded"):
                    new_c = res.get("new_commit", target_commit)
                    done_msg = f"Upgraded to {new_c}! Rebooting..."
                    if self.hud:
                        self.hud.show_toast(done_msg, duration=3.0)
                    else:
                        sys.stdout.write(f"[satellite] {done_msg}\n")
                    time.sleep(1.0)
                    self._running = False
                    if self.sock:
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                    if self.hud:
                        try:
                            self.hud.restore_terminal()
                        except Exception:
                            pass
                    if os.environ.get("GEMINI_WATCHDOG") == "1":
                        sys.exit(42)
                    else:
                        _exec_reboot()
                elif res.get("status") == "ok":
                    if self.hud:
                        self.hud.show_toast("Code already matches origin/main.", duration=3.0)
                    # If target_commit was passed and local git ref was behind, sync it
                    if target_commit and target_commit != "unknown":
                        try:
                            cwd = find_repo_root()
                            ref_path = cwd / ".git" / "refs" / "heads" / "main"
                            if ref_path.exists():
                                ref_path.write_text(f"{target_commit}\n", encoding="utf-8")
                        except Exception:
                            pass
                else:
                    err_msg = res.get("error", "Unknown upgrade error")
                    if self.hud:
                        self.hud.show_toast(f"Auto-update: {err_msg[:40]}", duration=4.0)
                    else:
                        sys.stderr.write(f"[satellite] Auto-upgrade paused: {err_msg}\n")
            except Exception as exc:
                if self.hud:
                    self.hud.show_toast(f"Auto-upgrade error: {exc}", duration=4.0)
                else:
                    sys.stderr.write(f"[satellite] Auto-upgrade exception: {exc}\n")
            finally:
                time.sleep(15.0)  # Rate-limit re-triggers
                self._is_upgrading = False

        threading.Thread(target=_worker, daemon=True, name="satellite-auto-upgrade").start()

    def _listen_loop(self) -> None:
        """Reads incoming line-delimited JSON commands from Mothership."""
        if not self.sock:
            return
        buf = ""
        while self._running:
            try:
                if not self.sock:
                    break
                r, _, _ = select.select([self.sock], [], [], 2.0)
                if not r:
                    continue
                data = self.sock.recv(4096)
                if not data:
                    if self.hud:
                        self.hud.set_connection_status(False)
                        self.hud.show_toast("Mothership cycling — reconnecting...", duration=3.0)
                        self.hud.log_event("Mothership closed connection (cycling/rebooting)")
                    else:
                        sys.stdout.write("[satellite] Connection closed by Mothership.\n")
                    self._running = False
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = FleetMessage.deserialize(line)
                        if msg.type == FleetMessage.TYPE_CHALLENGE:
                            nonce = msg.payload.get("nonce", "")
                            ts = msg.payload.get("timestamp", time.time())
                            fleet_key = get_or_create_fleet_key()
                            sig = compute_auth_signature(fleet_key, self.node_id, nonce, ts)
                            auth_msg = FleetMessage(
                                msg_type=FleetMessage.TYPE_AUTH,
                                node_id=self.node_id,
                                payload={
                                    "signature": sig,
                                    "timestamp": ts,
                                    "telemetry": collect_telemetry(),
                                },
                            )
                            self.send_message(auth_msg)
                        elif msg.type == FleetMessage.TYPE_AUTH_OK:
                            if self.hud:
                                self.hud.set_connection_status(True)
                            self._flush_pending_errors()
                        elif msg.type == FleetMessage.TYPE_AUTH_FAIL:
                            err_str = msg.payload.get("error", "Authentication rejected by Mothership")
                            if self.hud:
                                self.report_error(PermissionError(err_str), context="auth")
                            else:
                                sys.stderr.write(f"[satellite] AUTH FAILED: {err_str}\n")
                            self._running = False
                            break
                        elif msg.type == FleetMessage.TYPE_COMMAND:
                            resp = self.handle_command(msg)
                            self.send_message(resp)
                        elif msg.type == FleetMessage.TYPE_RESPONSE:
                            req_id = msg.msg_id
                            if req_id.startswith("resp-"):
                                req_id = req_id[5:]
                            if req_id in self.response_events:
                                self.pending_responses[req_id] = msg.payload
                                self.response_events[req_id].set()

                            if "pong" in msg.payload and self._pending_ping_t0:
                                rtt_ms = (time.perf_counter() - self._pending_ping_t0) * 1000.0
                                self._pending_ping_t0 = None
                                if self.hud:
                                    self.hud.set_connection_status(True, ping_ms=round(rtt_ms, 1))
                                if self.wingman_applet and hasattr(self.wingman_applet, "update_telemetry"):
                                    try:
                                        self.wingman_applet.update_telemetry({"ping_ms": round(rtt_ms, 1), "connected": True})
                                    except Exception:
                                        pass
                        elif msg.type == FleetMessage.TYPE_TELEMETRY:
                            telem_data = msg.payload.get("mothership_telemetry", msg.payload)
                            ms_boot_id = msg.payload.get("mothership_boot_id") or telem_data.get("mothership_boot_id")
                            ms_maintenance = msg.payload.get("wingman_maintenance")
                            if ms_maintenance is None:
                                ms_maintenance = telem_data.get("wingman_maintenance", False)
                            ms_maintenance = bool(ms_maintenance)

                            # Check for Mothership reboot epoch change
                            if ms_boot_id:
                                if self.mothership_boot_id and self.mothership_boot_id != ms_boot_id:
                                    if self.wingman_applet and hasattr(self.wingman_applet, "on_mothership_reboot"):
                                        try:
                                            self.wingman_applet.on_mothership_reboot(ms_boot_id)
                                        except Exception:
                                            pass
                                self.mothership_boot_id = ms_boot_id
                                if self.wingman_applet:
                                    self.wingman_applet.mothership_boot_id = ms_boot_id

                            # Sync maintenance state
                            if self.wingman_maintenance != ms_maintenance:
                                self.wingman_maintenance = ms_maintenance
                                if self.wingman_applet and hasattr(self.wingman_applet, "set_maintenance_mode"):
                                    try:
                                        self.wingman_applet.set_maintenance_mode(ms_maintenance)
                                    except Exception:
                                        pass
                                if not ms_maintenance:
                                    self._flush_pending_errors()
                                    if self.wingman_applet and hasattr(self.wingman_applet, "security"):
                                        with self.wingman_applet.security._lock:
                                            for sess in list(self.wingman_applet.security.sessions.values()):
                                                if getattr(sess, "status", "") == "pending":
                                                    self._on_wingman_pending_session(sess)

                            if self.hud:
                                self.hud.update_telemetry(telem_data)
                            if self.wingman_applet and hasattr(self.wingman_applet, "update_telemetry"):
                                try:
                                    self.wingman_applet.update_telemetry(telem_data)
                                except Exception:
                                    pass

                            # Adopt cluster fleet_key if shared by Mothership over LAN
                            provided_key = msg.payload.get("fleet_key")
                            if provided_key:
                                from gemini_app.fleet.security import save_fleet_key
                                save_fleet_key(provided_key)

                            # Dynamic Mothership Dual-IP Discovery (LAN + WAN update)
                            net_info = telem_data.get("network", {})
                            if net_info:
                                ms_lan = net_info.get("lan_ip")
                                ms_wan = net_info.get("wan_ip")
                                ms_v6 = net_info.get("wan_ipv6")
                                ms_port = net_info.get("port", self.mothership_port)
                                if ms_lan or ms_wan or ms_v6:
                                    self._update_dual_endpoints(ms_lan, ms_wan, ms_port, wan_ipv6=ms_v6)

                            # Autonomous check: has mothership advanced past local node git commit?
                            if self.auto_upgrade and not self._is_upgrading:
                                ms_git = telem_data.get("git", {})
                                ms_commit = ms_git.get("commit")
                                if ms_commit:
                                    self._latest_ms_commit = ms_commit
                                local_commit, _ = _get_git_info_fast()
                                if (
                                    ms_commit
                                    and local_commit
                                    and ms_commit not in ("unknown", None)
                                    and local_commit not in ("unknown", None)
                                    and ms_commit != local_commit
                                    and ms_commit != self._last_attempted_target
                                ):
                                    self._trigger_auto_upgrade(ms_commit, local_commit)
                        elif msg.type == FleetMessage.TYPE_EVENT:
                            ev = msg.payload.get("event", "")
                            if ev == "wingman_chat_message":
                                if self.wingman_applet and hasattr(self.wingman_applet, "push_chat_message"):
                                    try:
                                        self.wingman_applet.push_chat_message(
                                            sender=msg.payload.get("sender", "Gemini Core"),
                                            text=msg.payload.get("text", ""),
                                            is_user=msg.payload.get("is_user", False),
                                            msg_id=msg.payload.get("id") or msg.payload.get("msg_id", ""),
                                            timestamp=msg.payload.get("timestamp"),
                                            origin_device=msg.payload.get("origin_device", ""),
                                            origin_label=msg.payload.get("origin_label", ""),
                                            attachment=msg.payload.get("attachment"),
                                        )
                                    except Exception:
                                        pass
                            elif ev == "wingman_chat_clear":
                                if self.wingman_applet and hasattr(self.wingman_applet, "clear_chat"):
                                    try:
                                        self.wingman_applet.clear_chat()
                                    except Exception:
                                        pass
                            elif ev in ("wingman_maintenance_lock", "wingman_maintenance_clear"):
                                active = (ev == "wingman_maintenance_lock") or bool(msg.payload.get("active", False))
                                self.wingman_maintenance = active
                                if self.wingman_applet and hasattr(self.wingman_applet, "set_maintenance_mode"):
                                    try:
                                        self.wingman_applet.set_maintenance_mode(active, reason=msg.payload.get("reason", ""))
                                    except Exception:
                                        pass
                                if not active:
                                    self._flush_pending_errors()
                                    if self.wingman_applet and hasattr(self.wingman_applet, "security"):
                                        with self.wingman_applet.security._lock:
                                            for sess in list(self.wingman_applet.security.sessions.values()):
                                                if getattr(sess, "status", "") == "pending":
                                                    self._on_wingman_pending_session(sess)
                            elif ev in ("mothership_rebooted", "mothership_restart"):
                                ms_boot = msg.payload.get("mothership_boot_id") or ""
                                self.mothership_boot_id = ms_boot
                                if self.wingman_applet and hasattr(self.wingman_applet, "on_mothership_reboot"):
                                    try:
                                        self.wingman_applet.on_mothership_reboot(ms_boot)
                                    except Exception:
                                        pass
                            if self.hud:
                                self.hud.log_event(ev or "Event received")
                    except Exception as err:
                        if self.hud:
                            self.report_error(err, context="msg_parse")
                        else:
                            sys.stderr.write(f"[satellite] Error handling message: {err}\n")
            except Exception as exc:
                if self._running:
                    self._running = False
                if self.hud:
                    self.hud.set_connection_status(False)
                    self.report_error(exc, context="conn")
                break

    def _start_rendezvous_listener(self) -> None:
        """Starts a lightweight inbound listener allowing Mothership to call the node if IP changes."""
        from gemini_app.fleet.protocol import DEFAULT_RENDEZVOUS_PORT
        srv = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            r_port = getattr(self, "rendezvous_port", None) or DEFAULT_RENDEZVOUS_PORT
            srv.bind(("0.0.0.0", r_port))
            srv.listen(5)
            self._rendezvous_sock = srv

            def _listener():
                while self._running and self._rendezvous_sock:
                    try:
                        conn, addr = self._rendezvous_sock.accept()
                        threading.Thread(target=self._handle_rendezvous_client, args=(conn, addr), daemon=True).start()
                    except Exception:
                        if not self._running:
                            break

            self._rendezvous_thread = threading.Thread(target=_listener, daemon=True, name="rendezvous-listener")
            self._rendezvous_thread.start()
        except Exception:
            # If port cannot be bound (e.g. permission or in use), continue gracefully
            if srv:
                try:
                    srv.close()
                except Exception:
                    pass
            self._rendezvous_sock = None

    def _handle_rendezvous_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        """Processes inbound endpoint migration notifications from Mothership."""
        try:
            conn.settimeout(5.0)
            data = conn.recv(4096)
            if not data:
                return
            msg = FleetMessage.deserialize(data.decode("utf-8", errors="replace"))
            if msg.type == FleetMessage.TYPE_COMMAND and msg.payload.get("action") == "update_mothership_endpoint":
                fleet_key = get_or_create_fleet_key()
                sig = msg.payload.get("auth_sig")
                ts = msg.payload.get("auth_ts", 0.0)
                client_ip = addr[0]
                is_trusted_peer = (
                    client_ip in ("127.0.0.1", "::1", "localhost")
                    or client_ip == self.lan_host
                    or client_ip == self.active_host
                    or is_lan_address(client_ip)
                )
                verified = verify_command_signature(fleet_key, "update_mothership_endpoint", self.node_id, ts, sig)
                if not verified and not is_trusted_peer:
                    fail_resp = FleetMessage(
                        msg_type=FleetMessage.TYPE_RESPONSE,
                        node_id=self.node_id,
                        payload={"status": "error", "error": "Signature rejected"},
                    )
                    conn.sendall(fail_resp.serialize())
                    return

                params = msg.payload.get("params", {})
                new_lan = params.get("lan_ip")
                new_wan = params.get("wan_ip")
                new_port = params.get("port", DEFAULT_PORT)
                new_fleet_key = params.get("fleet_key")
                if new_fleet_key:
                    from gemini_app.fleet.security import save_fleet_key
                    save_fleet_key(new_fleet_key)

                self._update_dual_endpoints(new_lan, new_wan, new_port)

                ack = FleetMessage(
                    msg_type=FleetMessage.TYPE_RESPONSE,
                    node_id=self.node_id,
                    payload={"status": "ok", "message": "Mothership endpoints updated", "lan_ip": new_lan, "wan_ip": new_wan},
                )
                conn.sendall(ack.serialize())

                # Trigger reconnect to the new IP
                self._running = False
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _update_dual_endpoints(self, lan_ip: Optional[str], wan_ip: Optional[str], port: int, wan_ipv6: Optional[str] = None) -> None:
        """Dynamically caches updated LAN, WAN, and IPv6 endpoints streamed from Mothership."""
        changed = False
        if lan_ip and lan_ip != self.lan_host:
            self.lan_host = lan_ip
            changed = True
        if wan_ip and wan_ip != self.wan_host:
            self.wan_host = wan_ip
            changed = True
        if wan_ipv6 and wan_ipv6 != getattr(self, "wan_ipv6", None):
            self.wan_ipv6 = wan_ipv6
            changed = True
        if port and port != self.mothership_port:
            self.mothership_port = port
            changed = True
        if changed:
            save_mothership_dual_endpoints(self.lan_host, self.wan_host, self.mothership_port, wan_ipv6=getattr(self, "wan_ipv6", None))
            if self.hud:
                self.hud.set_endpoints(self.lan_host, self.wan_host)

    def _heartbeat_loop(self) -> None:
        """Sends periodic heartbeats with telemetry to Mothership."""
        while self._running:
            telem = collect_telemetry()
            if self.hud:
                self.hud.local_vitals = telem
            if self.wingman_applet and hasattr(self.wingman_applet, "update_local_vitals"):
                try:
                    self.wingman_applet.update_local_vitals(telem)
                except Exception:
                    pass
            hb = FleetMessage(
                msg_type=FleetMessage.TYPE_HEARTBEAT,
                node_id=self.node_id,
                payload={"telemetry": telem},
            )
            if not self.send_message(hb):
                break
            # Also measure latency to Mothership if interactive HUD loop is not actively doing so
            if not self.hud:
                try:
                    self._pending_ping_t0 = time.perf_counter()
                    ping_msg = FleetMessage(
                        msg_type=FleetMessage.TYPE_COMMAND,
                        node_id=self.node_id,
                        payload={"action": "ping"},
                    )
                    self.send_message(ping_msg)
                except Exception:
                    pass
            time.sleep(self.heartbeat_interval)

    def _start_screenshot_watcher(self) -> None:
        """Starts background thread watching for newly captured screenshots on mobile nodes."""
        if self._screenshot_watcher_thread and self._screenshot_watcher_thread.is_alive():
            return
        self._screenshot_watcher_thread = threading.Thread(
            target=self._screenshot_watcher_loop, daemon=True, name="screenshot-watcher"
        )
        self._screenshot_watcher_thread.start()

    def _screenshot_watcher_loop(self) -> None:
        """Polls screenshot directory every 1.5s and auto-syncs new screenshots to Mothership."""
        import base64
        last_mtime = 0.0
        try:
            initial = find_node_screenshots(limit=1)
            if initial:
                last_mtime = float(initial[0].get("mtime", 0.0))
        except Exception:
            pass

        while self._running:
            try:
                time.sleep(1.5)
                recent = find_node_screenshots(limit=1)
                if not recent:
                    continue
                top = recent[0]
                mtime = float(top.get("mtime", 0.0))
                if mtime > (last_mtime + 0.1):
                    last_mtime = mtime
                    p = Path(top["path"])
                    if p.exists() and p.is_file():
                        data = p.read_bytes()
                        event_msg = FleetMessage(
                            msg_type=FleetMessage.TYPE_EVENT,
                            node_id=self.node_id,
                            payload={
                                "event": "screenshot_captured",
                                "filename": p.name,
                                "path": str(p),
                                "mtime": mtime,
                                "size_bytes": len(data),
                                "data_b64": base64.b64encode(data).decode("ascii"),
                            },
                        )
                        self.send_message(event_msg)
            except Exception:
                time.sleep(3.0)

    def start(self) -> bool:
        """Connects and starts background listener and heartbeat loops."""
        if not self.connect():
            return False

        self._running = True

        if self.wingman_applet and not self.wingman_applet.engine.is_running:
            try:
                self.wingman_applet.start()
            except Exception:
                pass

        # Acquire Termux wake lock on Android to prevent system Doze from killing socket
        if is_termux_platform():
            acquire_termux_wake_lock()

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        # Send initial registration message
        reg = FleetMessage(
            msg_type=FleetMessage.TYPE_REGISTER,
            node_id=self.node_id,
            payload={"telemetry": collect_telemetry()},
        )
        self.send_message(reg)

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        self._start_rendezvous_listener()
        self._start_screenshot_watcher()

        if not self.hud:
            sys.stdout.write(f"[satellite] Node '{self.node_id}' online and connected to {self.mothership_host}:{self.mothership_port}\n")
        return True

    def run_hud(self) -> None:
        """Launches the interactive real-time Telemetry HUD for landscape mobile terminals."""
        from gemini_app.fleet.hud import SatelliteHUD, is_ish_platform

        is_ish = is_ish_platform()
        tick_delay = 1.2 if is_ish else 0.75
        local_c, _ = _get_git_info_fast()

        mothership_str = f"{self.mothership_host}:{self.mothership_port}"
        def _on_upgrade_hud():
            b_b64, ms_c = self.request_mothership_bundle(timeout=8.0)
            return execute_fleet_upgrade(
                target_commit=ms_c or getattr(self, "_latest_ms_commit", None),
                bundle_b64=b_b64,
            )

        self.hud = SatelliteHUD(
            node_id=self.node_id,
            mothership_addr=mothership_str,
            on_upgrade_request=_on_upgrade_hud,
            local_commit=local_c,
        )
        self.hud.local_vitals = collect_telemetry()
        self.hud.set_endpoints(self.lan_host, self.wan_host)

        # Connect
        if not self.start():
            self.hud.set_connection_status(False)

        self.hud.start_raw_terminal()
        last_ping_time = 0.0

        try:
            while True:
                try:
                    # Periodic ping measurement
                    now = time.time()
                    if self._running and (now - last_ping_time > 3.0):
                        last_ping_time = now
                        # Measure RTT
                        self._pending_ping_t0 = time.perf_counter()
                        ping_msg = FleetMessage(
                            msg_type=FleetMessage.TYPE_COMMAND,
                            node_id=self.node_id,
                            payload={"action": "ping"},
                        )
                        self.send_message(ping_msg)

                    # Render frame and check non-blocking input
                    key = self.hud.render_loop_tick()
                    if key:
                        if key.lower() == "q":
                            break
                        elif key.lower() == "u":
                            self.hud.show_toast("Checking & upgrading node from Mothership...", duration=4.0)
                            self.hud.render_loop_tick(force_redraw=True)
                            bundle_b64, ms_c = self.request_mothership_bundle(timeout=8.0)
                            target_c = ms_c or getattr(self, "_latest_ms_commit", None)
                            res = execute_fleet_upgrade(
                                target_ref="origin/main",
                                target_commit=target_c,
                                bundle_b64=bundle_b64,
                            )
                            if res.get("status") == "ok":
                                if res.get("upgraded"):
                                    self.hud.show_toast(f"Upgraded to {res['new_commit']}! Rebooting...", duration=3.0)
                                    self.hud.render_loop_tick(force_redraw=True)
                                    time.sleep(1.0)
                                    if os.environ.get("GEMINI_WATCHDOG") == "1":
                                        sys.exit(42)
                                    else:
                                        _exec_reboot()
                                else:
                                    self.hud.show_toast("Node is already up to date.", duration=3.0)
                            else:
                                self.hud.show_toast(f"Upgrade failed: {res.get('error', 'unknown')}", duration=5.0)
                        elif key.lower() == "r":
                            # Force screen clear & redraw
                            self.hud.show_toast("Screen Redrawn", duration=2.0)
                            self.hud.render_loop_tick(force_redraw=True)

                    # Responsive low-power tick sleep: slices delay so keypresses (e.g. 'r') respond immediately
                    elapsed = 0.0
                    slice_sec = 0.08
                    while elapsed < tick_delay:
                        time.sleep(slice_sec)
                        elapsed += slice_sec
                        k = self.hud.check_keyboard_input()
                        if k:
                            if k.lower() == "q":
                                return
                            elif k.lower() == "r":
                                self.hud.show_toast("Screen Redrawn", duration=2.0)
                                self.hud.render_loop_tick(force_redraw=True)
                                break
                            elif k.lower() == "u":
                                break

                    # Periodic memory garbage collection (safeguard against iOS iSH emulator memory creep)
                    hud_ticks = getattr(self, "_hud_ticks", 0) + 1
                    self._hud_ticks = hud_ticks
                    if hud_ticks % 30 == 0:
                        import gc
                        gc.collect()

                    # Reconnect attempt if disconnected
                    if not self._running:
                        self.hud.set_connection_status(False)
                        self.stop(release_wake_lock=False)
                        last_succ = getattr(self, "_last_hud_success_time", 0.0)
                        if last_succ > 0 and (time.time() - last_succ) < 15.0:
                            reconnect_attempts = getattr(self, "_reconnect_hud_attempts", 0) + 1
                        elif last_succ == 0.0:
                            reconnect_attempts = getattr(self, "_reconnect_hud_attempts", 0) + 1
                        else:
                            reconnect_attempts = 1
                        self._reconnect_hud_attempts = reconnect_attempts
                        backoff = calculate_reconnect_backoff(
                            attempt=reconnect_attempts,
                            base_delay=2.0,
                            factor=1.5,
                            max_delay=30.0,
                            jitter=0.1,
                        )
                        target_t = time.monotonic() + backoff
                        while time.monotonic() < target_t:
                            rem = max(0.0, target_t - time.monotonic())
                            self.hud.show_toast(f"Reconnecting in {format_reconnect_countdown(rem)} (try {reconnect_attempts})...", duration=0.4)
                            time.sleep(0.12)
                            k = self.hud.check_keyboard_input()
                            if k and k.lower() == "q":
                                return
                        saved_lan, saved_wan, saved_p = get_saved_mothership_endpoints()
                        if saved_lan:
                            self.lan_host = saved_lan
                        if saved_wan:
                            self.wan_host = saved_wan
                        if saved_p:
                            self.mothership_port = saved_p
                        self.wan_ipv6 = get_saved_mothership_ipv6()
                        if self.start():
                            self._last_hud_success_time = time.time()
                            self.hud.show_toast("✓ Reconnected to Mothership", duration=2.5)
                    else:
                        last_succ = getattr(self, "_last_hud_success_time", 0.0)
                        if last_succ > 0 and (time.time() - last_succ) >= 15.0:
                            self._reconnect_hud_attempts = 0
                except Exception:
                    time.sleep(0.5)

        except KeyboardInterrupt:
            pass
        finally:
            if self.hud:
                self.hud.restore_terminal()
            self.stop(release_wake_lock=True)

    def run_forever(self) -> None:
        """Blocks while satellite is running; handles Ctrl+C cleanly and auto-reconnects with calibrated backoff."""
        attempt = 0
        last_success_time = 0.0
        try:
            while True:
                if not self._running:
                    self.stop(release_wake_lock=False)
                    if last_success_time > 0 and (time.time() - last_success_time) < 15.0:
                        attempt += 1
                    elif last_success_time == 0.0:
                        attempt += 1
                    else:
                        attempt = 1
                    backoff = calculate_reconnect_backoff(
                        attempt=attempt,
                        base_delay=2.0,
                        factor=1.5,
                        max_delay=30.0,
                        jitter=0.1,
                    )
                    sys.stdout.write(f"[satellite] Connection lost. Reconnecting to {self.mothership_host}:{self.mothership_port} in {format_reconnect_countdown(backoff)} (retry #{attempt})...\n")
                    time.sleep(backoff)
                    saved_lan, saved_wan, saved_p = get_saved_mothership_endpoints()
                    if saved_lan:
                        self.lan_host = saved_lan
                    if saved_wan:
                        self.wan_host = saved_wan
                    if saved_p:
                        self.mothership_port = saved_p
                    self.wan_ipv6 = get_saved_mothership_ipv6()
                    if self.start():
                        last_success_time = time.time()
                        sys.stdout.write(f"[satellite] Reconnected successfully.\n")
                else:
                    if last_success_time > 0 and (time.time() - last_success_time) >= 15.0:
                        attempt = 0
                time.sleep(0.5)
        except KeyboardInterrupt:
            sys.stdout.write("\n[satellite] Interrupt received. Shutting down...\n")
        finally:
            self.stop(release_wake_lock=True)

    def stop(self, release_wake_lock: bool = False) -> None:
        """Closes socket and terminates background worker threads cleanly."""
        self._running = False
        if self.wingman_applet:
            try:
                self.wingman_applet.stop()
            except Exception:
                pass
            if get_active_wingman() is self.wingman_applet:
                set_active_wingman(None)
        if release_wake_lock and is_termux_platform():
            release_termux_wake_lock()
        if self._rendezvous_sock:
            try:
                self._rendezvous_sock.close()
            except Exception:
                pass
            self._rendezvous_sock = None
        if self.sock:
            try:
                disc = FleetMessage(msg_type=FleetMessage.TYPE_DISCONNECT, node_id=self.node_id)
                self.sock.sendall(disc.serialize())
            except Exception:
                pass
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        # Join worker threads with short timeout to prevent thread leakage
        if self._listener_thread and self._listener_thread.is_alive() and threading.current_thread() != self._listener_thread:
            self._listener_thread.join(timeout=0.3)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive() and threading.current_thread() != self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=0.3)
        if not self.hud:
            sys.stdout.write(f"[satellite] Node '{self.node_id}' stopped.\n")


def main() -> int:
    ensure_ish_background_keepalive()
    ensure_termux_mobile_environment()

    saved_host = get_saved_mothership()
    saved_port = get_saved_mothership_port()

    parser = argparse.ArgumentParser(description="Gemini Distributed Satellite Node Client")
    parser.add_argument("target_ip", nargs="?", default=None, help="Optional positional Mothership IP")
    parser.add_argument("--mothership", default=None, help=f"Mothership host IP (saved default: {saved_host})")
    parser.add_argument("--port", type=int, default=None, help=f"Mothership TCP port (saved default: {saved_port})")
    parser.add_argument("--node-id", default=None, help="Explicit node identifier")
    parser.add_argument("--role", default=None, help="Execution role (satellite|node|hud)")
    parser.add_argument("--interval", type=float, default=15.0, help="Heartbeat interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send single registration/telemetry probe and exit")
    parser.add_argument("--hud", "--monitor", action="store_true", help="Run in interactive Live Telemetry HUD mode")
    parser.add_argument("--upgrade", action="store_true", help="Run atomic 3-stage self-upgrade against origin/main and exit")
    parser.add_argument("--no-auto-upgrade", action="store_true", help="Disable autonomous upgrade on Mothership commit change")
    args = parser.parse_args()

    # Allow positional IP, e.g. python3 gemini-integrated.py node 192.168.1.91
    if args.target_ip and not args.mothership:
        if ":" in args.target_ip:
            h, p = args.target_ip.split(":", 1)
            args.mothership = h
            try:
                args.port = int(p)
            except ValueError:
                pass
        else:
            args.mothership = args.target_ip

    if args.upgrade:
        print("[satellite] Initiating 3-stage pre-flight upgrade...")
        res = execute_fleet_upgrade()
        print(f"Status: {res.get('status')}")
        print(f"Message: {res.get('message', res.get('error'))}")
        return 0 if res.get("status") == "ok" else 1

    # Enforce singleton lock so multiple background nodes or HUDs do not thrash terminal/threads
    if not args.once:
        mode = "hud" if args.hud else "node"
        if not acquire_singleton_lock(mode):
            return 0

    # When user provides --mothership, automatically persist it as the new default IP
    if args.mothership is not None:
        mothership_host = args.mothership.strip()
        save_mothership(mothership_host, port=args.port)
        route_lbl = "LAN" if is_lan_address(mothership_host) else "WAN"
        print(f"[satellite] Saved '{mothership_host}' as the active {route_lbl} Mothership IP.")
    else:
        mothership_host = None

    node = SatelliteNode(
        mothership_host=mothership_host,
        mothership_port=args.port,
        node_id=args.node_id,
        heartbeat_interval=args.interval,
        auto_upgrade=not args.no_auto_upgrade,
    )

    if args.once:
        print(f"Connecting to Mothership at {args.mothership}:{args.port}...")
        if not node.connect():
            return 1
        reg = FleetMessage(
            msg_type=FleetMessage.TYPE_REGISTER,
            node_id=node.node_id,
            payload={"telemetry": collect_telemetry(), "once": True},
        )
        node.send_message(reg)
        print(f"Probe registered successfully as '{node.node_id}'.")
        node.stop()
        return 0

    if args.hud:
        if not sys.stdin.isatty():
            sys.stderr.write("[satellite] Error: HUD monitor mode requires an interactive TTY terminal.\n")
            return 1
        node.run_hud()
        return 0

    node.start()
    node.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
