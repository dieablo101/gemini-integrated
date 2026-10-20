"""Unit tests for Gemini Fleet Architecture (Protocol, Satellite, Mothership, Telemetry, HUD)."""

import socket
import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.fleet.protocol import FleetMessage
from gemini_app.fleet.satellite import SatelliteNode, collect_telemetry, execute_fleet_upgrade
from gemini_app.fleet.mothership import MothershipServer
from gemini_app.fleet.hud import SatelliteHUD, clip_str, render_meter_bar
from gemini_app.fleet.telemetry import collect_mothership_telemetry, get_cpu_and_mem_vitals, get_git_vitals


class TestFleetProtocol(unittest.TestCase):
    def test_message_roundtrip(self) -> None:
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id="test-node-1",
            payload={"action": "ping", "params": {"foo": "bar"}},
        )
        raw = msg.serialize()
        self.assertTrue(raw.endswith(b"\n"))

        deserialized = FleetMessage.deserialize(raw.decode("utf-8"))
        self.assertEqual(deserialized.type, FleetMessage.TYPE_COMMAND)
        self.assertEqual(deserialized.node_id, "test-node-1")
        self.assertEqual(deserialized.payload["action"], "ping")
        self.assertEqual(deserialized.payload["params"]["foo"], "bar")

    def test_telemetry_and_event_types(self) -> None:
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_TELEMETRY,
            node_id="mothership",
            payload={"cpu": 45},
        )
        raw = msg.serialize()
        deserialized = FleetMessage.deserialize(raw.decode("utf-8"))
        self.assertEqual(deserialized.type, FleetMessage.TYPE_TELEMETRY)
        self.assertEqual(deserialized.payload["cpu"], 45)

    def test_collect_telemetry(self) -> None:
        telem = collect_telemetry()
        self.assertIn("hostname", telem)
        self.assertIn("system", telem)
        self.assertIn("python", telem)
        self.assertIn("disk_free_gb", telem)
        self.assertIn("has_ipad_mount", telem)


class TestFleetTelemetryAndHUD(unittest.TestCase):
    def test_clip_str(self) -> None:
        self.assertEqual(clip_str("hello", 10), "hello")
        self.assertEqual(clip_str("hello world", 8), "hello...")
        self.assertEqual(clip_str("hello", 3), "hel")

    def test_render_meter_bar(self) -> None:
        bar = render_meter_bar(50.0, width=10)
        self.assertIn("50%", bar)
        self.assertIn("█", bar)
        self.assertIn("░", bar)

    def test_hud_render_structure(self) -> None:
        hud = SatelliteHUD(node_id="ipad-test-01", mothership_addr="192.168.1.90:7331")
        hud.update_telemetry({
            "host": "mothership-host",
            "platform": "Linux x86_64",
            "vitals": {"cpu_pct": 25.0, "mem_used_mb": 2048.0, "mem_total_mb": 8192.0, "disk_free_gb": 40.0},
            "git": {"branch": "main", "commit": "abc1234", "is_clean": True, "recent_commits": [{"sha": "abc1234", "message": "Initial test commit"}]},
            "cognitive": {"state_desc": "Pair Programming", "task": "Fleet HUD", "thought": "Testing layout", "tool": "apply_patch", "turn_number": 19},
        })
        hud.set_connection_status(True, ping_ms=18.5)
        hud.log_event("Connected to Mothership")

        rendered = hud.render()
        self.assertIn("GEMINI HUD", rendered)
        self.assertIn("ipad-test-01", rendered)
        self.assertIn("192.168.1.90:7331", rendered)
        self.assertIn("abc1234", rendered)
        self.assertIn("AI COGNITIVE STREAM", rendered)
        self.assertIn("Fleet HUD", rendered)
        self.assertIn("Testing layout", rendered)
        self.assertIn("LIVE 18ms", rendered)

    def test_collect_mothership_telemetry(self) -> None:
        telem = collect_mothership_telemetry()
        self.assertIn("host", telem)
        self.assertIn("platform", telem)
        self.assertIn("vitals", telem)
        self.assertIn("git", telem)
        self.assertIn("cognitive", telem)
        self.assertIn("cpu_pct", telem["vitals"])
        self.assertIn("branch", telem["git"])


class TestFleetNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Find an open port
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.test_port = sock.getsockname()[1]
        sock.close()

    def setUp(self) -> None:
        self.server = MothershipServer(host="127.0.0.1", port=self.test_port, auto_broadcast_telemetry=False)
        self.assertTrue(self.server.start())

    def tearDown(self) -> None:
        self.server.stop()

    def test_satellite_mothership_interaction(self) -> None:
        node_id = "test-satellite-unit"
        satellite = SatelliteNode(
            mothership_host="127.0.0.1",
            mothership_port=self.test_port,
            node_id=node_id,
            heartbeat_interval=1.0,
        )

        started = satellite.start()
        self.assertTrue(started, "Satellite node failed to start and connect")

        # Allow registration to propagate
        time.sleep(0.3)

        # Check Mothership registry
        nodes = self.server.list_nodes()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["node_id"], node_id)
        self.assertIn("system", nodes[0]["telemetry"])

        # Test ping command
        ping_resp = self.server.ping_node(node_id, timeout=3.0)
        self.assertEqual(ping_resp.get("status"), "ok")
        self.assertIn("pong", ping_resp)
        self.assertIn("rtt_ms", ping_resp)
        self.assertGreater(ping_resp["rtt_ms"], 0)

        # Test exec command
        exec_resp = self.server.send_command(
            node_id=node_id,
            action="exec",
            params={"command": "echo fleet_unit_test"},
            timeout=3.0,
        )
        self.assertEqual(exec_resp.get("status"), "ok")
        self.assertIn("fleet_unit_test", exec_resp.get("stdout", ""))

        # Test broadcast telemetry
        broadcast_count = self.server.broadcast_telemetry()
        self.assertEqual(broadcast_count, 1)

        # Test push cognitive event
        event_count = self.server.push_cognitive_event("Test cognitive event")
        self.assertEqual(event_count, 1)

        # Stop satellite cleanly
        satellite.stop()
        time.sleep(0.3)

        # Node should be dereferenced from active nodes
        nodes_after = self.server.list_nodes()
        self.assertEqual(len(nodes_after), 0)


if __name__ == "__main__":
    unittest.main()
