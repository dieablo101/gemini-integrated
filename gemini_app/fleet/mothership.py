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

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self.nodes: Dict[str, ConnectedSatellite] = {}
        self.lock = threading.Lock()
        self.server_sock: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Binds and starts accepting incoming satellite node connections."""
        if self._running:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(10)
            self.server_sock = s
            self._running = True
            self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._accept_thread.start()
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

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        buf = ""
        node_id: Optional[str] = None
        satellite: Optional[ConnectedSatellite] = None

        try:
            while self._running:
                data = conn.recv(4096)
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

                        if msg.type == FleetMessage.TYPE_REGISTER:
                            with self.lock:
                                satellite = ConnectedSatellite(node_id, conn, addr)
                                satellite.telemetry = msg.payload.get("telemetry", {})
                                self.nodes[node_id] = satellite
                            sys.stdout.write(f"[mothership] Satellite registered: '{node_id}' from {addr}\n")

                        elif msg.type == FleetMessage.TYPE_HEARTBEAT:
                            with self.lock:
                                if node_id in self.nodes:
                                    sat = self.nodes[node_id]
                                    sat.last_heartbeat = time.time()
                                    if "telemetry" in msg.payload:
                                        sat.telemetry = msg.payload["telemetry"]

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
                conn.close()
            except Exception:
                pass

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

        cmd = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id="mothership",
            payload={"action": action, "params": params or {}},
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
