"""Mothership Fleet Registry and Dispatcher.

Runs on the main host console, coordinating distributed satellite nodes,
monitoring heartbeats, and dispatching tasks over persistent TCP sockets.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage
from gemini_app.fleet.telemetry import collect_mothership_telemetry
from gemini_app.fleet.security import (
    compute_command_signature,
    generate_challenge,
    get_or_create_fleet_key,
    verify_auth_signature,
)
from gemini_app.fleet.satellite import _get_git_info_fast, find_repo_root
from gemini_app.fleet.nodes import (
    execute_ssh_rescue,
    register_or_update_node,
    save_active_nodes,
)
from gemini_app.security.fleet_guard import FleetGuard


class ConnectedSatellite:
    """Represents an active satellite node connected to the Mothership."""

    def __init__(self, node_id: str, conn: socket.socket, addr: tuple[str, int]) -> None:
        self.node_id = node_id
        self.conn = conn
        self.addr = addr
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.last_active = time.time()
        self.last_error: Dict[str, Any] = {}
        self.telemetry: Dict[str, Any] = {}
        self.pending_responses: Dict[str, Any] = {}
        self.response_events: Dict[str, threading.Event] = {}
        self.write_lock = threading.Lock()

    def send(self, msg: FleetMessage) -> bool:
        with self.write_lock:
            try:
                self.conn.sendall(msg.serialize())
                return True
            except Exception:
                return False

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


class MothershipServer:
    """TCP server running on the Mothership, maintaining fleet registry."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        auto_broadcast_telemetry: bool = True,
        broadcast_interval: float = 1.5,
        require_auth: bool = False,
        auto_upgrade_nodes: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.auto_broadcast_telemetry = auto_broadcast_telemetry
        self.broadcast_interval = broadcast_interval
        self.require_auth = require_auth
        self.auto_upgrade_nodes = auto_upgrade_nodes
        self.fleet_key = get_or_create_fleet_key()
        self.previous_fleet_key: Optional[str] = None
        self.fleet_guard = FleetGuard(max_failures=5, ban_duration=600.0)

        self.nodes: Dict[str, ConnectedSatellite] = {}
        self.lock = threading.Lock()
        self.server_sock: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._telemetry_thread: Optional[threading.Thread] = None
        self._cognitive_override: Dict[str, Any] = {}
        self._upgrade_cooldowns: Dict[str, float] = {}
        self._node_upgrade_attempts: Dict[str, tuple[str, int]] = {}
        self.local_wingman = None
        self.local_inspector = None
        self.recent_wingman_actions: List[Dict[str, Any]] = []
        self.recent_wingman_chat: List[Dict[str, Any]] = []
        self._action_events: Dict[str, threading.Event] = {}
        self._action_results: Dict[str, Dict[str, Any]] = {}
        self.pending_wingman_auth_requests: Dict[str, Dict[str, Any]] = {}
        self._wingman_auth_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.mothership_boot_id = secrets.token_hex(8)
        self.wingman_maintenance_mode = False
        self.latest_node_media: Dict[str, Dict[str, Any]] = {}

    def start(self) -> bool:
        """Binds and starts accepting incoming satellite node connections."""
        if self._running:
            return True
        try:
            s = None
            if self.host in ("0.0.0.0", "", "::"):
                try:
                    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                    s.bind(("::", self.port))
                except Exception:
                    if s:
                        try:
                            s.close()
                        except Exception:
                            pass
                    s = None
            if s is None:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, self.port))
            self.port = s.getsockname()[1]
            s.listen(10)
            self.server_sock = s
            self._running = True

            self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._accept_thread.start()

            if self.auto_broadcast_telemetry:
                self._telemetry_thread = threading.Thread(target=self._telemetry_broadcast_loop, daemon=True)
                self._telemetry_thread.start()

            sys.stdout.write(f"[mothership] Fleet server listening on {self.host}:{self.port}\n")
            return True
        except Exception as exc:
            sys.stderr.write(f"[mothership] Failed to bind server on {self.host}:{self.port}: {exc}\n")
            return False

    def _accept_loop(self) -> None:
        while self._running and self.server_sock:
            try:
                conn, addr = self.server_sock.accept()
                # Normalize IPv4-mapped IPv6 address (::ffff:192.168.1.x -> 192.168.1.x)
                if addr and isinstance(addr[0], str) and addr[0].startswith("::ffff:"):
                    addr = (addr[0][7:], addr[1])
                try:
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    if hasattr(socket, "TCP_KEEPIDLE"):
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                    if hasattr(socket, "TCP_KEEPINTVL"):
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                    if hasattr(socket, "TCP_KEEPCNT"):
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                except Exception:
                    pass
                if self.fleet_guard.is_ip_banned(addr[0]):
                    sys.stderr.write(f"[mothership] REJECTED connection from banned IP: {addr[0]}\n")
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue
                client_thread = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
            except Exception:
                if not self._running:
                    break

    def _check_node_auto_upgrades(self) -> None:
        """Autonomously dispatches fleet_upgrade to satellites running behind the Mothership commit."""
        if not self.auto_upgrade_nodes:
            return
        ms_commit, _ = _get_git_info_fast()
        if not ms_commit or ms_commit == "unknown":
            return
        now = time.time()
        candidates: List[tuple[str, str]] = []
        with self.lock:
            for nid, sat in self.nodes.items():
                node_commit = sat.telemetry.get("git_commit", "unknown")
                if node_commit == ms_commit:
                    self._node_upgrade_attempts.pop(nid, None)
                    continue

                if node_commit != ms_commit:
                    prev_c, attempts = self._node_upgrade_attempts.get(nid, ("", 0))
                    if prev_c != ms_commit:
                        attempts = 0
                    if attempts >= 3:
                        cooldown = 300.0
                    elif attempts >= 2:
                        cooldown = 120.0
                    else:
                        cooldown = 45.0

                    if now - self._upgrade_cooldowns.get(nid, 0.0) > cooldown:
                        self._upgrade_cooldowns[nid] = now
                        self._node_upgrade_attempts[nid] = (ms_commit, attempts + 1)
                        candidates.append((nid, node_commit))

        for nid, n_commit in candidates:
            def _dispatch(target_nid=nid, old_c=n_commit):
                sys.stdout.write(
                    f"[mothership] Node '{target_nid}' is on commit {old_c} (mothership is on {ms_commit}). Dispatching upgrade...\n"
                )
                self.upgrade_node(target_nid)

            threading.Thread(target=_dispatch, daemon=True, name=f"upgrade-{nid}").start()

    def _telemetry_broadcast_loop(self) -> None:
        """Periodically streams host telemetry and cognitive updates to connected satellites."""
        last_check = 0.0
        last_lan = ""
        last_wan = ""
        while self._running:
            try:
                time.sleep(self.broadcast_interval)
                with self.lock:
                    if not self.nodes:
                        continue
                self.broadcast_telemetry()
                now = time.time()
                if now - last_check > 10.0:
                    last_check = now
                    self._check_node_auto_upgrades()

                    # Dynamic IP Migration Watcher: detect if Mothership IP changed
                    from gemini_app.fleet.telemetry import get_local_lan_ip, get_public_wan_ip
                    curr_lan = get_local_lan_ip()
                    curr_wan = get_public_wan_ip()
                    if last_lan and (curr_lan != last_lan or (curr_wan and last_wan and curr_wan != last_wan)):
                        sys.stdout.write(f"[mothership] Detected Mothership IP change ({last_lan}->{curr_lan}). Reaching out to fleet...\n")
                        self.notify_fleet_of_ip_change(new_lan_ip=curr_lan, new_wan_ip=curr_wan, port=self.port)
                    last_lan = curr_lan
                    last_wan = curr_wan
            except Exception:
                pass

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        buf = ""
        node_id: Optional[str] = None
        satellite: Optional[ConnectedSatellite] = None
        fleet_key = get_or_create_fleet_key()
        auth_nonce, auth_ts = generate_challenge()
        is_authenticated = False
        is_loopback = (addr[0] in ("127.0.0.1", "::1", "localhost"))

        # Issue immediate authentication challenge
        try:
            chal = FleetMessage(
                msg_type=FleetMessage.TYPE_CHALLENGE,
                node_id="mothership",
                payload={"nonce": auth_nonce, "timestamp": auth_ts},
            )
            conn.sendall(chal.serialize())
        except Exception:
            return

        try:
            while self._running:
                try:
                    data = conn.recv(4096)
                except (ConnectionResetError, BrokenPipeError, OSError):
                    break
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = FleetMessage.deserialize(line)
                        node_id = msg.node_id

                        if msg.type == FleetMessage.TYPE_AUTH:
                            sig = msg.payload.get("signature", "")
                            ts = msg.payload.get("timestamp", 0.0)
                            valid_auth = (
                                verify_auth_signature(fleet_key, node_id, auth_nonce, ts, sig)
                                or (
                                    getattr(self, "previous_fleet_key", None)
                                    and verify_auth_signature(self.previous_fleet_key, node_id, auth_nonce, ts, sig)
                                )
                            )
                            if (valid_auth
                                and self.fleet_guard.verify_and_consume_nonce(auth_nonce, auth_ts)):
                                self.fleet_guard.record_auth_success(addr[0])
                                is_authenticated = True
                                with self.lock:
                                    if node_id in self.nodes and self.nodes[node_id].conn == conn:
                                        satellite = self.nodes[node_id]
                                        if "telemetry" in msg.payload:
                                            satellite.telemetry.update(msg.payload["telemetry"])
                                    else:
                                        satellite = ConnectedSatellite(node_id, conn, addr)
                                        satellite.telemetry = msg.payload.get("telemetry", {})
                                        self.nodes[node_id] = satellite
                                sys.stdout.write(f"[mothership] Satellite authenticated & registered: '{node_id}' from {addr}\n")

                                ack = FleetMessage(
                                    msg_type=FleetMessage.TYPE_AUTH_OK,
                                    node_id="mothership",
                                    payload={"status": "authenticated", "node_id": node_id},
                                )
                                try:
                                    conn.sendall(ack.serialize())
                                except (ConnectionResetError, BrokenPipeError, OSError):
                                    return

                                try:
                                    host_ip = addr[0]
                                    register_or_update_node(
                                        node_id=node_id,
                                        host=host_ip,
                                        telemetry=satellite.telemetry,
                                    )
                                    save_active_nodes(self.list_nodes())
                                except Exception:
                                    pass

                                init_telem = collect_mothership_telemetry(
                                    cognitive_override=self._cognitive_override,
                                    satellites_info=self.list_nodes(),
                                )
                                greet = FleetMessage(
                                    msg_type=FleetMessage.TYPE_TELEMETRY,
                                    node_id="mothership",
                                    payload={
                                        "mothership_telemetry": init_telem,
                                        "mothership_boot_id": self.mothership_boot_id,
                                        "wingman_maintenance": self.wingman_maintenance_mode,
                                    },
                                )
                                satellite.send(greet)
                            else:
                                if self.require_auth:
                                    newly_banned = self.fleet_guard.record_auth_failure(addr[0])
                                    sys.stderr.write(f"[mothership] UNAUTHORIZED node '{node_id}' from {addr}: invalid signature\n")
                                    if newly_banned:
                                        sys.stderr.write(f"[mothership] IP '{addr[0]}' temporarily banned due to repeated auth failures\n")
                                    fail = FleetMessage(
                                        msg_type=FleetMessage.TYPE_AUTH_FAIL,
                                        node_id="mothership",
                                        payload={"error": "Authentication failed: invalid fleet key signature"},
                                    )
                                    try:
                                        conn.sendall(fail.serialize())
                                    except Exception:
                                        pass
                                    return
                                else:
                                    # Fallback: allow as unauthenticated LAN node when require_auth=False
                                    is_authenticated = True
                                    with self.lock:
                                        if node_id in self.nodes and self.nodes[node_id].conn == conn:
                                            satellite = self.nodes[node_id]
                                            if "telemetry" in msg.payload:
                                                satellite.telemetry.update(msg.payload["telemetry"])
                                        else:
                                            satellite = ConnectedSatellite(node_id, conn, addr)
                                            satellite.telemetry = msg.payload.get("telemetry", {})
                                            self.nodes[node_id] = satellite
                                    sys.stdout.write(f"[mothership] Satellite registered (LAN mode): '{node_id}' from {addr}\n")

                                    ack = FleetMessage(
                                        msg_type=FleetMessage.TYPE_AUTH_OK,
                                        node_id="mothership",
                                        payload={"status": "lan_registered", "node_id": node_id},
                                    )
                                    try:
                                        conn.sendall(ack.serialize())
                                    except (ConnectionResetError, BrokenPipeError, OSError):
                                        return

                                    try:
                                        host_ip = addr[0]
                                        register_or_update_node(
                                            node_id=node_id,
                                            host=host_ip,
                                            telemetry=satellite.telemetry,
                                        )
                                        save_active_nodes(self.list_nodes())
                                    except Exception:
                                        pass

                                    init_telem = collect_mothership_telemetry(
                                        cognitive_override=self._cognitive_override,
                                        satellites_info=self.list_nodes(),
                                    )
                                    greet = FleetMessage(
                                        msg_type=FleetMessage.TYPE_TELEMETRY,
                                        node_id="mothership",
                                        payload={
                                            "mothership_telemetry": init_telem,
                                            "fleet_key": self.fleet_key,
                                            "mothership_boot_id": self.mothership_boot_id,
                                            "wingman_maintenance": self.wingman_maintenance_mode,
                                        },
                                    )
                                    satellite.send(greet)

                        elif msg.type == FleetMessage.TYPE_REGISTER:
                            # Allow if loopback or auth not enforced
                            if is_loopback or not self.require_auth:
                                is_authenticated = True
                                with self.lock:
                                    if node_id in self.nodes and self.nodes[node_id].conn == conn:
                                        satellite = self.nodes[node_id]
                                        if "telemetry" in msg.payload:
                                            satellite.telemetry.update(msg.payload["telemetry"])
                                    else:
                                        satellite = ConnectedSatellite(node_id, conn, addr)
                                        satellite.telemetry = msg.payload.get("telemetry", {})
                                        self.nodes[node_id] = satellite
                                sys.stdout.write(f"[mothership] Satellite registered: '{node_id}' from {addr}\n")

                                # Persist to active nodes and update persistent registry
                                try:
                                    host_ip = addr[0]
                                    register_or_update_node(
                                        node_id=node_id,
                                        host=host_ip,
                                        telemetry=satellite.telemetry,
                                    )
                                    save_active_nodes(self.list_nodes())
                                except Exception:
                                    pass

                                # Send immediate telemetry greeting so HUD populates right away
                                init_telem = collect_mothership_telemetry(
                                    cognitive_override=self._cognitive_override,
                                    satellites_info=self.list_nodes(),
                                )
                                greet = FleetMessage(
                                    msg_type=FleetMessage.TYPE_TELEMETRY,
                                    node_id="mothership",
                                    payload={
                                        "mothership_telemetry": init_telem,
                                        "mothership_boot_id": self.mothership_boot_id,
                                        "wingman_maintenance": self.wingman_maintenance_mode,
                                    },
                                )
                                satellite.send(greet)
                            else:
                                sys.stderr.write(f"[mothership] Blocked unauthenticated registration from {addr}\n")
                                fail = FleetMessage(
                                    msg_type=FleetMessage.TYPE_AUTH_FAIL,
                                    node_id="mothership",
                                    payload={"error": "Challenge authentication required for non-loopback connections"},
                                )
                                try:
                                    conn.sendall(fail.serialize())
                                except Exception:
                                    pass
                                return

                        elif msg.type == FleetMessage.TYPE_HEARTBEAT:
                            with self.lock:
                                if node_id in self.nodes:
                                    sat = self.nodes[node_id]
                                    sat.last_heartbeat = time.time()
                                    sat.last_active = time.time()
                                    if "telemetry" in msg.payload:
                                        sat.telemetry = msg.payload["telemetry"]
                                        self._prune_pending_wingman_requests()
                                        pending_list = sat.telemetry.get("webapplet", {}).get("pending_auth", [])
                                        is_w_active = sat.telemetry.get("webapplet", {}).get("wingman_active", False)
                                        if is_w_active or pending_list:
                                            for p in pending_list:
                                                rid = p.get("auth_req_id") or p.get("session_id")
                                                dev_id = p.get("device_id", "")
                                                cip = p.get("client_ip", "")
                                                if cip in ("127.0.0.1", "::1", "localhost", ""):
                                                    cip = addr[0]
                                                match_key = None
                                                for r_rid, r in list(self.pending_wingman_auth_requests.items()):
                                                    if r.get("node_id") == node_id and (
                                                        (dev_id and r.get("device_id") == dev_id)
                                                        or (r.get("auth_req_id") or r.get("session_id")) == rid
                                                    ):
                                                        match_key = r_rid
                                                        break
                                                if rid:
                                                    entry = dict(p)
                                                    entry["node_id"] = node_id
                                                    entry["client_ip"] = cip
                                                    entry["timestamp"] = p.get("timestamp") or time.time()
                                                    if match_key and match_key != rid:
                                                        self.pending_wingman_auth_requests.pop(match_key, None)
                                                    self.pending_wingman_auth_requests[rid] = entry
                                                    self._notify_wingman_auth(entry)
                            try:
                                save_active_nodes(self.list_nodes())
                            except Exception:
                                pass

                        elif msg.type == FleetMessage.TYPE_ERROR:
                            err_info = msg.payload.get("error", {})
                            with self.lock:
                                if node_id in self.nodes:
                                    sat = self.nodes[node_id]
                                    sat.last_error = err_info
                                    sat.last_active = time.time()
                            err_short = err_info.get("short_str", str(err_info))
                            sys.stderr.write(f"[mothership] Satellite '{node_id}' reported error: {err_short}\n")

                        elif msg.type == FleetMessage.TYPE_RESPONSE:
                            with self.lock:
                                if node_id in self.nodes:
                                    sat = self.nodes[node_id]
                                    sat.last_active = time.time()
                                    req_id = msg.msg_id
                                    # Strip 'resp-' prefix if present to match request msg_id
                                    if req_id.startswith("resp-"):
                                        req_id = req_id[5:]
                                    sat.pending_responses[req_id] = msg.payload
                                    if req_id in sat.response_events:
                                        sat.response_events[req_id].set()

                        elif msg.type == FleetMessage.TYPE_COMMAND:
                            # Handle incoming commands from satellite (e.g. telemetry requests, node listings, or pings)
                            action = msg.payload.get("action", "")
                            resp_payload: Dict[str, Any] = {"status": "ok", "action": action}
                            if action == "ping":
                                resp_payload["pong"] = time.time()
                            elif action == "rotate_fleet_key":
                                new_k = msg.payload.get("params", {}).get("new_fleet_key", "").strip()
                                if new_k:
                                    self.previous_fleet_key = self.fleet_key
                                    self.fleet_key = new_k
                                    from gemini_app.fleet.security import save_fleet_key
                                    save_fleet_key(new_k)
                                    resp_payload["status"] = "ok"
                                    resp_payload["message"] = "Fleet key rotated with legacy grace transition"
                                else:
                                    resp_payload["status"] = "error"
                                    resp_payload["error"] = "No new_fleet_key provided"
                            elif action == "update_cognitive":
                                cog_data = msg.payload.get("cognitive", {})
                                if cog_data:
                                    self.set_cognitive_state(
                                        state_desc=cog_data.get("state_desc", ""),
                                        task=cog_data.get("task", ""),
                                        thought=cog_data.get("thought", ""),
                                        tool=cog_data.get("tool", "none"),
                                        turn_number=cog_data.get("turn_number"),
                                        topic=cog_data.get("topic", ""),
                                    )
                                resp_payload["status"] = "ok"
                            elif action == "list_nodes":
                                resp_payload["nodes"] = self.list_nodes()
                            elif action == "rescue_node":
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                rescue_act = msg.payload.get("params", {}).get("action", "restart")
                                resp_payload["rescue_result"] = execute_ssh_rescue(target_nid, action=rescue_act)
                            elif action == "get_update_bundle":
                                bundle_b64, ms_commit = self.get_repo_bundle()
                                resp_payload["bundle_b64"] = bundle_b64
                                resp_payload["target_commit"] = ms_commit
                                resp_payload["status"] = "ok" if bundle_b64 else "error"
                            elif action == "upgrade_node":
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                target_ref = msg.payload.get("params", {}).get("target_ref", "origin/main")
                                force = msg.payload.get("params", {}).get("force", False)
                                if target_nid:
                                    resp_payload["upgrade_result"] = self.upgrade_node(target_nid, target_ref=target_ref, force=force)
                                else:
                                    resp_payload["upgrade_result"] = self.upgrade_all_nodes(target_ref=target_ref, force=force)
                            elif action == "exec_node":
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                subcmd = msg.payload.get("params", {}).get("command", "")
                                cmd_timeout = float(msg.payload.get("params", {}).get("timeout", 15.0))
                                if target_nid and subcmd:
                                    resp_payload["exec_result"] = self.send_command(
                                        target_nid,
                                        "exec",
                                        {"command": subcmd, "timeout": cmd_timeout},
                                        timeout=cmd_timeout + 5.0,
                                    )
                                else:
                                    resp_payload["status"] = "error"
                                    resp_payload["error"] = "Missing node_id or command"
                            elif action in ("take_node_camera_photo", "take_camera_photo", "camera_photo"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "ipad-ish-localhost"
                                facing = str(msg.payload.get("params", {}).get("facing", "front")).lower().strip()
                                cam_id = "1" if facing in ("front", "user") else "0"
                                if "camera_id" in msg.payload.get("params", {}):
                                    cam_id = str(msg.payload["params"]["camera_id"])

                                if target_nid == "android-termux-localhost":
                                    # Android Termux camera execution
                                    photo_cmd = f"export PATH=$PREFIX/bin:$PATH; termux-camera-photo -c {cam_id} $HOME/camera_snap_{cam_id}.jpg && base64 $HOME/camera_snap_{cam_id}.jpg"
                                    sub_resp = self.send_command(
                                        target_nid,
                                        "exec",
                                        {"command": photo_cmd, "timeout": 15.0},
                                        timeout=20.0,
                                    )
                                    if sub_resp.get("status") == "ok" and sub_resp.get("stdout"):
                                        import base64
                                        from pathlib import Path
                                        from gemini_app.config import GEMINI_HOME
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        fname = f"camera_{target_nid}_facing_{facing}_{int(time.time())}.jpg"
                                        dest_file = dest_dir / fname
                                        raw_b64 = sub_resp["stdout"].strip()
                                        dest_file.write_bytes(base64.b64decode(raw_b64))
                                        resp_payload["status"] = "ok"
                                        resp_payload["local_path"] = str(dest_file)
                                        resp_payload["filename"] = fname
                                        resp_payload["node_id"] = target_nid
                                        resp_payload["facing"] = facing
                                        resp_payload["camera_id"] = cam_id
                                        resp_payload["size_bytes"] = len(dest_file.read_bytes())
                                    else:
                                        resp_payload["status"] = "error"
                                        resp_payload["error"] = sub_resp.get("stderr") or sub_resp.get("error", "Camera capture failed")
                                else:
                                    # iPad or other satellite node: push interactive camera shutter card to Wingman
                                    card_title = "📸 Screen-Side Camera Capture" if facing in ("front", "user") else "📸 Camera Capture"
                                    card_content = (
                                        f"Gemini requested a photo capture from the {facing} camera ({target_nid}).\n"
                                        "Tap 'Snap Front Camera' to capture via WebKit MediaDevices, or 'iOS Shutter' for native viewfinder snapshot."
                                    )
                                    push_res = self.push_wingman_card(
                                        node_id=target_nid,
                                        title=card_title,
                                        content=card_content,
                                        actions=[
                                            {"label": "📸 Snap Front Camera", "action": "camera_webrtc", "style": "primary"},
                                            {"label": "📷 iOS Viewfinder Shutter", "action": "camera_native", "style": "secondary"},
                                        ],
                                        accent=True,
                                    )
                                    resp_payload["status"] = "ok"
                                    resp_payload["push_result"] = push_res
                                    resp_payload["message"] = f"Camera shutter card pushed to Wingman on '{target_nid}'"

                            elif action in ("fetch_node_screenshot", "fetch_screenshot"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                if not target_nid:
                                    resp_payload["status"] = "error"
                                    resp_payload["error"] = "Missing node_id"
                                else:
                                    sub_resp = self.send_command(
                                        target_nid,
                                        "fetch_latest_screenshot",
                                        msg.payload.get("params", {}),
                                        timeout=20.0,
                                    )
                                    if sub_resp.get("status") == "ok" and sub_resp.get("data_b64"):
                                        import base64
                                        from pathlib import Path
                                        from gemini_app.config import GEMINI_HOME
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        fname = sub_resp.get("filename", "screenshot.png")
                                        dest_file = dest_dir / f"node_{target_nid}_{fname}"
                                        dest_file.write_bytes(base64.b64decode(sub_resp["data_b64"]))
                                        resp_payload["status"] = "ok"
                                        resp_payload["local_path"] = str(dest_file)
                                        resp_payload["filename"] = fname
                                        resp_payload["node_id"] = target_nid
                                        resp_payload["size_bytes"] = sub_resp.get("size_bytes", 0)
                                        resp_payload["mtime"] = sub_resp.get("mtime", 0)

                                        # RapidOCR text and media parsing
                                        try:
                                            from gemini_app.fleet.media_ocr import extract_screen_text, parse_mobile_media
                                            ocr_res = extract_screen_text(dest_file)
                                            media_data = parse_mobile_media(ocr_res, filename=fname)
                                            resp_payload["ocr_text"] = ocr_res.get("raw_text", "")
                                            resp_payload["ocr_lines"] = ocr_res.get("lines", [])
                                            resp_payload["media_info"] = media_data
                                            with self.lock:
                                                self.latest_node_media[target_nid] = {
                                                    **media_data,
                                                    "local_path": str(dest_file),
                                                    "filename": fname,
                                                    "timestamp": time.time(),
                                                }
                                        except Exception as ocr_err:
                                            resp_payload["ocr_error"] = str(ocr_err)
                                    else:
                                        resp_payload.update(sub_resp)
                            elif action in ("get_node_media", "node_media", "now_playing", "media_telemetry"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                cached = None
                                with self.lock:
                                    c = self.latest_node_media.get(target_nid)
                                    if c and (time.time() - c.get("timestamp", 0.0)) < 4.0:
                                        cached = dict(c)

                                if cached:
                                    resp_payload["status"] = "ok"
                                    resp_payload["media_info"] = cached
                                    resp_payload["cached"] = True
                                    resp_payload["local_path"] = cached.get("local_path", "")
                                    resp_payload["ocr_text"] = cached.get("summary", "")
                                else:
                                    sub_resp = self.send_command(
                                        target_nid,
                                        "fetch_latest_screenshot",
                                        msg.payload.get("params", {}),
                                        timeout=20.0,
                                    )
                                    if sub_resp.get("status") == "ok" and sub_resp.get("data_b64"):
                                        import base64
                                        from pathlib import Path
                                        from gemini_app.config import GEMINI_HOME
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        fname = sub_resp.get("filename", "screenshot.png")
                                        dest_file = dest_dir / f"node_{target_nid}_{fname}"
                                        dest_file.write_bytes(base64.b64decode(sub_resp["data_b64"]))
                                        from gemini_app.fleet.media_ocr import extract_screen_text, parse_mobile_media
                                        ocr_res = extract_screen_text(dest_file)
                                        media_data = parse_mobile_media(ocr_res, filename=fname)
                                        media_entry = {
                                            **media_data,
                                            "local_path": str(dest_file),
                                            "filename": fname,
                                            "timestamp": time.time(),
                                        }
                                        with self.lock:
                                            self.latest_node_media[target_nid] = media_entry
                                        resp_payload["status"] = "ok"
                                        resp_payload["media_info"] = media_entry
                                        resp_payload["ocr_text"] = ocr_res.get("raw_text", "")
                                        resp_payload["ocr_lines"] = ocr_res.get("lines", [])
                                        resp_payload["local_path"] = str(dest_file)
                                    else:
                                        resp_payload["status"] = "error"
                                        resp_payload["error"] = sub_resp.get("error", "No screenshot found or node unresponsive")
                            elif action in ("list_node_screenshots", "list_screenshots"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                if not target_nid:
                                    resp_payload["status"] = "error"
                                    resp_payload["error"] = "Missing node_id"
                                else:
                                    resp_payload["screenshots"] = self.send_command(
                                        target_nid,
                                        "list_screenshots",
                                        msg.payload.get("params", {}),
                                        timeout=10.0,
                                    ).get("screenshots", [])
                            elif action in ("control_node_media", "media_control"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                m_action = msg.payload.get("params", {}).get("media_action", "next")
                                resp_payload["media_result"] = self.send_command(
                                    target_nid,
                                    "media_control",
                                    {"media_action": m_action},
                                    timeout=10.0,
                                )
                            elif action in ("record_node_audio", "record_audio", "audio_record"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                dur = int(msg.payload.get("params", {}).get("duration", 5))
                                enc = msg.payload.get("params", {}).get("encoder", "opus")
                                sub_resp = self.send_command(
                                    target_nid,
                                    "record_audio",
                                    {"duration": dur, "encoder": enc, **msg.payload.get("params", {})},
                                    timeout=float(dur) + 15.0,
                                )
                                if sub_resp.get("status") == "ok" and sub_resp.get("data_b64"):
                                    import base64
                                    from pathlib import Path
                                    from gemini_app.config import GEMINI_HOME
                                    dest_dir = GEMINI_HOME / "audio" / "recordings"
                                    dest_dir.mkdir(parents=True, exist_ok=True)
                                    raw_fname = sub_resp.get("filename") or f"audio_{int(time.time())}.opus"
                                    dest_file = dest_dir / f"node_{target_nid}_{raw_fname}"
                                    dest_file.write_bytes(base64.b64decode(sub_resp["data_b64"]))
                                    resp_payload["status"] = "ok"
                                    resp_payload["local_path"] = str(dest_file)
                                    resp_payload["filename"] = raw_fname
                                    resp_payload["size_bytes"] = len(dest_file.read_bytes())
                                    resp_payload["duration"] = sub_resp.get("duration", dur)
                                    resp_payload["encoder"] = sub_resp.get("encoder", enc)
                                    resp_payload["node_id"] = target_nid
                                else:
                                    resp_payload["status"] = sub_resp.get("status", "error")
                                    resp_payload["error"] = sub_resp.get("error", "Audio recording failed or node unresponsive")
                            elif action in ("speak_node_tts", "tts_speak", "whisper", "say"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                resp_payload["tts_result"] = self.send_command(
                                    target_nid,
                                    "tts_speak",
                                    msg.payload.get("params", {}),
                                    timeout=25.0,
                                )
                            elif action in ("get_node_audio_info", "audio_info"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                resp_payload["audio_info"] = self.send_command(
                                    target_nid,
                                    "audio_info",
                                    msg.payload.get("params", {}),
                                    timeout=10.0,
                                )
                            elif action in ("control_node_volume", "volume_control", "volume"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                resp_payload["volume_result"] = self.send_command(
                                    target_nid,
                                    "volume_control",
                                    msg.payload.get("params", {}),
                                    timeout=10.0,
                                )
                            elif action in ("notify_node_toast", "toast"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                resp_payload["toast_result"] = self.send_command(
                                    target_nid,
                                    "toast",
                                    msg.payload.get("params", {}),
                                    timeout=10.0,
                                )
                            elif action in ("vibrate_node", "vibrate"):
                                target_nid = msg.payload.get("params", {}).get("node_id", "") or "android-termux-localhost"
                                resp_payload["vibrate_result"] = self.send_command(
                                    target_nid,
                                    "vibrate",
                                    msg.payload.get("params", {}),
                                    timeout=10.0,
                                )
                            elif action == "mothership_telemetry":
                                resp_payload["mothership_telemetry"] = collect_mothership_telemetry(
                                    cognitive_override=self._cognitive_override,
                                    satellites_info=self.list_nodes(),
                                )
                            elif action == "webapplet_push":
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                p_title = msg.payload.get("params", {}).get("title", "Gemini")
                                p_content = msg.payload.get("params", {}).get("content", "")
                                p_actions = msg.payload.get("params", {}).get("actions", [])
                                p_accent = msg.payload.get("params", {}).get("accent", True)
                                resp_payload["push_result"] = self.push_wingman_card(
                                    node_id=target_nid,
                                    title=p_title,
                                    content=p_content,
                                    actions=p_actions,
                                    accent=p_accent,
                                )
                            elif action == "biometric_auth":
                                target_nid = msg.payload.get("params", {}).get("node_id", "")
                                b_reason = msg.payload.get("params", {}).get("reason", "Authorize Action")
                                b_timeout = float(msg.payload.get("params", {}).get("timeout", 30.0))
                                b_method = msg.payload.get("params", {}).get("method", "auto")
                                resp_payload["biometric_result"] = self.request_node_biometric(
                                    node_id=target_nid,
                                    reason=b_reason,
                                    timeout=b_timeout,
                                    method=b_method,
                                )
                            elif action in ("get_wingman_actions", "wingman_actions"):
                                with self.lock:
                                    resp_payload["actions"] = list(self.recent_wingman_actions)
                            elif action in ("clear_pending_wingman_auth", "flush_pending_wingman_auth"):
                                with self.lock:
                                    self.pending_wingman_auth_requests.clear()
                                    resp_payload["status"] = "ok"
                            elif action in ("get_pending_wingman_auth", "pending_wingman_auth"):
                                with self.lock:
                                    self._prune_pending_wingman_requests()
                                    reqs = dict(self.pending_wingman_auth_requests)
                                    now_t = time.time()
                                    for nid, sat in self.nodes.items():
                                        if (now_t - getattr(sat, "last_heartbeat", 0.0)) > 60.0:
                                            continue
                                        pending_items = sat.telemetry.get("webapplet", {}).get("pending_auth", [])
                                        is_act = sat.telemetry.get("webapplet", {}).get("wingman_active", False)
                                        if is_act or pending_items:
                                            for p in pending_items:
                                                rid = p.get("auth_req_id") or p.get("session_id")
                                                p_ts = float(p.get("timestamp") or 0.0)
                                                if rid and p_ts > 0.0 and (now_t - p_ts <= 45.0) and rid not in reqs:
                                                    entry = dict(p)
                                                    entry["node_id"] = nid
                                                    entry["timestamp"] = p_ts
                                                    reqs[rid] = entry
                                                    self.pending_wingman_auth_requests[rid] = entry
                                    resp_payload["requests"] = list(reqs.values())
                            elif action in ("resolve_wingman_auth", "authorize_wingman"):
                                req_id = msg.payload.get("params", {}).get("auth_req_id") or msg.payload.get("params", {}).get("session_id", "")
                                dec = msg.payload.get("params", {}).get("decision", "accept")
                                nid = msg.payload.get("params", {}).get("node_id", "")
                                trust_dev = bool(msg.payload.get("params", {}).get("trust", False)) or (dec == "pair")
                                if not nid and req_id in self.pending_wingman_auth_requests:
                                    nid = self.pending_wingman_auth_requests[req_id].get("node_id", "local")
                                resp_payload["result"] = self.authorize_wingman(node_id=nid or "local", auth_req_id=req_id, decision=dec, trust=trust_dev)
                            elif action in ("prune_wingman_requests", "clear_pending_wingman_auth"):
                                with self.lock:
                                    self.pending_wingman_auth_requests.clear()
                                    resp_payload["status"] = "ok"
                            elif action in ("set_wingman_maintenance", "wingman_maintenance"):
                                active = bool(msg.payload.get("params", {}).get("active", False))
                                reason = str(msg.payload.get("params", {}).get("reason", ""))
                                self.set_wingman_maintenance(active, reason=reason)
                                resp_payload["status"] = "ok"
                                resp_payload["active"] = active
                                resp_payload["boot_id"] = self.mothership_boot_id
                            elif action in ("reset_wingman_epoch", "reset_epoch", "mothership_reboot"):
                                new_id = self.reset_wingman_epoch()
                                resp_payload["status"] = "ok"
                                resp_payload["mothership_boot_id"] = new_id
                            elif action == "get_mothership_boot_id":
                                resp_payload["status"] = "ok"
                                resp_payload["boot_id"] = self.mothership_boot_id
                                resp_payload["maintenance"] = self.wingman_maintenance_mode
                            elif action == "verify_wingman_passkey":
                                cand_pass = msg.payload.get("params", {}).get("passkey", "")
                                resp_payload["valid"] = self.verify_wingman_passkey(cand_pass)
                                resp_payload["status"] = "ok"
                            elif action == "broadcast_wingman_chat":
                                b_sender = msg.payload.get("params", {}).get("sender", "Gemini Core")
                                b_text = msg.payload.get("params", {}).get("text", "")
                                b_is_user = bool(msg.payload.get("params", {}).get("is_user", False))
                                b_msg_id = msg.payload.get("params", {}).get("id", "") or msg.payload.get("params", {}).get("msg_id", "")
                                b_exclude = msg.payload.get("params", {}).get("exclude_node_id")
                                b_origin_device = msg.payload.get("params", {}).get("origin_device", "")
                                b_origin_label = msg.payload.get("params", {}).get("origin_label", "")
                                count = self.broadcast_wingman_chat(
                                    sender=b_sender,
                                    text=b_text,
                                    is_user=b_is_user,
                                    msg_id=b_msg_id,
                                    exclude_node_id=b_exclude,
                                    origin_device=b_origin_device,
                                    origin_label=b_origin_label,
                                )
                                resp_payload["sent_count"] = count
                                resp_payload["status"] = "ok"
                            elif action in ("broadcast_wingman_clear", "clear_wingman_chat"):
                                count = self.broadcast_wingman_clear()
                                resp_payload["sent_count"] = count
                                resp_payload["status"] = "ok"
                            elif action in ("get_wingman_chat_history", "wingman_chat_history"):
                                with self.lock:
                                    if self.local_wingman and getattr(self.local_wingman, "_chat_history_fetcher", None):
                                        try:
                                            resp_payload["history"] = list(self.local_wingman._chat_history_fetcher()[-50:])
                                        except Exception:
                                            resp_payload["history"] = list(self.recent_wingman_chat[-50:])
                                    else:
                                        resp_payload["history"] = list(self.recent_wingman_chat[-50:])
                                resp_payload["status"] = "ok"
                            reply = FleetMessage(
                                msg_type=FleetMessage.TYPE_RESPONSE,
                                node_id="mothership",
                                payload=resp_payload,
                                msg_id=f"resp-{msg.msg_id}",
                            )
                            try:
                                conn.sendall(reply.serialize())
                            except Exception:
                                with self.lock:
                                    if node_id in self.nodes:
                                        self.nodes[node_id].send(reply)

                        elif msg.type == FleetMessage.TYPE_EVENT:
                            event_name = msg.payload.get("event", "")
                            if event_name == "wingman_action":
                                card_id = msg.payload.get("card_id", "")
                                action = msg.payload.get("action", "")
                                action_entry = {
                                    "node_id": node_id,
                                    "card_id": card_id,
                                    "action": action,
                                    "body": msg.payload.get("body", {}),
                                    "timestamp": msg.payload.get("timestamp", time.time()),
                                }
                                with self.lock:
                                    self.recent_wingman_actions.append(action_entry)
                                    if len(self.recent_wingman_actions) > 100:
                                        self.recent_wingman_actions.pop(0)
                                    if card_id in self._action_events:
                                        self._action_results[card_id] = action_entry
                                        self._action_events[card_id].set()

                            elif event_name == "wingman_closed":
                                with self.lock:
                                    to_del = [rid for rid, r in self.pending_wingman_auth_requests.items() if r.get("node_id") == node_id]
                                    for rid in to_del:
                                        self.pending_wingman_auth_requests.pop(rid, None)

                            elif event_name in ("wingman_auth_request", "wingman_access_request"):
                                req_id = msg.payload.get("session_id") or msg.payload.get("auth_req_id", "")
                                dev_id = msg.payload.get("device_id", "")
                                cip = msg.payload.get("client_ip", "")
                                if cip in ("127.0.0.1", "::1", "localhost", ""):
                                    cip = addr[0]
                                auth_entry = {
                                    "node_id": node_id,
                                    "session_id": req_id,
                                    "auth_req_id": req_id,
                                    "client_ip": cip,
                                    "user_agent": msg.payload.get("user_agent", ""),
                                    "device_id": dev_id,
                                    "timestamp": msg.payload.get("timestamp") or time.time(),
                                }
                                with self.lock:
                                    match_key = None
                                    for r_rid, r in list(self.pending_wingman_auth_requests.items()):
                                        if r.get("node_id") == node_id and (
                                            (dev_id and r.get("device_id") == dev_id)
                                            or (r.get("auth_req_id") or r.get("session_id")) == req_id
                                        ):
                                            match_key = r_rid
                                            break
                                    if match_key and match_key != req_id:
                                        self.pending_wingman_auth_requests.pop(match_key, None)
                                    self.pending_wingman_auth_requests[req_id] = auth_entry
                                    self._notify_wingman_auth(auth_entry)

                            elif event_name == "wingman_chat_message":
                                chat_text = msg.payload.get("text", "")
                                chat_sender = msg.payload.get("sender", "operator")
                                chat_msg_id = msg.payload.get("id") or msg.payload.get("msg_id", "")
                                chat_ts = time.time()
                                chat_entry = {
                                    "node_id": node_id,
                                    "sender": chat_sender,
                                    "text": chat_text,
                                    "id": chat_msg_id,
                                    "timestamp": chat_ts,
                                }
                                sys.stdout.write(
                                    f"[mothership] Wingman chat from {node_id} ({chat_entry['sender']}): {chat_entry['text']}\n"
                                )
                                if chat_text.strip().lower() == "/clear":
                                    self.broadcast_wingman_clear()
                                    try:
                                        from gemini_app.config import SOCKET_PATH
                                        if SOCKET_PATH.exists():
                                            s_cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                                            s_cli.settimeout(0.5)
                                            s_cli.connect(str(SOCKET_PATH))
                                            s_cli.sendall(json.dumps({
                                                "action": "clear_chat",
                                                "sender": chat_sender,
                                                "source": "wingman",
                                            }).encode("utf-8"))
                                            s_cli.close()
                                    except Exception:
                                        pass
                                    continue

                                chat_attachment = msg.payload.get("attachment")
                                if isinstance(chat_attachment, dict) and chat_attachment.get("data_b64"):
                                    try:
                                        import base64
                                        from gemini_app.config import GEMINI_HOME
                                        raw_b64 = str(chat_attachment["data_b64"])
                                        if "," in raw_b64:
                                            raw_b64 = raw_b64.split(",", 1)[1]
                                        att_bytes = base64.b64decode(raw_b64)
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        att_name = chat_attachment.get("filename") or f"screenshot_{int(time.time())}.jpg"
                                        dest_file = dest_dir / f"node_{node_id}_{att_name}"
                                        dest_file.write_bytes(att_bytes)
                                        chat_attachment["local_path"] = str(dest_file)

                                        from gemini_app.fleet.media_ocr import extract_screen_text, parse_mobile_media
                                        ocr_res = extract_screen_text(dest_file)
                                        ocr_str = ocr_res.get("raw_text", "") if isinstance(ocr_res, dict) else str(ocr_res)
                                        chat_attachment["ocr_text"] = ocr_str
                                        with self.lock:
                                            self.latest_node_media[node_id] = {
                                                **parse_mobile_media(ocr_res, filename=dest_file.name),
                                                "local_path": str(dest_file),
                                                "filename": dest_file.name,
                                                "timestamp": time.time(),
                                                "is_screenshot": True,
                                            }
                                    except Exception as exc:
                                        sys.stderr.write(f"[mothership] Error saving chat attachment: {exc}\n")

                                # Broadcast user message to ALL OTHER connected satellites & local wingman
                                self.broadcast_wingman_chat(
                                    sender=chat_sender,
                                    text=chat_text,
                                    is_user=True,
                                    msg_id=chat_msg_id,
                                    exclude_node_id=node_id,
                                    origin_device=chat_origin_device,
                                    origin_label=chat_origin_label,
                                    attachment=chat_attachment,
                                )

                                if hasattr(self, "_wingman_chat_callbacks"):
                                    for cb in list(self._wingman_chat_callbacks):
                                        try:
                                            cb(dict(chat_entry))
                                        except Exception:
                                            pass
                                try:
                                    from gemini_app.config import SOCKET_PATH
                                    if SOCKET_PATH.exists():
                                        s_cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                                        s_cli.settimeout(0.5)
                                        s_cli.connect(str(SOCKET_PATH))
                                        s_cli.sendall(json.dumps({
                                            "action": "wingman_chat",
                                            "sender": chat_entry["sender"],
                                            "text": chat_entry["text"],
                                            "attachment": chat_attachment,
                                            "device_id": node_id,
                                            "device_label": chat_origin_label,
                                        }).encode("utf-8"))
                                        s_cli.close()
                                except Exception:
                                    pass

                            elif event_name in ("camera_photo_captured", "photo_captured"):
                                raw_b64 = msg.payload.get("data_b64") or msg.payload.get("body", {}).get("data_b64", "")
                                fname = msg.payload.get("filename") or msg.payload.get("body", {}).get("filename", "camera_photo.jpg")
                                if raw_b64:
                                    try:
                                        import base64
                                        from pathlib import Path
                                        from gemini_app.config import GEMINI_HOME
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        dest_file = dest_dir / f"node_{node_id}_{fname}"
                                        dest_file.write_bytes(base64.b64decode(raw_b64))

                                        from gemini_app.fleet.media_ocr import extract_screen_text, parse_mobile_media
                                        ocr_res = extract_screen_text(dest_file)
                                        media_data = parse_mobile_media(ocr_res, filename=fname)
                                        with self.lock:
                                            self.latest_node_media[node_id] = {
                                                **media_data,
                                                "local_path": str(dest_file),
                                                "filename": fname,
                                                "timestamp": time.time(),
                                                "is_camera_photo": True,
                                            }
                                        sys.stdout.write(f"[mothership] Camera photo synchronized from {node_id}: {dest_file} ({dest_file.stat().st_size} bytes)\n")
                                    except Exception as exc:
                                        sys.stderr.write(f"[mothership] Failed to process camera photo: {exc}\n")

                            elif event_name in ("screenshot_captured", "new_screenshot"):
                                raw_b64 = msg.payload.get("data_b64", "")
                                fname = msg.payload.get("filename", "screenshot.png")
                                if raw_b64:
                                    try:
                                        import base64
                                        from pathlib import Path
                                        from gemini_app.config import GEMINI_HOME
                                        dest_dir = GEMINI_HOME / "screenshots"
                                        dest_dir.mkdir(parents=True, exist_ok=True)
                                        dest_file = dest_dir / f"node_{node_id}_{fname}"
                                        dest_file.write_bytes(base64.b64decode(raw_b64))

                                        from gemini_app.fleet.media_ocr import extract_screen_text, parse_mobile_media
                                        ocr_res = extract_screen_text(dest_file)
                                        media_data = parse_mobile_media(ocr_res, filename=fname)
                                        with self.lock:
                                            self.latest_node_media[node_id] = {
                                                **media_data,
                                                "local_path": str(dest_file),
                                                "filename": fname,
                                                "timestamp": time.time(),
                                            }
                                        sys.stdout.write(f"[mothership] Mobile screenshot synchronized from {node_id}: {media_data.get('summary', fname)}\n")
                                    except Exception as exc:
                                        sys.stderr.write(f"[mothership] Failed to process incoming screenshot: {exc}\n")

                        elif msg.type == FleetMessage.TYPE_DISCONNECT:
                            sys.stdout.write(f"[mothership] Satellite requested disconnect: '{node_id}'\n")
                            return

                    except Exception as err:
                        sys.stderr.write(f"[mothership] Parse error from {addr}: {err}\n")
            if not self._running:
                return

        finally:
            if node_id:
                with self.lock:
                    if node_id in self.nodes and self.nodes[node_id].conn == conn:
                        del self.nodes[node_id]
                sys.stdout.write(f"[mothership] Satellite disconnected: '{node_id}'\n")
                try:
                    save_active_nodes(self.list_nodes())
                except Exception:
                    pass
            try:
                conn.close()
            except Exception:
                pass

    def broadcast(self, msg: FleetMessage) -> int:
        """Sends a FleetMessage to all currently connected satellites."""
        sent_count = 0
        with self.lock:
            for sat in list(self.nodes.values()):
                if sat.send(msg):
                    sent_count += 1
        return sent_count

    def broadcast_telemetry(self, cognitive_override: Optional[Dict[str, Any]] = None) -> int:
        """Pushes current host telemetry and cognitive state to all satellites."""
        if cognitive_override:
            self._cognitive_override.update(cognitive_override)
        telem = collect_mothership_telemetry(
            cognitive_override=self._cognitive_override,
            satellites_info=self.list_nodes(),
            port=self.port,
        )
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_TELEMETRY,
            node_id="mothership",
            payload={
                "mothership_telemetry": telem,
                "fleet_key": self.fleet_key,
                "mothership_boot_id": self.mothership_boot_id,
                "wingman_maintenance": self.wingman_maintenance_mode,
            },
        )
        return self.broadcast(msg)

    def set_wingman_maintenance(self, active: bool, reason: str = "") -> None:
        """Enables or releases fleet-wide Wingman maintenance mode during updates/reboots."""
        self.wingman_maintenance_mode = active
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload={
                "event": "wingman_maintenance_lock" if active else "wingman_maintenance_clear",
                "active": active,
                "reason": reason,
                "timestamp": time.time(),
            },
        )
        self.broadcast(msg)
        self.broadcast_telemetry()
        if self.local_wingman and hasattr(self.local_wingman, "set_maintenance_mode"):
            try:
                self.local_wingman.set_maintenance_mode(active, reason=reason)
            except Exception:
                pass

    def reset_wingman_epoch(self, new_boot_id: Optional[str] = None) -> str:
        """Resets the Mothership boot ID epoch and broadcasts session invalidation to all fleet satellites."""
        self.mothership_boot_id = new_boot_id or secrets.token_hex(8)
        with self.lock:
            self.pending_wingman_auth_requests.clear()
        if self.local_wingman and hasattr(self.local_wingman, "on_mothership_reboot"):
            try:
                self.local_wingman.on_mothership_reboot(self.mothership_boot_id)
            except Exception:
                pass
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload={
                "event": "mothership_rebooted",
                "mothership_boot_id": self.mothership_boot_id,
                "timestamp": time.time(),
            },
        )
        self.broadcast(msg)
        self.broadcast_telemetry()
        sys.stdout.write(f"[mothership] Reset Wingman epoch to {self.mothership_boot_id} and broadcasted to fleet.\n")
        return self.mothership_boot_id

    def push_cognitive_event(self, event_text: str, details: Optional[Dict[str, Any]] = None) -> int:
        """Pushes an event toast/log entry across the fleet."""
        payload = {"event": event_text, "timestamp": time.time(), "details": details or {}}
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload=payload,
        )
        return self.broadcast(msg)

    def start_local_wingman(self, port: int = 8888) -> bool:
        """Starts a local Wingman instance on the Mothership (e.g. for dual-screen desktop use)."""
        if self.local_wingman and self.local_wingman.engine.is_running:
            return True
        try:
            from gemini_app.webapplet.applets.wingman import WingmanApplet
            self.local_wingman = WingmanApplet(port=port)
            return self.local_wingman.start()
        except Exception as exc:
            sys.stderr.write(f"[mothership] Failed to start local Wingman on port {port}: {exc}\n")
            return False

    def start_local_inspector(self, port: int = 8889) -> bool:
        """Starts a local Photon 3D Inspector on a separate port independently of Wingman."""
        if self.local_inspector and self.local_inspector.engine.is_running:
            return True
        try:
            from gemini_app.webapplet.applets.inspector import InspectorApplet
            self.local_inspector = InspectorApplet(port=port)
            return self.local_inspector.start()
        except Exception as exc:
            sys.stderr.write(f"[mothership] Failed to start local Inspector on port {port}: {exc}\n")
            return False

    def push_wingman_card(
        self,
        node_id: str,
        title: str,
        content: str,
        actions: Optional[List[Dict[str, str]]] = None,
        accent: bool = True,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Dispatches an interactive card to a node's open Wingman portal or local Wingman."""
        if node_id in ("local", "localhost", "mothership"):
            if self.local_wingman and self.local_wingman.engine.is_running:
                cid = self.local_wingman.push_card(title=title, content=content, actions=actions, accent=accent)
                return {"status": "ok", "card_id": cid}
            return {"status": "error", "error": "Local Wingman is not running"}

        return self.send_command(
            node_id=node_id,
            action="webapplet_push",
            params={
                "title": title,
                "content": content,
                "actions": actions or [],
                "accent": accent,
            },
            timeout=timeout,
        )

    def broadcast_wingman_chat(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        msg_id: str = "",
        exclude_node_id: Optional[str] = None,
        origin_device: str = "",
        origin_label: str = "",
        attachment: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Broadcasts a Wingman chat bubble across all connected satellites and local Wingman."""
        import secrets
        m_id = msg_id or f"msg-{int(time.time() * 1000)}-{secrets.token_hex(3)}"
        chat_item = {
            "id": m_id,
            "sender": sender,
            "text": text,
            "is_user": is_user,
            "timestamp": time.time(),
            "origin_device": origin_device,
            "origin_label": origin_label,
            "attachment": attachment,
        }
        with self.lock:
            if not any(m.get("id") == m_id for m in self.recent_wingman_chat):
                self.recent_wingman_chat.append(chat_item)
                if len(self.recent_wingman_chat) > 50:
                    self.recent_wingman_chat.pop(0)

        if self.local_wingman and hasattr(self.local_wingman, "push_chat_message"):
            try:
                self.local_wingman.push_chat_message(
                    sender=sender,
                    text=text,
                    is_user=is_user,
                    msg_id=m_id,
                    origin_device=origin_device,
                    origin_label=origin_label,
                    attachment=attachment,
                )
            except Exception:
                pass

        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload={
                "event": "wingman_chat_message",
                "id": m_id,
                "sender": sender,
                "text": text,
                "is_user": is_user,
                "timestamp": chat_item["timestamp"],
                "origin_device": origin_device,
                "origin_label": origin_label,
                "attachment": attachment,
            },
        )
        sent_count = 0
        with self.lock:
            for nid, sat in list(self.nodes.items()):
                if exclude_node_id and nid == exclude_node_id:
                    continue
                if sat.send(msg):
                    sent_count += 1
        return sent_count

    def broadcast_wingman_clear(self) -> int:
        """Clears chat history across local Wingman and all fleet satellites."""
        with self.lock:
            self.recent_wingman_chat.clear()
        if self.local_wingman and hasattr(self.local_wingman, "clear_chat"):
            try:
                self.local_wingman.clear_chat()
            except Exception:
                pass
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload={
                "event": "wingman_chat_clear",
                "timestamp": time.time(),
            },
        )
        return self.broadcast(msg)

    def request_node_biometric(
        self,
        node_id: str,
        reason: str = "Authorize Operation",
        timeout: float = 30.0,
        method: str = "auto",
    ) -> Dict[str, Any]:
        """Requests biometric authentication (Face ID or Fingerprint) from a specific node."""
        if not node_id:
            from gemini_app.fleet.biometrics import FleetBiometricsManager
            mgr = FleetBiometricsManager(self)
            return mgr.request_biometric(reason=reason, method=method, timeout=timeout)

        if node_id in ("local", "localhost", "mothership"):
            if self.local_wingman and self.local_wingman.engine.is_running:
                return self.local_wingman.request_biometric(reason=reason, method=method, timeout=timeout)
            return {"status": "error", "error": "Local Wingman not running for biometrics"}

        return self.send_command(
            node_id=node_id,
            action="biometric_auth",
            params={"reason": reason, "timeout": timeout, "method": method},
            timeout=timeout + 5.0,
        )

    def _prune_pending_wingman_requests(self, max_age: float = 45.0) -> None:
        """Removes expired pending auth requests and entries from nodes whose browser is closed."""
        now = time.time()
        to_remove = []
        for rid, req in list(self.pending_wingman_auth_requests.items()):
            ts = float(req.get("timestamp", now) or now)
            if now - ts > max_age:
                to_remove.append(rid)
                continue
            nid = req.get("node_id")
            if nid and nid not in ("local", "localhost", "mothership"):
                if nid not in self.nodes:
                    to_remove.append(rid)
                    continue
                sat = self.nodes[nid]
                if (now - getattr(sat, "last_heartbeat", now)) > 60.0:
                    to_remove.append(rid)
                    continue
                telem = sat.telemetry or {}
                # Only prune if node explicitly reports wingman browser is not open AND node has no pending auth in telemetry
                pending_on_node = telem.get("webapplet", {}).get("pending_auth", [])
                if telem.get("webapplet", {}).get("wingman_active") is False and not pending_on_node:
                    to_remove.append(rid)
        for rid in to_remove:
            self.pending_wingman_auth_requests.pop(rid, None)

    def _notify_wingman_auth(self, auth_entry: Dict[str, Any]) -> None:
        """Notifies local UI via UNIX socket and callbacks about pending Wingman authorization."""
        if time.time() - auth_entry.get("timestamp", time.time()) > 45.0:
            return
        req_id = auth_entry.get("auth_req_id") or auth_entry.get("session_id", "")
        nid = auth_entry.get("node_id", "local")
        cip = auth_entry.get("client_ip", "remote")
        sys.stdout.write(
            f"[mothership] Wingman access requested on node '{nid}' ({cip}) - req {req_id}\n"
        )
        for cb in list(self._wingman_auth_callbacks):
            try:
                cb(dict(auth_entry))
            except Exception:
                pass
        if self.port == 0:
            return
        nid_raw = str(nid).strip().lower()
        if nid_raw.startswith(("test-", "test_")) or nid_raw == "test":
            return
        try:
            from gemini_app.config import SOCKET_PATH
            if SOCKET_PATH.exists():
                s_cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s_cli.settimeout(0.5)
                s_cli.connect(str(SOCKET_PATH))
                s_cli.sendall(json.dumps({
                    "action": "wingman_auth_prompt",
                    "auth_data": auth_entry,
                }).encode("utf-8"))
                s_cli.close()
        except Exception:
            pass

    def on_wingman_auth(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a callback for incoming zero-trust Wingman connection requests."""
        with self.lock:
            self._wingman_auth_callbacks.append(callback)

    def authorize_wingman(
        self,
        node_id: str,
        auth_req_id: str,
        decision: str = "accept",
        trust: bool = False,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Sends bilateral authorization decision (accept, trust, or deny) for an auth request."""
        dev_id = ""
        with self.lock:
            # If node_id was not explicitly specified or is local, look up who owns this auth_req_id
            if (not node_id or node_id in ("local", "localhost")) and auth_req_id in self.pending_wingman_auth_requests:
                node_id = self.pending_wingman_auth_requests[auth_req_id].get("node_id", node_id)
            if auth_req_id in self.pending_wingman_auth_requests:
                dev_id = self.pending_wingman_auth_requests[auth_req_id].get("device_id", "")
            self.pending_wingman_auth_requests.pop(auth_req_id, None)

        accepted = (decision in ("accept", "accepted", "trust", "pair"))
        trust_device = trust or (decision in ("trust", "pair"))

        if node_id in ("local", "localhost", "mothership"):
            if self.local_wingman and hasattr(self.local_wingman, "authorize_session"):
                return self.local_wingman.authorize_session(auth_req_id, accepted=accepted, trust_device=trust_device, device_id=dev_id)
            elif self.local_wingman and hasattr(self.local_wingman, "resolve_auth_request"):
                return self.local_wingman.resolve_auth_request(auth_req_id, decision=decision, trust=trust_device)
            return {"status": "error", "error": "Local Wingman not running"}

        return self.send_command(
            node_id=node_id,
            action="authorize_wingman",
            params={
                "session_id": auth_req_id,
                "auth_req_id": auth_req_id,
                "device_id": dev_id,
                "decision": decision,
                "accepted": accepted,
                "trust_device": trust_device,
            },
            timeout=timeout,
        )

    def prompt_wingman_passkey(
        self,
        node_id: str,
        reason: str = "Authorize Bilateral Homebase Message",
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Prompts the connected Wingman browser for Homebase passkey verification."""
        if node_id in ("local", "localhost", "mothership"):
            if self.local_wingman and hasattr(self.local_wingman, "prompt_passkey"):
                p_id = self.local_wingman.prompt_passkey(reason=reason)
                return {"status": "ok", "prompt_id": p_id}
            return {"status": "error", "error": "Local Wingman not running"}

        return self.send_command(
            node_id=node_id,
            action="wingman_prompt_passkey",
            params={"reason": reason},
            timeout=timeout,
        )

    def verify_wingman_passkey(self, passkey: str) -> bool:
        """Cryptographically verifies a passkey against Homebase's PBKDF2 vault hash."""
        import importlib
        import gemini_app.fleet.wingman_auth as wauth
        try:
            importlib.reload(wauth)
        except Exception:
            pass
        return wauth.verify_homebase_passkey(passkey)

    def set_cognitive_state(
        self,
        state_desc: str = "",
        task: str = "",
        thought: str = "",
        tool: str = "none",
        turn_number: Optional[int] = None,
        topic: str = "",
    ) -> None:
        """Updates internal cognitive state and broadcasts immediately."""
        updates: Dict[str, Any] = {}
        if state_desc:
            updates["state_desc"] = state_desc
        if task:
            updates["task"] = task
        if thought:
            updates["thought"] = thought
        if tool:
            updates["tool"] = tool
        if turn_number is not None:
            updates["turn_number"] = turn_number
        if topic:
            updates["topic"] = topic
        self._cognitive_override.update(updates)
        self.broadcast_telemetry()

    def list_nodes(self) -> List[Dict[str, Any]]:
        """Returns snapshot list of currently connected satellite nodes, most recently used on top."""
        with self.lock:
            result = []
            now = time.time()
            for nid, sat in self.nodes.items():
                result.append({
                    "node_id": nid,
                    "address": f"{sat.addr[0]}:{sat.addr[1]}",
                    "uptime_seconds": round(now - sat.connected_at, 1),
                    "last_seen_seconds_ago": round(now - sat.last_heartbeat, 1),
                    "last_active_seconds_ago": round(now - getattr(sat, "last_active", sat.last_heartbeat), 1),
                    "last_error": getattr(sat, "last_error", {}),
                    "telemetry": dict(sat.telemetry),
                })
            # Most recent on top (lowest last_active_seconds_ago first)
            result.sort(key=lambda x: x.get("last_active_seconds_ago", 999999.0))
            return result

    def send_command(
        self,
        node_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Dispatches an action command to a specific connected satellite node and waits for response."""
        with self.lock:
            satellite = self.nodes.get(node_id)
            if not satellite:
                return {"status": "error", "error": f"Node '{node_id}' not connected"}
            satellite.last_active = time.time()

        req_id = f"cmd-{int(time.time() * 1000)}-{node_id}"
        event = threading.Event()
        satellite.response_events[req_id] = event

        cmd_ts = time.time()
        cmd_sig = compute_command_signature(self.fleet_key, action, node_id, cmd_ts)

        cmd = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id="mothership",
            payload={
                "action": action,
                "params": params or {},
                "auth_sig": cmd_sig,
                "auth_ts": cmd_ts,
            },
            msg_id=req_id,
        )

        sent = satellite.send(cmd)
        if not sent:
            satellite.response_events.pop(req_id, None)
            return {"status": "error", "error": f"Failed to send command to '{node_id}'"}

        # Wait for reply
        signaled = event.wait(timeout=timeout)
        satellite.response_events.pop(req_id, None)

        if not signaled:
            satellite.pending_responses.pop(req_id, None)
            return {"status": "error", "error": f"Command '{action}' timed out after {timeout}s"}

        return satellite.pending_responses.pop(req_id, {"status": "unknown"})

    def ping_node(self, node_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        """Sends ping to satellite and measures round-trip latency in milliseconds."""
        start_t = time.perf_counter()
        resp = self.send_command(node_id, "ping", timeout=timeout)
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        resp["rtt_ms"] = elapsed_ms
        return resp

    def get_repo_bundle(self, repo_dir: Optional[Path] = None) -> tuple[Optional[str], str]:
        """Creates a base64 gzipped tarball archive of HEAD for direct satellite upgrades."""
        cwd = find_repo_root(repo_dir)
        commit, _ = _get_git_info_fast(cwd)
        full_commit = ""
        try:
            res_full = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res_full.returncode == 0 and len(res_full.stdout.strip()) == 40:
                full_commit = res_full.stdout.strip()
        except Exception:
            pass
        target_commit_sha = full_commit or commit

        # 1. Prefer fast git archive of HEAD
        try:
            res = subprocess.run(
                ["git", "archive", "--format=tar.gz", "HEAD"],
                cwd=cwd,
                capture_output=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout:
                b64 = base64.b64encode(res.stdout).decode("ascii")
                return b64, target_commit_sha
        except Exception:
            pass

        # 2. Pure-Python tarball fallback (excluding __pycache__ and git metadata)
        try:
            import io
            import tarfile
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for top_f in ("gemini-integrated.py", "__main__.py", "LICENSE.txt", "README.md"):
                    p = cwd / top_f
                    if p.is_file():
                        tar.add(str(p), arcname=top_f)
                app_dir = cwd / "gemini_app"
                if app_dir.is_dir():
                    for root, dirs, files in os.walk(app_dir):
                        dirs[:] = [d for d in dirs if d != "__pycache__"]
                        for f in files:
                            if not f.endswith(".pyc"):
                                full = Path(root) / f
                                arcname = str(full.relative_to(cwd))
                                tar.add(str(full), arcname=arcname)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode("ascii")
            return b64, target_commit_sha
        except Exception:
            return None, target_commit_sha

    def upgrade_node(
        self,
        node_id: str,
        target_ref: str = "origin/main",
        force: bool = False,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        """Sends atomic 3-stage upgrade command to a specific node with direct Mothership bundle."""
        bundle_b64, ms_commit = self.get_repo_bundle()
        return self.send_command(
            node_id=node_id,
            action="fleet_upgrade",
            params={
                "target_ref": target_ref,
                "target_commit": ms_commit,
                "bundle_b64": bundle_b64,
                "force": force,
            },
            timeout=timeout,
        )

    def upgrade_all(
        self,
        target_ref: str = "origin/main",
        force: bool = False,
        timeout: float = 45.0,
    ) -> Dict[str, Dict[str, Any]]:
        """Sends atomic 3-stage upgrade command to all connected nodes."""
        with self.lock:
            node_ids = list(self.nodes.keys())
        results = {}
        for nid in node_ids:
            results[nid] = self.upgrade_node(nid, target_ref=target_ref, force=force, timeout=timeout)
        return results

    def rescue_remote_node(self, node_id: str, action: str = "restart", timeout: int = 15) -> Dict[str, Any]:
        """Dispatches an SSH rescue/reboot operation to a remote node using cluster key credentials."""
        return execute_ssh_rescue(node_id=node_id, action=action, timeout=timeout)

    def notify_fleet_of_ip_change(
        self,
        new_lan_ip: str,
        new_wan_ip: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 4.0,
    ) -> Dict[str, Any]:
        """Dispatches dynamic IP updates to registered satellite nodes (via Rendezvous TCP or SSH rescue)."""
        from gemini_app.fleet.nodes import load_nodes_registry
        from gemini_app.fleet.protocol import DEFAULT_RENDEZVOUS_PORT
        registry = load_nodes_registry()
        results: Dict[str, Any] = {}

        p = port or self.port
        for nid, ninfo in registry.items():
            nhost = ninfo.get("host")
            if not nhost:
                continue

            success = False
            method_used = "rendezvous_tcp"
            detail = ""

            # 1. Try Rendezvous TCP port
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                target_r_port = int(ninfo.get("rendezvous_port") or DEFAULT_RENDEZVOUS_PORT)
                s.connect((nhost, target_r_port))
                cmd_ts = time.time()
                cmd_sig = compute_command_signature(self.fleet_key, "update_mothership_endpoint", nid, cmd_ts)
                cmd = FleetMessage(
                    msg_type=FleetMessage.TYPE_COMMAND,
                    node_id="mothership",
                    payload={
                        "action": "update_mothership_endpoint",
                        "params": {"lan_ip": new_lan_ip, "wan_ip": new_wan_ip, "port": p, "fleet_key": self.fleet_key},
                        "auth_sig": cmd_sig,
                        "auth_ts": cmd_ts,
                    },
                )
                s.sendall(cmd.serialize())
                resp_line = s.recv(2048).decode("utf-8", errors="replace")
                s.close()
                if resp_line:
                    resp_msg = FleetMessage.deserialize(resp_line)
                    if resp_msg.payload.get("status") == "ok":
                        success = True
                        detail = "Endpoint accepted via Rendezvous listener"
            except Exception as exc:
                detail = f"Rendezvous TCP connection failed: {exc}"

            # 2. Fallback to SSH update if TCP listener didn't succeed
            if not success and ninfo.get("ssh_port"):
                method_used = "ssh_tunnel"
                py_cmd = (
                    f"python3 -c \"from gemini_app.fleet.satellite import save_mothership_dual_endpoints; "
                    f"save_mothership_dual_endpoints(lan_ip='{new_lan_ip}', wan_ip='{new_wan_ip or ''}', port={p})\""
                )
                ssh_res = execute_ssh_rescue(node_id=nid, action="exec", custom_cmd=py_cmd, timeout=8)
                if ssh_res.get("status") == "ok":
                    success = True
                    detail = "Endpoint updated via SSH cluster key"
                else:
                    detail += f" | SSH fallback failed: {ssh_res.get('error', 'unknown error')}"

            results[nid] = {
                "host": nhost,
                "status": "ok" if success else "failed",
                "method": method_used,
                "detail": detail,
            }

        return results

    def stop(self) -> None:
        """Shuts down server socket and disconnects connected satellites."""
        self._running = False
        if self.local_wingman:
            try:
                self.local_wingman.stop()
            except Exception:
                pass
        if self.local_inspector:
            try:
                self.local_inspector.stop()
            except Exception:
                pass
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None

        with self.lock:
            for sat in self.nodes.values():
                sat.close()
            self.nodes.clear()
        sys.stdout.write("[mothership] Fleet server stopped.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini Mothership Fleet Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Binding TCP port")
    parser.add_argument("--require-auth", action="store_true", default=False, help="Strictly enforce HMAC challenge auth for all connections")
    parser.add_argument("--no-auth", dest="require_auth", action="store_false", help="Allow unauthenticated LAN node registration (default)")
    parser.add_argument("--upgrade", metavar="NODE_ID", help="Dispatch atomic upgrade to specific satellite node")
    parser.add_argument("--upgrade-all", action="store_true", help="Dispatch atomic upgrade to all active satellite nodes")
    parser.add_argument("--notify-ip", metavar="LAN_IP", help="Dispatch Mothership IP migration to all registered fleet nodes")
    parser.add_argument("--wan-ip", metavar="WAN_IP", default=None, help="Optional WAN IP for --notify-ip")
    args = parser.parse_args()

    if args.notify_ip:
        server = MothershipServer(host=args.host, port=args.port, auto_broadcast_telemetry=False)
        print(f"[mothership] Disagreeing fleet of IP migration to LAN={args.notify_ip}, WAN={args.wan_ip}...")
        res = server.notify_fleet_of_ip_change(new_lan_ip=args.notify_ip, new_wan_ip=args.wan_ip, port=args.port)
        for nid, r in res.items():
            print(f"  • {nid} ({r.get('host')}): {r.get('status')} via {r.get('method')} ({r.get('detail')})")
        return 0

    server = MothershipServer(host=args.host, port=args.port, require_auth=args.require_auth)
    if not server.start():
        return 1

    print("Mothership Fleet Registry active. Press Ctrl+C to terminate.")
    try:
        while True:
            time.sleep(5)
            nodes = server.list_nodes()
            if nodes:
                print(f"[{time.strftime('%H:%M:%S')}] Active Satellites ({len(nodes)}):")
                for n in nodes:
                    sys_name = n['telemetry'].get('system', '?')
                    mach = n['telemetry'].get('machine', '?')
                    print(f"  • {n['node_id']} ({n['address']}) [{sys_name}/{mach}] last seen: {n['last_seen_seconds_ago']}s ago")
    except KeyboardInterrupt:
        print("\nStopping Mothership Fleet Server...")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())