"""Gemini Fleet & Distributed Satellite Node Architecture.

Enables the bilateral terminal console (Mothership) to register,
monitor, and coordinate distributed satellite nodes (iPad iSH, Android Termux,
remote compute workers), with boot-persistence autostart and SSH rescue.
"""

from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage
from gemini_app.fleet.satellite import SatelliteNode, execute_fleet_upgrade
from gemini_app.fleet.mothership import MothershipServer
from gemini_app.fleet.hud import SatelliteHUD
from gemini_app.fleet.telemetry import collect_mothership_telemetry
from gemini_app.fleet.nodes import (
    execute_ssh_rescue,
    get_dieablo_ssh_key,
    get_fleet_snapshot,
    load_active_nodes,
    load_nodes_registry,
    register_or_update_node,
    save_active_nodes,
    save_nodes_registry,
)
from gemini_app.fleet.autostart import (
    check_autostart_status,
    detect_init_system,
    install_autostart,
    remove_autostart,
)

__all__ = [
    "DEFAULT_PORT",
    "FleetMessage",
    "SatelliteNode",
    "MothershipServer",
    "SatelliteHUD",
    "execute_fleet_upgrade",
    "collect_mothership_telemetry",
    "get_dieablo_ssh_key",
    "load_nodes_registry",
    "save_nodes_registry",
    "register_or_update_node",
    "load_active_nodes",
    "save_active_nodes",
    "get_fleet_snapshot",
    "execute_ssh_rescue",
    "detect_init_system",
    "install_autostart",
    "remove_autostart",
    "check_autostart_status",
]
