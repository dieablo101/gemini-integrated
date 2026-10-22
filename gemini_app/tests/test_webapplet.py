"""Unit tests for Gemini WebApplet Subsystem.

Tests multi-instance engine, Wingman applet, Inspector isolation,
client activity tracking, and platform-aware biometrics.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request
import urllib.parse

from gemini_app.webapplet.engine import WebAppletEngine
from gemini_app.webapplet.applets.wingman import WingmanApplet
from gemini_app.webapplet.applets.inspector import InspectorApplet
from gemini_app.fleet.biometrics import (
    FleetBiometricsManager,
    is_termux_biometric_available,
)


class TestWebAppletEngine(unittest.TestCase):
    """Tests core multi-instance engine."""

    def setUp(self) -> None:
        self.engine1 = WebAppletEngine(name="test1", host="127.0.0.1", port=0)
        self.engine2 = WebAppletEngine(name="test2", host="127.0.0.1", port=0)
        self.assertTrue(self.engine1.start())
        self.assertTrue(self.engine2.start())

    def tearDown(self) -> None:
        self.engine1.stop()
        self.engine2.stop()

    def test_multi_instance_ports_concurrent(self) -> None:
        """Verifies two instances run simultaneously on separate ephemeral ports."""
        self.assertNotEqual(self.engine1.port, self.engine2.port)
        self.assertTrue(self.engine1.is_running)
        self.assertTrue(self.engine2.is_running)

        # Register different routes
        self.engine1.register_get("/hello", lambda h, q: {"source": "engine1"})
        self.engine2.register_get("/hello", lambda h, q: {"source": "engine2"})

        # Query engine 1
        url1 = f"http://127.0.0.1:{self.engine1.port}/hello"
        with urllib.request.urlopen(url1, timeout=2.0) as resp:
            data1 = json.loads(resp.read().decode())
            self.assertEqual(data1["source"], "engine1")

        # Query engine 2
        url2 = f"http://127.0.0.1:{self.engine2.port}/hello"
        with urllib.request.urlopen(url2, timeout=2.0) as resp:
            data2 = json.loads(resp.read().decode())
            self.assertEqual(data2["source"], "engine2")

    def test_client_activity_tracking(self) -> None:
        """Verifies client active detection on visits."""
        self.assertFalse(self.engine1.is_client_active())
        self.engine1.register_get("/ping", lambda h, q: "pong")

        url = f"http://127.0.0.1:{self.engine1.port}/ping"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.read().decode(), "pong")

        self.assertTrue(self.engine1.is_client_active(window_seconds=5.0))
        self.assertGreaterEqual(self.engine1.get_active_client_count(), 1)

    def test_client_abrupt_disconnect_suppression(self) -> None:
        """Verifies abrupt client TCP reset (Errno 104 / ECONNRESET) is silently absorbed."""
        import socket
        import struct
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", self.engine1.port))
        req = f"GET {self.engine1.sse_path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        s.sendall(req.encode())
        s.recv(64)
        # Enable SO_LINGER with 0 timeout to force hard TCP RST packet
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        s.close()

        # Broadcast event across closed socket
        self.engine1.broadcast_event("test_event", {"data": "ping"})
        time.sleep(0.1)
        # Verify server remains healthy and accepts new requests
        self.engine1.register_get("/alive", lambda h, q: "ok")
        url = f"http://127.0.0.1:{self.engine1.port}/alive"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.read().decode(), "ok")


class TestWingmanAndInspectorApplets(unittest.TestCase):
    """Tests Wingman portal and Inspector applets."""

    def setUp(self) -> None:
        self.wingman = WingmanApplet(port=0)
        self.inspector = InspectorApplet(port=0)
        self.assertTrue(self.wingman.start())
        self.assertTrue(self.inspector.start())

    def tearDown(self) -> None:
        self.wingman.stop()
        self.inspector.stop()

    def test_wingman_ui_serves_html(self) -> None:
        """Verifies Wingman serves the responsive bilateral talk portal."""
        url = f"http://127.0.0.1:{self.wingman.engine.port}/applet/wingman"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            content = resp.read().decode()
            self.assertEqual(resp.status, 200)
            self.assertIn("Wingman", content)
            self.assertIn("Bilateral Portal", content)

    def test_inspector_ui_serves_html(self) -> None:
        """Verifies Inspector serves the 3D asset visualizer on its own port."""
        url = f"http://127.0.0.1:{self.inspector.engine.port}/applet/inspector"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            content = resp.read().decode()
            self.assertEqual(resp.status, 200)
            self.assertIn("Photon 3D Asset Inspector", content)

    def test_wingman_push_card_and_action(self) -> None:
        """Tests card dispatch and action callback response."""
        received_actions = []

        def on_action(cid: str, act: str, body: dict) -> None:
            received_actions.append((cid, act))

        self.wingman.on_action(on_action)

        card_id = self.wingman.push_card(
            title="Deploy Approval",
            content="Proceed with commit 1a2b3c?",
            actions=[{"label": "Approve", "action": "approve", "style": "primary"}],
        )
        self.assertTrue(card_id.startswith("card-"))

        # Simulate browser submitting action
        action_url = f"http://127.0.0.1:{self.wingman.engine.port}/applet/wingman/action"
        req_data = json.dumps({"card_id": card_id, "action": "approve"}).encode()
        req = urllib.request.Request(
            action_url,
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)

        self.assertIn((card_id, "approve"), received_actions)

    def test_wingman_webauthn_biometric_flow(self) -> None:
        """Tests WebAuthn Face ID biometric challenge and response roundtrip."""
        port = self.wingman.engine.port

        def simulate_browser_client() -> None:
            time.sleep(0.1)
            # Find pending challenge and post response
            with self.wingman._lock:
                chal_ids = list(self.wingman._pending_biometrics.keys())
            if not chal_ids:
                return
            chal_id = chal_ids[0]
            resp_url = f"http://127.0.0.1:{port}/applet/wingman/webauthn_response"
            data = json.dumps({
                "challenge_id": chal_id,
                "result": {"status": "authenticated", "method": "apple_secure_enclave"},
            }).encode()
            req = urllib.request.Request(resp_url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=2.0) as r:
                    pass
            except Exception:
                pass

        threading.Thread(target=simulate_browser_client, daemon=True).start()

        res = self.wingman.request_biometric(reason="Unlock Encrypted Vault", timeout=3.0)
        self.assertEqual(res.get("status"), "authenticated")
        self.assertEqual(res.get("method"), "apple_secure_enclave")


class TestFleetBiometrics(unittest.TestCase):
    """Tests platform-aware fleet biometrics detection and coordinator."""

    def test_detect_available_biometrics_with_mock_nodes(self) -> None:
        class MockMothership:
            def list_nodes(self):
                return [
                    {
                        "node_id": "ipad-ish-localhost",
                        "telemetry": {
                            "is_ish": True,
                            "webapplet": {"wingman_active": True, "port": 8888},
                        },
                    },
                    {
                        "node_id": "android-termux-localhost",
                        "telemetry": {
                            "is_termux": True,
                            "webapplet": {"wingman_active": False},
                        },
                    },
                ]

        mgr = FleetBiometricsManager(MockMothership())
        available = mgr.detect_available_biometrics()
        self.assertEqual(len(available), 2)

        ios_node = next(d for d in available if d["platform"] == "ios")
        self.assertEqual(ios_node["method"], "apple_face_id")
        self.assertTrue(ios_node["ready"])

        android_node = next(d for d in available if d["platform"] == "android")
        self.assertEqual(android_node["method"], "android_fingerprint")


if __name__ == "__main__":
    unittest.main()
