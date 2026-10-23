"""
Peripheral Nervous System (PNS) Sensory Receiver & Ingestion Pipeline.
Connects Android Termux/Phone telemetry (light, battery, motion, audio, wifi)
into the sandbox cognitive hypergraph.
"""
from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge


@dataclass
class PhoneSensoryTelemetry:
    """Raw sensory telemetry snapshot from mobile peripheral."""
    timestamp: float = field(default_factory=time.time)
    device_id: str = "phone_pns"
    lux: float = 250.0                  # Ambient light level (lux)
    battery_pct: float = 85.0           # 0.0 - 100.0%
    battery_charging: bool = False      # Is connected to power?
    motion_magnitude: float = 0.02      # Accelerometer net g-force delta (0.0=desk, >0.5=in hand/moving)
    wifi_ssid: str = "offline"          # Connected SSID
    audio_amplitude_db: float = -45.0   # Decibel reading (-60 quiet room, 0 loud)
    screen_on: bool = True              # Device display active?
    proximity_covered: bool = False     # Pocket / facedown detection

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "device_id": self.device_id,
            "lux": self.lux,
            "battery_pct": self.battery_pct,
            "battery_charging": self.battery_charging,
            "motion_magnitude": self.motion_magnitude,
            "wifi_ssid": self.wifi_ssid,
            "audio_amplitude_db": self.audio_amplitude_db,
            "screen_on": self.screen_on,
            "proximity_covered": self.proximity_covered,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PhoneSensoryTelemetry:
        return cls(
            timestamp=data.get("timestamp", time.time()),
            device_id=data.get("device_id", "phone_pns"),
            lux=float(data.get("lux", 250.0)),
            battery_pct=float(data.get("battery_pct", 85.0)),
            battery_charging=bool(data.get("battery_charging", False)),
            motion_magnitude=float(data.get("motion_magnitude", 0.02)),
            wifi_ssid=str(data.get("wifi_ssid", "offline")),
            audio_amplitude_db=float(data.get("audio_amplitude_db", -45.0)),
            screen_on=bool(data.get("screen_on", True)),
            proximity_covered=bool(data.get("proximity_covered", False)),
        )


class PhoneSensorySynthesizer:
    """
    Translates raw continuous phone telemetry into discrete cognitive anchors
    and somatic context frames for hypergraph ingestion.
    """
    def __init__(self, hypergraph: Hypergraph):
        self.hypergraph = hypergraph
        self.last_telemetry: Optional[PhoneSensoryTelemetry] = None
        self._setup_sensory_anchors()

    def _setup_sensory_anchors(self):
        """Initializes somatic concept vertices in the hypergraph."""
        sensory_concepts = [
            ("somatic:circadian_night", "Circadian Night / Deep Focus Environment", 0.8),
            ("somatic:circadian_day", "Circadian Day / Daylight Work Environment", 0.8),
            ("somatic:user_present_desk", "User Present at Desk (Stationary phone)", 0.9),
            ("somatic:user_mobile", "User In Motion (Active phone movement)", 0.7),
            ("somatic:power_tethered", "Power Tethered (Phone on charge, sustained uptime)", 0.8),
            ("somatic:acoustic_quiet", "Acoustic Silence (Low room noise)", 0.7),
            ("somatic:acoustic_active", "Acoustic Activity (Room conversation or noise)", 0.7),
            ("somatic:pocket_standby", "Device in pocket / Face down (Suspended sensory field)", 0.8),
        ]
        for cid, desc, p in sensory_concepts:
            if not any(v.label == cid for v in self.hypergraph.vertices.values()):
                self.hypergraph.add_vertex(
                    v_id=cid,
                    label=cid,
                    vtype="sensory_somatic",
                    base_energy=p,
                    attributes={"description": desc, "persistence": p}
                )

    def ingest(self, telem: PhoneSensoryTelemetry) -> List[str]:
        """
        Interprets telemetry and energizes appropriate somatic vertices.
        Returns the list of triggered sensory node labels.
        """
        self.last_telemetry = telem
        activated_nodes = []

        # 1. Lux / Circadian Analysis
        if telem.lux < 15.0:
            activated_nodes.append("somatic:circadian_night")
        else:
            activated_nodes.append("somatic:circadian_day")

        # 2. Motion / User Physical Anchor
        if telem.proximity_covered:
            activated_nodes.append("somatic:pocket_standby")
        elif telem.motion_magnitude > 0.35:
            activated_nodes.append("somatic:user_mobile")
        else:
            activated_nodes.append("somatic:user_present_desk")

        # 3. Power State
        if telem.battery_charging:
            activated_nodes.append("somatic:power_tethered")

        # 4. Acoustic Environment
        if telem.audio_amplitude_db < -40.0:
            activated_nodes.append("somatic:acoustic_quiet")
        else:
            activated_nodes.append("somatic:acoustic_active")

        # Boost energy and recency in hypergraph
        now = telem.timestamp
        for v in self.hypergraph.vertices.values():
            if v.label in activated_nodes:
                v.last_accessed = now
                v.access_count += 1

        return activated_nodes

    def build_somatic_frame(self) -> str:
        """
        Generates a concise 1-2 line somatic priming tag for the API prefrontal core.
        """
        if not self.last_telemetry:
            return "PNS: offline"

        t = self.last_telemetry
        circadian = "Night" if t.lux < 15.0 else f"Day ({int(t.lux)}lx)"
        motion = "Desk/Stationary" if t.motion_magnitude < 0.2 else "Mobile"
        if t.proximity_covered:
            motion = "Pocket/FaceDown"
        pwr = "Chg" if t.battery_charging else f"{int(t.battery_pct)}%"
        sound = "Quiet" if t.audio_amplitude_db < -40.0 else f"AudioActive ({int(t.audio_amplitude_db)}dB)"

        return f"PNS Phone Sensor: [Env: {circadian} | User: {motion} | Power: {pwr} | Room: {sound}]"


class PNSSensoryReceiver:
    """
    Local TCP/Socket daemon receiver inside sandbox that listens for incoming
    sensor JSON payloads from Termux / Termux:API phone peripheral.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 7335, synthesizer: Optional[PhoneSensorySynthesizer] = None):
        self.host = host
        self.port = port
        self.synthesizer = synthesizer
        self.running = False
        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self.latest_packet: Optional[PhoneSensoryTelemetry] = None

    def start(self):
        """Starts socket receiver thread."""
        self.running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        self._server_sock.settimeout(0.5)

        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="pns-sensory-receiver")
        self._thread.start()

    def _listen_loop(self):
        while self.running:
            try:
                conn, _ = self._server_sock.accept()
                with conn:
                    conn.settimeout(2.0)
                    raw_data = b""
                    while True:
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        raw_data += chunk
                        if b"\n" in chunk or len(raw_data) > 8192:
                            break
                    if raw_data:
                        parsed = json.loads(raw_data.decode("utf-8").strip())
                        telem = PhoneSensoryTelemetry.from_dict(parsed)
                        self.latest_packet = telem
                        if self.synthesizer:
                            self.synthesizer.ingest(telem)
                        conn.sendall(b'{"status":"ok"}\n')
            except socket.timeout:
                continue
            except Exception:
                pass

    def stop(self):
        """Stops socket receiver."""
        self.running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
