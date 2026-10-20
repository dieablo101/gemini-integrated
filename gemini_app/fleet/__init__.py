"""Gemini Fleet & Distributed Satellite Node Architecture.

Enables the bilateral terminal console (Mothership) to register,
monitor, and coordinate distributed satellite nodes (iPad iSH, Android Termux,
remote compute workers).
"""

from gemini_app.fleet.protocol import DEFAULT_PORT, FleetMessage
from gemini_app.fleet.satellite import SatelliteNode
from gemini_app.fleet.mothership import MothershipServer

__all__ = [
    "DEFAULT_PORT",
    "FleetMessage",
    "SatelliteNode",
    "MothershipServer",
]
