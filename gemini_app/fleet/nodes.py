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
    if action == "restart":
        remote_cmd = (
            "systemctl restart gemini-satellite 2>/dev/null || "
            "(/etc/local.d/gemini-satellite.start 2>/dev/null || "
            "(pkill -f 'gemini-integrated.*hud' 2>/dev/null; "
            "nohup python3 gemini-integrated.py hud >/dev/null 2>&1 &)) ; "
            "echo 'RESTART_DISPATCHED'"
        )
    elif action == "reboot":
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
        remote_cmd = (
            "python3 -c '"
            "from gemini_app.fleet.autostart import install_autostart; "
            "print(install_autostart(mothership=\"192.168.1.90\"))' 2>/dev/null || "
            "python3 gemini-integrated.py autostart --install --mothership 192.168.1.90 2>/dev/null || "
            "python3 /root/gemini-integrated/gemini-integrated.py autostart --install --mothership 192.168.1.90"
        )
    else:
        return {"status": "error", "error": f"Unknown rescue action '{action}'. Options: restart, reboot, check, exec, provision, autostart"}

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
