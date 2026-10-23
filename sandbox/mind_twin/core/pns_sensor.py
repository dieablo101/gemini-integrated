"""
Peripheral Nervous System (PNS) Sensory Receiver & Ingestion Pipeline.
Connects Android Termux/Phone telemetry (light, battery, motion, audio, wifi)
into the sandbox cognitive hypergraph. Hardened against NaN/Inf, malformed payloads,
socket floods, and port conflicts.
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


def _safe_float(val: Any, default: float = 0.0, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        if min_val is not None:
            f = max(min_val, f)
        if max_val is not None:
            f = min(max_val, f)
        return f
    except (ValueError, TypeError):
        return default


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
            "lux": _safe_float(self.lux, 250.0, 0.0, 100000.0),
            "battery_pct": _safe_float(self.battery_pct, 85.0, 0.0, 100.0),
            "battery_charging": self.battery_charging,
            "motion_magnitude": _safe_float(self.motion_magnitude, 0.02, 0.0, 50.0),
            "wifi_ssid": str(self.wifi_ssid),
            "audio_amplitude_db": _safe_float(self.audio_amplitude_db, -45.0, -120.0, 20.0),
            "screen_on": self.screen_on,
            "proximity_covered": self.proximity_covered,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PhoneSensoryTelemetry:
        if not isinstance(data, dict):
            return cls()
        return cls(
            timestamp=_safe_float(data.get("timestamp"), time.time()),
            device_id=str(data.get("device_id", "phone_pns")),
            lux=_safe_float(data.get("lux"), 250.0, 0.0, 100000.0),
            battery_pct=_safe_float(data.get("battery_pct"), 85.0, 0.0, 100.0),
            battery_charging=bool(data.get("battery_charging", False)),
            motion_magnitude=_safe_float(data.get("motion_magnitude"), 0.02, 0.0, 50.0),
            wifi_ssid=str(data.get("wifi_ssid", "offline")),
            audio_amplitude_db=_safe_float(data.get("audio_amplitude_db"), -45.0, -120.0, 20.0),
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
        vertices_snap = self.hypergraph.get_vertices_snapshot()
        for cid, desc, p in sensory_concepts:
            if not any(v.label == cid for v in vertices_snap.values()):
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

        safe_lux = _safe_float(telem.lux, 250.0, 0.0, 100000.0)
        safe_motion = _safe_float(telem.motion_magnitude, 0.02, 0.0, 50.0)
        safe_audio = _safe_float(telem.audio_amplitude_db, -45.0, -120.0, 20.0)

        # 1. Lux / Circadian Analysis
        if safe_lux < 15.0:
            activated_nodes.append("somatic:circadian_night")
        else:
            activated_nodes.append("somatic:circadian_day")

        # 2. Motion / User Physical Anchor
        if telem.proximity_covered:
            activated_nodes.append("somatic:pocket_standby")
        elif safe_motion > 0.35:
            activated_nodes.append("somatic:user_mobile")
        else:
            activated_nodes.append("somatic:user_present_desk")

        # 3. Power State
        if telem.battery_charging:
            activated_nodes.append("somatic:power_tethered")

        # 4. Acoustic Environment
        if safe_audio < -40.0:
            activated_nodes.append("somatic:acoustic_quiet")
        else:
            activated_nodes.append("somatic:acoustic_active")

        # Boost energy and recency in hypergraph
        now = _safe_float(telem.timestamp, time.time())
        vertices_snap = self.hypergraph.get_vertices_snapshot()
        for v in vertices_snap.values():
            if v.label in activated_nodes:
                v.last_accessed = now
                v.access_count += 1

        return activated_nodes

    def build_somatic_frame(self) -> str:
        """
        Generates a concise 1-2 line somatic priming tag for the API prefrontal core.
        Guaranteed never to crash on NaN, Inf, or malformed values.
        """
        if not self.last_telemetry:
            return "PNS: offline"

        t = self.last_telemetry
        safe_lux = _safe_float(t.lux, 250.0, 0.0, 100000.0)
        safe_motion = _safe_float(t.motion_magnitude, 0.02, 0.0, 50.0)
        safe_bat = _safe_float(t.battery_pct, 85.0, 0.0, 100.0)
        safe_audio = _safe_float(t.audio_amplitude_db, -45.0, -120.0, 20.0)

        circadian = "Night" if safe_lux < 15.0 else f"Day ({int(safe_lux)}lx)"
        motion = "Desk/Stationary" if safe_motion < 0.2 else "Mobile"
        if t.proximity_covered:
            motion = "Pocket/FaceDown"
        pwr = "Chg" if t.battery_charging else f"{int(safe_bat)}%"
        sound = "Quiet" if safe_audio < -40.0 else f"AudioActive ({int(safe_audio)}dB)"

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
        self.bind_error: Optional[str] = None

    def start(self) -> bool:
        """Starts socket receiver thread. Catches bind errors gracefully without crashing."""
        self.running = True
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
            self._server_sock.settimeout(0.5)
            self.bind_error = None
        except OSError as e:
            self.running = False
            self.bind_error = str(e)
            return False

        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="pns-sensory-receiver")
        self._thread.start()
        return True

    def _listen_loop(self):
        while self.running and self._server_sock:
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
                        if b"\n" in chunk or len(raw_data) > 16384:
                            break
                    if raw_data:
                        try:
                            parsed = json.loads(raw_data.decode("utf-8", errors="replace").strip())
                            telem = PhoneSensoryTelemetry.from_dict(parsed)
                            self.latest_packet = telem
                            if self.synthesizer:
                                self.synthesizer.ingest(telem)
                            conn.sendall(b'{"status":"ok"}\n')
                        except Exception:
                            conn.sendall(b'{"status":"error","msg":"malformed_payload"}\n')
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
            self._server_sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
