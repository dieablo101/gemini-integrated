"""Fleet Nodes Registry and Remote SSH Rescue Engine.

Manages persistent node configurations, active status tracking, and autonomous
SSH rescue/reboot mechanisms using configured cluster SSH credentials.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from gemini_app.config import GEMINI_HOME
from gemini_app.fleet.keys import get_or_create_cluster_ssh_key, get_stored_cluster_key_path, save_cluster_key_path

FLEET_DIR = GEMINI_HOME / "fleet"
NODES_REGISTRY_FILE = FLEET_DIR / "nodes_registry.json"
ACTIVE_NODES_FILE = FLEET_DIR / "active_nodes.json"


def get_cluster_ssh_key() -> Optional[Path]:
    """Finds or creates the cluster SSH private key using setup configuration."""
    return get_or_create_cluster_ssh_key()


# Backwards compatibility alias
def get_dieablo_ssh_key() -> Optional[Path]:
    return get_cluster_ssh_key()


def ensure_fleet_dir() -> Path:
    """Ensures ~/.gemini/fleet exists with secure permissions."""
    FLEET_DIR.mkdir(parents=True, exist_ok=True)
    try:
        FLEET_DIR.chmod(0o700)
    except Exception:
        pass
    return FLEET_DIR


def load_nodes_registry() -> Dict[str, Dict[str, Any]]:
    """Loads all known persistent fleet nodes from disk."""
    ensure_fleet_dir()
    if not NODES_REGISTRY_FILE.exists():
        # Seed with initial known iPad satellite node if available
        default_key = get_cluster_ssh_key()
        default_registry = {
            "satellite-ipad": {
                "node_id": "satellite-ipad",
                "host": "192.168.1.38",
                "ssh_user": "root",
                "ssh_port": 22,
                "ssh_key": str(default_key) if default_key else str(FLEET_DIR / "id_cluster"),
                "autostart": "openrc",
                "status": "online",
                "last_seen": time.time(),
                "telemetry": {"system": "Linux", "machine": "i686", "platform": "iSH Alpine"},
            }
        }
        save_nodes_registry(default_registry)
        return default_registry

    try:
        return json.loads(NODES_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_nodes_registry(registry: Dict[str, Dict[str, Any]]) -> bool:
    """Saves persistent nodes registry to disk."""
    ensure_fleet_dir()
    try:
        NODES_REGISTRY_FILE.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        NODES_REGISTRY_FILE.chmod(0o600)
        return True
    except Exception:
        return False


def register_or_update_node(
    node_id: str,
    host: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    ssh_key: Optional[str] = None,
    autostart: str = "auto",
    telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Registers or updates a persistent node entry in the fleet registry."""
    registry = load_nodes_registry()

    resolved_key = ssh_key
    if not resolved_key:
        found_key = get_cluster_ssh_key()
        resolved_key = str(found_key) if found_key else str(FLEET_DIR / "id_cluster")

    # Deduplicate: if an older placeholder exists with the same host IP and a different node_id, retire it
    stale_keys = [
        k for k, v in registry.items()
        if k != node_id and v.get("host") == host and (k in ("satellite-ipad", "test-satellite-unit") or v.get("status") == "offline")
    ]
    for sk in stale_keys:
        del registry[sk]

    entry = registry.get(node_id, {})
    entry.update({
        "node_id": node_id,
        "host": host,
        "ssh_user": ssh_user or entry.get("ssh_user", "root"),
        "ssh_port": int(ssh_port or entry.get("ssh_port", 22)),
        "ssh_key": resolved_key or entry.get("ssh_key", ""),
        "autostart": autostart if autostart != "auto" else entry.get("autostart", "systemd"),
        "last_seen": time.time(),
        "status": "online",
    })
    if telemetry:
        if "telemetry" not in entry:
            entry["telemetry"] = {}
        entry["telemetry"].update(telemetry)

    registry[node_id] = entry
    save_nodes_registry(registry)
    return entry


def remove_node(node_id: str) -> bool:
    """Removes a node from the persistent registry."""
    registry = load_nodes_registry()
    if node_id in registry:
        del registry[node_id]
        save_nodes_registry(registry)
        return True
    return False


def load_active_nodes() -> List[Dict[str, Any]]:
    """Loads currently active nodes reported by the live Mothership daemon."""
    if not ACTIVE_NODES_FILE.exists():
        return []
    try:
        data = json.loads(ACTIVE_NODES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("nodes", [])
        return []
    except Exception:
        return []


def save_active_nodes(nodes: List[Dict[str, Any]]) -> bool:
    """Writes currently active nodes to ~/.gemini/fleet/active_nodes.json."""
    ensure_fleet_dir()
    try:
        ACTIVE_NODES_FILE.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
        ACTIVE_NODES_FILE.chmod(0o600)
        return True
    except Exception:
        return False


def get_fleet_snapshot() -> Dict[str, Any]:
    """Compiles a complete snapshot of live connected nodes and registered nodes."""
    active_list = load_active_nodes()
    registry = load_nodes_registry()

    active_map = {n.get("node_id", ""): n for n in active_list if n.get("node_id")}

    combined = []
    # 1. Process all registered nodes
    for nid, reg_data in registry.items():
        node_copy = dict(reg_data)
        if nid in active_map:
            node_copy["status"] = "online"
            node_copy["live_info"] = active_map[nid]
            node_copy["last_seen"] = active_map[nid].get("last_seen_seconds_ago", 0)
            if "telemetry" in active_map[nid]:
                node_copy["telemetry"] = active_map[nid]["telemetry"]
        else:
            # Check how long ago last_seen was
            diff = time.time() - node_copy.get("last_seen", 0)
            node_copy["status"] = "online" if diff < 45.0 else "offline"
            node_copy["last_seen_seconds_ago"] = round(diff, 1)

        combined.append(node_copy)

    # 2. Add any active nodes not yet in the registry
    for nid, act in active_map.items():
        if nid not in registry:
            host_part = act.get("address", "").split(":")[0] if ":" in act.get("address", "") else act.get("address", "")
            combined.append({
                "node_id": nid,
                "host": host_part,
                "ssh_user": "root",
                "ssh_port": 22,
                "ssh_key": str(get_cluster_ssh_key() or (FLEET_DIR / "id_cluster")),
                "autostart": "auto",
                "status": "online",
                "last_seen_seconds_ago": act.get("last_seen_seconds_ago", 0),
                "telemetry": act.get("telemetry", {}),
                "live_info": act,
            })

    return {
        "active_count": len(active_list),
        "total_registered": len(combined),
        "nodes": combined,
    }


def execute_ssh_rescue(
    node_id: str,
    action: str = "restart",
    custom_cmd: str = "",
    timeout: int = 15,
) -> Dict[str, Any]:
    """Connects to a remote node over SSH using the cluster key to check, restart, or reboot it."""
    registry = load_nodes_registry()
    node = registry.get(node_id)

    if not node:
        # Check active nodes if node_id wasn't in registry
        for n in load_active_nodes():
            if n.get("node_id") == node_id:
                host = n.get("address", "").split(":")[0]
                node = {
                    "node_id": node_id,
                    "host": host,
                    "ssh_user": "root",
                    "ssh_port": 22,
                    "ssh_key": str(get_cluster_ssh_key() or (FLEET_DIR / "id_cluster")),
                }
                break

    if not node:
        return {"status": "error", "error": f"Node '{node_id}' not found in registry or active connections."}

    host = node.get("host")
    if not host:
        return {"status": "error", "error": f"No host IP/address configured for node '{node_id}'."}

    user = node.get("ssh_user", "root")
    port = node.get("ssh_port", 22)

    key_path = node.get("ssh_key")
    if not key_path or not os.path.exists(os.path.expanduser(key_path)):
        cluster_key = get_cluster_ssh_key()
        if cluster_key:
            key_path = str(cluster_key)
        else:
            return {"status": "error", "error": f"SSH key not found: {key_path}"}

    key_path = str(Path(os.path.expanduser(key_path)).resolve())

    # Build rescue command according to action
    if action in ("restart", "reboot"):
        # For remote satellite nodes, reboot/restart should safely restart the satellite daemon,
        # preferring any local virtual environment (.venv / venv) over global system python.
        remote_cmd = (
            "systemctl restart gemini-satellite 2>/dev/null || "
            "(rc-service gemini-satellite restart 2>/dev/null || "
            "(/etc/local.d/gemini-satellite.start 2>/dev/null || "
            "(pkill -f 'gemini-integrated.*(node|satellite)' 2>/dev/null ; sleep 0.5 ; "
            "for d in /root/gemini-integrated ~/gemini-integrated /opt/gemini \"$HOME/gemini-integrated\" /data/data/com.termux/files/home/gemini-integrated; do "
            "if [ -d \"$d\" ]; then cd \"$d\" && "
            "if [ -f .venv/bin/python ]; then PY=.venv/bin/python; "
            "elif [ -f venv/bin/python ]; then PY=venv/bin/python; "
            "elif [ -f ~/.venv/bin/python ]; then PY=~/.venv/bin/python; "
            "else PY=python3; fi ; "
            "nohup $PY gemini-integrated.py node >/dev/null 2>&1 & break ; fi ; done))) ; "
            "echo 'RESTART_DISPATCHED'"
        )
    elif action in ("os_reboot", "system_reboot"):
        remote_cmd = "reboot"
    elif action == "check":
        remote_cmd = (
            "uptime ; "
            "ps aux | grep -E '(gemini-integrated|satellite|hud|sshd)' | grep -v grep ; "
            "if [ -d /mnt/ipad ]; then echo 'IPAD_MOUNT: ACTIVE'; fi"
        )
    elif action == "exec":
        if not custom_cmd:
            return {"status": "error", "error": "custom_cmd required for 'exec' action"}
        remote_cmd = custom_cmd
    elif action == "provision":
        from gemini_app.fleet.security import get_or_create_fleet_key
        fleet_key = get_or_create_fleet_key()
        remote_cmd = f"mkdir -p ~/.gemini && echo '{fleet_key}' > ~/.gemini/fleet.key && chmod 600 ~/.gemini/fleet.key && echo PROVISIONED"
    elif action in ("autostart", "install_autostart"):
        from gemini_app.fleet.protocol import get_local_lan_ip
        local_ip = get_local_lan_ip()
        remote_cmd = (
            f"for d in /root/gemini-integrated ~/gemini-integrated /opt/gemini \"$HOME/gemini-integrated\" /data/data/com.termux/files/home/gemini-integrated; do "
            f"if [ -d \"$d\" ]; then cd \"$d\" && "
            f"if [ -f .venv/bin/python ]; then PY=.venv/bin/python; "
            f"elif [ -f venv/bin/python ]; then PY=venv/bin/python; "
            f"else PY=python3; fi ; "
            f"$PY -c 'from gemini_app.fleet.autostart import install_autostart; print(install_autostart(mothership=\"{local_ip}\"))' 2>/dev/null || "
            f"$PY gemini-integrated.py autostart --install --mothership {local_ip} 2>/dev/null ; break ; fi ; done"
        )
    else:
        return {"status": "error", "error": f"Unknown rescue action '{action}'. Options: restart, reboot, os_reboot, check, exec, provision, autostart"}

    ssh_args = [
        "ssh",
        "-i", key_path,
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        f"{user}@{host}",
        remote_cmd,
    ]

    try:
        res = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "status": "ok" if res.returncode == 0 else "error",
            "node_id": node_id,
            "host": host,
            "action": action,
            "ssh_key": key_path,
            "returncode": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "node_id": node_id,
            "host": host,
            "action": action,
            "error": f"SSH connection to {user}@{host}:{port} timed out after {timeout}s.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "node_id": node_id,
            "host": host,
            "action": action,
            "error": str(exc),
        }


def send_mothership_command(
    action: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 8.0,
) -> Dict[str, Any]:
    """Sends an authenticated command to the local or remote Mothership daemon."""
    import socket
    from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage
    from gemini_app.fleet.security import compute_auth_signature, compute_command_signature, get_or_create_fleet_key

    fleet_key = get_or_create_fleet_key()
    node_id = "console-client"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(("127.0.0.1", DEFAULT_PORT))
        f = s.makefile("r", encoding="utf-8")

        # 1. Receive challenge
        line = f.readline()
        if not line:
            s.close()
            return {"status": "error", "error": "No challenge from Mothership"}
        c_msg = FleetMessage.deserialize(line)
        nonce = c_msg.payload.get("nonce", "")
        ts = c_msg.payload.get("timestamp", time.time())

        # 2. Authenticate
        sig = compute_auth_signature(fleet_key, node_id, nonce, ts)
        auth_msg = FleetMessage(
            msg_type=FleetMessage.TYPE_AUTH,
            node_id=node_id,
            payload={"signature": sig, "timestamp": ts, "telemetry": {}},
        )
        s.sendall(auth_msg.serialize())

        # 3. Receive AUTH_OK
        while True:
            line = f.readline()
            if not line:
                s.close()
                return {"status": "error", "error": "Connection closed during auth"}
            a_msg = FleetMessage.deserialize(line)
            if a_msg.type == FleetMessage.TYPE_AUTH_FAIL:
                s.close()
                return {"status": "error", "error": f"Auth rejected: {a_msg.payload}"}
            if a_msg.type == FleetMessage.TYPE_AUTH_OK:
                break

        # 4. Send Command
        cmd_ts = time.time()
        cmd_sig = compute_command_signature(fleet_key, action, "mothership", cmd_ts)
        cmd_msg = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id=node_id,
            payload={
                "action": action,
                "params": params or {},
                "auth_sig": cmd_sig,
                "auth_ts": cmd_ts,
            },
        )
        s.sendall(cmd_msg.serialize())

        # 5. Receive Response (skipping any async telemetry greetings)
        while True:
            line = f.readline()
            if not line:
                s.close()
                return {"status": "error", "error": "Connection closed waiting for command response"}
            r_msg = FleetMessage.deserialize(line)
            if r_msg.type == FleetMessage.TYPE_RESPONSE:
                s.close()
                return r_msg.payload
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def fetch_node_screenshot(node_id: str = "android-termux-localhost", custom_path: Optional[str] = None) -> Dict[str, Any]:
    """Fetches the latest screenshot from a connected satellite node and saves it to local screenshots."""
    params = {"node_id": node_id}
    if custom_path:
        params["path"] = custom_path
    return send_mothership_command("fetch_node_screenshot", params, timeout=25.0)


def list_node_screenshots(node_id: str = "android-termux-localhost", limit: int = 10) -> Dict[str, Any]:
    """Lists available screenshots on a remote satellite node."""
    params = {"node_id": node_id, "limit": limit}
    return send_mothership_command("list_node_screenshots", params, timeout=12.0)


def get_node_media_info(node_id: str = "android-termux-localhost") -> Dict[str, Any]:
    """Retrieves current media playback details and screenshot OCR telemetry from a satellite node."""
    params = {"node_id": node_id}
    return send_mothership_command("get_node_media", params, timeout=25.0)


def control_node_media(node_id: str = "android-termux-localhost", media_action: str = "next") -> Dict[str, Any]:
    """Dispatches media playback controls (next, prev, play, pause, toggle) to a satellite node."""
    params = {"node_id": node_id, "media_action": media_action}
    return send_mothership_command("control_node_media", params, timeout=10.0)


def record_node_audio(
    node_id: str = "android-termux-localhost",
    duration: int = 5,
    encoder: str = "opus",
    stop: bool = False,
    info: bool = False,
) -> Dict[str, Any]:
    """Captures audio from satellite node microphone (e.g. Bose Bluetooth earbuds) and returns saved local audio path."""
    params = {
        "node_id": node_id,
        "duration": duration,
        "encoder": encoder,
        "stop": stop,
        "info": info,
    }
    return send_mothership_command("record_node_audio", params, timeout=float(duration) + 20.0)


def speak_node_tts(
    node_id: str = "android-termux-localhost",
    text: str = "",
    stream: str = "MUSIC",
    pitch: float = 1.0,
    rate: float = 1.0,
    engine: str = "",
    duck: bool = True,
    duck_volume: Optional[int] = None,
) -> Dict[str, Any]:
    """Synthesizes text-to-speech audio directly to satellite node output or active Bluetooth earbuds with intelligent music ducking."""
    params: Dict[str, Any] = {
        "node_id": node_id,
        "text": text,
        "stream": stream,
        "pitch": pitch,
        "rate": rate,
        "engine": engine,
        "duck": duck,
    }
    if duck_volume is not None:
        params["duck_volume"] = duck_volume
    return send_mothership_command("speak_node_tts", params, timeout=30.0)


def get_node_audio_info(node_id: str = "android-termux-localhost") -> Dict[str, Any]:
    """Queries audio subsystem telemetry (Bluetooth A2DP, sample rate, routing) from a satellite node."""
    params = {"node_id": node_id}
    return send_mothership_command("get_node_audio_info", params, timeout=10.0)


def control_node_volume(
    node_id: str = "android-termux-localhost",
    stream: str = "music",
    volume: Optional[int] = None,
) -> Dict[str, Any]:
    """Gets or sets the hardware volume level for a specific audio stream on a satellite node."""
    params = {"node_id": node_id, "stream": stream}
    if volume is not None:
        params["volume"] = volume
    return send_mothership_command("control_node_volume", params, timeout=10.0)


def notify_node_toast(
    node_id: str = "android-termux-localhost",
    message: str = "",
    background: str = "gray",
    color: str = "white",
) -> Dict[str, Any]:
    """Displays a transient popup toast on the mobile satellite screen."""
    params = {
        "node_id": node_id,
        "message": message,
        "background": background,
        "color": color,
    }
    return send_mothership_command("notify_node_toast", params, timeout=10.0)


def vibrate_node(
    node_id: str = "android-termux-localhost",
    duration_ms: int = 300,
    force: bool = False,
) -> Dict[str, Any]:
    """Triggers physical haptic vibration on the mobile satellite node."""
    params = {
        "node_id": node_id,
        "duration_ms": duration_ms,
        "force": force,
    }
    return send_mothership_command("vibrate_node", params, timeout=10.0)


def take_node_camera_photo(
    node_id: str = "ipad-ish-localhost",
    facing: str = "front",
    camera_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Captures a photo from satellite camera (or dispatches Wingman front camera shutter card on iPad)."""
    params: Dict[str, Any] = {
        "node_id": node_id,
        "facing": facing,
    }
    if camera_id is not None:
        params["camera_id"] = str(camera_id)
    return send_mothership_command("take_node_camera_photo", params, timeout=25.0)





