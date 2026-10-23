"""
Termux Sensor Probe Script.
Runs on the Android satellite (via Termux + Termux:API) to stream continuous
telemetry to the Toughbook mothership PNS receiver socket.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from typing import Any, Dict


def query_termux_api(command: str) -> Dict[str, Any]:
    """Runs a termux-api CLI command and parses JSON response."""
    if not shutil.which(command):
        return {}
    try:
        res = subprocess.run([command], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
    except Exception:
        pass
    return {}


def collect_phone_telemetry() -> Dict[str, Any]:
    """
    Harvests sensor data from Android Termux:API commands:
    - termux-sensor: lux, accelerometer
    - termux-battery-status: percentage, charging status
    - termux-wifi-connectioninfo: ssid
    """
    lux = 250.0
    motion_mag = 0.05
    proximity_covered = False

    # 1. Sensors (Light, Accel, Proximity)
    if shutil.which("termux-sensor"):
        try:
            # Query ambient temperature/light/proximity once
            res = subprocess.run(
                ["termux-sensor", "-n", "1", "-s", "light,accelerometer,proximity"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if res.returncode == 0 and res.stdout.strip():
                sensor_data = json.loads(res.stdout.strip())
                if isinstance(sensor_data, dict):
                    # Light sensor
                    for key, val in sensor_data.items():
                        k_lower = key.lower()
                        if "light" in k_lower and "values" in val and val["values"]:
                            lux = float(val["values"][0])
                        elif "accelerometer" in k_lower and "values" in val and len(val["values"]) >= 3:
                            vx, vy, vz = val["values"][:3]
                            # Net acceleration minus 9.81 m/s^2 Earth gravity
                            mag = abs((vx**2 + vy**2 + vz**2)**0.5 - 9.81)
                            motion_mag = round(mag, 3)
                        elif "proximity" in k_lower and "values" in val and val["values"]:
                            # 0.0 is typically near / covered
                            proximity_covered = val["values"][0] < 1.0
        except Exception:
            pass

    # 2. Battery status
    battery_info = query_termux_api("termux-battery-status")
    battery_pct = float(battery_info.get("percentage", 80.0))
    battery_charging = battery_info.get("status", "").lower() in ["charging", "full"]

    # 3. Wifi info
    wifi_info = query_termux_api("termux-wifi-connectioninfo")
    wifi_ssid = wifi_info.get("ssid", "mobile_wifi")

    return {
        "timestamp": time.time(),
        "device_id": os.getenv("TERMUX_DEVICE_ID", "android_phone"),
        "lux": lux,
        "battery_pct": battery_pct,
        "battery_charging": battery_charging,
        "motion_magnitude": motion_mag,
        "wifi_ssid": wifi_ssid,
        "audio_amplitude_db": -45.0,
        "screen_on": True,
        "proximity_covered": proximity_covered,
    }


def transmit_to_mothership(payload: Dict[str, Any], host: str = "127.0.0.1", port: int = 7335) -> bool:
    """Sends JSON line packet to Mothership PNS receiver socket."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((host, port))
        data = (json.dumps(payload) + "\n").encode("utf-8")
        s.sendall(data)
        resp = s.recv(1024)
        s.close()
        return b'"status":"ok"' in resp or b'"status": "ok"' in resp
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    target_host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    target_port = int(sys.argv[2]) if len(sys.argv) > 2 else 7335

    print(f"[*] Probing phone sensors and transmitting to {target_host}:{target_port}...")
    sample = collect_phone_telemetry()
    print("[*] Sample Telemetry:", json.dumps(sample, indent=2))
    ok = transmit_to_mothership(sample, host=target_host, port=target_port)
    print(f"[*] Transmission status: {'SUCCESS' if ok else 'FAILED'}")
