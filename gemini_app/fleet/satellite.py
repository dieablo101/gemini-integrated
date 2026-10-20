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


def collect_telemetry() -> Dict[str, Any]:
    """Collects system capabilities and status using standard library only."""
    uname = platform.uname()
    total_b, used_b, free_b = shutil.disk_usage("/")
    
    # Check for iOS filesystem mount point
    ipad_mount = Path("/mnt/ipad")
    has_ipad_mount = ipad_mount.is_dir()
    ipad_files_count = 0
    if has_ipad_mount:
        try:
            ipad_files_count = len(list(ipad_mount.iterdir()))
        except Exception:
            pass

    # Check git repository commit if running from inside git directory
    git_commit = "unknown"
    git_branch = "unknown"
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            git_commit = res.stdout.strip()
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if branch_res.returncode == 0:
            git_branch = branch_res.stdout.strip()
    except Exception:
        pass

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


class SatelliteNode:
    """Satellite client connecting to the Mothership."""

    def __init__(
        self,
        mothership_host: str = "192.168.1.91",
        mothership_port: int = DEFAULT_PORT,
        node_id: Optional[str] = None,
        heartbeat_interval: float = 15.0,
    ) -> None:
        self.mothership_host = mothership_host
        self.mothership_port = mothership_port
        self.heartbeat_interval = heartbeat_interval
        
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

    def connect(self, timeout: float = 5.0) -> bool:
        """Establishes TCP connection to the Mothership."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((self.mothership_host, self.mothership_port))
            s.settimeout(None)  # Switch to blocking for threads
            self.sock = s
            return True
        except Exception as exc:
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
            except Exception as exc:
                sys.stderr.write(f"[satellite] Send failed: {exc}\n")
                return False

    def handle_command(self, cmd_msg: FleetMessage) -> FleetMessage:
        """Dispatches an incoming command from the Mothership and prepares response."""
        action = cmd_msg.payload.get("action", "unknown")
        params = cmd_msg.payload.get("params", {})
        result_payload: Dict[str, Any] = {"status": "ok", "action": action}

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

    def _listen_loop(self) -> None:
        """Reads incoming line-delimited JSON commands from Mothership."""
        if not self.sock:
            return
        buf = ""
        while self._running:
            try:
                data = self.sock.recv(4096)
                if not data:
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
                        if msg.type == FleetMessage.TYPE_COMMAND:
                            resp = self.handle_command(msg)
                            self.send_message(resp)
                    except Exception as err:
                        sys.stderr.write(f"[satellite] Error handling message: {err}\n")
            except Exception:
                if self._running:
                    self._running = False
                break

    def _heartbeat_loop(self) -> None:
        """Sends periodic heartbeats with telemetry to Mothership."""
        while self._running:
            hb = FleetMessage(
                msg_type=FleetMessage.TYPE_HEARTBEAT,
                node_id=self.node_id,
                payload={"telemetry": collect_telemetry()},
            )
            self.send_message(hb)
            time.sleep(self.heartbeat_interval)

    def start(self) -> bool:
        """Connects and starts background listener and heartbeat loops."""
        if not self.connect():
            return False

        self._running = True

        # Send initial registration message
        reg = FleetMessage(
            msg_type=FleetMessage.TYPE_REGISTER,
            node_id=self.node_id,
            payload={"telemetry": collect_telemetry()},
        )
        if not self.send_message(reg):
            self.stop()
            return False

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        sys.stdout.write(f"[satellite] Node '{self.node_id}' online and connected to {self.mothership_host}:{self.mothership_port}\n")
        return True

    def run_forever(self) -> None:
        """Blocks while satellite is running; handles Ctrl+C cleanly."""
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            sys.stdout.write("\n[satellite] Interrupt received. Shutting down...\n")
        finally:
            self.stop()

    def stop(self) -> None:
        """Closes socket and terminates background worker threads."""
        self._running = False
        if self.sock:
            try:
                disc = FleetMessage(msg_type=FleetMessage.TYPE_DISCONNECT, node_id=self.node_id)
                self.sock.sendall(disc.serialize())
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        sys.stdout.write(f"[satellite] Node '{self.node_id}' stopped.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini Distributed Satellite Node Client")
    parser.add_argument("--mothership", default=os.getenv("GEMINI_MOTHERSHIP", "192.168.1.91"), help="Mothership host IP")
    parser.add_argument("--port", type=int, default=int(os.getenv("GEMINI_PORT", str(DEFAULT_PORT))), help="Mothership TCP port")
    parser.add_argument("--node-id", default=None, help="Explicit node identifier")
    parser.add_argument("--interval", type=float, default=15.0, help="Heartbeat interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send single registration/telemetry probe and exit")
    args = parser.parse_args()

    node = SatelliteNode(
        mothership_host=args.mothership,
        mothership_port=args.port,
        node_id=args.node_id,
        heartbeat_interval=args.interval,
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

    if not node.start():
        return 1

    node.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
