"""Platform-Aware Biometrics Gateway.

Dispatches biometric challenges across heterogeneous edge platforms:
  - iOS (iSH / iPad Pro): Apple Secure Enclave Face ID via Wingman WebApplet
  - Android (Termux): Hardware fingerprint sensor via termux-fingerprint
  - Desktop / Local: WebAuthn / Touch ID / Console Passkey fallback
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from gemini_app.fleet.satellite import is_ish_platform, is_termux_platform


def is_termux_biometric_available() -> bool:
    """Checks whether Termux biometric API is installed and supported."""
    return is_termux_platform() and bool(shutil.which("termux-fingerprint"))


def authenticate_local_termux(reason: str = "Authorize Action", timeout: int = 30) -> Dict[str, Any]:
    """Triggers Android fingerprint sensor on device via termux-fingerprint."""
    if not is_termux_biometric_available():
        return {"status": "error", "error": "termux-fingerprint not available"}
    try:
        proc = subprocess.run(
            ["termux-fingerprint", "-t", reason],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            # termux-fingerprint returns {"errors": [], "failed_attempts": 0, "auth_result": "AUTH_RESULT_SUCCESS"}
            if data.get("auth_result") == "AUTH_RESULT_SUCCESS":
                return {"status": "authenticated", "method": "android_fingerprint", "details": data}
            return {"status": "rejected", "method": "android_fingerprint", "details": data}
        return {"status": "error", "error": proc.stderr.strip() or "Fingerprint failed"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Fingerprint timed out after {timeout}s"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


class FleetBiometricsManager:
    """Coordinates biometric requests from the Mothership to edge satellite devices."""

    def __init__(self, mothership: Any) -> None:
        self.mothership = mothership

    def detect_available_biometrics(self) -> List[Dict[str, Any]]:
        """Scans active fleet nodes for platform biometric capabilities."""
        available = []
        nodes = self.mothership.list_nodes()
        for node in nodes:
            nid = node["node_id"]
            telem = node.get("telemetry", {})
            webapplet = telem.get("webapplet", {})

            # 1. iOS device with Wingman WebApplet open
            if telem.get("is_ish") or "ipad" in nid.lower():
                wingman_active = webapplet.get("wingman_active", False)
                available.append({
                    "node_id": nid,
                    "platform": "ios",
                    "method": "apple_face_id",
                    "wingman_active": wingman_active,
                    "ready": wingman_active,
                    "description": "Apple TrueDepth Face ID (iPad Pro)" if wingman_active else "iPad (Wingman not open on localhost:8888)",
                })

            # 2. Android device with Termux
            elif telem.get("is_termux") or "android" in nid.lower():
                available.append({
                    "node_id": nid,
                    "platform": "android",
                    "method": "android_fingerprint",
                    "wingman_active": webapplet.get("wingman_active", False),
                    "ready": True,
                    "description": "Android Hardware Fingerprint (Termux)",
                })

        return available

    def request_biometric(
        self,
        reason: str = "Authorize Vault Operation",
        preferred_node: Optional[str] = None,
        method: str = "auto",
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Dispatches an interactive biometric authorization challenge to an active node."""
        available = self.detect_available_biometrics()
        if not available:
            return {"status": "error", "error": "No satellite nodes available for biometrics"}

        target_device = None
        if preferred_node:
            for d in available:
                if d["node_id"] == preferred_node:
                    target_device = d
                    break

        if not target_device:
            if method in ("facescan", "face_id", "apple_face_id"):
                ios_devices = [d for d in available if d["platform"] == "ios"]
                if ios_devices:
                    target_device = ios_devices[0]
            elif method in ("fingerprint", "android_fingerprint"):
                android_devices = [d for d in available if d["platform"] == "android"]
                if android_devices:
                    target_device = android_devices[0]

        if not target_device:
            # Prefer active Wingman session (user is looking at it right now)
            ready_ios = [d for d in available if d["method"] == "apple_face_id" and d["ready"]]
            if ready_ios:
                target_device = ready_ios[0]
            else:
                # Fallback to Android or other available device
                target_device = available[0]

        target_nid = target_device["node_id"]
        chosen_method = method if method != "auto" else target_device["method"]

        # Dispatch command over fleet socket
        resp = self.mothership.send_command(
            node_id=target_nid,
            action="biometric_auth",
            params={"reason": reason, "method": chosen_method, "timeout": timeout},
            timeout=timeout + 5.0,
        )

        return {
            "node_id": target_nid,
            "method": chosen_method,
            "response": resp,
        }

    def request_face_scan(
        self,
        reason: str = "Scan Face ID on iPad",
        preferred_node: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Dispatches an Apple Face ID / camera scan challenge specifically to iPad Wingman."""
        return self.request_biometric(
            reason=reason,
            preferred_node=preferred_node,
            method="facescan",
            timeout=timeout,
        )

    def request_fingerprint(
        self,
        reason: str = "Touch Fingerprint Sensor on Android",
        preferred_node: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Dispatches a hardware fingerprint scan challenge specifically to Android Termux."""
        return self.request_biometric(
            reason=reason,
            preferred_node=preferred_node,
            method="android_fingerprint",
            timeout=timeout,
        )
