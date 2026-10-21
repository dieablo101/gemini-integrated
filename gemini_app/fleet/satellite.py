"""Lightweight zero-dependency Satellite Node client.

Runs on mobile nodes (iPad iSH, Android Termux) and remote compute nodes
using only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage
from gemini_app.fleet.security import (
    compute_auth_signature,
    get_or_create_fleet_key,
    verify_command_signature,
)


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
    """Touches /dev/location in background on iOS iSH to prevent iOS app suspension."""
    if Path("/proc/ish").exists() or Path("/dev/location").exists():
        try:
            if not getattr(ensure_ish_background_keepalive, "_started", False):
                def _location_keeper():
                    try:
                        with open("/dev/location", "r") as f:
                            while True:
                                line = f.readline()
                                if not line:
                                    break
                                time.sleep(10.0)
                    except Exception:
                        pass
                t = threading.Thread(target=_location_keeper, daemon=True, name="ish-keepalive")
                t.start()
                ensure_ish_background_keepalive._started = True
        except Exception:
            pass


def collect_telemetry() -> Dict[str, Any]:
    """Collects system capabilities and status using standard library only."""
    uname = platform.uname()
    total_b, used_b, free_b = shutil.disk_usage("/")

    # Check for iOS filesystem mount point with cached scandir guard
    has_ipad_mount, ipad_files_count = check_ipad_mount()

    # Read git status using pure Python to avoid fork/exec crashes in iSH emulator
    git_commit, git_branch = _get_git_info_fast()

    return {
        "hostname": socket.gethostname(),
        "system": uname.system,
        "release": uname.release,
        "machine": uname.machine,
        "python": platform.python_version(),
        "pid": os.getpid(),
        "disk_free_gb": round(free_b / (1024 ** 3), 2),
        "disk_total_gb": round(total_b / (1024 ** 3), 2),
        "has_ipad_mount": has_ipad_mount,
        "ipad_files_count": ipad_files_count,
        "git_commit": git_commit,
        "git_branch": git_branch,
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
) -> Dict[str, Any]:
    """Executes atomic 3-stage safety gated upgrade on the local node repository.

    Stage 1: Fetch target remote ref safely.
    Stage 2: Fast-forward checkout/merge into clean state.
    Stage 3: Pre-flight syntax (py_compile) and import verification.
             Rolls back atomically via git reset if pre-flight fails!
    """
    cwd = find_repo_root(repo_dir)

    # Get current commit
    res_old = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if res_old.returncode != 0:
        return {"status": "error", "stage": "initial", "error": "Not a valid git repository"}
    old_commit = res_old.stdout.strip()

    # Stage 1: Fetch
    branch_target = target_ref.split("/")[-1] if "/" in target_ref else target_ref
    fetch_res = subprocess.run(
        ["git", "fetch", "origin", branch_target],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if fetch_res.returncode != 0:
        return {
            "status": "error",
            "stage": "fetch",
            "error": f"Git fetch failed: {fetch_res.stderr.strip()}",
        }

    # Stage 2: Fast-Forward Merge / Reset
    merge_cmd = ["git", "reset", "--hard", f"origin/{branch_target}"] if force else ["git", "merge", "--ff-only", "FETCH_HEAD"]
    merge_res = subprocess.run(
        merge_cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if merge_res.returncode != 0:
        # Fallback reset if force
        if not force:
            return {
                "status": "error",
                "stage": "checkout",
                "error": f"Merge failed (working tree not fast-forwardable): {merge_res.stderr.strip()}",
            }
        reset_res = subprocess.run(
            ["git", "reset", "--hard", f"origin/{branch_target}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if reset_res.returncode != 0:
            return {
                "status": "error",
                "stage": "checkout",
                "error": f"Reset failed: {reset_res.stderr.strip()}",
            }

    # Stage 3: Pre-Flight Syntax & Import Validation Gate
    py_files = [str(p) for p in cwd.glob("gemini_app/**/*.py")]
    for top_py in ("gemini-integrated.py", "__main__.py"):
        if (cwd / top_py).exists():
            py_files.append(top_py)

    if py_files:
        compile_res = subprocess.run(
            [sys.executable, "-m", "py_compile"] + py_files[:50],  # Sample compile
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
        [sys.executable, "-c", "import gemini_app; from gemini_app.fleet.satellite import SatelliteNode; print('VERIFIED')"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if import_res.returncode != 0 or "VERIFIED" not in import_res.stdout:
        # Atomic rollback!
        subprocess.run(["git", "reset", "--hard", old_commit], cwd=cwd, capture_output=True)
        return {
            "status": "error",
            "stage": "import_validation",
            "error": f"Pre-flight import check failed: {import_res.stderr.strip()}",
            "rolled_back": True,
            "current_commit": old_commit,
        }

    # Successful upgrade
    res_new = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=5,
    )
    new_commit = res_new.stdout.strip() if res_new.returncode == 0 else "updated"

    return {
        "status": "ok",
        "stage": "completed",
        "old_commit": old_commit,
        "new_commit": new_commit,
        "upgraded": old_commit != new_commit,
        "message": f"Pre-flight verified. Upgraded {old_commit} -> {new_commit}",
    }


CONFIG_FILE: Path = Path.home() / ".gemini" / "config.json"


def get_config_path() -> Path:
    """Returns path to ~/.gemini/config.json."""
    return CONFIG_FILE


def get_saved_mothership(default: Optional[str] = None) -> str:
    """Retrieves the default mothership IP/host.

    Resolution order:
    1. GEMINI_MOTHERSHIP environment variable
    2. ~/.gemini/config.json ("mothership_host" or "mothership")
    3. Provided default or fallback to dynamic LAN IP
    """
    env_host = os.getenv("GEMINI_MOTHERSHIP")
    if env_host and env_host.strip():
        return env_host.strip()

    cfg_file = get_config_path()
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            saved = cfg.get("mothership_host") or cfg.get("mothership")
            if saved and isinstance(saved, str) and saved.strip():
                return saved.strip()
        except Exception:
            pass

    return default or get_local_lan_ip()


def get_saved_mothership_port(default: int = DEFAULT_PORT) -> int:
    """Retrieves the default mothership TCP port."""
    env_port = os.getenv("GEMINI_PORT")
    if env_port:
        try:
            return int(env_port.strip())
        except ValueError:
            pass

    cfg_file = get_config_path()
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            val = cfg.get("mothership_port")
            if val is not None:
                return int(val)
        except Exception:
            pass

    return default


def save_mothership(host: str, port: Optional[int] = None) -> bool:
    """Persists mothership host and optional port to ~/.gemini/config.json,

    and updates any installed satellite autostart service/profile hooks.
    """
    host = host.strip()
    if not host:
        return False

    cfg_file = get_config_path()
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg: Dict[str, Any] = {}
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    cfg["mothership_host"] = host
    if port is not None:
        cfg["mothership_port"] = int(port)

    try:
        cfg_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        cfg_file.chmod(0o600)
    except Exception as exc:
        sys.stderr.write(f"[satellite] Warning: could not write config file {cfg_file}: {exc}\n")
        return False

    # Also update any installed autostart configuration so subsequent reboots target the new IP
    try:
        from gemini_app.fleet.autostart import update_autostart_mothership
        update_autostart_mothership(host, port=port)
    except Exception:
        pass

    return True


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
        self.mothership_host = (mothership_host or get_saved_mothership()).strip()
        self.mothership_port = mothership_port if mothership_port is not None else get_saved_mothership_port()
        self.heartbeat_interval = heartbeat_interval
        self.auto_upgrade = auto_upgrade
        self._is_upgrading = False

        # Derive an intuitive default node id
        if not node_id:
            h = socket.gethostname().lower()
            m = platform.machine().lower()
            if "ish" in h or Path("/mnt/ipad").exists():
                node_id = f"ipad-ish-{h}"
            else:
                node_id = f"node-{m}-{h}"
        self.node_id = node_id

        self.sock: Optional[socket.socket] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self.hud = None  # SatelliteHUD instance if running in HUD mode
        self._pending_ping_t0: Optional[float] = None

    def connect(self, timeout: float = 5.0) -> bool:
        """Establishes TCP connection to the Mothership."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((self.mothership_host, self.mothership_port))
            s.settimeout(None)  # Switch to blocking for threads
            self.sock = s
            if self.hud:
                self.hud.set_connection_status(True)
            return True
        except Exception as exc:
            if self.hud:
                self.hud.set_connection_status(False)
            sys.stderr.write(f"[satellite] Connection failed to {self.mothership_host}:{self.mothership_port}: {exc}\n")
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
                else:
                    sys.stderr.write(f"[satellite] Connection lost: {exc}\n")
                return False
            except Exception as exc:
                if not self.hud:
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

        elif action == "fleet_upgrade":
            target_ref = params.get("target_ref", "origin/main")
            force = params.get("force", False)
            if self.hud:
                self.hud.show_toast(f"Upgrading from {target_ref}...", duration=5.0)
            upgrade_res = execute_fleet_upgrade(target_ref=target_ref, force=force)
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
                        os.execv(sys.executable, [sys.executable] + sys.argv)

                threading.Thread(target=_do_reboot, daemon=True).start()

        elif action == "shutdown":
            result_payload["message"] = "Node shutting down cleanly"
            self._running = False

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
        if self._is_upgrading:
            return
        self._is_upgrading = True

        def _worker():
            try:
                msg = f"Mothership updated ({current_commit} -> {target_commit})! Auto-updating..."
                if self.hud:
                    self.hud.show_toast(msg, duration=5.0)
                else:
                    sys.stdout.write(f"[satellite] {msg}\n")

                res = execute_fleet_upgrade(target_ref="origin/main")
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
                        os.execv(sys.executable, [sys.executable] + sys.argv)
                elif res.get("status") == "ok":
                    if self.hud:
                        self.hud.show_toast("Code already matches origin/main.", duration=3.0)
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
                data = self.sock.recv(4096)
                if not data:
                    if self.hud:
                        self.hud.set_connection_status(False)
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
                        elif msg.type == FleetMessage.TYPE_AUTH_FAIL:
                            err_str = msg.payload.get("error", "Authentication rejected by Mothership")
                            if self.hud:
                                self.hud.show_toast(f"Auth failed: {err_str}", duration=5.0)
                            else:
                                sys.stderr.write(f"[satellite] AUTH FAILED: {err_str}\n")
                            self._running = False
                            break
                        elif msg.type == FleetMessage.TYPE_COMMAND:
                            resp = self.handle_command(msg)
                            self.send_message(resp)
                        elif msg.type == FleetMessage.TYPE_RESPONSE:
                            if "pong" in msg.payload and self._pending_ping_t0:
                                rtt_ms = (time.perf_counter() - self._pending_ping_t0) * 1000.0
                                self._pending_ping_t0 = None
                                if self.hud:
                                    self.hud.set_connection_status(True, ping_ms=round(rtt_ms, 1))
                        elif msg.type == FleetMessage.TYPE_TELEMETRY:
                            telem_data = msg.payload.get("mothership_telemetry", msg.payload)
                            if self.hud:
                                self.hud.update_telemetry(telem_data)
                            # Autonomous check: has mothership advanced past local node git commit?
                            if self.auto_upgrade and not self._is_upgrading:
                                ms_git = telem_data.get("git", {})
                                ms_commit = ms_git.get("commit")
                                local_commit, _ = _get_git_info_fast()
                                if (
                                    ms_commit
                                    and local_commit
                                    and ms_commit not in ("unknown", None)
                                    and local_commit not in ("unknown", None)
                                    and ms_commit != local_commit
                                ):
                                    self._trigger_auto_upgrade(ms_commit, local_commit)
                        elif msg.type == FleetMessage.TYPE_EVENT:
                            if self.hud:
                                self.hud.log_event(msg.payload.get("event", "Event received"))
                    except Exception as err:
                        sys.stderr.write(f"[satellite] Error handling message: {err}\n")
            except Exception:
                if self._running:
                    self._running = False
                if self.hud:
                    self.hud.set_connection_status(False)
                break

    def _heartbeat_loop(self) -> None:
        """Sends periodic heartbeats with telemetry to Mothership."""
        while self._running:
            hb = FleetMessage(
                msg_type=FleetMessage.TYPE_HEARTBEAT,
                node_id=self.node_id,
                payload={"telemetry": collect_telemetry()},
            )
            if not self.send_message(hb):
                break
            time.sleep(self.heartbeat_interval)

    def start(self) -> bool:
        """Connects and starts background listener and heartbeat loops."""
        if not self.connect():
            return False

        self._running = True

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
        self.hud = SatelliteHUD(
            node_id=self.node_id,
            mothership_addr=mothership_str,
            on_upgrade_request=lambda: execute_fleet_upgrade(),
            local_commit=local_c,
        )

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
                            self.hud.show_toast("Checking & upgrading node...", duration=4.0)
                            self.hud.render_loop_tick(force_redraw=True)
                            res = execute_fleet_upgrade()
                            if res.get("status") == "ok":
                                if res.get("upgraded"):
                                    self.hud.show_toast(f"Upgraded to {res['new_commit']}! Rebooting...", duration=3.0)
                                    self.hud.render_loop_tick(force_redraw=True)
                                    time.sleep(1.0)
                                    if os.environ.get("GEMINI_WATCHDOG") == "1":
                                        sys.exit(42)
                                    else:
                                        os.execv(sys.executable, [sys.executable] + sys.argv)
                                else:
                                    self.hud.show_toast("Node is already up to date.", duration=3.0)
                            else:
                                self.hud.show_toast(f"Upgrade failed: {res.get('error', 'unknown')}", duration=5.0)
                        elif key.lower() == "r":
                            # Force screen clear & redraw
                            self.hud.render_loop_tick(force_redraw=True)

                    # Low-power tick sleep (optimized for iOS/mobile battery and memory stability)
                    time.sleep(tick_delay)

                    # Reconnect attempt if disconnected
                    if not self._running:
                        self.hud.set_connection_status(False)
                        self.stop()
                        time.sleep(2.0)
                        self.start()
                except Exception:
                    time.sleep(0.5)

        except KeyboardInterrupt:
            pass
        finally:
            if self.hud:
                self.hud.restore_terminal()
            self.stop()

    def run_forever(self) -> None:
        """Blocks while satellite is running; handles Ctrl+C cleanly and auto-reconnects."""
        try:
            while True:
                if not self._running:
                    self.stop()
                    sys.stdout.write(f"[satellite] Connection lost. Reconnecting to {self.mothership_host}:{self.mothership_port} in 3s...\n")
                    time.sleep(3.0)
                    if self.start():
                        sys.stdout.write(f"[satellite] Reconnected successfully.\n")
                time.sleep(0.5)
        except KeyboardInterrupt:
            sys.stdout.write("\n[satellite] Interrupt received. Shutting down...\n")
        finally:
            self.stop()

    def stop(self) -> None:
        """Closes socket and terminates background worker threads cleanly."""
        self._running = False
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

    saved_host = get_saved_mothership()
    saved_port = get_saved_mothership_port()

    parser = argparse.ArgumentParser(description="Gemini Distributed Satellite Node Client")
    parser.add_argument("target_ip", nargs="?", default=None, help="Optional positional Mothership IP")
    parser.add_argument("--mothership", default=None, help=f"Mothership host IP (saved default: {saved_host})")
    parser.add_argument("--port", type=int, default=None, help=f"Mothership TCP port (saved default: {saved_port})")
    parser.add_argument("--node-id", default=None, help="Explicit node identifier")
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

    # When user provides --mothership, automatically persist it as the new default IP
    if args.mothership is not None:
        mothership_host = args.mothership.strip()
        save_mothership(mothership_host, port=args.port)
        print(f"[satellite] Saved '{mothership_host}' as the new default Mothership IP.")
    else:
        mothership_host = saved_host

    if args.port is not None:
        mothership_port = args.port
        save_mothership(mothership_host, port=mothership_port)
    else:
        mothership_port = saved_port

    node = SatelliteNode(
        mothership_host=mothership_host,
        mothership_port=mothership_port,
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
        node.run_hud()
        return 0

    if not node.start():
        return 1

    node.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
