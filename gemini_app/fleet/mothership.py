"""Mothership Fleet Registry and Dispatcher.

Runs on the main host console, coordinating distributed satellite nodes,
monitoring heartbeats, and dispatching tasks over persistent TCP sockets.
"""

from __future__ import annotations

import argparse
import json
import socket
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
from gemini_app.fleet.nodes import (
    execute_ssh_rescue,
    register_or_update_node,
    save_active_nodes,
)


class ConnectedSatellite:
    """Represents an active satellite node connected to the Mothership."""

    def __init__(self, node_id: str, conn: socket.socket, addr: tuple[str, int]) -> None:
        self.node_id = node_id
        self.conn = conn
        self.addr = addr
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
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
        require_auth: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.auto_broadcast_telemetry = auto_broadcast_telemetry
        self.broadcast_interval = broadcast_interval
        self.require_auth = require_auth
        self.fleet_key = get_or_create_fleet_key()

        self.nodes: Dict[str, ConnectedSatellite] = {}
        self.lock = threading.Lock()
        self.server_sock: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._telemetry_thread: Optional[threading.Thread] = None
        self._cognitive_override: Dict[str, Any] = {}

    def start(self) -> bool:
        """Binds and starts accepting incoming satellite node connections."""
        if self._running:
            return True
        try:
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
                client_thread = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
            except Exception:
                if not self._running:
                    break

    def _telemetry_broadcast_loop(self) -> None:
        """Periodically streams host telemetry and cognitive updates to connected satellites."""
        while self._running:
            try:
                time.sleep(self.broadcast_interval)
                with self.lock:
                    if not self.nodes:
                        continue
                self.broadcast_telemetry()
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
        if self.require_auth:
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
                            if verify_auth_signature(fleet_key, node_id, auth_nonce, ts, sig):
                                is_authenticated = True
                                with self.lock:
                                    satellite = ConnectedSatellite(node_id, conn, addr)
                                    satellite.telemetry = msg.payload.get("telemetry", {})
                                    self.nodes[node_id] = satellite
                                sys.stdout.write(f"[mothership] Satellite authenticated & registered: '{node_id}' from {addr}\n")

                                ack = FleetMessage(
                                    msg_type=FleetMessage.TYPE_AUTH_OK,
                                    node_id="mothership",
                                    payload={"status": "authenticated", "node_id": node_id},
                                )
                                conn.sendall(ack.serialize())

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
                                    payload={"mothership_telemetry": init_telem},
                                )
                                satellite.send(greet)
                            else:
                                sys.stderr.write(f"[mothership] UNAUTHORIZED node '{node_id}' from {addr}: invalid signature\n")
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

                        elif msg.type == FleetMessage.TYPE_REGISTER:
                            # Allow if loopback or auth not enforced
                            if is_loopback or not self.require_auth:
                                is_authenticated = True
                                with self.lock:
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
                                    payload={"mothership_telemetry": init_telem},
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
                                    if "telemetry" in msg.payload:
                                        sat.telemetry = msg.payload["telemetry"]
                            try:
                                save_active_nodes(self.list_nodes())
                            except Exception:
                                pass

                        elif msg.type == FleetMessage.TYPE_RESPONSE:
                            with self.lock:
                                if node_id in self.nodes:
                                    sat = self.nodes[node_id]
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
                            elif action == "mothership_telemetry":
                                resp_payload["mothership_telemetry"] = collect_mothership_telemetry(
                                    cognitive_override=self._cognitive_override,
                                    satellites_info=self.list_nodes(),
                                )
                            reply = FleetMessage(
                                msg_type=FleetMessage.TYPE_RESPONSE,
                                node_id="mothership",
                                payload=resp_payload,
                                msg_id=f"resp-{msg.msg_id}",
                            )
                            with self.lock:
                                if node_id in self.nodes:
                                    self.nodes[node_id].send(reply)

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
        )
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_TELEMETRY,
            node_id="mothership",
            payload={"mothership_telemetry": telem},
        )
        return self.broadcast(msg)

    def push_cognitive_event(self, event_text: str, details: Optional[Dict[str, Any]] = None) -> int:
        """Pushes an event toast/log entry across the fleet."""
        payload = {"event": event_text, "timestamp": time.time(), "details": details or {}}
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload=payload,
        )
        return self.broadcast(msg)

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
        """Returns snapshot list of currently connected satellite nodes."""
        with self.lock:
            result = []
            now = time.time()
            for nid, sat in self.nodes.items():
                result.append({
                    "node_id": nid,
                    "address": f"{sat.addr[0]}:{sat.addr[1]}",
                    "uptime_seconds": round(now - sat.connected_at, 1),
                    "last_seen_seconds_ago": round(now - sat.last_heartbeat, 1),
                    "telemetry": dict(sat.telemetry),
                })
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

    def upgrade_node(
        self,
        node_id: str,
        target_ref: str = "origin/main",
        force: bool = False,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        """Sends atomic 3-stage upgrade command to a specific node."""
        return self.send_command(
            node_id=node_id,
            action="fleet_upgrade",
            params={"target_ref": target_ref, "force": force},
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
        """Dispatches an SSH rescue/reboot operation to a remote node using dieablo key credentials."""
        return execute_ssh_rescue(node_id=node_id, action=action, timeout=timeout)

    def stop(self) -> None:
        """Shuts down server socket and disconnects connected satellites."""
        self._running = False
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
    parser.add_argument("--upgrade", metavar="NODE_ID", help="Dispatch atomic upgrade to specific satellite node")
    parser.add_argument("--upgrade-all", action="store_true", help="Dispatch atomic upgrade to all active satellite nodes")
    args = parser.parse_args()

    server = MothershipServer(host=args.host, port=args.port)
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
